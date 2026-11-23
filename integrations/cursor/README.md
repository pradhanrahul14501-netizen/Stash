# Stash for Cursor

This read-only Cursor plug-in lets Cursor list recent Stash items, search saved text when asked, and find local media files. It does not upload, edit, or delete anything.

## Install

1. Copy this whole `cursor` folder into `~/.cursor/plugins/local/copy-maker`.
2. Restart Cursor or run **Developer: Reload Window**.
3. Open Cursor's **Customize** page and enable **Stash Library**.

The MCP server uses Python 3 and the standard library only. By default it looks for `~/copy-maker`. If Stash is installed elsewhere, set `COPY_MAKER_HOME` in Cursor's MCP configuration to that folder.

## What Cursor can read

- Item names and metadata from `storage/clipboard.json`.
- Saved text only when Cursor calls the search or get-text tool.
- File names and local paths under `storage/media`, `storage/videos`, and `storage/integrations/cursor`.

Cursor receives any text returned by a tool call. Use the tools only for content you want available in your Cursor conversation. Cloud files are not read automatically; in Stash Settings, choose **Add to app folder → Cursor** for a file you want Cursor to find.

## App-specific integrations

Cursor supports plug-ins that package MCP servers. CapCut's general desktop plug-in route is not documented for this use, so Stash uses a media import folder there. DaVinci Resolve uses the included menu script under `../davinci/CopyMakerImport.py`.
