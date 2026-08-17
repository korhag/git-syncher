# Changelog

All notable changes to Git Syncher will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.1.0] - 2026-08-17

### Added

- Plain-English status lines (this computer vs Git) instead of arrows / “ahead of tag”
- Pull uses the branch you are on; missing remote-ref dialog with a **Pull current branch** next step
- When there is no Changelog version: suggest next version from the latest Git tag on Commit and Push
- Push dialog option to **Push and tag** with an editable suggested version
- **Make this computer match Git** — fetch + hard-reset to origin + clean (remote unchanged)
- `install.bat` / `install.sh` and `run.bat` / `run.sh` for setup and launch

### Changed

- Unrelated-histories and Resolve dialogs lead with match-Git, not force-push only
- Destructive actions still require an explicit confirmation checkbox

### Fixed

- Pull no longer prefers a stale stored `main` when the current branch is `master`
- Missing remote ref is no longer a generic Retry / Cancel dead end

## [1.0.0] - 2026-08-17

### Added

- Encrypted vault for projects and PATs (master password)
- Add / edit projects with remote, identity, and PAT
- Dashboard Refresh for all projects
- Guided push / pull / commit with choice dialogs instead of raw Git errors
- Per-file compare and discard
- Changelog.md version suggestion on commit
