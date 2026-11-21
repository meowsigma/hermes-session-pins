"""Small, local-only session pin manager for Hermes. No core patches or model calls."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import os
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import unicodedata

from hermes_constants import get_hermes_home
from hermes_state import SessionDB

STAR = "★"
LOCAL_SURFACES = {"cli", "tui", "local", "desktop"}
BACKGROUND_SOURCES = {"tool", "cron", "kanban", "delegate", "subagent", "system"}
MAX_PAGE = 50
MAX_BULK = 50
MAX_QUERY = 200
DISPLAY_LABEL_LIMIT = 90


class PinsError(RuntimeError):
    """An actionable error safe to show in a command response."""


def clean_label(value: object, limit: int | None = DISPLAY_LABEL_LIMIT) -> str:
    """Keep stored titles from injecting terminal escape/control sequences."""
    text = "".join(c for c in str(value or "") if not unicodedata.category(c).startswith("C"))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def title(row: dict) -> str:
    return clean_label(row.get("title") or row.get("preview")) or "Untitled chat"


def command_error(exc: Exception) -> str:
    return "Session Pins: " + (clean_label(exc, limit=300) or "The command failed. Try again.")


def display_id(sid: str) -> str:
    return sid if sid.isprintable() else ascii(sid)


@contextmanager
def database(*, writable: bool = False, home: Path | None = None):
    # Resolve per call: one process can serve several Hermes profiles.
    path = (Path(get_hermes_home()) if home is None else home) / "state.db"
    if not path.is_file():
        raise PinsError("No sessions yet. Send a message in Hermes, then use /pin.")
    with SessionDB(db_path=path, read_only=not writable) as db:
        if not hasattr(db, "set_session_pinned"):
            raise PinsError("This Hermes build lacks session pins. Update Hermes first.")
        yield db


def stored_rows(db: SessionDB) -> list[dict]:
    # Selector uniqueness includes all stored rows, not the visible picker's
    # page or projected lineages.
    return db.list_sessions_rich(
        limit=-1, include_children=True, project_compression_tips=False,
        include_archived=True, include_hidden=True, include_subagents=True,
        compact_rows=True,
    )


def resolve_selector(db: SessionDB, value: str) -> tuple[str, bool]:
    """Return the exact key and whether it was selected by title."""
    if db.get_session(value) is not None:
        return value, False

    # Native resume prefers newer numbered titles. The exact-title API also
    # returns only one row, so use it as a hit probe, not a uniqueness check.
    if db.get_session_by_title(value) is not None:
        matches = [row["id"] for row in stored_rows(db) if row.get("title") == value]
        if len(matches) > 1:
            raise PinsError("That title is ambiguous in this profile. Use the full session ID.")
        if not matches:
            raise PinsError("That title changed during lookup. Retry or use the full session ID.")
        return matches[0], True

    # SQLite LIKE folds ASCII case. Decide uniqueness over literal matches.
    matches = [row["id"] for row in stored_rows(db) if row["id"].startswith(value)]
    if len(matches) != 1:
        raise PinsError("Session not found in this profile, or that ID prefix is ambiguous. "
                        "Use the exact title or full session ID.")
    return matches[0], False


def set_pin(value: str, pinned: bool, *, exact: bool = False, home: Path | None = None,
            visible_only: bool = False, widget_admit=None) -> dict:
    if not value:
        raise PinsError("No current session yet. Send a message first, or provide a title or full session ID.")
    home = Path(get_hermes_home()) if home is None else home
    missing = "That session no longer exists in this profile. Refresh or use a full session ID."
    if visible_only:
        if not exact:
            raise PinsError("Select an exact session ID.")
        if not callable(getattr(SessionDB, "set_projected_session_pinned", None)):
            raise PinsError("Selected pin changes require a Hermes build with safe session selection support. "
                            "Use /pin or /unpin with an explicit ID instead.")
        with database(writable=True, home=home) as db:
            if not db.set_projected_session_pinned(value, pinned, admit=widget_admit):
                raise PinsError("Session is missing or not visible in this profile. Search for it again.")
            updated = db.get_session(value)
            if updated is None or bool(updated.get("pinned")) != pinned:
                raise PinsError("Hermes did not confirm the pin change. Try again.")
            return updated
    # Resolve before opening a writer, which could repair legacy duplicate
    # titles. A failed selector shouldn't change the store at all.
    with database(home=home) as db:
        if exact:
            # Current/picker IDs never fall back to a title or prefix match.
            if db.get_session(value) is None:
                raise PinsError(missing)
            sid, by_title = value, False
        else:
            sid, by_title = resolve_selector(db, value)
    with database(writable=True, home=home) as db:
        # Recheck only the selected key. Never re-resolve a disappearing target.
        row = db.get_session(sid)
        if row is None:
            raise PinsError(missing)
        if by_title and row.get("title") != value:
            raise PinsError("That title changed during lookup. Retry or use the full session ID.")
        if not db.set_session_pinned(sid, pinned):
            raise PinsError("Hermes could not update that session's pin. Refresh and try again.")
        updated = db.get_session(sid)
        if updated is None or bool(updated.get("pinned")) != pinned:
            raise PinsError("Hermes did not confirm the pin change. Try again.")
        return updated


def session_rows(*, recent: bool = False, home: Path | None = None) -> list[dict]:
    with database(home=home) as db:
        # Back-fill pins eligible under native visibility filters before UI paging.
        # Core projects compression tips.
        rows = db.list_sessions_rich(
            limit=40 if recent else 1, include_pinned=True, order_by_last_active=True,
        )
    by_id = {row["id"]: row for row in rows if recent or row.get("pinned")}
    return sorted(by_id.values(), key=lambda r: (
        not bool(r.get("pinned")),
        -float(r.get("last_active") or r.get("started_at") or 0),
        r["id"],
    ))


def discoverable(row: dict) -> bool:
    # The native query hides delegates; also check the projected row, which
    # can differ from the root on which native SQL filters were applied.
    if (row.get("hidden") or row.get("source") in BACKGROUND_SOURCES
            or row.get("archived") and not row.get("pinned")):
        return False
    config = row.get("model_config")
    if isinstance(config, str):
        try:
            config = json.loads(config)
        except ValueError:
            config = None
    return not (isinstance(config, dict) and config.get("_delegate_from"))


def discovery_rows(db: SessionDB) -> list[dict]:
    rows = db.list_sessions_rich(limit=-1, include_pinned=True, compact_rows=True,
                                 exclude_sources=sorted(BACKGROUND_SOURCES))
    visible = {}
    exact_metadata = getattr(db, "get_session_list_row", db.get_session)
    for row in rows:
        if not discoverable(row):
            continue
        sid = row["id"]
        if row.get("_lineage_root_id"):
            # Native compression projection retains the root's visibility fields.
            # A hidden tip must not leak its title, model, or ID through those fields.
            tip = exact_metadata(sid)
            if not tip or not discoverable({**row, **tip}):
                continue
        visible[sid] = row
    return sorted(visible.values(), key=lambda row: (
        not bool(row.get("pinned")), -activity(row), row["id"],
    ))


def activity(row: dict) -> float:
    return float(row.get("last_active") or row.get("started_at") or 0)


def discover_sessions(query: str = "", *, limit: int = 20, offset: int = 0,
                      pinned_only: bool = False, home: Path | None = None) -> dict:
    if not isinstance(query, str) or len(query) > MAX_QUERY:
        raise PinsError(f"Search text must be at most {MAX_QUERY} characters.")
    if type(limit) is not int or not 1 <= limit <= MAX_PAGE or type(offset) is not int or offset < 0:
        raise PinsError(f"Use a page size between 1 and {MAX_PAGE} and a nonnegative offset.")
    if type(pinned_only) is not bool:
        raise PinsError("pinned_only must be true or false.")
    with database(home=home) as db:
        rows = discovery_rows(db)
    # An explicit branch marker is evidence; an arbitrary parent edge is not.
    handles = {sid: row["id"] for row in rows for sid in (row.get("_lineage_ids") or [row["id"]])}
    handles.update({row["_lineage_root_id"]: row["id"] for row in rows if row.get("_lineage_root_id")})
    originals = {handles.get(row.get("_branched_from")) for row in rows if row.get("_branched_from")}
    terms = query.casefold().split()
    matches = []
    for row in rows:
        if pinned_only and not row.get("pinned"):
            continue
        sid = row["id"]
        full_title = clean_label(row.get("title"), limit=None) or "Untitled chat"
        haystack = f"{full_title} {sid}".casefold()
        if not all(term in haystack for term in terms):
            continue
        label = full_title[:DISPLAY_LABEL_LIMIT]
        branch_from = row.get("_branched_from")
        matches.append({
            "id": sid, "display_id": display_id(sid), "title": label,
            "pinned": bool(row.get("pinned")), "recorded_model": clean_label(row.get("model")) or None,
            "last_active": activity(row), "relationship": "fork" if branch_from else "original" if sid in originals else None,
            "original_id": handles.get(branch_from),
        })
    end = offset + limit
    return {"sessions": matches[offset:end], "total": len(matches),
            "next_offset": end if end < len(matches) else None}


def bulk_set_pins(ids: list[str], pinned: bool, *, home: Path | None = None, widget_admit=None) -> list[dict]:
    if (type(pinned) is not bool or not isinstance(ids, list) or not 1 <= len(ids) <= MAX_BULK
            or any(not isinstance(sid, str) or not sid for sid in ids)):
        raise PinsError(f"Supply 1–{MAX_BULK} exact session IDs and a boolean pin state.")
    home = Path(get_hermes_home()).absolute() if home is None else home
    results = []
    for sid in dict.fromkeys(ids):
        try:
            row = set_pin(sid, pinned, exact=True, home=home, visible_only=True, widget_admit=widget_admit)
            results.append({"id": sid, "ok": True, "pinned": bool(row["pinned"])})
        except (PinsError, OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
            results.append({"id": sid, "ok": False, "error": command_error(exc)})
    return results


def discovery_tool(ctx, args: dict, *, session_id: str = "") -> str:
    try:
        surface = getattr(ctx, "session_surface", None)
        require_local(surface() if callable(surface) else "")
        if not session_id:
            raise PinsError("Session discovery requires a bound local session.")
        home = Path(get_hermes_home()).resolve()
        with database(home=home) as db:
            caller = db.get_session(session_id)
        if not caller or caller.get("source") not in LOCAL_SURFACES or not discoverable(caller):
            raise PinsError("Session discovery requires a visible, stored local owner chat.")
        if not isinstance(args, dict):
            raise PinsError("Expected discovery tool arguments.")
        # Like the selector scope, this fences profile changes, not callers.
        scope = hashlib.sha256(os.fsencode(home)).hexdigest()
        action = args.get("action")
        if action == "find":
            result = discover_sessions(args.get("query", ""), limit=args.get("limit", 20),
                                       offset=args.get("offset", 0), home=home)
            result["scope"] = scope
        elif action in ("pin", "unpin"):
            if args.get("scope") != scope:
                raise PinsError("Selection scope is missing or belongs to a different profile. "
                                "Run find in the active profile and pass its returned scope.")
            result = {"results": bulk_set_pins(args.get("ids"), action == "pin", home=home)}
        else:
            raise PinsError("Choose find, pin, or unpin.")
        return json.dumps(result)
    except (OSError, RuntimeError, TypeError, ValueError, sqlite3.Error) as exc:
        return json.dumps({"error": command_error(exc)})


def command_pins_ui(raw_args: str, *, platform: str = "", widget_admit=None) -> str:
    """Structured request/response for the Ink companion; never asks a question."""
    try:
        require_local(platform)
        home = Path(get_hermes_home()).absolute().resolve()
        # Consistency fence, not authorization. Local-surface policy is checked
        # above and the active profile comes from Hermes, never widget input.
        scope = hashlib.sha256(os.fsencode(home)).hexdigest()
        request = json.loads(raw_args)
        if not isinstance(request, dict):
            raise PinsError("Invalid selector request.")
        if (request.get("op") != "list" or "scope" in request) and request.get("scope") != scope:
            raise PinsError("The active profile changed. Close and reopen /pins.")
        if request.get("op") == "list":
            result = discover_sessions(request.get("query", ""), offset=request.get("offset", 0),
                                       pinned_only=request.get("pinned_only", False), home=home)
            result["scope"] = scope
        elif request.get("op") == "set":
            if not callable(widget_admit):
                raise PinsError("Selector pin changes require an active native session selector.")
            result, = bulk_set_pins([request.get("id")], request.get("pinned"), home=home,
                                    widget_admit=widget_admit)
        elif request.get("op") == "open":
            with database(home=home) as db:
                if not any(row["id"] == request.get("id") for row in discovery_rows(db)):
                    raise PinsError("Session is missing or not visible in this profile. Refresh and try again.")
            result = {"ok": True}
        else:
            raise PinsError("Invalid selector request.")
        return json.dumps(result)
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
        return json.dumps({"error": command_error(exc)})


def resume_argv(sid: str, home: Path) -> list[str]:
    """Keep exact opaque IDs and the selected profile on both launch paths."""
    resume = [f"--resume={sid}"] if sid.startswith("-") else ["--resume", sid]
    # Root homes need an explicit default to override a sticky active_profile.
    profile = [] if home.parent.name == "profiles" else ["--profile", "default"]
    return ["chat", *resume, *profile]


def resume_home(home: Path) -> str:
    """Refuse homes that a new Hermes process could interpret differently."""
    path = str(home)
    # Be conservative about variable syntax, even if currently undefined: startup
    # may supply additional environment values. Never rewrite the selected home.
    if ("$" in path or path != path.strip()
            or os.path.expanduser(os.path.expandvars(path)) != path):
        raise PinsError("Resume unavailable: this Hermes home would be reinterpreted at startup.")
    return path


def resume_command(sid: str, *, home: Path | None = None) -> str:
    # Shell quoting is not terminal escaping. Never rewrite the ID to make it fit.
    id_error = "Resume command unavailable: this session ID cannot be copied safely."
    if not sid.isprintable() or sid != sid.strip():
        raise PinsError(id_error)
    if home is None:
        # The classic /resume parser treats these as a menu index or unwraps them.
        if sid.isdigit() or (len(sid) >= 2 and sid[0] + sid[-1] in {"<>", "[]", '""', "''"}):
            raise PinsError(id_error)
        return f"/resume {sid}"

    if os.name != "posix":
        raise PinsError("Printed shell resume commands require a POSIX shell. Launch it from the picker instead.")
    path = resume_home(home)
    if not path.isprintable():
        raise PinsError("Resume command unavailable: this Hermes home cannot be copied safely.")
    return shlex.join(["env", f"HERMES_HOME={path}", "hermes", *resume_argv(sid, home)])


def resume_line(sid: str, *, home: Path | None = None) -> str:
    try:
        return resume_command(sid, home=home)
    except PinsError as exc:
        return str(exc)


def require_local(platform: str) -> None:
    # A remote chat must not use this local terminal manager to enumerate or
    # modify unrelated private conversations. Adapter identity is not a grant.
    if platform not in LOCAL_SURFACES:
        raise PinsError("Session Pins is for local Hermes terminals and Desktop, not messaging chats.")


def command_pin(raw_args: str, *, session_id: str = "", platform: str = "", pinned: bool = True) -> str:
    try:
        require_local(platform)
        selector = raw_args.strip()
        row = set_pin(selector or session_id, pinned, exact=not bool(selector))
        if pinned:
            hint = ("This chat is still marked hidden; Hermes may omit it from pin lists."
                    if row.get("hidden") else "Browse visible pins with /pins or hermes pins.")
            return f"{STAR} Pinned: {title(row)}\n{hint}"
        return f"Unpinned: {title(row)}"
    except (PinsError, OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
        return command_error(exc)


def discovery_text(query: str, home: Path) -> str:
    result = discover_sessions(query, home=home)
    if not result["sessions"]:
        return "No matching visible chats. Try other title words or ID text."
    lines = [f"Showing {len(result['sessions'])} of {result['total']} matching chats"]
    for row in result["sessions"]:
        marker = f"{STAR} " if row["pinned"] else ""
        relation = f" · {row['relationship']}" if row["relationship"] else ""
        model = row["recorded_model"] or "unknown"
        stamp = (datetime.fromtimestamp(row['last_active'], tz=timezone.utc).strftime("%Y-%m-%d %H:%MZ")
                 if row['last_active'] else "unknown")
        lines.append(f"{marker}{row['title']}{relation} · recorded model: {model} · last active: {stamp}\n"
                     f"  {row['display_id']}")
    return "\n".join(lines)


def command_pins(ctx, raw_args: str, *, platform: str = "") -> str:
    try:
        require_local(platform)
        arg = raw_args.strip()
        mode = arg.lower()
        home = Path(get_hermes_home()).absolute()
        if mode.split(maxsplit=1)[:1] == ["find"]:
            return discovery_text(arg[4:].strip(), home)
        if mode not in {"", "list", "manage"}:
            return "Usage: /pins [list|manage|find [words]]. Pin or unpin a known chat with /pin or /unpin."
        with database(home=home) as db:
            rows = [row for row in discovery_rows(db) if row.get("pinned")]
        if not rows:
            return "No pinned chats in this list. Use /pin in a chat you want to keep."
        listing = "\n".join(
            f"{STAR} {clean_label(row.get('title')) or 'Untitled chat'}\n  {resume_line(row['id'])}"
            for row in rows
        )
        if mode == "list":
            return listing
        return ("Native selector not available here. Use /pin or /unpin with an exact ID, "
                "or run hermes pins in a separate terminal.\n" + listing)
    except (PinsError, OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
        return command_error(exc)


def picker(rows: list[dict], *, home: Path | None = None, input=None, output=None) -> dict | None:
    """Native-style history list using Hermes's existing prompt_toolkit dependency."""
    from time import time

    from prompt_toolkit import Application
    from prompt_toolkit.application import get_app
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import FormattedTextControl, Layout, Window

    if __package__:
        from .picker_style import fit, picker_style, session_age, session_row
    else:
        from picker_style import fit, picker_style, session_age, session_row

    home = Path(get_hermes_home()).absolute() if home is None else home
    index = 0
    query = ""
    error = ""
    keys = KeyBindings()

    def visible():
        needle = query.casefold()
        return [row for row in rows if needle in (title(row) + " " + row["id"]).casefold()] if needle else rows

    def content():
        size = get_app().output.get_size()
        width = min(size.columns, 128)
        matches = visible()
        total = len(matches)
        pinned_count = sum(bool(row.get("pinned")) for row in matches)
        count = f"{total} of {len(rows)}" if query else str(total)
        fragments = [("class:heading", fit("Sessions", width) + "\n"),
                     ("class:muted", fit(f"{count} resumable · {pinned_count} pinned", width) + "\n")]
        if error:
            fragments.append(("class:error", fit(error, width) + "\n"))
        if query:
            fragments.append(("class:muted", fit(f"Search: {query}", width) + "\n"))

        space = size.rows - 3 - bool(query) - bool(error)  # header, count, footer
        # Reserve room for scroll indicators, but keep the selection visible.
        room = min(12, max(1, space))
        show_scroll = total > room and space >= 3
        if show_scroll:
            room = min(12, space - 2)
        start = max(0, min(index - room // 2, total - room))
        stop = min(total, start + room)
        if show_scroll and start:
            fragments.append(("class:muted", fit(f"↑ {start} more above", width) + "\n"))
        now = time()
        for position in range(start, stop):
            row = matches[position]
            label = title(row)
            fragments.extend(session_row(
                width=width, number=position + 1, selected=position == index,
                sid=clean_label(row["id"]), age=session_age(row.get("started_at"), now),
                count=row.get("message_count"), title=label,
                pin=STAR if row.get("pinned") else "",
            ))
            fragments.append(("", "\n"))
        if show_scroll and stop < total:
            fragments.append(("class:muted", fit(f"↓ {total - stop} more below", width) + "\n"))
        if not matches:
            fragments.append(("class:muted", fit("No matching sessions" if query else "No sessions", width) + "\n"))

        if width >= 70:
            for hotkey, hint in (("↑↓", " move · "), ("Enter", " resume · "),
                                 ("Ctrl-P", " pin/unpin · "), ("Esc", " close · type to filter")):
                fragments.extend((("class:hotkey", hotkey), ("class:muted", hint)))
        else:
            fragments.append(("class:muted", fit("↑↓ Enter Ctrl-P Esc · type to filter", width)))
        return fragments

    @keys.add("up")
    def up(event):
        nonlocal index
        index = max(0, index - 1)

    @keys.add("down")
    def down(event):
        nonlocal index
        index = min(max(0, len(visible()) - 1), index + 1)

    @keys.add("enter")
    def enter(event):
        selected = visible()
        if selected:
            event.app.exit(result=selected[index])

    @keys.add("escape")
    @keys.add("c-c")
    @keys.add("c-d")
    def cancel(event):
        event.app.exit(result=None)

    @keys.add("c-p")
    def toggle(event):
        nonlocal rows, index, error
        selected = visible()
        if not selected:
            return
        try:
            set_pin(selected[index]["id"], not bool(selected[index].get("pinned")),
                    exact=True, home=home, visible_only=True)
            rows = session_rows(recent=True, home=home)
            index = 0
            error = ""
        except (PinsError, OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
            error = clean_label(exc)

    @keys.add("backspace")
    def erase(event):
        nonlocal query, index
        query, index = query[:-1], 0

    @keys.add("<any>")
    def search(event):
        nonlocal query, index
        if event.data.isprintable():
            query, index = query + event.data, 0

    body = Window(FormattedTextControl(content, focusable=True, show_cursor=False),
                  wrap_lines=False, dont_extend_height=True, always_hide_cursor=True)
    return Application(
        layout=Layout(body), key_bindings=keys, style=picker_style(),
        erase_when_done=True, input=input, output=output,
    ).run()


def setup_cli(parser):
    parser.add_argument("action", nargs="?", choices=["pick", "list", "find", "pin", "unpin"], default="pick")
    parser.add_argument("session_id", metavar="selector-or-query", nargs="?",
                        help="Search words for find, or exact ID/title or unique ID prefix for pin/unpin (quote spaces)")
    parser.add_argument("--print", dest="print_only", action="store_true", help="Print the selected resume command instead of launching Hermes")


def cli(args):
    try:
        if args.action in {"pin", "unpin"}:
            if not args.session_id:
                raise PinsError(f"Usage: hermes pins {args.action} <full-id-or-title>")
            row = set_pin(args.session_id, args.action == "pin")
            print(f"{'★ Pinned' if args.action == 'pin' else 'Unpinned'}: {title(row)}")
            return 0
        home = Path(get_hermes_home()).absolute()
        if args.action == "find":
            print(discovery_text(args.session_id or "", home))
            return 0
        if args.session_id:
            raise PinsError("A session selector is accepted only with pin or unpin.")
        rows = session_rows(recent=args.action == "pick", home=home)
        if args.action == "list":
            from rich.console import Console
            console = Console()
            for row in rows:
                console.print(f"{STAR} {title(row)}", style="bold yellow", markup=False, highlight=False)
                # Keep the copyable line literal: no Rich wrapping or emoji replacement.
                print(resume_line(row["id"], home=home))
            if not rows:
                console.print("No pinned chats in this list. Use /pin in Hermes.")
            return 0
        if not rows:
            print("No chats yet. Send a message in Hermes first.")
            return 0
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise PinsError("The picker needs a terminal. Use hermes pins list for plain output.")
        selected = picker(rows, home=home)
        if selected is None:
            return 0
        if args.print_only:
            print(resume_command(selected["id"], home=home))
            return 0
        path = resume_home(home)
        executable = shutil.which("hermes")
        if not executable:
            raise PinsError("Cannot find the Hermes executable in PATH.")
        # No shell, no option-shaped ID injection, and no sticky-profile redirect.
        return subprocess.call([executable, *resume_argv(selected["id"], home)],
                               env=dict(os.environ, HERMES_HOME=path))
    except (PinsError, OSError, RuntimeError, ValueError, sqlite3.Error, EOFError) as exc:
        print(command_error(exc), file=sys.stderr)
        return 1


def register(ctx):
    ctx.register_command("pin", command_pin, description="★ Pin this chat or another by exact title or session ID",
                         args_hint="[title-or-id]")

    def unpin(raw_args: str, *, session_id: str = "", platform: str = ""):
        return command_pin(raw_args, session_id=session_id, platform=platform, pinned=False)

    def pins(raw_args: str, *, platform: str = ""):
        return command_pins(ctx, raw_args, platform=platform)

    ctx.register_command("unpin", unpin, description="Unpin this chat or another by exact title or session ID",
                         args_hint="[title-or-id]")
    ctx.register_command("pins", pins, description="★ Find or manage pinned chats", args_hint="[list|manage|find words]")
    ctx.register_command("session-pins-ui", command_pins_ui, description="Session Pins selector data (local)")
    ctx.register_tool(
        name="session_pins_manage", toolset="session-pins",
        schema={"name": "session_pins_manage",
                "description": "Find visible local-profile chats by title words or ID text without returning transcript text, "
                               "or pin/unpin user-selected exact IDs. Echo the scope returned by find for pin/unpin. "
                               "If several matches fit, show choices before changing pins.",
                "parameters": {"type": "object", "required": ["action"], "additionalProperties": False,
                               "properties": {
                                   "action": {"type": "string", "enum": ["find", "pin", "unpin"]},
                                   "query": {"type": "string", "maxLength": MAX_QUERY},
                                   "limit": {"type": "integer", "minimum": 1, "maximum": MAX_PAGE},
                                   "offset": {"type": "integer", "minimum": 0},
                                   "scope": {"type": "string", "description": "Required for pin/unpin: copy the scope "
                                             "from the find result that supplied the selected IDs."},
                                   "ids": {"type": "array", "minItems": 1, "maxItems": MAX_BULK,
                                           "items": {"type": "string", "minLength": 1}},
                               }}},
        handler=lambda args, *, session_id="": discovery_tool(ctx, args, session_id=session_id),
    )
    ctx.register_cli_command("pins", "★ Pick, resume, or manage pinned Hermes chats", setup_cli, cli)
