# Stash for Android

## Build on this Mac

Android Studio's bundled JDK 25 is used by default, so a separate Java install is not needed.
Kotlin output is pinned to Java 17 bytecode for Android compatibility.
The SDK location can be overridden with `ANDROID_HOME`; the default is `~/Library/Android/sdk`.

```sh
cd android
./gradlew :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

Debug APKs are split by processor type under `app/build/outputs/apk/debug/`; choose the matching
ABI package (most current Android phones use `arm64-v8a`). Release APKs are split the same way.
For Play-style distribution, prefer the Android App Bundle, which allows stores to deliver only
the device's required processor libraries.

Run the Android KeyStore integration test on an attached device or running emulator with:

```sh
./gradlew :app:connectedDebugAndroidTest
```

## Encrypted backup and restore

Choose **More → Backup and restore** from Library. Backups include Library and Bin items, files,
and Vault entries. The archive is encrypted with AES-256-GCM and a password-derived key; use a
unique password with at least 12 characters and keep it somewhere safe. Stash cannot recover a
forgotten backup password. When restoring a backup with Vault enabled, choose a new Vault password:
the restored Vault is bound to the new device's Android KeyStore and does not reuse the old device key.
Restore is limited to an empty Stash installation to avoid overwriting existing data. This creates a portable backup. Cross-device sync is a separate opt-in feature through Shared Stash.

## Release build

Release builds enable code shrinking and resource shrinking. A Play-ready Android App Bundle can be
built with `./gradlew :app:bundleRelease`; without signing environment variables the bundle is
unsigned. Configure signing only in the release environment, never in a committed Gradle file:

- `STASH_RELEASE_STORE_FILE`
- `STASH_RELEASE_STORE_PASSWORD`
- `STASH_RELEASE_KEY_ALIAS`
- `STASH_RELEASE_KEY_PASSWORD`

The current CI workflow builds and tests an unsigned bundle. Before distributing any build, complete
the video extractor's GPL-3.0 and bundled-native-component license review below, verify the release
signing key and application privacy disclosures, and test the release build on supported devices.

## Video extractor license

The private prototype uses `youtubedl-android` 0.18.1 and its FFmpeg module. The wrapper project
is licensed under GPL-3.0. This prototype is not configured for Play Store distribution. Before
redistributing the app, review GPL-3.0 and the separate notices and licenses for bundled native
components with a qualified legal reviewer.

Only download videos that you own or are authorized to download. DRM-protected or otherwise
protected video is unsupported.
