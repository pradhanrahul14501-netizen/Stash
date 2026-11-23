from AppKit import NSPasteboard, NSWorkspace
from Foundation import NSURL
from PIL import Image
from io import BytesIO
import os


def get_frontmost_app_bundle_id():
    """Read the foreground app identifier for a best-effort capture exclusion."""
    try:
        application = NSWorkspace.sharedWorkspace().frontmostApplication()
        bundle_id = application.bundleIdentifier() if application else None
        return str(bundle_id) if bundle_id else None
    except Exception:
        return None


def get_clipboard_content():

    pasteboard = NSPasteboard.generalPasteboard()

    if pasteboard is None:
        return None

    change_count = pasteboard.changeCount()

    # --------------------------------
    # TEXT
    # --------------------------------
    text = pasteboard.stringForType_("public.utf8-plain-text")

    # Don't immediately return.
    # The clipboard may contain both text and a file reference.

    # --------------------------------
    # FILE REFERENCES
    # --------------------------------
    files = []

    # Modern macOS apps expose copied files as NSURL objects using
    # NSPasteboard's file URL representation.
    try:
        file_url_objects = pasteboard.readObjectsForClasses_options_(
            [NSURL],
            None
        ) or []

        for file_url in file_url_objects:

            if file_url.isFileURL():
                path = str(file_url.path())

                if os.path.isfile(path) and path not in files:
                    files.append(path)

    except Exception:
        # Keep compatibility with pasteboards that only expose the
        # older NSFilenamesPboardType property list.
        pass

    legacy_file_urls = pasteboard.propertyListForType_(
        "NSFilenamesPboardType"
    ) or []

    for path in legacy_file_urls:

        if os.path.isfile(path) and path not in files:
            files.append(path)

    if files:

        return {
            "type": "file",
            "files": files,
            "change_count": change_count
        }

    # --------------------------------
    # IMAGE
    # --------------------------------
    image_types = [
        "public.png",
        "public.tiff",
        "public.jpeg"
    ]

    for image_type in image_types:

        image_data = pasteboard.dataForType_(image_type)

        if image_data:

            image_bytes = bytes(image_data)

            try:

                image = Image.open(
                    BytesIO(image_bytes)
                )

                return {
                    "type": "image",
                    "content": image,
                    "raw_bytes": image_bytes,
                    "format": image.format,
                    "change_count": change_count
                }

            except Exception:
                pass

    # --------------------------------
    # AUDIO BYTES
    # --------------------------------
    audio_types = [
        "public.audio",
        "public.mpeg-4-audio",
        "public.mp3",
        "com.apple.m4a-audio",
        "public.wav"
    ]

    for audio_type in audio_types:

        audio_data = pasteboard.dataForType_(audio_type)

        if audio_data:

            audio_bytes = bytes(audio_data)

            return {
                "type": "audio",
                "raw_bytes": audio_bytes,
                "format": audio_type,
                "change_count": change_count
            }

    # --------------------------------
    # NORMAL TEXT
    # --------------------------------
    if text:

        return {
            "type": "text",
            "content": text,
            "change_count": change_count
        }

    return None


def get_clipboard_change_count():

    pasteboard = NSPasteboard.generalPasteboard()

    if pasteboard is None:
        return None

    return int(pasteboard.changeCount())


def set_file_on_system_clipboard(file_path, expected_change_count):

    pasteboard = NSPasteboard.generalPasteboard()

    if pasteboard is None:
        print(
            "⚠️ Video clipboard handoff failed: "
            "macOS returned no general pasteboard."
        )
        return False, None

    if expected_change_count is None:
        print(
            "⚠️ Video clipboard handoff failed: "
            "no clipboard snapshot was recorded before capture."
        )
        return False, None

    try:
        expected_change_count = int(expected_change_count)
    except (TypeError, ValueError):
        print(
            "⚠️ Video clipboard handoff failed: "
            "the clipboard snapshot was invalid."
        )
        return False, None

    current_change_count = int(pasteboard.changeCount())

    if current_change_count != expected_change_count:
        print(
            "⚠️ Video clipboard handoff skipped: "
            "the macOS clipboard changed during video capture."
        )
        return False, None

    if not os.path.isfile(file_path):
        print(
            "⚠️ Video clipboard handoff failed: "
            "the saved video file could not be found."
        )
        return False, None

    try:
        file_url = NSURL.fileURLWithPath_(os.path.abspath(file_path))

        pasteboard.clearContents()

        if not pasteboard.writeObjects_([file_url]):
            print(
                "⚠️ Video clipboard handoff failed: "
                "macOS rejected the video file URL."
            )
            return False, None

    except Exception as error:
        print(
            "⚠️ Video clipboard handoff failed while writing to macOS: "
            + str(error)
        )
        return False, None

    return True, int(pasteboard.changeCount())
