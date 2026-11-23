# STASH security notes

## Keep private data private

STASH stores copied text, media, account data, and Firebase configuration under `storage/`. Keep that folder and `.backups/` on your Mac. They are excluded from Git by `.gitignore`, and the storage folder is restricted to your macOS account.

Never publish a Firebase service-account JSON file, the Stash databases, `clipboard.json`, or copied media. The Firebase web API key in the browser configuration is intended to be public; the service-account private key is not. If a service-account key has ever been uploaded, committed, or shared, revoke it in Google Cloud IAM and create a replacement before using the app again.

## Public access

The local owner app is designed for one person on the Mac that runs it. Direct public internet requests are rejected. The phone and laptop links use HTTP on the private Wi-Fi network, so use them only on a trusted network. For remote access, place Stash behind an HTTPS reverse proxy and set `COPY_MAKER_TRUSTED_PROXY_IPS` to the proxy's exact peer IP (or narrow CIDR). The proxy must overwrite `X-Forwarded-Proto` with the browser-facing scheme and set `X-Forwarded-Host`; Stash rejects proxy requests that are not HTTPS. Do not expose the Flask port directly or trust a broad network range. Firebase Authorized Domains only permits authentication and does not restrict who can reach the site. For a multi-user service, use the shared app behind a production WSGI server and leave Firebase Storage private. Shared Stash account registration is closed by default; set `COPY_MAKER_SHARED_REGISTRATION_OPEN=1` only while you want new accounts to register. Existing accounts can still sign in when registration is closed. Keep the temporary Quick Tunnel for short tests only.

For a multi-account hosted Stash, use `shared_app.py` and configure the host, HTTPS, and Firebase Storage deliberately. Keep the Firebase bucket private and grant the service account only the permissions the app needs.

After changing security code, stop and restart Stash so the running process loads it. Reconnect the local browser extension with a fresh one-time code from Settings.

## Local library protection

The local library index, folder names, and copied media are encrypted with AES-GCM. The encryption key is stored in the macOS Keychain and is never written into the Stash storage folder. Existing local files are encrypted the next time the app starts after this protection is installed. Encrypted backups contain a copy of the library key protected by the backup password; keep the backup and password separately. Restore is staged and applied only after restarting Stash, and it revokes browser sessions and extension tokens. A forgotten backup password cannot be recovered. This migration cannot rewrite old backups, Time Machine snapshots, or copies you exported elsewhere; those may still contain plaintext. Viewing media or sending a file to another app briefly creates a private temporary copy for the receiving app; Stash removes clipboard exports after 20 minutes and integration handoff copies after one hour.

Browser sessions expire after 12 hours without use and 14 days total. A signed-in owner can review and revoke browser sessions and local extension access in Settings. Optional authenticator-based two-step verification applies to both password and connected sign-in. Recovery codes are shown once, stored as hashes, and each can be used once. Login, pairing, and verification attempts are rate-limited.

Sensitive text detection is heuristic. Text matching a known-sensitive pattern while the Vault is locked is discarded instead of written to the ordinary library, but detection can miss secrets. Use the Vault or pause capture before copying sensitive material. Settings also supports app bundle ID and website-domain exclusions. App exclusion is best-effort because Stash observes the foreground app when polling the clipboard; it may not be the app that originally placed the item. Site exclusions apply to browser captures that include their page URL. Pause capture for stronger protection. These controls apply to the configured Stash service; shared mode must be configured and reviewed separately.

## Browser extension

Connect the local extension using the one-time code in Stash Settings. A code expires after ten minutes and can be used once. Creating a new local code replaces the prior local extension token. Use HTTPS and the pairing flow for a hosted Stash address. The extension injects only after the user clicks its button or right-click action, requests optional host access one website at a time, and asks the user to confirm the selected Stash destination before saving. It does not inject in every frame or on every page.

## Reporting a vulnerability

Please do not post exploitable details, credentials, or private user data in a public issue. When this repository is hosted on GitHub with private vulnerability reporting enabled, use the repository's **Security → Report a vulnerability** option. Otherwise, contact the repository maintainer privately. Include the affected version or commit, the setup, steps to reproduce, and the impact. Redact tokens, account identifiers, and personal file paths.
