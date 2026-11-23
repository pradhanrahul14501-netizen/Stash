# Firebase Cloud Storage for Stash

Stash stores selected cloud uploads under the signed-in Firebase user's UID and checks the total against a 2 GB demo quota before accepting each upload. Files are not uploaded automatically. The app uses the existing Firebase Admin service account on this Mac; do not make the bucket public.

## Enable the Firebase bucket

1. Open the Firebase project `copymaker-89702` and choose **Storage** under **Databases & Storage**.
2. Select **Get started**, choose a bucket region, and keep the bucket private.
3. Complete the billing setup Firebase requires for Cloud Storage.
4. If Firebase shows a bucket name different from `copymaker-89702.firebasestorage.app`, add the shown name as `storage_bucket` in `storage/firebase_auth_config.json`.
5. Restart Stash. Open **Settings → Firebase cloud storage → Check storage**.

Firebase requires the pay-as-you-go Blaze plan to provision Cloud Storage buckets as of February 3, 2026. Linking billing can incur charges if project usage exceeds applicable no-cost quotas. Stash's 2 GB per-account upload limit is not a Google Cloud billing cap. Review Firebase pricing and billing before enabling the bucket.

## Account and privacy

- Cloud storage requires a Google identity linked to the Stash account.
- The user must choose each file in **Settings → Upload files**. Existing local media is not synced automatically.
- The backend stores objects below `users/<Firebase UID>/files/` and only exposes that user's objects through the authenticated Stash session.
- Do not set Storage rules to public access or share the Firebase Admin service-account key.
