# Secret handling policy

- Automatic password, token, and financial-data detection is best-effort only. It is not a security boundary and cannot identify every secret.
- Keep sensitive material out of the ordinary clipboard history when possible. Save credentials in the Stash Vault or use **Pause all capture** before copying them.
- When a known-sensitive text pattern is detected while the Vault is locked, Stash discards that text instead of saving it in the ordinary library. A false negative can still occur.
- Do not store passwords, recovery codes, private keys, `.env` files, or service-account credentials in browser-extension settings, Ava prompts, shared mode, or ordinary clipboard history.
- App and site exclusions are additional safeguards. App exclusion uses the foreground macOS app identifier observed when the clipboard is checked; it can miss a source app if focus changes first. Site exclusion applies to the page URL submitted by the browser extension. Pause capture for stronger protection.
- Stash must not log clipboard contents, Vault values, access tokens, file contents, or encryption keys. Error logs should contain only safe status and error categories.
- Decrypted handoff copies exist temporarily so another app can open them. Stash deletes these files on expiry or startup cleanup; users should close the receiving app when done.

