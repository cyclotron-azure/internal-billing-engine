"""Privacy-safe project-root label for a session, derived from its cwd history.

`session_repo_timeline` already stores the working directory of every hook event.
This module turns one session's cwd history into a single label naming the
project's ROOT folder (e.g. `local:Dashnoard`), or "" when there is nothing to
label. It is used only to explain `unknown` usage; it is never a repo key and is
never persisted -- it is recomputed from the timeline at query time.

Only one folder name is ever emitted: never a path, drive letter, `Users`/`home`,
a username, or a OneDrive folder. Paths come from other machines, so nothing here
touches the filesystem.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Sequence

from billing.otel.attribute import TIMELINE_TABLE

LOCAL_PREFIX = "local:"
HOME_LABEL = "local:(home)"
SCRATCHPAD_LABEL = "local:(scratchpad)"
OTHER_LABEL = "local:(other)"
CONTAINER_DIRS = frozenset(
    {"code", "src", "source", "repos", "projects", "dev", "git", "github", "workspace"}
)

_OUTER_NAMES = frozenset({"desktop", "documents", "downloads", "library", "cloudstorage"})
_MAX_LABEL = 100
_SPLIT = re.compile(r"[\\/]")
_DRIVE = re.compile(r"^[A-Za-z]:$")
_SLUG = re.compile(r"^[A-Za-z]--")
_LETTER = re.compile(r"^[A-Za-z]$")


def _raw_segments(cwd: str) -> list[str]:
    return [p for p in (x.strip() for x in _SPLIT.split(cwd)) if p]


def path_segments(cwd: str) -> list[str]:
    """Split a Windows/POSIX/UNC/WSL/MSYS path into segments, minus its root prefix."""
    segs = _raw_segments(cwd)
    if cwd.startswith(("\\\\", "//")):
        return segs[2:]  # UNC host and share
    if segs and _DRIVE.match(segs[0]):
        return segs[1:]
    if segs and segs[0] == "~":
        return segs[1:]
    if len(segs) >= 2 and segs[0].lower() == "mnt" and _LETTER.match(segs[1]):
        return segs[2:]
    if segs and cwd.startswith("/") and _LETTER.match(segs[0]):
        return segs[1:]
    return segs


def is_scratchpad(cwd: str) -> bool:
    """True for any Claude-internal directory (`.claude`, `Temp\\claude`, `T/claude`)."""
    seen_temp = False
    for seg in _SPLIT.split(cwd):
        low = seg.strip().lower()
        if low == ".claude" or (low == "claude" and seen_temp):
            return True
        if low in ("temp", "tmp", "t"):
            seen_temp = True
    return False


def _is_outer_folder(seg: str) -> bool:
    low = seg.lower()
    return low.startswith(("onedrive", "visual studio ")) or low in _OUTER_NAMES


def _home_len(segs: list[str]) -> int:
    if not segs:
        return 0
    low = segs[0].lower()
    if low in ("users", "home"):
        return 2 if len(segs) >= 2 else 1
    return 1 if low == "root" else 0


def _outer_zone(segs: list[str]) -> tuple[int, bool]:
    """(outer_len, has_outer_container) for the home prefix plus the outer run."""
    n = _home_len(segs)
    has_container = False
    while n < len(segs):
        low = segs[n].lower()
        if low in CONTAINER_DIRS:
            has_container = True
        elif not _is_outer_folder(segs[n]):
            break
        n += 1
    return n, has_container


def _usernames(cwds: list[str]) -> set[str]:
    names: set[str] = set()
    for segs in map(_raw_segments, cwds):  # raw: a UNC share may itself be `Users`
        for i in range(len(segs) - 1):
            if segs[i].lower() in ("users", "home"):
                names.add(segs[i + 1].lower())
    return names


def _is_prefix(anc: list[str], full: list[str]) -> bool:
    return len(anc) <= len(full) and [a.lower() for a in anc] == [f.lower() for f in full[: len(anc)]]


def _label(history: Sequence[tuple[str, str]]) -> str:
    rows = [(str(e or ""), str(c or "")) for e, c in history]
    start = next((c for e, c in rows if e == "SessionStart" and c.strip()), "")
    if not start:
        start = next((c for _, c in rows if c.strip()), "")
    if not start:
        return ""
    if is_scratchpad(start):
        return SCRATCHPAD_LABEL

    segs = path_segments(start)
    o, has_container = _outer_zone(segs)
    if len(segs) <= o:
        return HOME_LABEL

    cwds = [c for _, c in rows if c.strip()]
    cwd_segs = [path_segments(c) for c in cwds]

    candidates: list[int] = []
    if has_container:
        candidates.append(o)
    for i in range(o + 1, len(segs)):
        if segs[i].lower() in CONTAINER_DIRS:
            candidates.append(i - 1)
            break
    shortest = min(
        (
            len(cs)
            for c, cs in zip(cwds, cwd_segs)
            if not is_scratchpad(c) and len(cs) > o and _is_prefix(cs, segs)
        ),
        default=len(segs),
    )
    candidates.append(shortest - 1)

    seg = segs[min(candidates)]
    low = seg.lower()
    if (
        any(ch in seg for ch in ":/\\")
        or seg.startswith(".")
        or _SLUG.match(seg)
        or seg.startswith("-Users-")
        or "onedrive" in low
        or low in ("users", "home")
        or any(ord(ch) < 32 for ch in seg)
        or low in _usernames(cwds)
    ):
        return OTHER_LABEL
    return LOCAL_PREFIX + seg[:_MAX_LABEL]


def root_label(history: Sequence[tuple[str, str]]) -> str:
    """Label for one session's [(event, cwd), ...] history; "" if nothing to label."""
    try:
        return _label(history)
    except Exception:
        return ""


def load_session_labels(db: sqlite3.Connection) -> dict[str, str]:
    """{session_id: label} for every session with a non-empty label (one SELECT)."""
    cur = db.execute(
        f"SELECT session_id, event, cwd FROM {TIMELINE_TABLE} ORDER BY session_id, ts, seq"
    )
    by_session: dict[str, list[tuple[str, str]]] = {}
    for session_id, event, cwd in cur:
        by_session.setdefault(session_id, []).append((event or "", cwd or ""))
    labels = {sid: root_label(hist) for sid, hist in by_session.items()}
    return {sid: lab for sid, lab in labels.items() if lab}
