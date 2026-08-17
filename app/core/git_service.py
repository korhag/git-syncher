from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.core.actions import ActionMapper, ActionOutcome
from app.core.changelog import ChangelogParser
from app.models.project import (
    FileChange,
    FileChangeKind,
    ProjectConfig,
    ProjectStatus,
    SuggestedAction,
)


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
        self.git_executable = git_executable or shutil.which("git") or "git"

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
    def initRepo(self, path: str | Path) -> ActionOutcome:
        root = Path(path)
        root.mkdir(parents=True, exist_ok=True)
        result = self._run(["init"], cwd=root)
        if result.ok:
            return ActionMapper.success("Repository initialized", result.stdout.strip())
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

        if fetch and (project.remote_url or status.remote_url):
            self._runWithAuth(
                ["fetch", "--prune", "origin"],
                cwd=root,
                project=project,
                timeout=60,
            )

        status.changes = self.listChanges(root)
        status.dirty = len(status.changes) > 0
        ahead, behind = self._aheadBehind(root, status.branch)
        status.ahead = ahead
        status.behind = behind
        status.last_tag = self._latestTag(root)
        status.changelog_version = ChangelogParser.readVersion(root)
        status.suggested_action = self._suggestAction(status)
        return status

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
    # Method: pull
    # Purpose: Pull from origin with optional rebase.
    # --------------------------------------------------------
    def pull(self, project: ProjectConfig, rebase: bool = False) -> ActionOutcome:
        root = Path(project.path)
        args = ["pull"]
        if rebase:
            args.append("--rebase")
        args.extend(["origin", project.default_branch or self.detectBranch(root) or "main"])
        result = self._runWithAuth(args, cwd=root, project=project, timeout=120)
        if result.ok:
            return ActionMapper.success("Pull complete", result.stdout.strip())
        return ActionMapper.mapError("pull", result.stderr, result.stdout, result.returncode)

    # --------------------------------------------------------
    # Method: push
    # Purpose: Push current branch; optional force with lease.
    # --------------------------------------------------------
    def push(
        self,
        project: ProjectConfig,
        force: bool = False,
        set_upstream: bool = False,
    ) -> ActionOutcome:
        root = Path(project.path)
        branch = self.detectBranch(root) or project.default_branch or "main"
        args = ["push"]
        if force:
            args.append("--force-with-lease")
        if set_upstream:
            args.extend(["-u", "origin", branch])
        else:
            args.extend(["origin", branch])
        result = self._runWithAuth(args, cwd=root, project=project, timeout=120)
        if result.ok:
            label = "Force push complete" if force else "Push complete"
            return ActionMapper.success(label, result.stdout.strip() or branch)
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
        if status.dirty:
            return SuggestedAction.COMMIT
        if status.ahead and status.behind:
            return SuggestedAction.RESOLVE
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
    # --------------------------------------------------------
    def _aheadBehind(self, root: Path, branch: str) -> tuple[int, int]:
        if not branch:
            return 0, 0
        upstream = f"origin/{branch}"
        # Verify upstream exists
        check = self._run(["rev-parse", "--verify", upstream], cwd=root)
        if not check.ok:
            return 0, 0
        result = self._run(
            ["rev-list", "--left-right", "--count", f"{upstream}...HEAD"],
            cwd=root,
        )
        if not result.ok:
            return 0, 0
        parts = result.stdout.strip().split()
        if len(parts) != 2:
            return 0, 0
        try:
            behind = int(parts[0])
            ahead = int(parts[1])
            return ahead, behind
        except ValueError:
            return 0, 0

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
        if env:
            run_env.update(env)
        try:
            completed = subprocess.run(
                command,
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=run_env,
                check=False,
            )
            return GitResult(
                returncode=completed.returncode,
                stdout=completed.stdout or "",
                stderr=completed.stderr or "",
            )
        except subprocess.TimeoutExpired as exc:
            return GitResult(
                returncode=124,
                stdout=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
                stderr="Git command timed out",
            )
        except OSError as exc:
            return GitResult(returncode=127, stdout="", stderr=str(exc))

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
