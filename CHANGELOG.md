# Changelog

## 0.4.0

Published as a preview on `release/v0.4.0`; stable `main` stays at v0.3.0.

- Search visible chats by title words or ID beyond the recent list, with truthful
  pages and counts, recorded model, last activity, and confirmed fork labels.
- Add a local agent tool for discovery and exact-ID bulk pin/unpin.
- Add an optional nonblocking Ink `/pins` selector with keyboard search,
  pin/unpin, and native session switching. It requires the separate Hermes
  session-widget hook; stock Ink and Desktop use plain output without asking a
  question. Classic CLI still provides its original prompt and resume handoff.
- Compatibility: the safe selected-write core API is now required for Ctrl-P
  pin/unpin in the shell picker as well as the Ink overlay. On stock builds
  without it, selected changes are refused; explicit typed `/pin` and `/unpin`
  still work. Installing this preview does not install the core hook or the
  optional Ink companion. Use the preview release's pinned install command;
  ordinary updates from stable `main` intentionally stay on v0.3.0.

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
