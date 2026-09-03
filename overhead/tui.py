from __future__ import annotations

import curses
import threading
from typing import Any

from . import client
from .geo import format_alt, format_coords, format_miles
from .protocol import RINGS


class TuiState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.status: dict[str, Any] = {}
        self.message = ""
        self.running = True
        self.generation = 0
        self.mode = "main"
        self.prompt = ""

    def snapshot(self) -> tuple[dict[str, Any], str, int, str, str]:
        with self.lock:
            return dict(self.status), self.message, self.generation, self.mode, self.prompt

    def update(self, payload: dict[str, Any]) -> None:
        with self.lock:
            data = {k: v for k, v in payload.items() if k != "event"}
            self.status.update(data)
            self.generation += 1

    def note(self, message: str) -> None:
        with self.lock:
            self.message = message
            self.generation += 1

    def set_mode(self, mode: str, prompt: str = "") -> None:
        with self.lock:
            self.mode = mode
            self.prompt = prompt
            self.generation += 1


def _follow(state: TuiState) -> None:
    while state.running:
        try:
            for event in client.follow():
                if not state.running:
                    return
                state.update(event)
        except Exception as exc:
            if not state.running:
                return
            state.note(str(exc))
            threading.Event().wait(0.4)


def _rpc(state: TuiState, op: str, **fields: Any) -> None:
    try:
        reply = client.request(op, **fields)
        err = str(reply.get("error") or "")
        if err:
            state.note(err)
        elif op == "locate":
            loc = reply.get("location") or {}
            state.note(f"location {loc.get('label') or format_coords(loc.get('lat', 0), loc.get('lon', 0))}")
        elif op == "location":
            if fields.get("clear"):
                state.note("location cleared")
            else:
                loc = reply.get("location") or {}
                state.note(f"location {loc.get('label') or ''}")
        state.update(reply)
    except Exception as exc:
        state.note(str(exc))


def _kick(state: TuiState, op: str, **fields: Any) -> None:
    threading.Thread(target=_rpc, args=(state, op), kwargs=fields, daemon=True).start()


def run_tui() -> None:
    client.start_daemon()
    state = TuiState()
    state.update(client.request("status"))
    thread = threading.Thread(target=_follow, args=(state,), daemon=True)
    thread.start()
    curses.wrapper(lambda stdscr: _loop(stdscr, state))
    state.running = False


def _needs_consent(status: dict[str, Any]) -> bool:
    return not status.get("location") and str(status.get("consent") or "none") == "none"


def _loop(stdscr: curses.window, state: TuiState) -> None:
    curses.curs_set(0)
    curses.use_default_colors()
    stdscr.leaveok(True)
    stdscr.keypad(True)
    stdscr.timeout(80)
    if curses.has_colors():
        curses.init_pair(1, curses.COLOR_YELLOW, -1)
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        curses.init_pair(3, curses.COLOR_CYAN, -1)
        curses.init_pair(4, curses.COLOR_RED, -1)

    last_frame: tuple[Any, ...] | None = None
    last_size = (-1, -1)

    while state.running:
        try:
            key = stdscr.getch()
        except KeyboardInterrupt:
            break
        status, note, generation, mode, prompt = state.snapshot()
        if mode == "prompt":
            if key in (27,):
                state.set_mode("main")
                curses.curs_set(0)
            elif key in (curses.KEY_ENTER, 10, 13):
                value = prompt.strip()
                state.set_mode("main")
                curses.curs_set(0)
                if value:
                    _kick(state, "location", query=value)
            elif key in (curses.KEY_BACKSPACE, 127, 8):
                state.set_mode("prompt", prompt[:-1])
            elif 32 <= key <= 126:
                state.set_mode("prompt", prompt + chr(key))
            key = -1
        elif key in (ord("q"), ord("Q")):
            break
        elif key in (ord(" "),):
            _kick(state, "stop" if status.get("watching") else "start")
        elif key in (ord("a"), ord("A")):
            state.note("requesting location…")
            _kick(state, "locate")
        elif key in (ord("m"), ord("M")):
            state.set_mode("prompt", "")
            curses.curs_set(1)
        elif key in (ord("c"), ord("C")):
            _kick(state, "location", clear=True)
        elif key in (ord("n"), ord("N")):
            _kick(state, "notify", enabled=not bool(status.get("notify")))
        elif key in (ord("r"), ord("R")):
            _kick(state, "poll")
        elif key in (ord("1"), ord("5"), ord("0")):
            ring = 10 if key == ord("0") else int(chr(key))
            current = [int(item) for item in (status.get("rings") or list(RINGS))]
            if ring in current:
                current = [item for item in current if item != ring] or [ring]
            else:
                current.append(ring)
                current.sort()
            _kick(state, "rings", rings=current)

        try:
            height, width = stdscr.getmaxyx()
        except curses.error:
            continue
        status, note, generation, mode, prompt = state.snapshot()
        loc = status.get("location")
        loc_key = () if not loc else (loc.get("lat"), loc.get("lon"), loc.get("source"))
        planes = tuple(
            (row.get("hex"), row.get("miles"), row.get("callsign"), row.get("alt_ft"))
            for row in (status.get("aircraft") or [])[:24]
        )
        frame = (
            generation,
            height,
            width,
            note,
            mode,
            prompt,
            status.get("watching"),
            status.get("error"),
            loc_key,
            tuple(status.get("rings") or []),
            status.get("notify"),
            status.get("provider"),
            planes,
        )
        if frame == last_frame:
            continue
        resized = (height, width) != last_size
        last_frame = frame
        last_size = (height, width)
        _draw(stdscr, status, note, mode, prompt, clear=resized)


