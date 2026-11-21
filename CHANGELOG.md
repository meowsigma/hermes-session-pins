# Changelog

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
