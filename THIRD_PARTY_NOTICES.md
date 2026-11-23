# Third-party notices

This is an initial notice for identified components, not a complete inventory of every transitive dependency. Each dependency and downloaded model retains its own license and terms.

## Android video extraction

The Android app depends on io.github.junkfood02.youtubedl-android:library:0.18.1 and its FFmpeg module. The upstream project declares GPL-3.0: [youtubedl-android](https://github.com/yausername/youtubedl-android). FFmpeg and other native components may carry additional notices and license terms. Review the exact artifacts resolved by Gradle before redistributing an Android APK or App Bundle.

## QR code encoder

ui/qrcodegen.js is based on Project Nayuki's QR Code generator and an MIT-licensed implementation. The applicable notice is in [ui/QRCODE-LICENSE.txt](ui/QRCODE-LICENSE.txt).

## Downloaded Android model

The Android Ava screen identifies its optional Qwen3 0.6B INT4 model as Apache-2.0. Model files are downloaded at runtime and are not included in this source tree. Verify the exact model repository and its model card before redistributing weights or offering downloads.

## Other dependencies

Python, Android, browser, and model-serving dependencies are declared in the repository's requirements and Gradle files. Their own license notices remain in effect. Generate and review a full dependency notice bundle before distributing compiled releases; this file does not replace those notices.
