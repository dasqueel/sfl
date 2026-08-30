"""Durable store for your own reads on players.

Everything else in this project can be rebuilt from the projection sources.
This file cannot: gem/fade tags and hand-edited projections exist only
because you typed them. That shapes every decision here — writes are atomic,
a damaged file is never overwritten, and nothing is deleted on a parse error.

Keepers live here too. They are the highest-stakes entry in the file: a
wrong keeper price does not just misprice that player, it shifts the
inflation multiplier applied to every other price on the board.

The store is a flat JSON document keyed by "POS|Player Name", the same
identifier the browser uses, so a key is readable and greppable rather than
an opaque id that means nothing when you open the file yourself.
"""

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

VALID_TAGS = ("gem", "fade")
SECTIONS = ("tags", "projections", "keepers")

# Serialises read-modify-write cycles so two open tabs cannot clobber each
# other's last change. Flask's dev server is threaded by default.
_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def empty(season: int) -> dict:
    return {
        "season": season,
        "updated": None,
        "tags": {},
        "projections": {},
        "keepers": {},
    }


def load(path=None, season: int = None) -> dict:
    """Read the store, degrading rather than raising.

    A missing file is simply an empty store. A damaged one returns empty
    *plus* an `error` key — callers refuse to write over it, so a corrupt
    file can be repaired by hand instead of being silently replaced.
    """
    from config import RANKINGS_PATH, SEASON

    path = Path(path or RANKINGS_PATH)
    season = SEASON if season is None else season

    if not path.exists():
        return empty(season)

    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as bad:
        return {**empty(season), "error": f"could not read {path.name}: {bad}"}

    if not isinstance(data, dict):
        return {**empty(season), "error": f"{path.name} is not a JSON object"}

    store = empty(season)
    store["season"] = data.get("season", season)
    store["updated"] = data.get("updated")
    for field in SECTIONS:
        value = data.get(field)
        if isinstance(value, dict):
            store[field] = value
    return store


def save(data: dict, path=None) -> dict:
    """Write the store atomically.

    The temp-file-then-rename dance matters here more than usual: os.replace
    is atomic on POSIX, so a crash or a full disk leaves the previous version
    intact rather than a half-written file. Writing in place could destroy
    hours of prep in the one place there is no backup.
    """
    from config import RANKINGS_PATH

    path = Path(path or RANKINGS_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "season": data.get("season"),
        "updated": _now(),
        "tags": data.get("tags") or {},
        "projections": data.get("projections") or {},
        "keepers": data.get("keepers") or {},
    }

    handle, temp = tempfile.mkstemp(
        dir=str(path.parent), prefix=".rankings-", suffix=".tmp"
    )
    try:
        with os.fdopen(handle, "w") as out:
            json.dump(payload, out, indent=2, sort_keys=True)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    except BaseException:
        # Never leave debris beside the real file.
        if os.path.exists(temp):
            os.unlink(temp)
        raise

    return payload


def _guard(store: dict) -> None:
    if store.get("error"):
        raise ValueError(
            f"refusing to overwrite a damaged rankings file — {store['error']}"
        )


def set_tag(key: str, tag, path=None, season: int = None) -> dict:
    """Set, change, or clear one player's tag. `tag=None` clears it."""
    if not key or "|" not in key:
        raise ValueError("key must look like 'POS|Player Name'")
    if tag is not None and tag not in VALID_TAGS:
        raise ValueError(f"tag must be one of {', '.join(VALID_TAGS)}, or null")

    with _lock:
        store = load(path, season)
        _guard(store)
        if tag is None:
            store["tags"].pop(key, None)
        else:
            store["tags"][key] = tag
        return save(store, path)


def set_projection(key: str, points, path=None, season: int = None) -> dict:
    """Set or clear one hand-edited projection. `points=None` restores the blend."""
    if not key or "|" not in key:
        raise ValueError("key must look like 'POS|Player Name'")

    if points is not None:
        try:
            points = float(points)
        except (TypeError, ValueError):
            raise ValueError(f"projection for {key} must be a number")
        if not 0 <= points <= 1000:
            raise ValueError(f"projection for {key} must be between 0 and 1000")

    with _lock:
        store = load(path, season)
        _guard(store)
        if points is None:
            store["projections"].pop(key, None)
        else:
            store["projections"][key] = points
        return save(store, path)


def set_keeper(
    key: str, paid, path=None, season: int = None, mine: bool = True
) -> dict:
    """Record or remove one keeper. `paid=None` removes him.

    Argument order deliberately matches set_tag and set_projection —
    (key, value, path, season) — with `mine` trailing as a keyword. A
    third positional here would be a path-shaped hole that silently
    swallows a path.

    `paid` is the acquisition price, not this year's cost — the doubling
    rule lives in config so the sheet can show "$4 -> $8" and so a league
    that changes the rule needs one edit, not a re-entry of every keeper.
    """
    if not key or "|" not in key:
        raise ValueError("key must look like 'POS|Player Name'")

    if paid is not None:
        try:
            paid = float(paid)
        except (TypeError, ValueError):
            raise ValueError(f"keeper price for {key} must be a number")
        if not 0 <= paid <= 500:
            raise ValueError(f"keeper price for {key} must be between 0 and 500")

    with _lock:
        store = load(path, season)
        _guard(store)
        if paid is None:
            store["keepers"].pop(key, None)
        else:
            store["keepers"][key] = {"paid": paid, "mine": bool(mine)}
        return save(store, path)


def clear(field: str, path=None, season: int = None) -> dict:
    """Empty one section wholesale."""
    if field not in SECTIONS:
        raise ValueError(f"field must be one of {', '.join(SECTIONS)}")

    with _lock:
        store = load(path, season)
        _guard(store)
        store[field] = {}
        return save(store, path)


def counts(store: dict) -> dict:
    tags = store.get("tags") or {}
    keepers = store.get("keepers") or {}
    return {
        "gems": sum(1 for t in tags.values() if t == "gem"),
        "fades": sum(1 for t in tags.values() if t == "fade"),
        "projections": len(store.get("projections") or {}),
        "keepers": len(keepers),
        "mine": sum(1 for k in keepers.values() if k.get("mine")),
    }
