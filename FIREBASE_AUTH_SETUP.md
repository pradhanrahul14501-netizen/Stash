# Firebase Authentication for Stash

Shared Stash uses Firebase Authentication to give each verified email address or phone number a separate workspace. The Flask server verifies Firebase ID tokens using the Firebase Admin SDK. The Admin service-account key stays in `storage/` and is never sent to the browser. The original Mac-only Stash login can still use the configured Google, Apple, or phone providers.

## Set up the provider project

1. Create a Firebase project and register a Web app in it.
2. In Firebase Console, open **Authentication → Sign-in method** and enable **Email/Password** and **Phone**. Email accounts must verify their address before Stash creates their workspace. Phone sign-in verifies users with an SMS code and reCAPTCHA.
3. Under **Authentication → Settings → Authorized domains**, add the hostname serving Shared Stash (for example, `stash.example.com`, without `https://` or a path). A temporary `trycloudflare.com` hostname must be added again if Cloudflare gives you a different one.
4. For phone sign-in, configure the permitted SMS regions in Firebase Authentication settings. Phone sign-in requires an authorized HTTPS website; Firebase does not allow `localhost` for phone sign-in.
5. Apple sign-in is optional for the original Mac-only app. It requires an Apple Developer account, an HTTPS website, and an Apple Service ID/key configured in Firebase.
6. Open **Project settings → General → Your apps** and copy the Web app's API key, auth domain, project ID, app ID, and messaging sender ID.
7. In **Project settings → Service accounts**, generate a private key for the Firebase Admin SDK. Save it as `storage/firebase-admin.json` in this project. Keep this file private.

## Configure Stash

Copy `storage/firebase_auth_config.example.json` to `storage/firebase_auth_config.json`, then replace its sample values with the Web app values. Leave `service_account_path` as `firebase-admin.json` if that is where you saved the private key. Stash restricts both configuration and key file permissions when it starts.

For Shared Stash, install its server dependencies in the environment used to run `shared_app:app`:

```bash
python3 -m pip install -r requirements-shared.txt
```

For the original Mac-only owner login, use `requirements-auth.txt` in the environment used to run `main.py`.

Restart the shared Stash server after configuring Firebase. A new email account receives a verification email; after verifying it, the user signs in to create a workspace. A phone account receives an SMS code and creates a workspace after the code is confirmed. The same Firebase identity returns to its existing workspace; a different Firebase identity gets a new, empty workspace. Each account's library records and storage prefix are scoped to that account.

The public Firebase web configuration is included in the shared page so its browser can start sign-in. This configuration is designed to be public; the private Firebase Admin service-account key must never be put in a web page, a public repository, or a shared download.

## Access from another device

Sign-in on another device needs that device to open the same Stash server and a public hostname added to Firebase's Authorized domains. Phone sign-in also needs an allowed SMS region. Shared libraries live in the storage configured for the Shared Stash host; they do not sync with the separate Mac-only library.

Firebase reference pages: [Google sign-in](https://firebase.google.com/docs/auth/web/google-signin), [Apple sign-in](https://firebase.google.com/docs/auth/web/apple), [phone sign-in](https://firebase.google.com/docs/auth/web/phone-auth), and [server-side ID token verification](https://firebase.google.com/docs/auth/admin/verify-id-tokens).
