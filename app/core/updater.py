from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.core.git_service import GitService
from app.core.shortcuts import consolePython, installShortcuts, projectRoot

_VERSION_RE = re.compile(r"""__version__\s*=\s*["']([^"']+)["']""")
_PYPI_INDEX = "https://pypi.org/simple"


# ------------------------------------------------------------
# Class: UpdateResult
# Purpose: Outcome of downloading this app from its own Git remote.
# ------------------------------------------------------------
@dataclass
class UpdateResult:
    ok: bool
    message: str
    updated: bool = False
    version_before: str = ""
    version_after: str = ""


# ------------------------------------------------------------
# Function: _fileHash
# Purpose: SHA-256 of a file, or empty when the file is missing.
# ------------------------------------------------------------
def _fileHash(path: Path) -> str:
    if not path.is_file():
        return ""
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


# ------------------------------------------------------------
# Function: _readVersion
# Purpose: Read __version__ from app/__init__.py on disk.
# ------------------------------------------------------------
def _readVersion(root: Path) -> str:
    init_file = root / "app" / "__init__.py"
    if not init_file.is_file():
        return ""
    match = _VERSION_RE.search(init_file.read_text(encoding="utf-8", errors="replace"))
    if match is None:
        return ""
    return match.group(1)


# ------------------------------------------------------------
# Function: _firstLine
# Purpose: First non-empty line of a command's output.
# ------------------------------------------------------------
def _firstLine(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


# ------------------------------------------------------------
# Function: _pullUpdated
# Purpose: True when git pull moved HEAD (not "Already up to date").
# ------------------------------------------------------------
def _pullUpdated(stdout: str) -> bool:
    lowered = stdout.lower()
    if "already up to date" in lowered or "already up-to-date" in lowered:
        return False
    return True


# ------------------------------------------------------------
# Function: _run
# Purpose: Run a command in the repo with no visible console and no
#          interactive Git credential prompt.
# ------------------------------------------------------------
def _run(
    root: Path,
    args: list[str],
    timeout: int,
    extra_env: Optional[dict[str, str]] = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "Never"
    env["GIT_MERGE_AUTOEDIT"] = "no"
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        args,
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        env=env,
        **GitService._hideConsoleKwargs(),
    )


# ------------------------------------------------------------
# Function: _pipEnv
# Purpose: Force pip to use PyPI. Debian/Pi images add piwheels, which
#          ships a stub flet package that cannot start this app.
# ------------------------------------------------------------
def _pipEnv() -> dict[str, str]:
    config_file = "NUL" if os.name == "nt" else "/dev/null"
    return {
        "PIP_CONFIG_FILE": config_file,
        "PIP_INDEX_URL": _PYPI_INDEX,
        "PIP_EXTRA_INDEX_URL": "",
    }


# ------------------------------------------------------------
# Function: _message
# Purpose: Short sentence for the dashboard after a successful update.
# ------------------------------------------------------------
def _message(
    updated: bool,
    version_before: str,
    version_after: str,
    reinstalled: bool,
    shortcut_message: str,
) -> str:
    if updated and version_before and version_after and version_before != version_after:
        text = f"Updated {version_before} to {version_after}."
    elif updated:
        text = "Updated from Git."
    else:
        shown = version_after or version_before
        text = f"Already up to date (v{shown})." if shown else "Already up to date."
    if reinstalled:
        text += " Dependencies were reinstalled."
    if shortcut_message:
        text += f" {shortcut_message}"
    return text


# ------------------------------------------------------------
# Function: updateApp
# Purpose: Fast-forward this checkout, reinstall dependencies when
#          requirements.txt changed, then refresh the menu icon.
# Input: root - repo folder. Defaults to this checkout.
# ------------------------------------------------------------
def updateApp(root: Optional[Path] = None) -> UpdateResult:
    try:
        return _updateApp(root)
    except subprocess.TimeoutExpired:
        return UpdateResult(
            ok=False,
            message="The update timed out. Check your network and try again.",
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return UpdateResult(ok=False, message=f"Update failed: {exc}")


# ------------------------------------------------------------
# Function: _updateApp
# Purpose: Implementation of updateApp, with failures as results.
# ------------------------------------------------------------
def _updateApp(root: Optional[Path]) -> UpdateResult:
    folder = (root or projectRoot()).resolve()
    if not (folder / ".git").exists():
        return UpdateResult(
            ok=False,
            message="This folder is not a Git checkout, so Git Syncher cannot update itself.",
        )

    git = GitService.resolveGitExecutable()
    if not GitService(git).isGitAvailable():
        return UpdateResult(
            ok=False,
            message="Git was not found. Install Git, then try again.",
        )

    status = _run(
        folder,
        [git, "status", "--porcelain", "--untracked-files=no"],
        timeout=30,
    )
    if status.returncode != 0:
        detail = _firstLine(status.stderr or status.stdout)
        if detail:
            return UpdateResult(ok=False, message=f"Could not read Git status: {detail}")
        return UpdateResult(ok=False, message="Could not read Git status of this app.")
    if status.stdout.strip():
        return UpdateResult(
            ok=False,
            message="This copy of Git Syncher has local edits, so it was not updated.",
        )

    requirements = folder / "requirements.txt"
    before_hash = _fileHash(requirements)
    version_before = _readVersion(folder)

    # --no-rebase ignores a global pull.rebase setting so a divergence fails
    # instead of rewriting this checkout.
    pull = _run(folder, [git, "pull", "--ff-only", "--no-rebase"], timeout=120)
    if pull.returncode != 0:
        detail = _firstLine(pull.stderr or pull.stdout)
        if detail:
            return UpdateResult(ok=False, message=f"Could not download updates. {detail}")
        return UpdateResult(ok=False, message="Could not download updates.")

    updated = _pullUpdated(pull.stdout)
    version_after = _readVersion(folder)
    reinstalled = False
    if before_hash != _fileHash(requirements):
        python = consolePython(folder)
        if python is None:
            return UpdateResult(
                ok=False,
                message=(
                    "Dependencies changed, but the virtual environment was not found. "
                    "Run the installer again."
                ),
                updated=updated,
                version_before=version_before,
                version_after=version_after,
            )
        pip = _run(
            folder,
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--index-url",
                _PYPI_INDEX,
                "-r",
                "requirements.txt",
            ],
            timeout=300,
            extra_env=_pipEnv(),
        )
        if pip.returncode != 0:
            detail = _firstLine(pip.stderr or pip.stdout)
            if detail:
                return UpdateResult(
                    ok=False,
                    message=f"Could not install dependencies. {detail}",
                    updated=updated,
                    version_before=version_before,
                    version_after=version_after,
                )
            return UpdateResult(
                ok=False,
                message="Could not install dependencies.",
                updated=updated,
                version_before=version_before,
                version_after=version_after,
            )
        reinstalled = True

    shortcut = installShortcuts(folder)
    shortcut_message = ""
    if not shortcut.ok and not shortcut.skipped:
        shortcut_message = f"The menu icon was not refreshed: {shortcut.message}"

    return UpdateResult(
        ok=True,
        message=_message(
            updated,
            version_before,
            version_after,
            reinstalled,
            shortcut_message,
        ),
        updated=updated,
        version_before=version_before,
        version_after=version_after,
    )
