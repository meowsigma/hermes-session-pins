# Changelog

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
