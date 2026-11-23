from AppKit import NSPasteboard
import time

pb = NSPasteboard.generalPasteboard()

last_count = pb.changeCount()

print("========================================")
print("      STASH CLIPBOARD WATCHER")
print("========================================")
print("Current change count:", last_count)
print("")
print("Now:")
print("1. Open Finder")
print("2. Select the VIDEO FILE")
print("3. Press CMD+C")
print("4. Come back here")
print("")
print("Waiting for clipboard change...")
print("========================================")

while True:
    count = pb.changeCount()

    if count != last_count:
        print("\n🔥 CLIPBOARD CHANGED!")
        print("Old:", last_count)
        print("New:", count)

        print("\nPasteboard types:")

        types = pb.types()

        if types:
            for t in types:
                print(" -", t)

        print("\nFile URL:")

        value = pb.stringForType_("public.file-url")
        print(value if value else "NOT FOUND")

        print("\nFilename list:")

        files = pb.propertyListForType_("NSFilenamesPboardType")
        print(files if files else "NOT FOUND")

        print("\n========================================")

        last_count = count

    time.sleep(0.2)
