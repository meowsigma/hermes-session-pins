"""Small, local-only session pin manager for Hermes. No core patches or model calls."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
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


class PinsError(RuntimeError):
    """An actionable error safe to show in a command response."""


def clean_label(value: object, limit: int = 90) -> str:
    """Keep stored titles from injecting terminal escape/control sequences."""
    text = "".join(c for c in str(value or "") if not unicodedata.category(c).startswith("C"))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def title(row: dict) -> str:
    return clean_label(row.get("title") or row.get("preview")) or "Untitled chat"


@contextmanager
def database(*, writable: bool = False):
    # Resolve per call: one process can serve several Hermes profiles.
    path = Path(get_hermes_home()) / "state.db"
    if not path.is_file():
        raise PinsError("No sessions yet. Send a message in Hermes, then use /pin.")
    with SessionDB(db_path=path, read_only=not writable) as db:
        if not hasattr(db, "set_session_pinned"):
            raise PinsError("This Hermes build lacks session pins. Update Hermes first.")
        yield db


def resolve(db, value: str) -> dict:
    sid = db.resolve_session_id(value.strip())
    if not sid:
        raise PinsError("Session not found, or that ID prefix is ambiguous. Use the full session ID.")
    row = db.get_session(sid)
    if not row:
        raise PinsError("That session no longer exists.")
    return row


def set_pin(value: str, pinned: bool) -> dict:
    if not value.strip():
        raise PinsError("No current session yet. Send a message first, or provide a session ID.")
    with database(writable=True) as db:
        row = resolve(db, value)
        if not db.set_session_pinned(row["id"], pinned):
            raise PinsError("Hermes could not update that session's pin.")
        updated = db.get_session(row["id"])
        if updated is None or bool(updated.get("pinned")) != pinned:
            raise PinsError("Hermes did not confirm the pin change. Try again.")
        return updated


def session_rows(*, recent: bool = False) -> list[dict]:
    with database() as db:
        # Back-fill ALL durable pins before any UI paging; old pins must not disappear
        # behind thousands of recent worker sessions. Core projects compression tips.
        rows = db.list_sessions_rich(
            limit=40 if recent else 1, include_pinned=True, order_by_last_active=True,
        )
    by_id = {row["id"]: row for row in rows if recent or row.get("pinned")}
    return sorted(by_id.values(), key=lambda r: (
        not bool(r.get("pinned")),
        -float(r.get("last_active") or r.get("started_at") or 0),
        r["id"],
    ))


def resume_command(sid: str, *, terminal: bool = False) -> str:
    return shlex.join(["hermes", "chat", "--resume", sid]) if terminal else f"/resume {sid}"


def require_local(platform: str) -> None:
    # A remote chat must not use this local terminal manager to enumerate or
    # modify unrelated private conversations. Adapter identity is not a grant.
    if platform not in LOCAL_SURFACES:
        raise PinsError("Session Pins is for local Hermes terminals and Desktop, not messaging chats.")


def command_pin(raw_args: str, *, session_id: str = "", platform: str = "", pinned: bool = True) -> str:
    try:
        require_local(platform)
        value = raw_args.strip() or session_id
        row = set_pin(value, pinned)
        if pinned:
            return f"{STAR} Pinned: {title(row)}\nFind it with /pins or the terminal picker: hermes pins"
        return f"Unpinned: {title(row)}"
    except (PinsError, OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
        return f"Session Pins: {exc}"


def command_pins(ctx, raw_args: str, *, platform: str = "") -> str:
    try:
        require_local(platform)
        mode = raw_args.strip().lower()
        if mode not in {"", "list", "manage"}:
            return "Usage: /pins [list|manage]. Pin this chat with /pin; remove its pin with /unpin."
        rows = session_rows()
        if not rows:
            return "No pinned chats. Use /pin in a chat you want to keep."
        listing = "\n".join(f"{STAR} {title(row)}\n  {resume_command(row['id'])}" for row in rows)
        if mode == "list":
            return listing
        picked = ctx.ask_choice("Pinned chats — choose a chat", [
            {"value": row["id"], "label": f"{STAR} {title(row)}", "description": row["id"]}
            for row in rows
        ])
        if not picked:
            return "No chat selected. /pins list shows your pins without a picker."
        row = next((r for r in rows if r["id"] == picked), None)
        if row is None:
            return "No chat selected."
        if mode == "manage":
            action = ctx.ask_choice(f"{STAR} {title(row)}", [
                {"value": "resume", "label": "Show resume command"},
                {"value": "unpin", "label": "Unpin this chat"},
            ])
            if action == "unpin":
                return f"Unpinned: {title(set_pin(row['id'], False))}"
            if action != "resume":
                return "No change."
        # Plugin handlers return text, not frontend session-switch directives.
        # Never pretend this switches the active TUI or inject a model turn.
        return f"{STAR} {title(row)}\nRun this in your current chat:\n{resume_command(row['id'])}"
    except (PinsError, OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
        return f"Session Pins: {exc}"


def picker(rows: list[dict], *, input=None, output=None) -> dict | None:
    """Keyboard-only picker; using Hermes's existing prompt_toolkit dependency."""
    from prompt_toolkit import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import HSplit, Layout
    from prompt_toolkit.styles import Style
    from prompt_toolkit.widgets import Frame, Label

    index = 0
    query = ""
    error = ""
    keys = KeyBindings()

    def visible():
        return [row for row in rows if query.casefold() in (title(row) + " " + row["id"]).casefold()]

    def content():
        selected = visible()
        start = max(0, index - 6)
        fragments = []
        for position, row in enumerate(selected[start:start + 12], start):
            mark = STAR if row.get("pinned") else " "
            style = "class:selected" if position == index else "class:pinned" if row.get("pinned") else ""
            fragments.append((style, f"{'›' if position == index else ' '} {mark} {title(row)}  [{clean_label(row['id'], 36)}]\n"))
        if not selected:
            fragments.append(("class:muted", "  No matching chats\n"))
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
            set_pin(selected[index]["id"], not bool(selected[index].get("pinned")))
            rows = session_rows(recent=True)
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

    body = HSplit([
        Label("★ Pinned chats first · recent chats below"),
        Label(lambda: f"Search: {query}"),
        Label(content),
        Label(lambda: error or "↑/↓ select · Enter resume · Ctrl-P pin/unpin · Esc close"),
    ])
    return Application(
        layout=Layout(Frame(body, title="Hermes Session Pins")), key_bindings=keys,
        style=Style.from_dict({"pinned": "ansiyellow bold", "selected": "reverse bold", "muted": "ansibrightblack"}),
        full_screen=True, input=input, output=output,
    ).run()


