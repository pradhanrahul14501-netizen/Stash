from AppKit import NSPasteboard

pb = NSPasteboard.generalPasteboard()

print("\n========================================")
print("        STASH VIDEO PROBE")
print("========================================")

print("\nChange count:")
print(pb.changeCount())

print("\nPasteboard types:")
types = pb.types()

if not types:
    print("No types found")
else:
    for t in types:
        print(" -", t)

print("\n----------------------------------------")
print("IMPORTANT FILE / URL REPRESENTATIONS")
print("----------------------------------------")

check_types = [
    "public.file-url",
    "public.url",
    "NSURLPboardType",
    "NSFilenamesPboardType",
    "com.apple.pasteboard.promised-file-url",
    "com.apple.pasteboard.promised-file-content-type"
]

for t in check_types:
    print(f"\n[{t}]")

    try:
        value = pb.propertyListForType_(t)

        if value:
            print("propertyList:", value)
        else:
            value = pb.stringForType_(t)

            if value:
                print("string:", value)
            else:
                print("NOT FOUND")

    except Exception as e:
        print("ERROR:", e)

print("\n========================================")
