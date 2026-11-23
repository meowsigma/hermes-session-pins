# Changelog

## 0.4.2

- Keep the chat background unchanged while the in-chat selector loads; use a
  static loading hint instead of an animated shimmer and viewport backdrop.
- On qualified local Linux launches, read native session metadata through the
  TUI's existing Python runtime instead of bootstrapping the full CLI per read.
  The first picker open starts a bounded public runtime-version check; until it
  finishes, inventory uses the stock CLI. That check can perform Hermes's normal
  update check and cache writes, so first-open speed is not guaranteed to improve.
- Preserve profile binding, native visibility, full-title search and metadata-only
  Ink output. Stable reopens can reuse a short-lived cache; Ctrl+R reads afresh.
- Add Left = Pinned and Right = All, retaining Tab, and simplify the README.
- Enter still copies the resume command for paste and confirmation. This release
  does not add same-view Enter-to-open or change Hermes core.

Upgrade with `hermes plugins update session-pins`, then refresh the widget with
`hermes pins install-ui`. If an older widget conflicts, preserve
`$HERMES_HOME/tui-widgets/session-pins.mjs` elsewhere before running `install-ui`
again. Use `/widgets-reload`, then reopen `/pins`; no service restart is needed.

## 0.4.1

- Add `/pin status`: a read-only check of the exact calling chat's pin flag.
  Empty/missing sessions and database errors are reported without changing pins.
- Reserve the exact lowercase `/pin status` argument; use a full session ID
  to pin a chat titled `status`. `/unpin status` keeps its selector behavior.
- Status-only release: `/pin all` and the `(This one)` marker are not included.
  Native/plugin-only discovery for open-chat bulk pinning remains research.

Upgrade with `hermes plugins update session-pins` in the profile you use.
The bundled widget is unchanged; this update does not require reinstalling it.

## 0.4.0

- Reopen an unchanged in-chat picker without launching a new inventory process:
  keep metadata in profile-local memory for at most 30 seconds, invalidated by
  SQLite database/WAL fingerprint changes, expiry or widget reload.
- Ctrl+R always reads fresh inventory. Cache misses clear old rows and disable
  selection while loading; refresh failures never restore stale rows.
- No disk cache, transcript previews, core patches or new dependencies.
- This improves warm reopening only, not first-open or forced-refresh latency.
  Enter still copies `/resume ID` for manual paste and confirmation; composer
  autofill and same-view navigation await a public host API (issue #158663).
- Independent Astra high exact-source review approved the loading changes;
  all 18 Node tests passed. The previous 57-pass Python receipt applies to the
  unchanged Python source/tests, not a new Python run. Synthetic native-CLI/SDK
  measurements do not establish real Ink keyboard/rendering acceptance.

Upgrade with `hermes plugins update session-pins`, then run
`hermes pins install-ui` in each profile where you use the Ink picker.
Modified widget files are preserved rather than silently overwritten.

## 0.3.9

- Add an optional native `/pins` modal inside the existing Hermes Ink chat,
  using the stock public widget SDK with no core patch, browser or second chat.
- Search full stored titles and IDs, switch Pinned / All with Tab, select with
  arrows/Page keys, and see stored model, last activity and the selected ID.
- Enter copies `/resume ID` and closes; Ctrl+P copies `/pin ID` or `/unpin ID`.
  Paste and confirm in the current composer to apply either command. This is
  not automatic navigation or direct selected-row mutation; refresh/reselect
  after profile changes or deleted rows because pasted selectors resolve again.
- Esc closes without a choice answer or pin change; Ctrl+U clears search and
  Ctrl+R refreshes. Inventory is read-only and follows native visibility rules.
- Add `hermes pins install-ui` and `hermes pins remove-ui`. Widget installation
  is explicit and hot-loaded; modified user-widget files are preserved.
- In Ink without the widget, `/pins` gives setup instructions instead of
  opening a blocking choice prompt. Classic CLI/Desktop choice behavior and
  the standalone shell picker remain available; built-in `/resume` is unchanged.
- Verification: independent Astra 6.2 source review, syntax checks, native
  zero-warning plugin validation and live widget registration. Automated
  product suites and native interactive acceptance are not yet completed for
  this build; no full-runtime pass is claimed.

Upgrade with `hermes plugins update session-pins`, then run
`hermes pins install-ui` in each profile where you want the Ink picker.

## 0.3.0

- `/pin` and `/unpin` can target another chat in the active profile by its
  exact stored title (including spaces) or full local ID, without switching
  chats. With no selector they still target the current session. `hermes pins
  pin` and `hermes pins unpin` accept the same selectors.
- A full ID wins over an exact title, and an exact title wins over a unique
  literal, case-sensitive ID prefix. Duplicate titles, ambiguous prefixes and
  unknown targets are refused without changing pins. Current and picker IDs
  stay exact-only.
- `/pins manage` and the standalone picker update pins in the profile that
  supplied the selection.
- Stored titles can resolve outside the recent list, including archived chats.
  Native lineage pinning and visibility rules are unchanged.

## 0.2.0

- Native-style standalone picker: compact borderless layout, numbered metadata
  rows, session counts, a filled selection highlight, custom profile-skin colors,
  and stock light/dark fallbacks. Metadata collapses on narrow terminals.
- Keep starred, bold, pinned-first rows, filtering, Ctrl-P management and Enter
  resume handoff. This replaces the old fixed-yellow frame and reverse cursor.
- Escape unsafe ID descriptions and refuse unsafe copyable commands without
  rewriting stored IDs.
- Preserve the selected home/profile in printed commands and direct launches;
  keep option-shaped IDs from being interpreted as command-line options.
- Qualify pin confirmations and lists to respect native hidden-session rules.
- Refuse child launches when Hermes would reinterpret the selected home, and
  prevent stale picker/current-session IDs from mutating a surviving prefix match.

The built-in `/resume` picker remains unchanged. `/pins` still uses Hermes's
host-owned choice prompt and returns a resume command; `hermes pins` is the
separate native-style shell picker. Printed commands require a POSIX shell.

Upgrade with `hermes plugins update session-pins`. For a fresh installation,
use `hermes plugins install meowsigma/hermes-session-pins --enable`.

## 0.1.0

- `/pin`, `/unpin`, and `/pins` using native profile-scoped Hermes pins.
- A separate `hermes pins` terminal picker with starred, highlighted pins first,
  filtering, pin/unpin management, and Enter-to-resume.
- No changes to Hermes core or the built-in `/resume` picker.
