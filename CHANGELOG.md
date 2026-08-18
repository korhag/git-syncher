# Changelog

All notable changes to Git Syncher will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.12.0] - 2026-08-18

### Changed

- Add/Edit project dialog is larger, fields align in one column, and **Account picker** is at the top (fills Git username and email)

## [1.11.5] - 2026-08-18

### Fixed

- Saving a Git account closes the Add/Edit form (the success toast no longer keeps that dialog open)
- Refresh and other Git work no longer flash command-prompt windows on Windows

## [1.11.4] - 2026-08-18

### Fixed

- Unlock vault accepts typing and clicks again (version footer no longer covers the form)
- A second launch no longer starts another Flet window that froze the first Unlock screen

## [1.11.3] - 2026-08-18

### Fixed

- Unlock no longer freezes after Restart (new instance launches with pythonw, not CREATE_NO_WINDOW)
- Restart / run.bat no longer leave an empty command prompt open

## [1.11.2] - 2026-08-18

### Added

- Unlock screen footer shows the app version (e.g. v1.11.2)

### Fixed

- Restart no longer leaves the old window open or opens an extra command prompt

## [1.11.1] - 2026-08-18

### Fixed

- Restart closes the current window after launching the new instance (no leftover dialog or old process)

## [1.11.0] - 2026-08-18

### Added

- Saved **Git accounts** in the vault (label, username, email) — manage them from the dashboard **Accounts** button
- **Git account** picker in Add/Edit project autofills username and email from a saved identity

## [1.10.1] - 2026-08-18

### Added

- Dashboard footer shows the current app version (e.g. v1.10.1)

## [1.10.0] - 2026-08-17

### Added

- Empty Git remotes (no branches yet) can be added using **main** / **master** (or Git’s `init.defaultBranch`) for the first push

### Changed

- Refreshing branches on an empty remote offers default names instead of blocking with “No branches found”
- Saving a project no longer requires picking a branch first — it falls back to the local branch or **main**

### Fixed

- Checkout no longer fails when `origin/<branch>` does not exist yet — local branch is prepared so Push can create it

## [1.9.0] - 2026-08-17

### Added

- Dashboard cards have **Edit** and **Remove** so you can fix or drop a project without opening it
- Loading overlay with spinner while Refresh, Save, Pull, Push, and other Git work runs
- Vault uniqueness: the same folder + default branch cannot be added twice

### Changed

- Opening a project paints the detail screen first, then loads Git status in the background
- Unlock collapses existing duplicate folder+branch entries automatically (keeps the first)

### Fixed

- Extra clicks on Save could add the same project multiple times before Git finished

## [1.8.0] - 2026-08-17

### Changed

- Merge dialogs spell out **after merge** and **after push**: which branch keeps which Changelog version (`v…`), that GitHub `main` can stay old until you update it, and that the card’s Git line is the website default
- Confirm screens repeat the same After table so ① / ② / Match / Overwrite are not just direction labels

## [1.7.4] - 2026-08-17

### Added

- Only one Git Syncher window at a time — a second launch shows “Already running” and exits
- Restart releases the instance lock before starting a new process so the new window can open

## [1.7.3] - 2026-08-17

### Changed

- Merge dialogs spell out **Now** (this computer vs Git, branch + version), what merges into what, and the **After** result (which branch you stay on, what Git gets)
- Confirms repeat the same short After / Git online lines so the direction is clear before you run it

## [1.7.2] - 2026-08-17

### Added

- Unlock screen **Start over** when the vault is empty or damaged — removes the broken file and lets you create a new vault (keeps `vault.enc.bak` if present)
- Damaged vault is detected on open (before Unlock), so recovery buttons show immediately

## [1.7.1] - 2026-08-17

### Added

- Vault saves write to a temp file then replace atomically, and keep `data/vault.enc.bak`
- Unlock screen **Restore backup** when the vault is empty/damaged and a backup exists

### Fixed

- Empty or truncated `vault.enc` (e.g. after a crash mid-save) no longer shows a cryptic JSON error — clear recovery message instead

## [1.7.0] - 2026-08-17

### Added

- Dashboard cards show **This computer** vs **Git** on two lines when they differ (branch + Changelog version)
- **Merge** action with direction picker: bring Git into this computer, or send this computer into Git (real `git merge`, then push when sending)
- Merge conflicts open the existing file-by-file resolve path (no auto-resolve)

### Changed

- When histories diverge, the suggested chip is **Merge** instead of only Resolve; overwrite / match-Git remain as destructive options in the same dialog

## [1.6.0] - 2026-08-17

### Added

- Saving a Default branch in Edit project **checks out** that branch (from `origin/<name>`) so picking **main** actually switches this computer off **master**

### Changed

- Overwrite remote (force push) also updates Git’s **default** branch when it differs from the current branch (so the website matches this computer)
- Resolve / overwrite confirmations name **master** vs **main** when those differ

### Fixed

- Refresh no longer overwrites the saved Default branch with whatever branch the folder happens to be on

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
