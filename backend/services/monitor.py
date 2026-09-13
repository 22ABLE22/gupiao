"""Background market-hours monitor: polls quotes, scores, emits alerts."""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

from . import alerts as alerts_svc
from . import data as data_svc
from . import market_clock as clock
from . import portfolio as pf_svc
from . import signal_engine as se

logger = logging.getLogger("monitor")

_state: dict[str, Any] = {
    "running": False,
    "thread_alive": False,
    "interval_sec": 45,
    "last_scan_at": None,
    "last_scan_iso": None,
    "last_phase": None,
    "scans": 0,
    "alerts_emitted": 0,
    "error": None,
    "watch_codes": [],
}
_thread: threading.Thread | None = None
_stop = threading.Event()
_lock = threading.Lock()

# score thresholds for alerting
ALERT_STRONG_BUY = 72
ALERT_BUY = 60
ALERT_STRONG_SELL = 35
ALERT_SELL = 42


def get_status() -> dict[str, Any]:
    phase = clock.market_phase()
    with _lock:
        st = {
            **_state,
            "thread_alive": bool(_thread and _thread.is_alive()),
            "server_phase": phase,
            "should_monitor": phase["is_trading"] and _state["running"],
        }
    return st


def _universe() -> list[tuple[str, str, float | None, float | None]]:
    pf = pf_svc.load()
    rows: list[tuple[str, str, float | None, float | None]] = []
    seen = set()
    for h in pf.get("holdings", []):
        key = (str(h["code"]), str(h.get("market", "")).upper())
        if key in seen:
            continue
        seen.add(key)
        rows.append((key[0], key[1], float(h.get("cost") or 0) or None, float(h.get("shares") or 0) or None))
    for w in pf.get("watchlist", []):
        key = (str(w["code"]), str(w.get("market", "")).upper())
        if key in seen:
            continue
        seen.add(key)
        rows.append((key[0], key[1], None, None))
    return rows


def _emit_from_score(item: dict) -> None:
    if not item.get("ok"):
        return
    score = float(item.get("score") or 50)
    tone = item.get("tone")
    name = item.get("name") or item.get("code")
    full = item.get("full") or f"{item.get('code')}.{item.get('market')}"

    kind = None
    title = None
    body = item.get("advice") or ""

    if score >= ALERT_STRONG_BUY:
        kind, title = "strong_buy", f"【买入关注】{name}"
    elif score >= ALERT_BUY:
        kind, title = "buy", f"【偏多】{name}"
    elif score <= ALERT_STRONG_SELL:
        kind, title = "strong_sell", f"【减仓/止损关注】{name}"
    elif score <= ALERT_SELL:
        kind, title = "sell", f"【偏空】{name}"
    else:
        # neutral: only alert on fresh cross events
        recent = item.get("recent_signals") or []
        if recent:
            s0 = recent[-1]
            if s0.get("kind") in ("buy", "sell"):
                kind = "signal_" + s0["kind"]
                title = f"【信号】{name} · {s0.get('name')}"

    if not kind:
        return

    top_factors = sorted(item.get("factors") or [], key=lambda x: abs(x.get("delta") or 0), reverse=True)[:4]
    lines = [
        f"{full} 现价 {item.get('price')} · 综合分 {score:.0f}（置信 {item.get('confidence')}%）",
        body,
    ]
    if item.get("stop_hint") is not None:
        lines.append(f"参考止损观察 {item.get('stop_hint')} / 目标观察 {item.get('target_hint')}（非指令）")
    if top_factors:
        lines.append("因子：" + "；".join(f"{f['name']}({f['delta']:+})" for f in top_factors))

    inserted = alerts_svc.push_alert({
        "code": item.get("code"),
        "market": item.get("market"),
        "full": full,
        "name": name,
        "kind": kind,
        "tone": tone,
        "title": title,
        "body": "\n".join(lines),
        "score": score,
        "confidence": item.get("confidence"),
        "price": item.get("price"),
        "advice": item.get("advice"),
        "stop_hint": item.get("stop_hint"),
        "target_hint": item.get("target_hint"),
        "factors": top_factors,
    })
    if inserted:
        with _lock:
            _state["alerts_emitted"] += 1
        logger.info("alert %s %s score=%.1f", kind, full, score)


