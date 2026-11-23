# Shared Stash setup

This project has two libraries:

- **Mac Stash** is the existing library saved on this Mac. It remains the default when you run `main.py`.
- **Shared Stash** is a separate cloud library for the website, phones, and paired Chrome extensions. Existing Mac library items do not sync into it automatically.

New captures sent by a paired Chrome extension, shared from Android, or uploaded from a phone are saved in that user's Shared Stash account. A verified email or phone identity gets its own workspace. Signing in later with the same Firebase identity returns to that workspace; signing in with a different identity starts a new, empty one.

## Hosting Shared Stash

The Mac server listens only on `127.0.0.1:5050`; it is not reachable from a phone or another computer. To use Stash away from this Mac, deploy the shared web app at a public HTTPS address. No public address is configured in this project yet.

The hosting entry point is `shared_app:app`. It serves only the shared website and does not start the Mac clipboard watcher or AVA model. Use a persistent disk for the project's `storage/` folder and run one app instance because Shared Stash stores its account and library index in SQLite.

1. Create a public HTTPS address for the app, such as `https://stash.example.com`.
2. Install the shared server dependencies from `requirements-shared.txt`.
3. Configure these environment values on the server:

~~~text
COPY_MAKER_SHARED_MODE=1
COPY_MAKER_SHARED_REGISTRATION_OPEN=1
COPY_MAKER_COOKIE_SECURE=1
COPY_MAKER_SECRET_KEY=<long random secret>
~~~

4. Enable **Email/Password** and **Phone** in Firebase Authentication and add the website hostname to **Authorized domains** as described in `FIREBASE_AUTH_SETUP.md`. Set up the Firebase service account and private Firebase Storage bucket described in `FIREBASE_STORAGE_SETUP.md`. The bucket must remain private. Firebase Storage may require a billing plan; its charges are separate from Stash's per-account upload limit.
5. Run `gunicorn --workers 1 --threads 4 --bind 0.0.0.0:$PORT shared_app:app` behind the host's HTTPS proxy. The proxy should forward the original host and HTTPS scheme and allow request bodies up to the 2 GB Stash limit.
6. Keep the server's `storage/` folder on persistent disk. Do not commit the Firebase service-account key or expose the Flask development server directly.

When Shared Stash is running at the HTTPS address, the site root opens the shared library. Each account has its own account ID, library records, and Firebase Storage path. The server creates the app workspace only after Firebase verifies the email or SMS sign-in. Registration is closed by default; set `COPY_MAKER_SHARED_REGISTRATION_OPEN=1` only while you want new signups, then remove it or set it to `0` while allowing existing accounts to sign in.

## Temporary phone test from this Mac

For a short test before creating a cloud host or Firebase Storage bucket, set `COPY_MAKER_SHARED_LOCAL_STORAGE=1` along with the shared-mode and secure-cookie settings. Uploaded media is saved under `storage/shared_media/` on this Mac, with a 2 GB per-account limit. Multiple accounts can be created; each account's media is kept under its own storage key.

Run the shared app on port `5051`, then start a Cloudflare Quick Tunnel pointing to `http://localhost:5051`. The Quick Tunnel provides a temporary public HTTPS address. Keep the Mac awake and both processes running; the address changes when the tunnel is restarted. Anyone with the address can reach the sign-in page, so share it carefully. This is for trying the phone workflow; it is not permanent hosting.

## Connect Chrome on each laptop or PC

1. In Chrome, open `chrome://extensions`.
2. Enable **Developer mode**.
3. Choose **Load unpacked** and select this project's `browser-extension` folder.
4. Open the hosted Stash website, sign in, and choose **Create pairing code**.
5. Open the Stash extension, enter the HTTPS website address, paste the code, and select **Connect Stash**.

The code expires after 10 minutes and works once. Repeat the pairing on each Chrome installation. Copies from the extension go to the signed-in Shared Stash account.

## Use Stash on Android

1. Open the hosted HTTPS website in Chrome and sign in.
2. In Chrome's menu, choose **Add to Home screen** or **Install app**.
3. From a media app, use **Share** and choose Stash. Shared video, audio, and image files are uploaded to the account. If the app shares only a web page address, Stash saves that address as a link; it does not download the video from the page.

## Use Stash on iPhone

Open the hosted website in Safari and sign in. Choose **Add from your phone → Choose file** to save a video from Photos or Files. To keep a page address, use Safari's Share menu to copy the link, paste it into **Save a video page link**, and tap **Save link**. A saved page link is not a copy of the video.

The iPhone web app cannot receive items directly in the system Share menu. Saving the video itself requires selecting the media file in Photos or Files. Capturing the video directly from a mobile webpage would need a site-specific downloader or an iOS app/shortcut integration.

## Shared storage setup

Shared Stash uploads media to the Firebase bucket. If the website shows **Cloud storage needs setup**, follow `FIREBASE_STORAGE_SETUP.md` and restart the hosted app. The 2 GB per-account upload limit is not a cap on Firebase billing.
