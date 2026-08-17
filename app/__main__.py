# ------------------------------------------------------------
# Module: app.__main__
# Purpose: Allow `python -m app` as an alternate entrypoint.
# ------------------------------------------------------------
from app.main import main
import flet as ft

if __name__ == "__main__":
    ft.run(main)