def _check_price_lines(results: list[dict]) -> None:
    """Alert when a holding crosses its configured stop/take lines."""
    lines = {}
    for h in pf_svc.load().get("holdings", []):
        stop = h.get("stop_line")
        take = h.get("take_line")
        if stop or take:
            lines[(str(h["code"]), str(h.get("market", "")).upper())] = (
                float(stop) if stop else None,
                float(take) if take else None,
            )
    if not lines:
        return
    for item in results:
        if not item.get("ok"):
            continue
        key = (str(item.get("code")), str(item.get("market", "")).upper())
        pair = lines.get(key)
        if not pair:
            continue
        stop, take = pair
        price = float(item.get("price") or 0)
        if not price:
            continue
        base = {
            "code": item.get("code"),
            "market": item.get("market"),
            "full": item.get("full"),
            "name": item.get("name") or item.get("code"),
            "score": item.get("score"),
            "confidence": item.get("confidence"),
            "price": price,
            "stop_hint": item.get("stop_hint"),
            "target_hint": item.get("target_hint"),
        }
        if stop and price <= stop:
            alerts_svc.push_alert({
                **base,
                "kind": "price_break",
                "tone": "sell",
                "title": f"【跌破止损线】{base['name']}",
                "body": f"{base['full']} 现价 {price} ≤ 你设的提醒线 {stop}（预设提醒，非指令）\n"
                        + (item.get("advice") or ""),
                "advice": f"已跌破提醒线 {stop}，请按既定纪律评估，避免情绪化操作。",
            })
        if take and price >= take:
            alerts_svc.push_alert({
                **base,
                "kind": "price_target",
                "tone": "buy",
                "title": f"【触及目标线】{base['name']}",
                "body": f"{base['full']} 现价 {price} ≥ 你设的目标线 {take}（预设提醒，非指令）",
                "advice": f"已到目标位 {take}，可评估止盈或上调移动止盈线。",
            })


def scan_once() -> list[dict]:
    uni = _universe()
    with _lock:
        _state["watch_codes"] = [f"{c}.{m}" for c, m, _, _ in uni]
    results = se.score_universe(uni)
    for item in results:
        try:
            _emit_from_score(item)
        except Exception:
            logger.exception("emit failed")
    try:
        _check_price_lines(results)
    except Exception:
        logger.exception("price-line check failed")
    with _lock:
        _state["scans"] += 1
        _state["last_scan_at"] = time.time()
        _state["last_scan_iso"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _state["error"] = None
    return results


def _loop() -> None:
    logger.info("monitor loop started")
    while not _stop.is_set():
        try:
            phase = clock.market_phase()
            with _lock:
                _state["last_phase"] = phase
            if _state["running"] and phase["is_trading"]:
                try:
                    scan_once()
                except Exception as e:
                    logger.exception("scan failed")
                    with _lock:
                        _state["error"] = str(e)
                # slightly faster in first/last 15 minutes
                interval = _state["interval_sec"]
                try:
                    hm = clock.now_cn().time()
                    from datetime import time as dtime
                    volatile = (
                        dtime(9, 30) <= hm <= dtime(9, 45)
                        or dtime(14, 45) <= hm <= dtime(15, 0)
                    )
                    if volatile:
                        interval = max(20, int(interval * 0.6))
                except Exception:
                    pass
            else:
                interval = max(30, _state["interval_sec"])
            _stop.wait(interval)
        except Exception:
            logger.exception("monitor loop error")
            _stop.wait(15)
    logger.info("monitor loop stopped")


def start(interval_sec: int = 45) -> dict:
    global _thread
    interval_sec = max(20, int(interval_sec))
    with _lock:
        _state["interval_sec"] = interval_sec
        _state["running"] = True
    if _thread and _thread.is_alive():
        return get_status()
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="market-monitor", daemon=True)
    _thread.start()
    return get_status()


def stop() -> dict:
    with _lock:
        _state["running"] = False
    # keep thread alive to resume later; just stop scanning
    return get_status()


def shutdown() -> None:
    with _lock:
        _state["running"] = False
    _stop.set()
