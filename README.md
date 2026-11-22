# ★ Hermes Session Pins

Keep important Hermes chats easy to find without deleting your worker chats.
A small Python plugin: no model calls, network requests, extra packages, or core patches.

## Read-only pin status (v0.4.1)

`/pin status` reports whether the calling chat is pinned, using its exact
host-supplied session ID and a read-only database view. It does not change pins,
titles, visibility or message contents. A missing session or unavailable store
is an error, not an "unpinned" result. The exact lowercase argument `status`
is reserved for this check; pin a chat titled `status` by its full ID instead.
`/unpin status` and shell `hermes pins pin status` keep their selector behavior.

This release adds status only. `/pin all` (currently open chats, not recent
history) is deferred while native/plugin-only discovery is investigated.
The `(This one)` picker marker is also deferred. Neither feature is included.

## Faster reopening (v0.4.0)

The picker reuses the last successful metadata inventory in memory
for up to 30 seconds while the profile's SQLite DB and WAL fingerprints remain
unchanged. Reopening an unchanged picker avoids starting `hermes pins data` again.
Database/WAL changes, expiry, a widget reload, or **Ctrl+R** require a fresh read;
refresh clears the old rows and never falls back to them on failure. No cache is
written to disk and the native visibility projection is unchanged.

This improves **reopening**, not first-open or forced-refresh latency. Enter
still copies the resume command; composer autofill and same-view navigation need
a public host API ([proposal #158663](https://github.com/NousResearch/hermes-agent/issues/158663)).
The loading changes passed independent source review and 18 Node tests. Real
native Ink keyboard/rendering acceptance remains unverified.

## Native in-chat picker (0.3.9)

The in-chat picker uses Hermes's stock widget SDK and needs no core patch.
The native widget is plain ESM for the Node runtime Hermes Ink already uses;
it installs no packages and imports no private Hermes frontend code.

After installing the plugin, run `hermes pins install-ui`
once. Then **`/pins` opens inside the existing Ink chat**, not a new terminal,
browser or second Hermes chat. The widget hot-loads; `/widgets-reload` is the
stock fallback if discovery is delayed. No restart is required.

- Starts on Pinned; **Tab** switches Pinned / All visible chats.
- Type to search full stored titles and IDs; **↑/↓** selects; Page Up/Down scrolls.
- Shows stored model and last activity, selection highlight and selected ID.
- **Enter copies the exact `/resume ID` and closes. Paste and confirm in the
  same composer to actually open it.** It never sends fake keys or changes models.
- **Ctrl+P copies `/pin ID` or `/unpin ID` and closes**; paste and confirm in
  this chat to apply it, then reopen or Ctrl+R refresh. This is deliberately NOT
  a direct selected-row mutation: stock public SDK lacks the safe selection
  transaction/lifecycle API. Explicit typed pin commands remain unchanged.
  The copied argument preserves the selected ID, but pasted commands use the
  stock typed-selector rules in the current profile. If the row disappears or
  the profile changes before confirmation, refresh/reselect rather than assuming
  the command still resolves to the old target.
- **Esc** closes without a command, answer, pause request or pin change.
- **Ctrl+U** clears search; **Ctrl+R** refreshes. Clipboard failure keeps the
  picker open with an error. POSIX clipboard utilities: `wl-copy` on Wayland,
  `xclip` on X11, `pbcopy` on macOS. Windows clipboard is not implemented here.

Copy/paste is the navigation and pin-management handoff, not automatic
Enter-to-open or a tested live-turn continuity claim. Independent source review,
syntax checks, native plugin validation and live widget registration were
verified for v0.3.9. Its post-publication automated checks passed 57 Python and
7 Node tests after a test-fixture repair. Real native interactive acceptance is
still unverified; registration and automated checks do not imply it.

`hermes pins remove-ui` removes only the exact unchanged bundled widget. Plugin
removal alone does not remove this explicitly installed user-widget file.

## Install

```sh
hermes plugins install meowsigma/hermes-session-pins --enable
hermes pins install-ui  # Enable the optional in-chat Ink picker
```

For an existing installation, run `hermes plugins update session-pins`, then
`hermes pins install-ui` to install or refresh the bundled widget in that same
profile. The widget installer preserves a modified user-widget file rather than
silently overwriting it.

Requires Hermes **0.22.5+** with its native session-pin API. Install into the
profile you use (`hermes -p work plugins install … --enable` for a named profile).
The normal Hermes plugin reload applies; if a running client has a stale command
catalog, reopen that client. No background-service restart is required by this plugin.

## Classic CLI / Desktop choice UI

| Command | Action |
|---|---|
| `/pin` | Pin the current chat; safe to repeat. |
| `/pin status` | Report whether the current chat is pinned, without changing it. |
| `/unpin` | Unpin the current chat. |
| `/pin example-session` | Pin the chat with that exact stored title without switching chats. |
| `/pin LOCAL_ID` | Pin the chat with that full local session ID. |
| `/unpin <title-or-id>` | Unpin the target using the same rules. |
| `/pins` | Choose a visible starred pin and get its `/resume` command (native overlay in Ink when installed). |
| `/pins list` | List visible pins and their available `/resume` commands. |
| `/pins manage` | Choose a pin, then show its resume command or unpin it. |

Type titles with spaces as-is, for example `/pin My Project` (no quotes). A
full ID wins if it also happens to be another chat's title. Otherwise an exact,
case-sensitive stored title wins. If neither matches, an explicitly typed ID
prefix is accepted only when exactly one stored ID starts with it, matching case.
Duplicate titles, ambiguous prefixes, and unknown selectors do not change pins.
Use the full ID to disambiguate. Title matching doesn't use previews, partial
titles, or newer `#2`-style names as fallbacks. The search covers the active
profile's stored chats, not just the recent or visible list.

**Important: this does not change the built-in `/resume` picker.** Hermes reserves
that command and does not expose a session-picker sorting/decorating hook. Plugin
command results also cannot switch the active frontend session. `/pins` uses
Hermes's existing choice UI outside Ink and prints the command to run; it does not pretend it
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

Pins use Hermes's own `SessionDB.set_session_pinned` metadata in the active
profile's `state.db`. They survive plugin updates/removal and share the same pins
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
redirected. Direct current-session and standalone-picker mutations refuse a
missing exact ID instead of falling back to a title or prefix. Standalone-picker
pin changes stay in the profile that supplied the selection. The in-chat
widget's copied commands instead follow the typed-selector/current-profile
rules when pasted, as explained above.

## Remove

If you installed the Ink widget, run `hermes pins remove-ui` before removing the
plugin. It removes only the unchanged bundled widget, preserving user edits.

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
