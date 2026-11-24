# ------------------------------------------------------------
# Module: app.__main__
# Purpose: Allow `python -m app` as an alternate entrypoint.
# ------------------------------------------------------------
from app.main import launchApp

if __name__ == "__main__":
    launchApp()
