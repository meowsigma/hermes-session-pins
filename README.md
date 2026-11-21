# ★ Hermes Session Pins

Keep important Hermes chats easy to find without deleting your worker chats.
A small Python plugin: no model calls, network requests, extra packages, or core patches.

## Install

```sh
hermes plugins install meowsigma/hermes-session-pins --enable
```

Requires Hermes **0.22.5+** with its native session-pin API. Install into the
profile you use (`hermes -p work plugins install … --enable` for a named profile).
The normal Hermes plugin reload applies; if a running client has a stale command
catalog, reopen that client. No background-service restart is required by this plugin.

## In your chat

| Command | Action |
|---|---|
| `/pin` | Pin the current chat; safe to repeat. |
| `/unpin` | Unpin the current chat. |
| `/pin <session-id>` | Pin another chat by full ID or unambiguous prefix. |
| `/unpin <session-id>` | Unpin that chat. |
| `/pins` | Choose a visible starred pin and get its `/resume` command, if it can be copied safely. |
| `/pins list` | List visible pins and their available `/resume` commands. |
| `/pins manage` | Choose a pin, then show its resume command or unpin it. |

**Important: this does not change the built-in `/resume` picker.** Hermes reserves
that command and does not expose a session-picker sorting/decorating hook. Plugin
command results also cannot switch the active frontend session. `/pins` uses
Hermes's existing choice UI and prints the command to run; it does not pretend it
has already switched chats. Pin labels have a ★; the native choice UI owns its colors.

For a highlighted picker that **does resume your selection**, run this from a
separate shell—not as a command in your active chat:

```sh
hermes pins
```

The compact, borderless **Sessions** list follows the native resume picker's
visual language: session counts, numbered ID/age/message-count/title columns,
a ▸ cursor, and a filled selection highlight. Pinned chats stay at the top with
**bold ★ labels**, followed by up to 40 recent chats. Custom profile skin colors
are read when available; otherwise it uses Hermes's stock light/dark tones.
Non-default built-in skins without a profile YAML use the stock fallback. This
is a separate prompt-toolkit picker, not the native Ink component. On narrow
terminals, metadata columns collapse to leave room for chat titles.

Pins eligible under Hermes's native visibility filters are loaded
even when they are older than that recent page. A chat that Hermes excludes,
such as the canonical hidden Bot Chat, can stay pinned without appearing here.
Type to filter by title/ID, use **↑/↓**, **Enter** to launch the selected chat, or
**Ctrl-P** to pin/unpin the selection. **Esc** closes it. It launches the normal
Hermes chat client; it does not replace another already-open terminal's session.

```sh
hermes pins list             # Plain list of visible pins
hermes pins pin SESSION_ID  # Pin from the shell
hermes pins unpin SESSION_ID
hermes pins --print          # Pick, then print the shell resume command only
hermes -p work pins          # Use the work profile's sessions
```

Shell commands printed by `list` or `--print` are for POSIX shells and carry the
selected Hermes home, so you can paste them back into your original shell after
using `hermes -p work pins`. In-chat `/resume` commands use the current chat's
profile.

## Storage and privacy

Pins use Hermes's own `SessionDB.set_session_pinned` metadata in the active
profile's `state.db`. They survive plugin updates/removal and share the same pins
as `hermes sessions pin` and Desktop. Native pins are exempt from Hermes's
auto-archive sweep. Native pinning can unhide an explicitly chosen hidden chat;
the plugin never archives, deletes, renames, rewrites timestamps, or changes chat
contents. Compression-lineage handling stays with Hermes itself.

Slash commands are limited to local terminal/Desktop surfaces; messaging chats
cannot enumerate or modify your local pins through this plugin. No secrets or
session contents are sent anywhere. Display text removes or escapes control
characters. If a session ID cannot be copied safely, no resume command is
printed for it; the stored ID is not changed. Direct launching uses an exact
argument vector, without a shell, and preserves the selected home/profile.

## Remove

```sh
hermes plugins disable session-pins
hermes plugins remove session-pins
```

Pins remain. Remove an individual pin with `hermes sessions unpin SESSION_ID`.

## Development

Use a disposable `HERMES_HOME`, never your real session store:

```sh
python scripts/check.py
HERMES_HOME=/path/to/disposable-home hermes plugins validate . --json
```

Tests use real Hermes SQLite session stores in temporary directories. Picker tests
exercise real prompt-toolkit input/rendering, pin persistence, ordering, cancel,
and the resume subprocess argument contract without invoking a model.
