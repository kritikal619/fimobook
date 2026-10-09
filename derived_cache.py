"""Shared, disposable statistics cache; requests never wait for DB aggregation."""
import fcntl
import hashlib
import json
import logging
import os
import tempfile
import threading
import time
from pathlib import Path

_STATES = {}
_LOCK = threading.Lock()
_READ_LOCK = threading.Lock()
_READ_CACHE = {}
_LOG = logging.getLogger(__name__)


def _signature(paths):
    parts = [1]
    for path in paths:
        try:
            info = os.stat(path)
            parts.append([str(path), info.st_mtime_ns, info.st_size])
        except OSError:
            parts.append([str(path), None])
    return hashlib.sha256(json.dumps(parts).encode()).hexdigest()


def _read(path):
    try:
        info = path.stat()
        signature = (info.st_mtime_ns, info.st_size, info.st_ino)
        with _READ_LOCK:
            cached = _READ_CACHE.get(str(path))
            if cached and cached[0] == signature:
                return cached[1]
            with path.open(encoding="utf-8") as stream:
                value = json.load(stream)
            if isinstance(value, dict) and isinstance(value.get("payload"), dict):
                _READ_CACHE[str(path)] = (signature, value)
                return value
    except (OSError, ValueError):
        pass
    return None


def _refresh(path, signature, build, state):
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.with_suffix(".lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return
            cached = _read(path)
            if cached and cached.get("signature") == signature:
                with _LOCK:
                    state["value"] = cached
                return
            started = time.monotonic()
            payload = build()
            value = {"signature": signature, "payload": payload}
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                             prefix=path.name + ".", delete=False) as stream:
                temporary = stream.name
                json.dump(value, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            temporary = None
            with _LOCK:
                state["value"] = value
            _LOG.warning("Derived cache %s refreshed in %.3fs", path.name, time.monotonic() - started)
    except Exception:
        _LOG.exception("Derived cache refresh failed: %s", path.name)
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass
        with _LOCK:
            state["running"] = False
            state["retry_at"] = time.monotonic() + 15


def shared_derived_cache(instance_path, name, source_paths, build, fallback):
    """Serve saved results or cheap local data while one process refreshes.

    File signatures invalidate only on input changes, rather than every five
    minutes. A nonblocking flock serializes builders across Gunicorn workers.
    Atomic replacement keeps saved results available across service restarts.
    """
    path = Path(instance_path) / "derived_statistics" / (name + ".json")
    key = str(path)
    now = time.monotonic()
    with _LOCK:
        state = _STATES.setdefault(key, {"value": None, "checked_at": -10,
                                        "running": False, "retry_at": 0})
        if now - state["checked_at"] >= 2:
            signature = _signature(source_paths)
            saved = _read(path)
            if saved:
                state["value"] = saved
            state["checked_at"] = now
            value = state["value"]
            if (not value or value.get("signature") != signature) and not state["running"] and now >= state["retry_at"]:
                state["running"] = True
                threading.Thread(target=_refresh, args=(path, signature, build, state),
                                 name="derived-" + name, daemon=True).start()
        if state["value"] is None:
            state["value"] = {"signature": None, "payload": fallback()}
        return state["value"]["payload"]