def _put(stdscr: curses.window, row: int, text: str, width: int, attr: int = 0, col: int = 0) -> None:
    if row < 0 or width <= 0 or col >= width:
        return
    try:
        stdscr.addnstr(row, col, text[: max(0, width - col)], max(0, width - col), attr)
    except curses.error:
        pass


def _ring_marks(rings: list[int]) -> str:
    parts = []
    for ring in RINGS:
        mark = "[x]" if ring in rings else "[ ]"
        parts.append(f"{mark} {ring}")
    return "  ".join(parts) + " mi"


def _draw(
    stdscr: curses.window,
    status: dict[str, Any],
    note: str,
    mode: str,
    prompt: str,
    *,
    clear: bool = False,
) -> None:
    try:
        if clear:
            stdscr.clear()
        else:
            stdscr.erase()
    except curses.error:
        return
    try:
        height, width = stdscr.getmaxyx()
    except curses.error:
        return
    cols = max(1, width - 1)
    watching = bool(status.get("watching"))
    loc = status.get("location") or {}
    error = str(status.get("error") or "")
    rings = [int(item) for item in (status.get("rings") or list(RINGS))]
    title = " overhead  [" + ("watch" if watching else "idle") + "]"
    if loc:
        title += "  " + str(loc.get("label") or format_coords(float(loc.get("lat") or 0), float(loc.get("lon") or 0)))
        if loc.get("source"):
            title += f"  {loc.get('source')}"
    if status.get("provider"):
        title += f"  {status.get('provider')}"
    _put(stdscr, 0, title, cols, curses.color_pair(2 if watching else 0) | curses.A_BOLD)
    _put(
        stdscr,
        1,
        "rings  " + _ring_marks(rings) + ("   notify on" if status.get("notify") else "   notify off"),
        cols,
        curses.color_pair(3),
    )
    help_line = "space watch   a allow location   m set location   1/5/0 rings   n notify   r refresh   q quit"
    _put(stdscr, 2, help_line, cols, curses.color_pair(3))
    if mode == "prompt":
        _put(stdscr, 3, "location: " + prompt, cols, curses.color_pair(1) | curses.A_BOLD)
    elif error:
        _put(stdscr, 3, error, cols, curses.color_pair(1))
    elif note:
        _put(stdscr, 3, note, cols)
    elif _needs_consent(status):
        _put(stdscr, 3, "Allow location (a) or type coordinates / a place (m). Stored locally.", cols, curses.color_pair(1))

    aircraft = list(status.get("aircraft") or [])
    body_top = 5
    if not aircraft:
        msg = "Watching the sky…" if watching and loc else "No aircraft in range."
        if not loc:
            msg = "No location yet."
        _put(stdscr, body_top, msg, cols, curses.A_DIM)
    else:
        for offset, item in enumerate(aircraft):
            row = body_top + offset
            if row >= height:
                break
            miles = float(item.get("miles") or 0)
            ring = item.get("ring")
            attr = curses.color_pair(4) | curses.A_BOLD if ring == 1 else (
                curses.color_pair(1) if ring == 5 else (curses.color_pair(2) if ring == 10 else 0)
            )
            callsign = str(item.get("callsign") or item.get("hex") or "")
            kind = str(item.get("type") or "")
            alt = format_alt(item.get("alt_ft"), bool(item.get("ground")))
            gs = item.get("gs_kt")
            speed = f"{gs:.0f} kt" if isinstance(gs, (int, float)) else ""
            line = f"{format_miles(miles):>7}  {callsign:<8}  {kind:<4}  {alt:<11}  {speed}"
            _put(stdscr, row, line, cols, attr)
    try:
        stdscr.refresh()
    except curses.error:
        pass
