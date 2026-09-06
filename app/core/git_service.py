from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.core.actions import ActionChoice, ActionId, ActionMapper, ActionOutcome
from app.core.changelog import CHANGELOG_FILENAMES, ChangelogParser
from app.models.project import (
    FileChange,
    FileChangeKind,
    ProjectConfig,
    ProjectStatus,
    SuggestedAction,
)

# Hide git.cmd / console windows on Windows (refresh otherwise flashes cmd).
_CREATE_NO_WINDOW = 0x08000000


# ------------------------------------------------------------
# Class: GitResult


# ------------------------------------------------------------
# Class: GitResult
# Purpose: Raw result of a single git subprocess invocation.
# ------------------------------------------------------------
@dataclass
class GitResult:
    returncode: int
    stdout: str
    stderr: str

    # --------------------------------------------------------
    # Method: ok
    # Purpose: Whether the command exited successfully.
    # --------------------------------------------------------
    @property
    def ok(self) -> bool:
        return self.returncode == 0


# ------------------------------------------------------------
# Class: GitService
# Purpose: Cross-platform Git CLI wrapper with status, commit,
#          pull, push, discard, and credential injection.
# ------------------------------------------------------------
class GitService:
    # --------------------------------------------------------
    # Method: __init__
    # Purpose: Optionally override the git executable path.
    # --------------------------------------------------------
    def __init__(self, git_executable: Optional[str] = None) -> None:
        self.git_executable = git_executable or self.resolveGitExecutable()

    # --------------------------------------------------------
    # Method: resolveGitExecutable
    # Purpose: Prefer git.exe over git.cmd so Windows does not flash a console.
    # --------------------------------------------------------
    @staticmethod
    def resolveGitExecutable() -> str:
        found = shutil.which("git")
        if not found:
            return "git"
        path = Path(found)
        if path.suffix.lower() == ".cmd":
            exe = path.with_suffix(".exe")
            if exe.is_file():
                return str(exe)
        return found

    # --------------------------------------------------------
    # Method: _hideConsoleKwargs
    # Purpose: Windows flags so git subprocesses create no visible console.
    # --------------------------------------------------------
    @staticmethod
    def _hideConsoleKwargs() -> dict:
        if os.name != "nt":
            return {}
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        return {
            "creationflags": _CREATE_NO_WINDOW,
            "startupinfo": startupinfo,
        }

    # --------------------------------------------------------
    # Method: isGitAvailable
    # Purpose: Check that the system git binary works.
    # --------------------------------------------------------
    def isGitAvailable(self) -> bool:
        try:
            version = subprocess.run(
                [self.git_executable, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
                **self._hideConsoleKwargs(),
            )
            return version.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    # --------------------------------------------------------
    # Method: gitVersion
    # Purpose: Return `git --version` output or empty string.
    # --------------------------------------------------------
    def gitVersion(self) -> str:
        try:
            version = subprocess.run(
                [self.git_executable, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
                **self._hideConsoleKwargs(),
            )
            return version.stdout.strip() if version.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            return ""

    # --------------------------------------------------------
    # Method: isRepo
    # Purpose: True if path is inside a Git working tree.
    # --------------------------------------------------------
    def isRepo(self, path: str | Path) -> bool:
        root = Path(path)
        if not root.is_dir():
            return False
        result = self._run(["rev-parse", "--is-inside-work-tree"], cwd=root)
        return result.ok and result.stdout.strip() == "true"

    # --------------------------------------------------------
    # Method: initRepo
    # Purpose: Initialize a new Git repository at path.
    # --------------------------------------------------------
    def initRepo(self, path: str | Path, branch: str = "") -> ActionOutcome:
        root = Path(path)
        root.mkdir(parents=True, exist_ok=True)
        name = (branch or "").strip()
        args = ["init", "-b", name] if name else ["init"]
        result = self._run(args, cwd=root)
        if not result.ok and name:
            fallback = self._run(["init"], cwd=root)
            if fallback.ok:
                self._run(["checkout", "-B", name], cwd=root)
                return ActionMapper.success("Repository initialized", name)
            result = fallback
        if result.ok:
            return ActionMapper.success(
                "Repository initialized",
                name or result.stdout.strip(),
            )
        return ActionMapper.mapError("init", result.stderr, result.stdout, result.returncode)

    # --------------------------------------------------------
    # Method: setRemote
    # Purpose: Add or update the `origin` remote URL.
    # --------------------------------------------------------
    def setRemote(self, path: str | Path, remote_url: str) -> ActionOutcome:
        root = Path(path)
        existing = self._run(["remote", "get-url", "origin"], cwd=root)
        if existing.ok:
            result = self._run(["remote", "set-url", "origin", remote_url], cwd=root)
        else:
            result = self._run(["remote", "add", "origin", remote_url], cwd=root)
        if result.ok:
            return ActionMapper.success("Remote saved", remote_url)
        return ActionMapper.mapError("remote", result.stderr, result.stdout, result.returncode)

    # --------------------------------------------------------
    # Method: applyLocalIdentity
    # Purpose: Set local (repo-only) user.name / user.email.
    # --------------------------------------------------------
    def applyLocalIdentity(self, path: str | Path, username: str, email: str) -> None:
        root = Path(path)
        if username:
            self._run(["config", "--local", "user.name", username], cwd=root)
        if email:
            self._run(["config", "--local", "user.email", email], cwd=root)

    # --------------------------------------------------------
    # Method: detectRemoteUrl
    # Purpose: Read origin URL if present.
    # --------------------------------------------------------
    def detectRemoteUrl(self, path: str | Path) -> str:
        result = self._run(["remote", "get-url", "origin"], cwd=Path(path))
        return result.stdout.strip() if result.ok else ""

    # --------------------------------------------------------
    # Method: detectBranch
    # Purpose: Current branch name, or empty if detached.
    # --------------------------------------------------------
    def detectBranch(self, path: str | Path) -> str:
        result = self._run(["branch", "--show-current"], cwd=Path(path))
        return result.stdout.strip() if result.ok else ""

    # --------------------------------------------------------
    # Method: detectInitDefaultBranch
    # Purpose: Git’s init.defaultBranch (usually main), else main.
    # --------------------------------------------------------
    def detectInitDefaultBranch(self, path: str | Path | None = None) -> str:
        cwd = Path(path) if path else None
        result = self._run(["config", "--get", "init.defaultBranch"], cwd=cwd)
        name = result.stdout.strip() if result.ok else ""
        return name or "main"

    # --------------------------------------------------------
    # Method: listLocalBranches
    # Purpose: Real local branch refs (empty on an unborn HEAD).
    # --------------------------------------------------------
    def listLocalBranches(self, path: str | Path) -> list[str]:
        root = Path(path)
        if not root.is_dir():
            return []
        result = self._run(
            ["for-each-ref", "--format=%(refname:short)", "refs/heads"],
            cwd=root,
        )
        if not result.ok:
            return []
        names: list[str] = []
        for line in result.stdout.splitlines():
            name = line.strip()
            if name and name not in names:
                names.append(name)
        return names

    # --------------------------------------------------------
    # Method: suggestBranchNames
    # Purpose: Branch names to offer for a first push / new project.
    # Output: Real local refs when they exist; otherwise only main.
    # --------------------------------------------------------
    def suggestBranchNames(self, path: str | Path = "") -> list[str]:
        if path and self.isRepo(path):
            local_refs = self.listLocalBranches(path)
            if local_refs:
                ordered: list[str] = []
                current = self.detectBranch(path)
                if current and current in local_refs:
                    ordered.append(current)
                for name in local_refs:
                    if name not in ordered:
                        ordered.append(name)
                return ordered
        return ["main"]

    # --------------------------------------------------------
    # Method: resolveBranchForSave
    # Purpose: Branch to store when the user left Default branch blank.
    # --------------------------------------------------------
    def resolveBranchForSave(self, path: str | Path, preferred: str = "") -> str:
        preferred = (preferred or "").strip()
        if preferred:
            return preferred
        suggestions = self.suggestBranchNames(path)
        return suggestions[0] if suggestions else "main"

    # --------------------------------------------------------
    # Method: detectLocalUser
    # Purpose: Read local or global user.name / user.email.
    # --------------------------------------------------------
    def detectLocalUser(self, path: str | Path) -> tuple[str, str]:
        root = Path(path)
        name = self._run(["config", "--get", "user.name"], cwd=root)
        email = self._run(["config", "--get", "user.email"], cwd=root)
        return (
            name.stdout.strip() if name.ok else "",
            email.stdout.strip() if email.ok else "",
        )

    # --------------------------------------------------------
    # Method: displayNameFromRemoteUrl
    # Purpose: Repo name from a remote URL (MyCad.git → MyCad).
    # --------------------------------------------------------
    @staticmethod
    def displayNameFromRemoteUrl(url: str) -> str:
        cleaned = (url or "").strip().rstrip("/")
        if cleaned.lower().endswith(".git"):
            cleaned = cleaned[:-4]
        cleaned = cleaned.replace("\\", "/")
        if ":" in cleaned and "://" not in cleaned:
            cleaned = cleaned.rsplit(":", 1)[-1]
        name = cleaned.rsplit("/", 1)[-1].strip()
        return name

    # --------------------------------------------------------
    # Method: isEmptyDirectory
    # Purpose: True when path exists and contains no files or folders.
    # --------------------------------------------------------
    @staticmethod
    def isEmptyDirectory(path: str | Path) -> bool:
        root = Path(path)
        if not root.is_dir():
            return False
        try:
            next(root.iterdir())
        except StopIteration:
            return True
        return False

    # --------------------------------------------------------
    # Method: cloneRepo
    # Purpose: Clone a remote into an empty local folder.
    # --------------------------------------------------------
    def cloneRepo(
        self,
        project: ProjectConfig,
        dest: str | Path,
        branch: str = "",
    ) -> ActionOutcome:
        dest_path = Path(dest)
        remote_url = (project.remote_url or "").strip()
        if not remote_url:
            return ActionOutcome(
                title="No remote URL",
                message="Enter a remote URL first.",
            )
        dest_path.mkdir(parents=True, exist_ok=True)
        if self.isRepo(dest_path):
            return ActionOutcome(
                title="Already a Git repository",
                message=(
                    "This folder is already a Git repo. "
                    "Use the This computer tab instead."
                ),
            )
        if not self.isEmptyDirectory(dest_path):
            return ActionOutcome(
                title="Folder is not empty",
                message="Choose an empty folder to clone into.",
            )

        args = ["clone"]
        name = (branch or "").strip()
        if name:
            args.extend(["-b", name])
        args.extend([remote_url, str(dest_path)])
        result = self._runWithAuth(
            args,
            cwd=dest_path.parent,
            project=project,
            timeout=180,
        )
        if not result.ok:
            return ActionMapper.mapError(
                "clone",
                result.stderr,
                result.stdout,
                result.returncode,
                requested_branch=name,
            )

        self.applyLocalIdentity(dest_path, project.username, project.email)
        checked_out = self.detectBranch(dest_path) or name
        return ActionMapper.success(
            "Cloned from Git",
            checked_out or remote_url,
        )

    # --------------------------------------------------------
    # Method: listRemoteBranches
    # Purpose: Read-only list of branch names on the Git remote.
    # Output: (branches, default_branch, error_message)
    # --------------------------------------------------------
    def listRemoteBranches(
        self,
        project: ProjectConfig,
    ) -> tuple[list[str], str, str]:
        root = Path(project.path) if (project.path or "").strip() else None
        remote_url = (project.remote_url or "").strip()
        if not remote_url:
            return [], "", "Enter a remote URL first."

        temp_cwd: Optional[Path] = None
        if root is None or not root.is_dir():
            temp_cwd = Path(tempfile.mkdtemp(prefix="gs_lsremote_"))
            root = temp_cwd

        try:
            heads = self._runWithAuth(
                ["ls-remote", "--heads", remote_url],
                cwd=root,
                project=project,
                timeout=60,
            )
            if not heads.ok:
                message = (heads.stderr or heads.stdout or "Could not list remote branches").strip()
                return [], "", message

            branches = self.parseLsRemoteHeads(heads.stdout)
            default_branch = self._detectDefaultFromLsRemote(root, project, remote_url)
            if default_branch and default_branch not in branches:
                default_branch = ""
            if not default_branch and branches:
                for name in ("main", "master"):
                    if name in branches:
                        default_branch = name
                        break
            return branches, default_branch, ""
        finally:
            if temp_cwd is not None:
                shutil.rmtree(temp_cwd, ignore_errors=True)

    # --------------------------------------------------------
    # Method: parseLsRemoteHeads
    # Purpose: Extract branch names from `git ls-remote --heads` stdout.
    # --------------------------------------------------------
    @staticmethod
    def parseLsRemoteHeads(stdout: str) -> list[str]:
        branches: list[str] = []
        seen: set[str] = set()
        prefix = "refs/heads/"
        for line in (stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            # Format: <sha>\trefs/heads/<name>  (or spaces)
            parts = line.split()
            if len(parts) < 2:
                continue
            ref = parts[-1]
            if not ref.startswith(prefix):
                continue
            name = ref[len(prefix) :]
            if not name or name in seen:
                continue
            seen.add(name)
            branches.append(name)
        return branches

    # --------------------------------------------------------
    # Method: _detectDefaultFromLsRemote
    # Purpose: Resolve remote default branch via ls-remote --symref HEAD.
    # --------------------------------------------------------
    def _detectDefaultFromLsRemote(
        self,
        root: Path,
        project: ProjectConfig,
        target: str,
    ) -> str:
        result = self._runWithAuth(
            ["ls-remote", "--symref", target, "HEAD"],
            cwd=root,
            project=project,
            timeout=60,
        )
        if not result.ok:
            return ""
        for line in result.stdout.splitlines():
            # ref: refs/heads/main\tHEAD
            stripped = line.strip()
            if not stripped.lower().startswith("ref:"):
                continue
            # ref: refs/heads/main HEAD
            rest = stripped[4:].strip()
            ref = rest.split()[0] if rest else ""
            prefix = "refs/heads/"
            if ref.startswith(prefix):
                return ref[len(prefix) :]
        return ""

    # --------------------------------------------------------
    # Method: getStatus
    # Purpose: Build a full ProjectStatus for one project.
    # --------------------------------------------------------
    def getStatus(self, project: ProjectConfig, fetch: bool = False) -> ProjectStatus:
        status = ProjectStatus(project_id=project.id)
        root = Path(project.path)
        if not root.is_dir():
            status.path_exists = False
            status.suggested_action = SuggestedAction.MISSING_PATH
            status.error_message = "Folder does not exist"
            return status

        status.path_exists = True
        if not self.isRepo(root):
            status.is_repo = False
            status.suggested_action = SuggestedAction.NOT_A_REPO
            return status

        status.is_repo = True
        status.branch = self.detectBranch(root) or project.default_branch
        status.remote_url = self.detectRemoteUrl(root) or project.remote_url
        # Do not overwrite project.default_branch from the checkout — that setting
        # is chosen in Edit project and drives checkoutSavedBranch on Save.

        if fetch and (project.remote_url or status.remote_url):
            fetch_result = self._runWithAuth(
                ["fetch", "--prune", "origin"],
                cwd=root,
                project=project,
                timeout=60,
            )
            status.remote_empty = self._detectRemoteEmpty(
                root,
                project,
                fetch_ok=fetch_result.ok,
            )
        else:
            status.remote_empty = not self._hasAnyOriginRefs(root)

        status.changes = self.listChanges(root)
        status.dirty = len(status.changes) > 0
        status.has_local_commits = self._hasLocalCommits(root)
        ahead, behind, upstream_ok = self._aheadBehind(root, status.branch)
        status.ahead = ahead
        status.behind = behind
        status.upstream_missing = bool(status.branch) and not upstream_ok

        status.remote_default_branch = self.detectRemoteDefaultBranch(root)
        if (
            status.branch
            and status.remote_default_branch
            and status.branch != status.remote_default_branch
        ):
            status.diverges_from_default = self._refsDiffer(
                root,
                "HEAD",
                f"origin/{status.remote_default_branch}",
            )

        status.last_tag = self._latestTag(root)
        status.changelog_version = ChangelogParser.readVersion(root)
        # Prefer Git's default branch for "what's on GitHub" when it differs.
        remote_version_branch = status.branch or project.default_branch
        if status.diverges_from_default and status.remote_default_branch:
            remote_version_branch = status.remote_default_branch
        status.git_changelog_version = self.readRemoteChangelogVersion(
            root,
            remote_version_branch,
        )
        status.suggested_action = self._suggestAction(status)
        return status

    # --------------------------------------------------------
    # Method: readRemoteChangelogVersion
    # Purpose: Parse Changelog version from origin/<branch> (Git's tip).
    # --------------------------------------------------------
    def readRemoteChangelogVersion(
        self,
        path: str | Path,
        branch: str,
    ) -> Optional[str]:
        root = Path(path)
        if not branch:
            return None
        for name in CHANGELOG_FILENAMES:
            spec = f"origin/{branch}:{name}"
            result = self._run(["show", spec], cwd=root, timeout=30)
            if not result.ok:
                continue
            version = ChangelogParser.parseVersionFromText(result.stdout)
            if version:
                return version
        return None

    # --------------------------------------------------------
    # Method: refreshAll
    # Purpose: Fetch status for every project in parallel.
    # --------------------------------------------------------
    def refreshAll(
        self,
        projects: list[ProjectConfig],
        fetch: bool = True,
        max_workers: int = 6,
    ) -> dict[str, ProjectStatus]:
        results: dict[str, ProjectStatus] = {}
        if not projects:
            return results

        workers = min(max_workers, max(1, len(projects)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(self.getStatus, project, fetch): project.id
                for project in projects
            }
            for future in as_completed(futures):
                project_id = futures[future]
                try:
                    results[project_id] = future.result()
                except Exception as exc:  # noqa: BLE001 — surface per-project
                    results[project_id] = ProjectStatus(
                        project_id=project_id,
                        error_message=str(exc),
                        suggested_action=SuggestedAction.UNKNOWN,
                    )
        return results

    # --------------------------------------------------------
    # Method: listChanges
    # Purpose: Parse porcelain status into FileChange list.
    # --------------------------------------------------------
    def listChanges(self, path: str | Path) -> list[FileChange]:
        root = Path(path)
        result = self._run(["status", "--porcelain", "-u"], cwd=root)
        if not result.ok:
            return []
        changes: list[FileChange] = []
        for line in result.stdout.splitlines():
            if not line or len(line) < 3:
                continue
            xy = line[:2]
            file_path = line[3:].strip()
            if " -> " in file_path:
                file_path = file_path.split(" -> ", 1)[1]
            kind = self._classifyPorcelain(xy)
            staged = xy[0] not in (" ", "?")
            changes.append(FileChange(path=file_path, kind=kind, staged=staged))
        return changes

    # --------------------------------------------------------
    # Method: getDiff
    # Purpose: Unified diff for one file (staged + unstaged).
    # --------------------------------------------------------
    def getDiff(self, path: str | Path, file_path: str) -> str:
        root = Path(path)
        # Untracked files have no diff against HEAD — show content preview.
        untracked = self._run(["ls-files", "--others", "--exclude-standard", "--", file_path], cwd=root)
        if untracked.ok and untracked.stdout.strip():
            target = root / file_path
            try:
                content = target.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                return f"(Could not read file: {exc})"
            preview = "\n".join(content.splitlines()[:200])
            return f"--- /dev/null\n+++ b/{file_path}\n(untracked file preview)\n\n{preview}"

        unstaged = self._run(["diff", "--", file_path], cwd=root)
        staged = self._run(["diff", "--cached", "--", file_path], cwd=root)
        parts: list[str] = []
        if staged.stdout.strip():
            parts.append(staged.stdout.strip())
        if unstaged.stdout.strip():
            parts.append(unstaged.stdout.strip())
        if parts:
            return "\n\n".join(parts)
        # Deleted or binary fallback
        against_head = self._run(["diff", "HEAD", "--", file_path], cwd=root)
        return against_head.stdout or against_head.stderr or "(no textual diff)"

    # --------------------------------------------------------
    # Method: stageAll
    # Purpose: Stage all changes including untracked.
    # --------------------------------------------------------
    def stageAll(self, path: str | Path) -> ActionOutcome:
        result = self._run(["add", "-A"], cwd=Path(path))
        if result.ok:
            return ActionMapper.success("Changes staged")
        return ActionMapper.mapError("add", result.stderr, result.stdout, result.returncode)

    # --------------------------------------------------------
    # Method: commit
    # Purpose: Stage all and create a commit with the message.
    # --------------------------------------------------------
    def commit(self, project: ProjectConfig, message: str) -> ActionOutcome:
        root = Path(project.path)
        self.applyLocalIdentity(root, project.username, project.email)
        staged = self.stageAll(root)
        if not staged.success:
            return staged
        result = self._run(["commit", "-m", message], cwd=root)
        if result.ok:
            return ActionMapper.success("Committed", message)
        # Nothing to commit is not a hard failure for UX.
        if "nothing to commit" in (result.stdout + result.stderr).lower():
            return ActionMapper.success("Nothing to commit", "Working tree clean")
        return ActionMapper.mapError("commit", result.stderr, result.stdout, result.returncode)

    # --------------------------------------------------------
    # Method: checkoutSavedBranch
    # Purpose: Switch this folder to project.default_branch (origin tip).
    #          Empty remotes: rename/create the local branch for first push.
    # --------------------------------------------------------
    def checkoutSavedBranch(self, project: ProjectConfig) -> ActionOutcome:
        root = Path(project.path)
        target = (project.default_branch or "").strip()
        if not target:
            return ActionMapper.success("No branch selected", "")

        current = self.detectBranch(root)
        fetch = self._runWithAuth(
            ["fetch", "--prune", "origin"],
            cwd=root,
            project=project,
            timeout=60,
        )
        remote_ref = f"origin/{target}"
        remote_ok = self._run(["rev-parse", "--verify", remote_ref], cwd=root)
        changes = self.listChanges(root)
        tracked_dirty = any(
            change.kind != FileChangeKind.UNTRACKED for change in changes
        )

        if current != target:
            # Switching onto an existing remote branch needs a clean tree.
            # First-push rename (no origin/<target>) is safe with untracked files,
            # including an unborn master → main before the first commit.
            if remote_ok.ok and changes:
                return ActionOutcome(
                    title="Cannot switch branch",
                    message=(
                        f"Cannot switch to {target} while this computer has unsaved files. "
                        "Commit or discard them first, then save again."
                    ),
                    choices=[],
                    details="",
                )
            if not remote_ok.ok and tracked_dirty:
                return ActionOutcome(
                    title="Cannot switch branch",
                    message=(
                        f"Cannot switch to {target} while this computer has unsaved tracked files. "
                        "Commit or discard them first, then save again."
                    ),
                    choices=[],
                    details="",
                )

        if current == target:
            if remote_ok.ok:
                return ActionMapper.success("Already on branch", target)
            return ActionMapper.success(
                "Ready for first push",
                f"Remote has no {target} yet — Push will create it.",
            )

        if not remote_ok.ok:
            # No origin/<target> — empty repo or branch not pushed yet.
            rename = self._run(["branch", "-M", target], cwd=root)
            if not rename.ok:
                created = self._run(["checkout", "-B", target], cwd=root)
                if not created.ok:
                    if not fetch.ok:
                        return ActionMapper.mapError(
                            "fetch",
                            fetch.stderr,
                            fetch.stdout,
                            fetch.returncode,
                        )
                    return ActionMapper.mapError(
                        "checkout",
                        created.stderr or rename.stderr,
                        created.stdout,
                        created.returncode,
                    )
            return ActionMapper.success(
                "Ready for first push",
                f"Remote has no {target} yet — local branch is {target}; Push will create it.",
            )

        local_ok = self._run(
            ["show-ref", "--verify", "--quiet", f"refs/heads/{target}"],
            cwd=root,
        )
        if local_ok.ok:
            result = self._run(["checkout", target], cwd=root)
        else:
            result = self._run(
                ["checkout", "-b", target, "--track", remote_ref],
                cwd=root,
            )
            if not result.ok:
                # Fallback when --track is unavailable for this ref shape.
                result = self._run(["checkout", "-B", target, remote_ref], cwd=root)

        if not result.ok:
            return ActionMapper.mapError(
                "checkout",
                result.stderr,
                result.stdout,
                result.returncode,
            )
        return ActionMapper.success(f"Switched to {target}", remote_ref)

    # --------------------------------------------------------
    # Method: pull
    # Purpose: Pull from origin for the branch you are on.
    # --------------------------------------------------------
    def pull(
        self,
        project: ProjectConfig,
        rebase: bool = False,
        branch: Optional[str] = None,
    ) -> ActionOutcome:
        root = Path(project.path)
        current = self.detectBranch(root)
        target = (branch or current or project.default_branch or "main").strip()
        args = ["pull"]
        if rebase:
            args.append("--rebase")
        args.extend(["origin", target])
        result = self._runWithAuth(args, cwd=root, project=project, timeout=120)
        if result.ok:
            return ActionMapper.success("Pull complete", result.stdout.strip())
        return ActionMapper.mapError(
            "pull",
            result.stderr,
            result.stdout,
            result.returncode,
            local_branch=current or target,
            requested_branch=target,
        )

    # --------------------------------------------------------
    # Method: push
    # Purpose: Push current branch; optional force with lease.
    #          Force also updates remote default when it differs.
    # --------------------------------------------------------
    def push(
        self,
        project: ProjectConfig,
        force: bool = False,
        set_upstream: bool = False,
    ) -> ActionOutcome:
        root = Path(project.path)
        branch = self.detectBranch(root) or project.default_branch or "main"
        remote_ref_ok = self._run(
            ["rev-parse", "--verify", f"origin/{branch}"],
            cwd=root,
        ).ok
        # --force-with-lease fails when there is no remote-tracking ref
        # (empty Git remotes). First publish is a normal -u push.
        use_force = force and remote_ref_ok
        use_upstream = set_upstream or not remote_ref_ok
        args = ["push"]
        if use_force:
            args.append("--force-with-lease")
        if use_upstream:
            args.extend(["-u", "origin", branch])
        else:
            args.extend(["origin", branch])
        result = self._runWithAuth(args, cwd=root, project=project, timeout=120)
        if not result.ok:
            return ActionMapper.mapError(
                "push",
                result.stderr,
                result.stdout,
                result.returncode,
                local_branch=branch,
            )

        updated = [branch]
        if force:
            remote_default = self.detectRemoteDefaultBranch(root)
            if remote_default and remote_default != branch:
                second = self._runWithAuth(
                    ["push", "--force-with-lease", "origin", f"HEAD:{remote_default}"],
                    cwd=root,
                    project=project,
                    timeout=120,
                )
                if not second.ok:
                    return ActionMapper.mapError(
                        "push",
                        second.stderr,
                        second.stdout,
                        second.returncode,
                    )
                updated.append(remote_default)

        label = "Force push complete" if force else "Push complete"
        return ActionMapper.success(label, " and ".join(updated))

    # --------------------------------------------------------
    # Method: mergeBringRemote
    # Purpose: Merge origin/<remote_branch> into the current checkout.
    # --------------------------------------------------------
    def mergeBringRemote(
        self,
        project: ProjectConfig,
        remote_branch: str,
    ) -> ActionOutcome:
        root = Path(project.path)
        target = (remote_branch or "").strip()
        if not target:
            return ActionOutcome(
                title="No remote branch",
                message="Could not tell which Git branch to merge from.",
            )
        if self.listChanges(root):
            return ActionOutcome(
                title="Unsaved files",
                message=(
                    "Commit or discard unsaved files on this computer before merging."
                ),
            )

        fetch = self._runWithAuth(
            ["fetch", "--prune", "origin"],
            cwd=root,
            project=project,
            timeout=60,
        )
        if not fetch.ok:
            return ActionMapper.mapError(
                "fetch",
                fetch.stderr,
                fetch.stdout,
                fetch.returncode,
            )

        remote_ref = f"origin/{target}"
        check = self._run(["rev-parse", "--verify", remote_ref], cwd=root)
        if not check.ok:
            return ActionOutcome(
                title="Remote branch not found",
                message=f"Git does not have {remote_ref} to merge from.",
                details=check.stderr,
            )

        current = self.detectBranch(root) or "this branch"
        result = self._run(
            ["merge", "--no-edit", remote_ref],
            cwd=root,
            timeout=120,
        )
        if result.ok:
            return ActionMapper.success(
                "Merge complete",
                f"Merged {remote_ref} into {current}",
            )
        return ActionMapper.mapError(
            "merge",
            result.stderr,
            result.stdout,
            result.returncode,
            local_branch=current,
            requested_branch=target,
        )

    # --------------------------------------------------------
    # Method: mergeSendToRemote
    # Purpose: Merge current checkout into origin/<remote_branch>, then push.
    # --------------------------------------------------------
    def mergeSendToRemote(
        self,
        project: ProjectConfig,
        remote_branch: str,
    ) -> ActionOutcome:
        root = Path(project.path)
        target = (remote_branch or "").strip()
        if not target:
            return ActionOutcome(
                title="No remote branch",
                message="Could not tell which Git branch to merge into.",
            )
        if self.listChanges(root):
            return ActionOutcome(
                title="Unsaved files",
                message=(
                    "Commit or discard unsaved files on this computer before merging."
                ),
            )

        was_on = self.detectBranch(root)
        if not was_on:
            return ActionOutcome(
                title="Detached HEAD",
                message="Check out a branch on this computer first, then try again.",
            )

        fetch = self._runWithAuth(
            ["fetch", "--prune", "origin"],
            cwd=root,
            project=project,
            timeout=60,
        )
        if not fetch.ok:
            return ActionMapper.mapError(
                "fetch",
                fetch.stderr,
                fetch.stdout,
                fetch.returncode,
            )

        remote_ref = f"origin/{target}"
        check = self._run(["rev-parse", "--verify", remote_ref], cwd=root)
        if not check.ok:
            return ActionOutcome(
                title="Remote branch not found",
                message=f"Git does not have {remote_ref} to merge into.",
                details=check.stderr,
            )

        checkout = self._run(["checkout", "-B", target, remote_ref], cwd=root)
        if not checkout.ok:
            return ActionMapper.mapError(
                "checkout",
                checkout.stderr,
                checkout.stdout,
                checkout.returncode,
            )

        merge = self._run(["merge", "--no-edit", was_on], cwd=root, timeout=120)
        if not merge.ok:
            return ActionMapper.mapError(
                "merge",
                merge.stderr,
                merge.stdout,
                merge.returncode,
                local_branch=was_on,
                requested_branch=target,
            )

        push = self._runWithAuth(
            ["push", "origin", target],
            cwd=root,
            project=project,
            timeout=120,
        )
        if not push.ok:
            return ActionMapper.mapError(
                "push",
                push.stderr,
                push.stdout,
                push.returncode,
            )

        if was_on != target:
            self._run(["checkout", was_on], cwd=root)

        return ActionMapper.success(
            "Merge and push complete",
            f"Merged {was_on} into {target} and pushed",
        )

    # --------------------------------------------------------
    # Method: createTag
    # Purpose: Create an annotated (or lightweight) version tag locally.
    # --------------------------------------------------------
    def createTag(
        self,
        path: str | Path,
        version: str,
        message: str = "",
    ) -> ActionOutcome:
        root = Path(path)
        tag_name = version if version.lower().startswith("v") else f"v{version}"
        tag_message = message or f"Release {tag_name}"
        result = self._run(["tag", "-a", tag_name, "-m", tag_message], cwd=root)
        if result.ok:
            return ActionMapper.success("Tag created", tag_name)
        # Fall back to lightweight tag if annotated fails (e.g. no identity).
        light = self._run(["tag", tag_name], cwd=root)
        if light.ok:
            return ActionMapper.success("Tag created", tag_name)
        return ActionMapper.mapError(
            "tag",
            result.stderr or light.stderr,
            result.stdout or light.stdout,
            result.returncode or light.returncode,
        )

    # --------------------------------------------------------
    # Method: pushTag
    # Purpose: Push one tag to origin.
    # --------------------------------------------------------
    def pushTag(self, project: ProjectConfig, version: str) -> ActionOutcome:
        root = Path(project.path)
        tag_name = version if version.lower().startswith("v") else f"v{version}"
        result = self._runWithAuth(
            ["push", "origin", tag_name],
            cwd=root,
            project=project,
            timeout=120,
        )
        if result.ok:
            return ActionMapper.success("Tag pushed", tag_name)
        return ActionMapper.mapError("push", result.stderr, result.stdout, result.returncode)

    # --------------------------------------------------------
    # Method: discardFile
    # Purpose: Discard local changes for one file (tracked or untracked).
    # --------------------------------------------------------
    def discardFile(self, path: str | Path, file_path: str) -> ActionOutcome:
        root = Path(path)
        tracked = self._run(["ls-files", "--error-unmatch", "--", file_path], cwd=root)
        if tracked.ok:
            result = self._run(["checkout", "--", file_path], cwd=root)
            # Also unstage if staged
            self._run(["reset", "HEAD", "--", file_path], cwd=root)
            if result.ok:
                return ActionMapper.success("Discarded", file_path)
            return ActionMapper.mapError("discard", result.stderr, result.stdout, result.returncode)
        # Untracked — remove the file / directory
        target = root / file_path
        try:
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
            return ActionMapper.success("Removed untracked", file_path)
        except OSError as exc:
            return ActionMapper.mapError("discard", str(exc), "", 1)

    # --------------------------------------------------------
    # Method: discardAll
    # Purpose: Hard reset + clean untracked (destructive).
    # --------------------------------------------------------
    def discardAll(self, path: str | Path) -> ActionOutcome:
        root = Path(path)
        reset = self._run(["reset", "--hard", "HEAD"], cwd=root)
        clean = self._run(["clean", "-fd"], cwd=root)
        if reset.ok and clean.ok:
            return ActionMapper.success("All local changes discarded")
        return ActionMapper.mapError(
            "discard",
            reset.stderr or clean.stderr,
            reset.stdout or clean.stdout,
            reset.returncode or clean.returncode,
        )

    # --------------------------------------------------------
    # Method: stashThenPull
    # Purpose: Stash local changes, pull, leave stash for user.
    # --------------------------------------------------------
    def stashThenPull(self, project: ProjectConfig) -> ActionOutcome:
        root = Path(project.path)
        stash = self._run(["stash", "push", "-u", "-m", "git-syncher auto-stash"], cwd=root)
        if not stash.ok and "no local changes" not in (stash.stderr + stash.stdout).lower():
            return ActionMapper.mapError("stash", stash.stderr, stash.stdout, stash.returncode)
        pull_outcome = self.pull(project)
        if pull_outcome.success:
            pull_outcome.message = (
                (pull_outcome.message or "")
                + "\nLocal changes were stashed. Use git stash pop if you need them back."
            ).strip()
        return pull_outcome

    # --------------------------------------------------------
    # Method: discardThenPull
    # Purpose: Discard all local changes then pull.
    # --------------------------------------------------------
    def discardThenPull(self, project: ProjectConfig) -> ActionOutcome:
        discard = self.discardAll(project.path)
        if not discard.success:
            return discard
        return self.pull(project)

    # --------------------------------------------------------
    # Method: resetToRemote
    # Purpose: Make this computer identical to origin (Git unchanged).
    #          Fetch, hard-reset to origin/<branch>, then clean.
    # --------------------------------------------------------
    def resetToRemote(self, project: ProjectConfig) -> ActionOutcome:
        root = Path(project.path)
        fetch = self._runWithAuth(
            ["fetch", "--prune", "origin"],
            cwd=root,
            project=project,
            timeout=120,
        )
        if not fetch.ok:
            return ActionMapper.mapError(
                "fetch",
                fetch.stderr,
                fetch.stdout,
                fetch.returncode,
                local_branch=self.detectBranch(root),
            )

        remote_ref = self._resolveOriginBranch(root, project)
        if not remote_ref:
            return ActionOutcome(
                title="Remote branch not found",
                message=(
                    "Git has no branches yet — there is nothing to match. "
                    "Commit if needed, then send this branch to Git (first push)."
                ),
                choices=[
                    ActionChoice(
                        ActionId.FIRST_PUSH,
                        "Send this branch to Git",
                        description="Create this branch on the remote (first push).",
                    ),
                    ActionChoice(ActionId.OPEN_SETTINGS, "Open project settings"),
                    ActionChoice(ActionId.CANCEL, "Cancel"),
                ],
                details=fetch.stdout + "\n" + fetch.stderr,
            )

        # Point local branch at the remote tip (does not change Git online).
        branch_name = remote_ref.removeprefix("origin/")
        checkout = self._run(["checkout", "-B", branch_name, remote_ref], cwd=root)
        if not checkout.ok:
            # Fallback: reset hard if already on a branch that can track the ref.
            reset = self._run(["reset", "--hard", remote_ref], cwd=root)
            if not reset.ok:
                return ActionMapper.mapError(
                    "reset",
                    reset.stderr or checkout.stderr,
                    reset.stdout or checkout.stdout,
                    reset.returncode or checkout.returncode,
                )
        else:
            reset = self._run(["reset", "--hard", remote_ref], cwd=root)
            if not reset.ok:
                return ActionMapper.mapError(
                    "reset",
                    reset.stderr,
                    reset.stdout,
                    reset.returncode,
                )

        clean = self._run(["clean", "-fd"], cwd=root)
        if not clean.ok:
            return ActionMapper.mapError(
                "clean",
                clean.stderr,
                clean.stdout,
                clean.returncode,
            )

        if project.default_branch != branch_name:
            project.default_branch = branch_name

        return ActionMapper.success(
            "This computer now matches Git",
            f"Reset to {remote_ref}",
        )

    # --------------------------------------------------------
    # Method: _hasAnyOriginRefs
    # Purpose: True when fetch stored at least one origin remote-tracking ref.
    # --------------------------------------------------------
    def _hasAnyOriginRefs(self, root: Path) -> bool:
        result = self._run(
            ["for-each-ref", "--format=%(refname)", "refs/remotes/origin"],
            cwd=root,
        )
        if not result.ok:
            return False
        return any(line.strip() for line in result.stdout.splitlines())

    # --------------------------------------------------------
    # Method: _detectRemoteEmpty
    # Purpose: Prefer live ls-remote after a failed fetch so stale
    #          origin/* refs cannot hide an empty Git remote.
    # --------------------------------------------------------
    def _detectRemoteEmpty(
        self,
        root: Path,
        project: ProjectConfig,
        fetch_ok: bool,
    ) -> bool:
        if fetch_ok:
            return not self._hasAnyOriginRefs(root)
        heads, _default, err = self.listRemoteBranches(project)
        if not err:
            return len(heads) == 0
        return not self._hasAnyOriginRefs(root)

    # --------------------------------------------------------
    # Method: _hasLocalCommits
    # Purpose: True when HEAD exists (not an unborn branch).
    # --------------------------------------------------------
    def _hasLocalCommits(self, root: Path) -> bool:
        result = self._run(["rev-parse", "--verify", "HEAD"], cwd=root)
        return result.ok

    # --------------------------------------------------------
    # Method: detectRemoteDefaultBranch
    # Purpose: Branch name pointed at by origin/HEAD (GitHub default).
    # --------------------------------------------------------
    def detectRemoteDefaultBranch(self, path: str | Path) -> str:
        root = Path(path)
        head = self._run(
            ["symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"],
            cwd=root,
        )
        if head.ok:
            ref_path = head.stdout.strip()
            prefix = "refs/remotes/origin/"
            if ref_path.startswith(prefix):
                return ref_path[len(prefix) :]
        for name in ("main", "master"):
            check = self._run(["rev-parse", "--verify", f"origin/{name}"], cwd=root)
            if check.ok:
                return name
        return ""

    # --------------------------------------------------------
    # Method: _refsDiffer
    # Purpose: True when two refs resolve to different commits.
    # --------------------------------------------------------
    def _refsDiffer(self, root: Path, ref_a: str, ref_b: str) -> bool:
        a = self._run(["rev-parse", "--verify", ref_a], cwd=root)
        b = self._run(["rev-parse", "--verify", ref_b], cwd=root)
        if not a.ok or not b.ok:
            return False
        return a.stdout.strip() != b.stdout.strip()

    # --------------------------------------------------------
    # Method: _resolveOriginBranch
    # Purpose: Pick origin/<branch> for hard reset — Git default first.
    # --------------------------------------------------------
    def _resolveOriginBranch(self, root: Path, project: ProjectConfig) -> str:
        candidates: list[str] = []
        remote_default = self.detectRemoteDefaultBranch(root)
        if remote_default:
            candidates.append(remote_default)
        if project.default_branch and project.default_branch not in candidates:
            candidates.append(project.default_branch)
        for name in ("main", "master"):
            if name not in candidates:
                candidates.append(name)
        current = self.detectBranch(root)
        if current and current not in candidates:
            candidates.append(current)

        for name in candidates:
            ref = f"origin/{name}"
            check = self._run(["rev-parse", "--verify", ref], cwd=root)
            if check.ok:
                return ref
        return ""

    # --------------------------------------------------------
    # Method: resolveFileKeepLocal
    # Purpose: During conflict, keep our (local) version.
    # --------------------------------------------------------
    def resolveFileKeepLocal(self, path: str | Path, file_path: str) -> ActionOutcome:
        root = Path(path)
        result = self._run(["checkout", "--ours", "--", file_path], cwd=root)
        if result.ok:
            self._run(["add", "--", file_path], cwd=root)
            return ActionMapper.success("Kept local", file_path)
        return ActionMapper.mapError("resolve", result.stderr, result.stdout, result.returncode)

    # --------------------------------------------------------
    # Method: resolveFileTakeRemote
    # Purpose: During conflict, take their (remote) version.
    # --------------------------------------------------------
    def resolveFileTakeRemote(self, path: str | Path, file_path: str) -> ActionOutcome:
        root = Path(path)
        result = self._run(["checkout", "--theirs", "--", file_path], cwd=root)
        if result.ok:
            self._run(["add", "--", file_path], cwd=root)
            return ActionMapper.success("Took remote", file_path)
        return ActionMapper.mapError("resolve", result.stderr, result.stdout, result.returncode)

    # --------------------------------------------------------
    # Method: _suggestAction
    # Purpose: Map status fields to SuggestedAction.
    # --------------------------------------------------------
    @staticmethod
    def _suggestAction(status: ProjectStatus) -> SuggestedAction:
        if not status.path_exists:
            return SuggestedAction.MISSING_PATH
        if not status.is_repo:
            return SuggestedAction.NOT_A_REPO
        if any(change.kind == FileChangeKind.CONFLICT for change in status.changes):
            return SuggestedAction.RESOLVE
        if status.diverges_from_default:
            return SuggestedAction.MERGE
        if status.remote_empty:
            if status.dirty or not status.has_local_commits:
                return SuggestedAction.COMMIT
            return SuggestedAction.PUSH
        if status.upstream_missing and not status.has_local_commits:
            return SuggestedAction.COMMIT
        if status.upstream_missing:
            return SuggestedAction.RESOLVE
        if status.dirty:
            return SuggestedAction.COMMIT
        if status.ahead and status.behind:
            return SuggestedAction.MERGE
        if status.behind:
            return SuggestedAction.PULL
        if status.ahead:
            return SuggestedAction.PUSH
        if ChangelogParser.isChangelogNewerThanTag(status.changelog_version, status.last_tag):
            # Changelog bumped but nothing committed yet was handled by dirty;
            # if clean and ahead tags lag, still suggest push if ahead else synced.
            pass
        return SuggestedAction.SYNCED

    # --------------------------------------------------------
    # Method: _aheadBehind
    # Purpose: Count commits ahead/behind origin/<branch>.
    # Output: (ahead, behind, upstream_ok)
    # --------------------------------------------------------
    def _aheadBehind(self, root: Path, branch: str) -> tuple[int, int, bool]:
        if not branch:
            return 0, 0, False
        upstream = f"origin/{branch}"
        # Verify upstream exists
        check = self._run(["rev-parse", "--verify", upstream], cwd=root)
        if not check.ok:
            return 0, 0, False
        result = self._run(
            ["rev-list", "--left-right", "--count", f"{upstream}...HEAD"],
            cwd=root,
        )
        if not result.ok:
            return 0, 0, False
        parts = result.stdout.strip().split()
        if len(parts) != 2:
            return 0, 0, False
        try:
            behind = int(parts[0])
            ahead = int(parts[1])
            return ahead, behind, True
        except ValueError:
            return 0, 0, False

    # --------------------------------------------------------
    # Method: latestTag
    # Purpose: Public accessor for the newest tag in a repo.
    # --------------------------------------------------------
    def latestTag(self, path: str | Path) -> str:
        return self._latestTag(Path(path))

    # --------------------------------------------------------
    # Method: _latestTag
    # Purpose: Most recent tag by creatordate, or empty.
    # --------------------------------------------------------
    def _latestTag(self, root: Path) -> str:
        result = self._run(
            ["tag", "-l", "--sort=-creatordate"],
            cwd=root,
        )
        if not result.ok or not result.stdout.strip():
            return ""
        return result.stdout.strip().splitlines()[0].strip()

    # --------------------------------------------------------
    # Method: _classifyPorcelain
    # Purpose: Map porcelain XY codes to FileChangeKind.
    # --------------------------------------------------------
    @staticmethod
    def _classifyPorcelain(xy: str) -> FileChangeKind:
        if "U" in xy or xy in ("AA", "DD"):
            return FileChangeKind.CONFLICT
        if xy == "??":
            return FileChangeKind.UNTRACKED
        if xy[0] == "A" or xy[1] == "A":
            return FileChangeKind.ADDED
        if xy[0] == "D" or xy[1] == "D":
            return FileChangeKind.DELETED
        if xy[0] == "R" or xy[1] == "R":
            return FileChangeKind.RENAMED
        if xy[0] == "M" or xy[1] == "M":
            return FileChangeKind.MODIFIED
        return FileChangeKind.UNKNOWN

    # --------------------------------------------------------
    # Method: _run
    # Purpose: Run git with args in cwd; no auth injection.
    # --------------------------------------------------------
    def _run(
        self,
        args: list[str],
        cwd: Optional[Path],
        timeout: int = 60,
        env: Optional[dict[str, str]] = None,
    ) -> GitResult:
        command = [self.git_executable, *args]
        run_env = os.environ.copy()
        # Never prompt interactively — map to ActionOutcome instead.
        run_env["GIT_TERMINAL_PROMPT"] = "0"
        # Prefer UTF-8 for changelog / commit text on Windows (default is often cp1252).
        run_env.setdefault("PYTHONUTF8", "1")
        run_env.setdefault("LANG", "C.UTF-8")
        if env:
            run_env.update(env)
        try:
            completed = subprocess.run(
                command,
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=run_env,
                check=False,
                **self._hideConsoleKwargs(),
            )
            return GitResult(
                returncode=completed.returncode,
                stdout=completed.stdout or "",
                stderr=completed.stderr or "",
            )
        except subprocess.TimeoutExpired as exc:
            stdout = ""
            if isinstance(exc.stdout, str):
                stdout = exc.stdout
            elif isinstance(exc.stdout, (bytes, bytearray)):
                stdout = bytes(exc.stdout).decode("utf-8", errors="replace")
            return GitResult(
                returncode=124,
                stdout=stdout,
                stderr="Git command timed out",
            )
        except OSError as exc:
            return GitResult(returncode=127, stdout="", stderr=str(exc))
        except UnicodeDecodeError as exc:
            return GitResult(
                returncode=1,
                stdout="",
                stderr=f"Could not decode Git output as UTF-8: {exc}",
            )
    # --------------------------------------------------------
    # Method: _runWithAuth
    # Purpose: Inject PAT via temporary askpass helper for HTTPS.
    # --------------------------------------------------------
    def _runWithAuth(
        self,
        args: list[str],
        cwd: Path,
        project: ProjectConfig,
        timeout: int = 120,
    ) -> GitResult:
        if not project.pat:
            return self._run(args, cwd=cwd, timeout=timeout)

        username = project.username or "git"
        password = project.pat
        askpass_path: Optional[Path] = None
        try:
            askpass_path = self._writeAskpassScript(username, password)
            env = {
                "GIT_ASKPASS": str(askpass_path),
                "SSH_ASKPASS": str(askpass_path),
                "GIT_TERMINAL_PROMPT": "0",
                "GCM_INTERACTIVE": "never",
            }
            # Prefer askpass over stored credentials for this process.
            extra_args = ["-c", "credential.helper=", *args]
            return self._run(extra_args, cwd=cwd, timeout=timeout, env=env)
        finally:
            if askpass_path is not None:
                try:
                    askpass_path.unlink(missing_ok=True)
                except OSError:
                    pass

    # --------------------------------------------------------
    # Method: _writeAskpassScript
    # Purpose: Create a short-lived executable that prints creds.
    # --------------------------------------------------------
    def _writeAskpassScript(self, username: str, password: str) -> Path:
        # Escape for embedding in generated scripts.
        safe_user = username.replace("\\", "\\\\").replace('"', '\\"')
        safe_pass = password.replace("\\", "\\\\").replace('"', '\\"')
        if os.name == "nt":
            # Windows batch askpass — Git invokes with a prompt argument.
            fd, name = tempfile.mkstemp(suffix=".cmd", prefix="gs_askpass_")
            os.close(fd)
            path = Path(name)
            script = (
                "@echo off\r\n"
                "set \"PROMPT=%~1\"\r\n"
                "echo.%PROMPT% | findstr /I \"Username\" >nul\r\n"
                "if %ERRORLEVEL%==0 (\r\n"
                f"  echo {safe_user}\r\n"
                "  exit /b 0\r\n"
                ")\r\n"
                f"echo {safe_pass}\r\n"
            )
            path.write_text(script, encoding="utf-8")
            return path

        fd, name = tempfile.mkstemp(suffix=".sh", prefix="gs_askpass_")
        os.close(fd)
        path = Path(name)
        script = (
            "#!/bin/sh\n"
            "case \"$1\" in\n"
            f'  *Username*) echo "{safe_user}" ;;\n'
            f'  *) echo "{safe_pass}" ;;\n'
            "esac\n"
        )
        path.write_text(script, encoding="utf-8")
        path.chmod(0o700)
        return path
