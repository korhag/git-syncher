from __future__ import annotations

import os
import platform
import re
import subprocess
import webbrowser
from pathlib import Path
from typing import Optional


# ------------------------------------------------------------
# Function: openFolderInExplorer
# Purpose: Open a folder in the OS file manager (Explorer / Finder / etc.).
# Input: folder_path (str | Path)
# Output: bool - True if the open command was started.
# ------------------------------------------------------------
def openFolderInExplorer(folder_path: str | Path) -> bool:
    path = Path(folder_path)
    if not path.is_dir():
        return False

    resolved = str(path.resolve())
    system = platform.system()
    try:
        if system == "Windows":
            os.startfile(resolved)  # type: ignore[attr-defined]
            return True
        if system == "Darwin":
            subprocess.Popen(["open", resolved])
            return True
        # Linux and other Unix-like
        subprocess.Popen(["xdg-open", resolved])
        return True
    except OSError:
        return False


# ------------------------------------------------------------
# Function: remoteUrlToBrowserUrl
# Purpose: Turn a Git remote (HTTPS or SSH) into a browser HTTPS URL.
# Input: remote_url (str) - e.g. git@github.com:org/repo.git
# Output: Optional[str] - https://… URL, or None if unknown.
# ------------------------------------------------------------
def remoteUrlToBrowserUrl(remote_url: str) -> Optional[str]:
    raw = (remote_url or "").strip()
    if not raw:
        return None

    # Already a browseable http(s) URL
    if re.match(r"^https?://", raw, re.IGNORECASE):
        url = re.sub(r"\.git$", "", raw, flags=re.IGNORECASE)
        return url

    # SSH: git@host:owner/repo.git  or  ssh://git@host/owner/repo.git
    ssh_scp = re.match(
        r"^git@(?P<host>[^:]+):(?P<path>.+)$",
        raw,
        re.IGNORECASE,
    )
    if ssh_scp:
        host = ssh_scp.group("host")
        path = re.sub(r"\.git$", "", ssh_scp.group("path"), flags=re.IGNORECASE)
        return f"https://{host}/{path}"

    ssh_uri = re.match(
        r"^ssh://(?:git@)?(?P<host>[^/]+)/(?P<path>.+)$",
        raw,
        re.IGNORECASE,
    )
    if ssh_uri:
        host = ssh_uri.group("host")
        path = re.sub(r"\.git$", "", ssh_uri.group("path"), flags=re.IGNORECASE)
        return f"https://{host}/{path}"

    return None


# ------------------------------------------------------------
# Function: openRemoteInBrowser
# Purpose: Open the Git remote repository page in the default browser.
# Input: remote_url (str)
# Output: bool - True if a browser open was attempted with a valid URL.
# ------------------------------------------------------------
def openRemoteInBrowser(remote_url: str) -> bool:
    url = remoteUrlToBrowserUrl(remote_url)
    if not url:
        return False
    try:
        webbrowser.open(url)
        return True
    except Exception:
        return False