def setup_cli(parser):
    parser.add_argument("action", nargs="?", choices=["pick", "list", "pin", "unpin"], default="pick")
    parser.add_argument("session_id", nargs="?", help="Session ID or unambiguous prefix for pin/unpin")
    parser.add_argument("--print", dest="print_only", action="store_true", help="Print the selected resume command instead of launching Hermes")


def cli(args):
    try:
        if args.action in {"pin", "unpin"}:
            if not args.session_id:
                raise PinsError(f"Usage: hermes pins {args.action} <session-id>")
            row = set_pin(args.session_id, args.action == "pin")
            print(f"{'★ Pinned' if args.action == 'pin' else 'Unpinned'}: {title(row)}")
            return 0
        if args.session_id:
            raise PinsError("A session ID is accepted only with pin or unpin.")
        rows = session_rows(recent=args.action == "pick")
        if args.action == "list":
            from rich.console import Console
            console = Console()
            for row in rows:
                console.print(f"{STAR} {title(row)}", style="bold yellow", markup=False, highlight=False)
                console.print(resume_command(row["id"], terminal=True), markup=False, highlight=False)
            if not rows:
                console.print("No pinned chats. Use /pin in Hermes.")
            return 0
        if not rows:
            print("No chats yet. Send a message in Hermes first.")
            return 0
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise PinsError("The picker needs a terminal. Use hermes pins list for plain output.")
        selected = picker(rows)
        if selected is None:
            return 0
        if args.print_only:
            print(resume_command(selected["id"], terminal=True))
            return 0
        executable = shutil.which("hermes")
        if not executable:
            raise PinsError("Cannot find the Hermes executable in PATH.")
        # No shell; the active HERMES_HOME stays intact for named/custom profiles.
        return subprocess.call([executable, "chat", "--resume", selected["id"]])
    except (PinsError, OSError, RuntimeError, ValueError, sqlite3.Error, EOFError) as exc:
        print(f"Session Pins: {exc}", file=sys.stderr)
        return 1


def register(ctx):
    ctx.register_command("pin", command_pin, description="★ Pin this chat", args_hint="[session-id]")

    def unpin(raw_args: str, *, session_id: str = "", platform: str = ""):
        return command_pin(raw_args, session_id=session_id, platform=platform, pinned=False)

    def pins(raw_args: str, *, platform: str = ""):
        return command_pins(ctx, raw_args, platform=platform)

    ctx.register_command("unpin", unpin, description="Unpin this chat", args_hint="[session-id]")
    ctx.register_command("pins", pins, description="★ Find or manage pinned chats", args_hint="[list|manage]")
    ctx.register_cli_command("pins", "★ Pick, resume, or manage pinned Hermes chats", setup_cli, cli)
