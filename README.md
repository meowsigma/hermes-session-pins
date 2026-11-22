# ★ Hermes Session Pins

Keep important Hermes chats easy to find. Uses Hermes's native pins, with no
model calls, network requests, extra packages, or core patches.

## Install

Requires **Hermes 0.22.5+**. Install into the profile you use.

```sh
hermes plugins install meowsigma/hermes-session-pins --enable
hermes pins install-ui  # Optional in-chat Ink selector
```

For a named profile, prefix commands with `hermes -p work`.
The widget hot-loads; use `/widgets-reload` if it doesn't appear. No
background-service restart is required. Reopen a client if its command catalog
is stale.

## In chat

| Command | Action |
|---|---|
| `/pin` | Pin the current chat. |
| `/pin status` | Check whether the current chat is pinned, without changing it. |
| `/unpin` | Unpin the current chat. |
| `/pin My Project` | Pin by exact stored title or session ID. |
| `/unpin TITLE_OR_ID` | Unpin by the same rules. |
| `/pins` | Open the selector in Ink when the widget is installed. |
| `/pins list` | Outside Ink, list visible pins and resume commands; with the Ink widget loaded, open Pinned. |
| `/pins manage` | In Ink, open Pinned; outside Ink, choose a pin, then show its resume command or unpin it. |

Titles with spaces need no quotes in chat. Exact IDs take priority over exact,
case-sensitive titles, then unique case-sensitive ID prefixes. Ambiguous or
missing targets change nothing; use a full ID to disambiguate. `/pin status`
reserves the lowercase word `status`; pin a chat with that title by its ID.
A missing current chat or unavailable store reports an error, not “unpinned.”

### In-chat selector

Starts on **Pinned**. **Tab** toggles Pinned / All visible chats;
**←** selects Pinned and **→** selects All visible chats.
Type to search full stored titles and IDs.

| Key | Action |
|---|---|
| ↑ / ↓ | Select a chat. |
| Page Up / Down | Scroll the selection. |
| Enter | Copy `/resume ID` and close. **Paste + Enter in this chat to open it.** |
| Ctrl+P | Copy `/pin ID` or `/unpin ID` and close; paste + Enter to apply. |
| Ctrl+U | Clear search. |
| Ctrl+R | Reload chats. |
| Esc | Close without changing anything. |

Shows the stored model and last activity; it never changes models. Clipboard
support uses `wl-copy` (Wayland), `xclip` (X11), or `pbcopy` (macOS). Windows
clipboard support is not implemented. A clipboard error keeps the selector open.

Copying is not a direct session switch or pin change. Pasted commands use the
current profile and Hermes's normal selector rules. If the profile changes or
the chosen chat disappears, refresh and reselect before confirming. This plugin
does not alter the built-in `/resume` picker. Outside Ink, `/pins` uses Hermes's
choice UI and returns a resume command rather than opening a chat.

On a supported local Linux launch with a matching plugin and widget, the
selector reads through the TUI's existing Python runtime rather than starting
the full Hermes CLI. On the first picker open, one background `hermes --version`
command qualifies the captured runtime (20-second timeout). This native command
can check for updates and write its normal cache; it does not run merely because
the plugin loaded. Opens before qualification finishes keep the stock inventory
path and can be slower while both commands run. Other launches also keep the
CLI inventory path. Both use the same native session inventory. The selector
keeps the chat background unchanged and shows a static loading hint while waiting.

Reopening can reuse metadata for up to 30 seconds if the DB, WAL and local
plugin configuration are unchanged. First open, expiry, DB changes, widget
reload, and Ctrl+R require a fresh read. Failed refreshes never restore stale rows.

## From a terminal

Run this in a separate shell, not inside an active chat:

```sh
hermes pins
```

**Enter opens the selected chat immediately** in a normal Hermes client.
Pinned chats come first, followed by recent chats. Type to search, use ↑ / ↓ to
select, Ctrl+P to pin/unpin, and Esc to close. This does not switch another
already-open terminal's chat.

```sh
hermes pins list              # List visible pins
hermes pins pin "My Project"  # Pin by title or ID
hermes pins unpin SESSION_ID
hermes pins --print           # Select, then print a POSIX shell resume command
hermes -p work pins           # Use another profile
```

Printed shell commands carry the selected Hermes home. In-chat commands use
the current chat's profile.

## Privacy and storage

Pins live in the active profile's `state.db`, shared with Hermes CLI and Desktop.
They survive plugin removal and are exempt from Hermes's auto-archive sweep.
Native compression-lineage behavior applies. Archived chats stay archived;
explicit pinning may unhide a target, but Hermes's protected hidden chats and
native visibility filters are preserved. A hidden chat can remain pinned
without appearing in the selector.

The Ink selector receives only session metadata, not transcript previews.
The shell picker and Classic CLI/Desktop choices may use a message preview
when a chat has no title. The plugin does not change titles, timestamps, or
messages. Messaging-platform chats cannot enumerate or modify local pins
through this plugin. IDs are preserved exactly; unsafe copyable commands and
homes that cannot round-trip safely are refused.

## Update or remove

```sh
hermes plugins update session-pins
hermes pins install-ui
```

The widget installer refuses to overwrite a different file, including an older
widget version. If it reports a conflict, preserve the existing
`$HERMES_HOME/tui-widgets/session-pins.mjs` elsewhere, then run `install-ui` again.

To remove the widget, run `hermes pins remove-ui` **before** updating or removing
the plugin; it removes only a file identical to that plugin's bundled widget.
Modified or older widget files are preserved and need manual removal.

```sh
hermes plugins disable session-pins
hermes plugins remove session-pins
```

Pins remain. Remove a pin with `hermes sessions unpin SESSION_ID`.

## Development

Use a disposable `HERMES_HOME`, never your real session store:

```sh
python scripts/check.py
HERMES_HOME=/path/to/disposable-home hermes plugins validate . --json
```

Tests exercise real temporary SQLite stores and picker controls without model
calls. Automated checks are separate from native interactive acceptance.
See [CHANGELOG.md](CHANGELOG.md) for release history.
