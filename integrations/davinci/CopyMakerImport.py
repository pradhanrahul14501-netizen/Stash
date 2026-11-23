"""Import files from Stash's DaVinci handoff folder into the open Resolve project."""

import os


COPY_MAKER_HOME = os.path.expanduser(os.environ.get("COPY_MAKER_HOME", "~/copy-maker"))
IMPORT_DIR = os.path.join(
    os.environ.get("STASH_STORAGE_DIR", os.path.join(COPY_MAKER_HOME, "storage")),
    "integrations",
    "davinci",
)


def run():
    try:
        import DaVinciResolveScript as dvr_script
    except ImportError as error:
        raise RuntimeError(
            "Run this script from DaVinci Resolve's Scripts menu so its scripting API is available."
        ) from error

    resolve = dvr_script.scriptapp("Resolve")
    if not resolve:
        raise RuntimeError("DaVinci Resolve is not open.")

    manager = resolve.GetProjectManager()
    project = manager.GetCurrentProject() if manager else None
    if not project:
        raise RuntimeError("Open a DaVinci Resolve project first.")

    os.makedirs(IMPORT_DIR, exist_ok=True)
    media = [
        os.path.join(IMPORT_DIR, name)
        for name in sorted(os.listdir(IMPORT_DIR))
        if not name.startswith(".") and os.path.isfile(os.path.join(IMPORT_DIR, name))
    ]
    if not media:
        raise RuntimeError(
            f"The Stash import folder is empty. Add downloaded clips here: {IMPORT_DIR}"
        )

    imported = project.GetMediaPool().ImportMedia(media)
    resolve.OpenPage("media")
    count = len(imported or [])
    print(f"Stash: imported {count} file(s) from {IMPORT_DIR}")


if __name__ == "__main__":
    run()
