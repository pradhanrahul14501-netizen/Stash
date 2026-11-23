# Stash data flow and consent

## Local Stash

- Copied text and metadata are stored in the `storage/` library. The library index and managed media are encrypted with a key held in macOS Keychain. The key is not stored beside the library.
- The Vault is a separate, locally encrypted area for secrets. Secret detection is heuristic: it can miss passwords and can flag ordinary text. Treat it as a backup, not a guarantee.
- Finder access is read-only and only covers the folder the user selected. A file is not added to Stash unless the user chooses an import or save action.
- Ava sends prompts to the locally configured Ollama service at `127.0.0.1:11434`. Stash's Ava code does not send prompts to a hosted model. A separate network feature, if enabled, must disclose its destination before sending content.
- The browser extension stores its Stash address and pairing token in Chrome extension storage. It inspects a page only after the user clicks the extension or its right-click action.

## Shared Stash and cloud files

- Shared Stash stores account data and shared library items on the configured Stash server. Depending on server configuration, media is stored in its local shared-storage directory or Firebase Storage; account metadata is stored by the shared service.
- Connecting the browser extension requires a consent checkbox explaining which Stash address receives copies. A local `127.0.0.1` address keeps extension captures on this Mac; a hosted address sends chosen captures to that server.
- Google/Firebase connection and cloud-file upload are separate, user-initiated actions. Review the destination and item before uploading. Local and Shared Stash libraries are separate; signing in does not silently migrate the local encrypted library.
- If the configured remote server or Firebase is unavailable, shared operations fail; local library access remains a separate mode.

## Consent rule

Stash must not silently send copied text, media, Finder files, Vault entries, or Ava prompts off-device. Remote sharing requires an explicit connection/consent action and a separate save or upload action. Vault entries are never uploaded by ordinary library sync. If a future feature sends content to another service, add a destination-specific consent step before the first transfer and provide a way to disconnect it.

