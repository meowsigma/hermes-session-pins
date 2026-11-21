"""Presentation for the standalone picker; no dependency on Ink internals."""
from __future__ import annotations

import math
import os
from pathlib import Path
import re

from prompt_toolkit.styles import Style
from prompt_toolkit.utils import get_cwidth

from hermes_constants import get_hermes_home

_HEX = re.compile(r"#[0-9a-fA-F]{6}")
# Stock Hermes picker tones. Non-default built-ins have no standalone palette API.
_DARK = ("#ffbf00", "#b8860b", "#fff8dc", "#333355", "#ef5350")
_LIGHT = ("#956e00", "#8b680c", "#5c4718", "#e0d1bf", "#c14240")


def _luminance(color: str) -> float:
    rgb = (int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    linear = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb)
    return sum(weight * component for weight, component in zip((0.2126, 0.7152, 0.0722), linear))


def _light_terminal() -> bool:
    theme = os.environ.get("HERMES_TUI_THEME", "").strip().lower()
    if theme in {"light", "dark"}:
        return theme == "light"
    for hint in (theme, os.environ.get("HERMES_TUI_BACKGROUND", "")):
        color = "#" + hint.strip().lstrip("#")
        if _HEX.fullmatch(color):
            return _luminance(color) >= 0.6
    ansi_bg = os.environ.get("COLORFGBG", "").strip().rsplit(";", 1)[-1]
    if ansi_bg in {str(i) for i in range(16)}:
        return ansi_bg in {"7", "15"}
    return os.environ.get("TERM_PROGRAM") == "Apple_Terminal"


def _skin_colors(light: bool) -> dict[str, str]:
    # Read the documented profile skin files. Do not import the private skin
    # engine or try to change the terminal's background via OSC.
    try:
        from hermes_cli.config import load_config
        from ruamel.yaml import YAML
        from ruamel.yaml.error import YAMLError
    except ImportError:
        return {}
    try:
        display = load_config().get("display")
        name = display.get("skin") if isinstance(display, dict) else None
        if not isinstance(name, str) or not re.fullmatch(r"[\w-][\w.-]*", name):
            return {}
        path = Path(get_hermes_home()) / "skins" / f"{name}.yaml"
        skin = YAML(typ="safe").load(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, YAMLError):
        return {}
    if not isinstance(skin, dict):
        return {}
    colors = {}
    for section in ("colors", "light_colors" if light else "dark_colors"):
        palette = skin.get(section)
        if isinstance(palette, dict):
            colors.update({k: v for k, v in palette.items() if isinstance(v, str) and _HEX.fullmatch(v)})
    return colors


def picker_style() -> Style:
    light = _light_terminal()
    accent, muted, ink, chip, error = _LIGHT if light else _DARK
    colors = _skin_colors(light)
    accent = colors.get("ui_accent", colors.get("banner_accent", accent))
    muted = colors.get("banner_dim", muted)
    ink = colors.get("ui_text", colors.get("banner_text", ink))
    chip = colors.get("completion_menu_current_bg", chip)
    error = colors.get("ui_error", error)
    fill, foreground = _luminance(chip), _luminance(ink)
    if (max(fill, foreground) + 0.05) / (min(fill, foreground) + 0.05) < 4.5:
        ink = "#000000" if (fill + 0.05) ** 2 >= 1.05 * 0.05 else "#ffffff"
    return Style.from_dict({
        "heading": f"{accent} bold",
        "hotkey": accent,
        "muted": muted,
        "selected": f"{ink} bg:{chip}",
        "strong": "bold",
        "pin": f"{accent} bold",
        "error": error,
    })


def fit(text: str, width: int, *, pad: bool = False) -> str:
    """End-truncate in prompt_toolkit's terminal cells, not Python characters."""
    if width <= 0:
        return ""
    if get_cwidth(text) > width:
        used = 0
        for i, ch in enumerate(text):
            used += get_cwidth(ch)
            if used >= width:  # reserve one cell for the ellipsis
                text = text[:i] + "…"
                break
    return text + " " * (width - get_cwidth(text)) if pad else text


def session_age(timestamp: object, now: float) -> str:
    if not isinstance(timestamp, (int, float)) or not timestamp or not math.isfinite(timestamp):
        return ""
    days = int(max(0, now - timestamp) // 86400)
    return "today" if not days else "yesterday" if days == 1 else f"{days}d ago"


def session_row(*, width: int, number: int, selected: bool, sid: str, age: str,
                count: object, title: str, pin: str) -> list[tuple[str, str]]:
    # Native history columns on roomy terminals; reclaim metadata space for the
    # title in narrow panes. The number and pin stay visible.
    if width >= 64:
        widths = (11, 11, 18)
    elif width >= 40:
        widths = (11, 10, 8)
    else:
        widths = (10 if width >= 24 else 0, 0, 0)
    messages = count if type(count) is int and count >= 0 else 0
    base = "class:selected" if selected else "class:muted"
    emphasis = base + " class:strong" if selected else base
    parts = [(emphasis, "▸ " if selected else "  "),
             (emphasis, f"{number:>2}.".ljust(5))]
    for text, size, style in zip((sid, age, f"{messages} msgs"), widths, (emphasis, base, base)):
        if size:
            parts.append((style, fit(text, size - 1, pad=True) + " "))
    rest = max(0, width - sum(get_cwidth(text) for _, text in parts))
    if rest >= 2:
        parts.append(("class:pin" if pin and not selected else emphasis, (pin or " ") + " "))
        rest -= 2
    elif rest and pin:
        parts.append(("class:pin" if not selected else emphasis, pin))
        rest -= 1
    parts.append((base + " class:strong" if pin else emphasis, fit(title, rest, pad=selected)))
    return parts
