# Stash

Stash is a local-first clipboard and file library for macOS, with an Android companion. Save copied text, links, media, and files, then search and organize them later. Ava runs locally for desktop tasks and previews file actions for approval.

## What is included

- An encrypted local library, folders, tags, favorites, and a restorable Bin.
- A local Vault for sensitive entries, with biometric unlock on Android.
- Ava search and file organization with previews before desktop file changes.
- A browser extension that saves only after the user invokes it and chooses where an item goes.
- Optional Shared Stash accounts for library sync, configured separately from the local library.
- Android capture, local reminders, phone cleanup previews, and private-Wi-Fi pairing with desktop Stash.

Stash is an early beta. The desktop app currently targets macOS and uses macOS Keychain, Finder, and clipboard APIs. Shared Stash is an optional server deployment. Read [SECURITY.md](SECURITY.md) before enabling remote access or connecting a hosted server.

## Start the macOS app

Requirements and setup details are in [QUICKSTART.md](QUICKSTART.md). On a supported Mac, from the repository root:

```sh
./scripts/stash
```

Keep the terminal open and visit <http://127.0.0.1:5050>. Desktop Ava requires a local Ollama service. Optional hosted features have separate setup guides: [Shared Stash](SHARED_STASH_SETUP.md), [Firebase authentication](FIREBASE_AUTH_SETUP.md), and [Firebase Storage](FIREBASE_STORAGE_SETUP.md).

## Build Android

Install Android Studio and its Android SDK, then run:

```sh
cd android
./gradlew :app:assembleDebug
```

See [android/README.md](android/README.md) for tests, backup behavior, and release notes. The Android video extractor and bundled native components have separate licensing terms; review them before distributing Android builds.

## Privacy and safety

- Local library data is encrypted using a key stored in macOS Keychain.
- Finder access is limited to the folder the user selects.
- Ava file changes require reviewing a preview and confirming it.
- Phone pairing and desktop file-action approvals use a one-time code on private Wi-Fi.
- Bin review dates send reminders. They do not delete items automatically.
- Shared Stash and cloud storage are opt-in and remain separate from the local library.

See [DATA-FLOW.md](DATA-FLOW.md), [DATA-CONTRACT.md](DATA-CONTRACT.md), [SECRET-HANDLING.md](SECRET-HANDLING.md), and [SECURITY.md](SECURITY.md) for details and limitations.

## License

Stash's original source code is licensed under GNU GPL version 3; see [LICENSE](LICENSE). Third-party libraries, downloaded models, and platform components keep their own licenses and terms. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the components identified so far. Review those terms before distributing a build.
