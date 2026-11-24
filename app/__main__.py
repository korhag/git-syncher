# ------------------------------------------------------------
# Module: app.__main__
# Purpose: Allow `python -m app` as an alternate entrypoint.
# ------------------------------------------------------------
from app.main import main, runApp

if __name__ == "__main__":
    runApp(main)
