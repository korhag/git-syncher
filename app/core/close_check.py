from __future__ import annotations

from app.models.project import ProjectConfig, ProjectStatus

_MAX_NAMES = 8


# ------------------------------------------------------------
# Function: unsyncedProjectNames
# Purpose: Names of saved projects whose latest status is not
#          in sync with Git (used before allowing window close).
# ------------------------------------------------------------
def unsyncedProjectNames(
    projects: list[ProjectConfig],
    statuses: dict[str, ProjectStatus],
) -> list[str]:
    names: list[str] = []
    for project in projects:
        status = statuses.get(project.id)
        if status is None or not status.needsSync():
            continue
        names.append(project.name or project.path or project.id)
    return names


# ------------------------------------------------------------
# Function: closeWarningMessage
# Purpose: Warning copy listing unsynced repos before close.
# ------------------------------------------------------------
def closeWarningMessage(names: list[str]) -> str:
    count = len(names)
    noun = "repository" if count == 1 else "repositories"
    verb = "is" if count == 1 else "are"
    shown = names[:_MAX_NAMES]
    extra = count - len(shown)
    bullets = "\n".join(f"• {name}" for name in shown)
    if extra > 0:
        bullets += f"\n• and {extra} more"
    return (
        f"{count} {noun} {verb} not in sync with Git:\n\n"
        f"{bullets}\n\n"
        "Do you still want to close? Stay and sync to keep working."
    )
