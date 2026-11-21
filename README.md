# ★ Hermes Session Pins

Keep important Hermes chats easy to find without deleting your worker chats.
A small Python plugin: no model calls, external network requests, or extra packages.

## v0.4 preview — patched Hermes only

This branch provides the optional native Ink selector. It needs the separate
session-widget core hook described below; installing the Python plugin alone
does not add that hook. **Stock users should stay on [main](https://github.com/meowsigma/hermes-session-pins/tree/main)
and stable v0.3.0.** The preview does not replace the stable release.

Install the pinned, reviewed implementation:

```sh
hermes plugins install meowsigma/hermes-session-pins --ref 2dbf6851b96eb4b896c30701d22c386baa16911c --enable
```

Release documentation may have a later commit with identical runtime files.
The [v0.4.0 preview release](https://github.com/meowsigma/hermes-session-pins/releases/tag/v0.4.0)
also gives the exact tag-commit install command, the separately reviewed core
patch, and its SHA-256. Do not apply the patch to an unrelated Hermes revision:
its base is `bf0203a794a07aac3ff764972ab9087baa4e4f4e`. This plugin never applies
or activates a core patch itself.

On that patched Hermes build, copy `tui/pins.mjs` from the installed plugin into
the **same profile's** `tui-widgets/pins.mjs`. The TUI loads that companion; the
plugin installer does not copy it. No clarification prompt is used.

## Stock install (stable v0.3.0)

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
| `/pin example-session` | Pin the chat with that exact stored title without switching chats. |
| `/pin LOCAL_ID` | Pin the chat with that full local session ID. |
| `/unpin <title-or-id>` | Unpin the target using the same rules. |
| `/pins` | Browse starred pins. In supported Ink TUI builds, Tab shows all eligible chats. |
| `/pins list` | List visible pins and their available `/resume` commands. |
| `/pins find PROJECT NOTES` | Find eligible chats matching all the words, by title or ID, including older chats. |
| `/pins manage` | Open the selector where supported; otherwise list eligible pins in plain text. |

Type titles with spaces as-is, for example `/pin My Project` (no quotes). A
full ID wins if it also happens to be another chat's title. Otherwise an exact,
case-sensitive stored title wins. If neither matches, an explicitly typed ID
prefix is accepted only when exactly one stored ID starts with it, matching case.
Duplicate titles, ambiguous prefixes, and unknown selectors do not change pins.
Use the full ID to disambiguate. Title matching doesn't use previews, partial
titles, or newer `#2`-style names as fallbacks. The search covers the active
profile's stored chats, not just the recent or visible list.

**Ink TUI:** With the `tui/pins.mjs` companion and the separate Hermes
session-widget host hook (API v1 in both Ink and the canonical gateway), `/pins`
opens a themed, nonblocking overlay. Type to search; use ↑/↓ to move, PgUp/PgDn
to page, Ctrl-P to pin/unpin, Enter to switch, or Esc to close. Tab toggles between
pins and all eligible chats. Rows show last activity, the **recorded** model, and
original/fork labels when known. The built-in `/resume` picker is unchanged.

**Stock Hermes:** On classic CLI, Ink, and Desktop, `/pins` and `/pins manage`
list eligible pins in plain text without asking a question or switching chats.
Untitled chats show “Untitled chat”, not message previews. The list prints a
`/resume` command only when safe; use `/pin` or `/unpin` to change pins. The
Python fallback works without the core hook. The optional Ink companion is not
installed or activated by the plugin.

**Selected-write compatibility:** Agent bulk pin/unpin and Ctrl-P in both the
native overlay and the standalone shell picker require the matching core's public
`SessionDB.set_projected_session_pinned` API. It checks current exact projected
eligibility in the write transaction and never unhides a selected chat. Without
that API, these selected changes fail closed with an explanation; metadata
search, plain listings, the shell picker's Enter handoff, and explicit typed
`/pin` or `/unpin` still work. The proposed core patch also owns selector
revocation and exact eligible native attachment.
The preview does not install or activate that separate core patch.

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
**Ctrl-P** to pin/unpin the selection on a core with safe selected writes.
**Esc** closes it. Enter launches the normal Hermes chat client; it does not
replace another already-open terminal's session.

```sh
hermes pins list             # Plain list of visible pins
hermes pins find "project notes" # Search eligible chats, not just recently used ones
hermes pins pin SESSION_ID   # Pin from the shell
hermes pins pin "My Project" # Same selectors; quote a title with spaces in the shell
hermes pins unpin SESSION_ID
hermes pins --print          # Pick, then print the shell resume command only
hermes -p work pins          # Use the work profile's sessions
```

Shell commands printed by `list` or `--print` are for POSIX shells and carry the
selected Hermes home, so you can paste them back into your original shell after
using `hermes -p work pins`. In-chat `/resume` commands use the current chat's
profile.

## Storage and privacy

Pins use Hermes's own native `SessionDB` metadata in the active profile's
`state.db`: explicit commands use `set_session_pinned`, while selected changes
require `set_projected_session_pinned`. They survive plugin updates/removal and
share the same pins
as `hermes sessions pin` and Desktop. Native pins are exempt from Hermes's
auto-archive sweep. An archived target remains archived. Native pinning can
unhide an explicitly targeted hidden chat, but preserves the canonical hidden
Bot Chat and the picker's native visibility filters. The plugin doesn't write
titles, timestamps, or chat contents. Hermes applies pin changes across its
native compression lineage; a separate caller chat is unaffected.

Slash commands are limited to local terminal/Desktop surfaces; messaging chats
cannot enumerate or modify your local pins through this plugin. No secrets or
session contents are sent anywhere. Display text removes or escapes control
characters. If a session ID cannot be copied safely, no resume command is
printed for it; the stored ID is not changed. Direct launching uses an exact
argument vector, without a shell, and preserves the selected home/profile.
Homes that Hermes would reinterpret on child startup are refused rather than
redirected. A current or picker-selected session ID that disappeared never falls
back to a title or prefix match. Picker pin changes stay in the profile that
supplied the selection.

The local `session_pins_manage` tool offers `find`, `pin` and `unpin`. `find`
returns metadata only, paginates with `next_offset`, and includes the source
profile's `scope`. For `pin` or `unpin`, echo that `scope` with up to 50 selected
exact IDs from the results. A missing or foreign scope is refused; run `find`
again if you change profiles. Missing or no-longer-visible IDs are not resolved
by title or prefix. The scope guards against profile mix-ups, not unauthorized
callers: Hermes must still identify a visible, stored local owner chat.

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
