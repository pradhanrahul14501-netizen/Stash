# Local and shared data contract

| Mode | Where data lives | Authentication | Offline behavior | Mode switching |
|---|---|---|---|---|
| Local Stash | Encrypted local library under `storage/`; media protected with the local Keychain key | Local Stash account/session on this Mac | Library remains local; local Ava requires the local Ollama service | Enabling Shared Stash does not move or merge the local library |
| Shared Stash | Shared service database plus configured local shared storage or Firebase Storage | Shared account and extension access token | Remote saves/search fail while the configured service is unavailable | Shared data stays separate; switching back to Local opens the local library |

The beta support declaration is macOS only. Local Stash depends on AppKit, macOS Keychain, Finder, and the Mac system clipboard; no Windows or Linux compatibility is promised. Shared Stash is a separately configured server deployment and does not make the local desktop app cross-platform.

Treat a successful API response as confirmation that the selected mode accepted the item. If remote storage is unavailable, return an error and keep the source item unchanged. Do not silently fall back to another account, storage location, or mode. A future migration between modes must be an explicit export/import operation with a count and confirmation.
