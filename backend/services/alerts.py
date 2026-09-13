"""Persistent alert log with per-trading-day de-duplication."""
from __future__ import annotations

import json
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any

from . import market_clock as clock

_lock = threading.Lock()
_alerts: deque[dict] = deque(maxlen=300)
_seen: dict[str, dict] = {}  # key -> {ts, score, day}
_seen_ttl = 30 * 60  # 30 min

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
ALERTS_FILE = DATA_DIR / "alerts.json"
_MAX_PERSIST = 200

_loaded = False


def _key(code: str, market: str, kind: str) -> str:
    return f"{code}.{market}:{kind}"


def _today() -> str:
    try:
        return clock.now_cn().strftime("%Y-%m-%d")
    except Exception:
        return time.strftime("%Y-%m-%d")


def _load() -> None:
    """Restore a previous run's alerts once so a restart keeps history.
    Caller must hold _lock."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        if not ALERTS_FILE.exists():
            return
        with open(ALERTS_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        for item in reversed(saved.get("alerts", [])):
            if isinstance(item, dict) and item.get("id"):
                _alerts.append(item)
    except Exception:
        pass  # a corrupt log must never break the API


def _persist() -> None:
    """Caller must hold _lock. Best-effort; never raise into the monitor loop."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = ALERTS_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"alerts": list(_alerts)[:_MAX_PERSIST]}, f,
                      ensure_ascii=False, indent=2)
        tmp.replace(ALERTS_FILE)
    except Exception:
        pass


def push_alert(alert: dict) -> dict | None:
    now = time.time()
    code = str(alert.get("code", ""))
    market = str(alert.get("market", ""))
    kind = str(alert.get("kind", "info"))
    k = _key(code, market, kind)
    score = float(alert.get("score") or 50)
    today = _today()

    with _lock:
        _load()
        prev = _seen.get(k)
        if prev and prev.get("day") == today and now - prev["ts"] < _seen_ttl:
            # only re-alert if meaningfully stronger
            if abs(score - 50) <= abs(float(prev.get("score", 50)) - 50) + 8:
                return None
        _seen[k] = {"ts": now, "score": score, "day": today}
        item = {
            **alert,
            "id": str(uuid.uuid4())[:8],
            "ts": now,
            "time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        _alerts.appendleft(item)
        _persist()
        return item


def list_alerts(limit: int = 50) -> list[dict]:
    with _lock:
        _load()
        return list(_alerts)[:limit]


def clear_alerts() -> int:
    with _lock:
        n = len(_alerts)
        _alerts.clear()
        _seen.clear()
        _persist()
        return n
