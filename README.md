# Git Syncher

A cross-platform desktop app to track many local Git projects from one place:
add folders, store per-project credentials in an encrypted vault, refresh all
statuses with one button, and resolve push/pull problems with guided choices
instead of raw Git error messages.

## Requirements

- Python 3.11+ (install will refuse 3.9/3.10 — those can only get Flet 0.28, which cannot start this app)
- [Git](https://git-scm.com/) installed and available on your `PATH`

On Raspberry Pi OS Bullseye / Debian 11 the system Python is 3.9. `./install.sh` will download a local Python 3.12 with [uv](https://docs.astral.sh/uv/) if needed, and install Flet from PyPI (not piwheels).

## Install (once)

**Windows** — double-click or from a terminal:

```bat
install.bat
```

**macOS / Linux:**

```bash
chmod +x install.sh run.sh   # once
./install.sh
```

This checks for Python (and warns if Git is missing), creates `.venv`, upgrades pip, and installs dependencies.

## Run

**Windows:**

```bat
run.bat
```

**macOS / Linux:**

```bash
./run.sh
```

If `.venv` is missing or was created with Python 3.9 / old Flet, `run` will call the install script first.

## First launch

1. Create a **master password** — it encrypts your PATs and project settings on this machine (`data/vault.enc`).
2. Click **Add project**, pick a folder, and fill remote URL / username / email / PAT.
3. Use **Refresh** on the dashboard to check every project against Git.
4. Open a project for commit, pull, push, per-file compare, or discard.

Destructive actions (discard local changes, overwrite remote) always ask for an extra confirmation.

## Security notes

- The vault file is gitignored. Never commit `data/vault.enc`.
- PATs are injected at HTTPS time via a temporary askpass helper — they are not written into `.git/config`.
- `user.name` / `user.email` are set with `git config --local` only for that repo.

## Changelog-aware commits

If a project has `CHANGELOG.md` / `Changelog.md` / `changelog.md`, the commit
dialog suggests a message from the newest version heading (Keep a Changelog or
simple `## v1.2.3` styles).

## Tests

```bash
pytest
```

## Uploading this app to Git

This repository is ready to push: source only, no secrets. Add it as a Syncher
project like any other folder once a remote exists.
