# Changelog

All notable changes to Git Syncher will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.5.0] - 2026-08-17

### Added

- Add/Edit project: **Refresh** next to Default branch loads real branch names from the Git remote (using the URL and PAT you entered) so you can pick instead of guessing `main`

### Changed

- New projects no longer prefill Default branch as `main`; click refresh to load branches from Git

## [1.4.0] - 2026-08-17

### Changed

- Status compares this computer to Git’s **default branch** (`origin/HEAD`), not only `origin/<current branch>`
- Globe opens the remote at `/tree/<branch>` so the browser matches the branch on the card
- **Make this computer match Git** resets to the remote **default** branch first (e.g. `origin/main`)

### Fixed

- No longer reports **Synced** when on `master` matching `origin/master` while GitHub’s default (`main`) has different commits
- Missing `origin/<current branch>` no longer looks like a clean sync (suggests Resolve instead)

## [1.3.0] - 2026-08-17

### Added

- Project detail shows **This computer** Changelog version, **Git (latest commit)** Changelog version, and **Git tag** side by side
- Globe icon next to the folder icon to open the Git remote in the browser
- Changelog rule: every change ships as a dated version (no Unreleased holding pen)

### Fixed

- Git command output is decoded as UTF-8 on Windows (no more crash when Changelog has special characters)

## [1.2.0] - 2026-08-17

### Added

- Cursor rule requiring Changelog updates with every meaningful change
- Open project folder in Explorer / Finder from the dashboard card and project detail
- Restart button on the dashboard (relaunches via `run.bat` / `run.sh`, then exits)

### Changed

- Dashboard project rows are denser (two-line layout: name/branch/actions, then path/status)

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
