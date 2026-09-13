"""In-memory alert log with de-duplication for the trading session."""
from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from typing import Any

_lock = threading.Lock()
_alerts: deque[dict] = deque(maxlen=300)
_seen: dict[str, dict] = {}  # key -> {ts, score}
_seen_ttl = 30 * 60  # 30 min


def _key(code: str, market: str, kind: str) -> str:
    return f"{code}.{market}:{kind}"


def push_alert(alert: dict) -> dict | None:
    now = time.time()
    code = str(alert.get("code", ""))
    market = str(alert.get("market", ""))
    kind = str(alert.get("kind", "info"))
    k = _key(code, market, kind)
    score = float(alert.get("score") or 50)

    with _lock:
        prev = _seen.get(k)
        if prev and now - prev["ts"] < _seen_ttl:
            # only re-alert if meaningfully stronger
            if abs(score - 50) <= abs(float(prev.get("score", 50)) - 50) + 8:
                return None
        _seen[k] = {"ts": now, "score": score}
        item = {
            **alert,
            "id": str(uuid.uuid4())[:8],
            "ts": now,
            "time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        _alerts.appendleft(item)
        return item


def list_alerts(limit: int = 50) -> list[dict]:
    with _lock:
        return list(_alerts)[:limit]


def clear_alerts() -> int:
    with _lock:
        n = len(_alerts)
        _alerts.clear()
        _seen.clear()
        return n
