# Stash browser extension permissions

- `activeTab`: temporary access to the current browser tab after the user clicks the Stash toolbar button or its context-menu action.
- `scripting`: inject `content.js` into the current top-level tab after that explicit action; no all-frame injection is configured.
- `host_permissions` (`http://127.0.0.1:5050/*`): connect automatically to Stash running on this Mac. Copies remain local.
- `optional_host_permissions` (`http://*/*`, `https://*/*`): request the remote Stash host only when the user connects a remote server in Advanced with its one-time pairing code and consent. No source-site permission step is needed; `activeTab` is used for the current tab after the user opens the extension.
- `contextMenus`: create the user-invoked “Copy with Stash” and audio menu actions.
- `downloads`: receive an audio/video file after the user explicitly chooses a Stash capture action and the source supports it.
- `storage`: retain the remote Stash address, paired access token, and the user's remote destination consent in Chrome's extension storage. The local token is obtained automatically from Stash on this Mac.

The extension has no static content-script match list and does not run in all frames. The toolbar and right-click capture actions are user-initiated. It does not attempt to bypass DRM or access controls.
