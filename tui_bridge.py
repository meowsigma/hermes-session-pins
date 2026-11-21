"""Plugin-owned, read-only inventory and explicit native-widget installation."""
from __future__ import annotations

import json
from pathlib import Path

if __package__:
    from . import session_pins as pins
else:
    import session_pins as pins


def inventory(home: Path) -> dict:
    """Use the public native list projection, not a recreated SQLite filter.

    No writer, routing index or credentials are touched. Native visibility
    filters are preserved. Search titles remain full length. The native list
    computes previews, but no message previews leave this helper.
    """
    home = home.absolute()
    with pins.database(home=home) as db:
        rows = db.list_sessions_rich(limit=-1, include_pinned=True, order_by_last_active=True, compact_rows=True)
    seen = set()
    result = []
    for row in rows:
        sid = row["id"]
        if sid in seen:
            continue
        seen.add(sid)
        config = row.get("model_config") or {}
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except (ValueError, TypeError):
                config = {}
        if not isinstance(config, dict):
            config = {}
        model = config.get("model") or row.get("model") or ""
        result.append({
            "id": sid,
            "title": pins.clean_label(row.get("title") or "Untitled chat", limit=1_000_000),
            "pinned": bool(row.get("pinned")),
            "model": pins.clean_label(model, limit=300),
            "updated": row.get("last_active") or row.get("started_at") or 0,
        })
    result.sort(key=lambda r: (not r["pinned"], -float(r["updated"]), r["id"]))
    return {"home": str(home), "rows": result}


def install(home: Path) -> Path:
    """Explicit install only; plugin registration itself has no file effects."""
    source = Path(__file__).parent / "tui" / "pins.mjs"
    destination = home / "tui-widgets" / "session-pins.mjs"
    data = source.read_bytes()
    if destination.is_symlink():
        raise pins.PinsError("Refusing to replace a symlinked user widget.")
    if destination.exists() and destination.read_bytes() != data:
        raise pins.PinsError("A different session-pins.mjs already exists. Preserve it before installing this preview.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        # Exclusive create: never clobber a concurrently created user file.
        with destination.open("xb") as out:
            out.write(data)
    if destination.read_bytes() != data:
        raise pins.PinsError("Widget installation did not verify.")
    return destination


def remove(home: Path) -> Path:
    source = Path(__file__).parent / "tui" / "pins.mjs"
    destination = home / "tui-widgets" / "session-pins.mjs"
    if destination.is_symlink():
        raise pins.PinsError("Refusing to remove a symlinked user widget.")
    if destination.exists():
        if destination.read_bytes() != source.read_bytes():
            raise pins.PinsError("The user widget has changed; preserve it and remove it manually.")
        destination.unlink()
    return destination
