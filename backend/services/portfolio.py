"""Portfolio persistence and P&L calculations."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from . import data as data_svc

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PORTFOLIO_FILE = DATA_DIR / "portfolio.json"
_lock = threading.Lock()


def _default() -> dict:
    return {"holdings": [], "watchlist": []}


def load() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not PORTFOLIO_FILE.exists():
        save(_default())
        return _default()
    try:
        with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return _default()


def save(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = PORTFOLIO_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(PORTFOLIO_FILE)


def portfolio_overview() -> dict[str, Any]:
    pf = load()
    holdings = []
    total_mv = 0.0
    total_cost = 0.0

    for h in pf.get("holdings", []):
        code, market = h["code"], h.get("market", "")
        quote = data_svc.get_quote(code, market)
        price = float(quote.get("price") or 0)
        shares = float(h.get("shares") or 0)
        cost = float(h.get("cost") or 0)
        mv = price * shares
        cost_amt = cost * shares
        pnl = mv - cost_amt
        pnl_pct = (pnl / cost_amt * 100) if cost_amt else 0
        day_chg = float(quote.get("change") or 0)
        day_pnl = day_chg * shares
        total_mv += mv
        total_cost += cost_amt

        holdings.append({
            "code": code,
            "market": market,
            "full": quote.get("full") or data_svc._full_code(code, market),
            "name": quote.get("name") or code,
            "shares": shares,
            "cost": cost,
            "price": price,
            "mv": mv,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "change": day_chg,
            "change_pct": quote.get("change_pct"),
            "day_pnl": day_pnl,
            "weight": 0.0,  # filled later
            "type": quote.get("type"),
        })

    total_pnl = total_mv - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0
    day_pnl_total = sum(h["day_pnl"] for h in holdings)

    for h in holdings:
        h["weight"] = (h["mv"] / total_mv * 100) if total_mv else 0

    watchlist = []
    for w in pf.get("watchlist", []):
        q = data_svc.get_quote(w["code"], w.get("market", ""))
        watchlist.append({
            "code": w["code"],
            "market": w.get("market", ""),
            "full": q.get("full"),
            "name": q.get("name"),
            "price": q.get("price"),
            "change_pct": q.get("change_pct"),
            "change": q.get("change"),
            "type": q.get("type"),
        })

    return {
        "total_mv": total_mv,
        "total_cost": total_cost,
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct,
        "day_pnl": day_pnl_total,
        "holdings": holdings,
        "watchlist": watchlist,
    }


def add_holding(payload: dict) -> dict:
    with _lock:
        pf = load()
        code = str(payload["code"]).strip()
        market = str(payload.get("market", "")).upper()
        if not market:
            _, market = data_svc.parse_symbol(code)
        else:
            code, market = data_svc.parse_symbol(data_svc._full_code(code, market))
        shares = float(payload["shares"])
        cost = float(payload["cost"])
        found = False
        for h in pf["holdings"]:
            if h["code"] == code and h.get("market", "").upper() == market:
                old_shares = float(h["shares"])
                old_cost = float(h["cost"])
                new_shares = old_shares + shares
                h["cost"] = (old_shares * old_cost + shares * cost) / new_shares if new_shares else cost
                h["shares"] = new_shares
                found = True
                break
        if not found:
            pf["holdings"].append({
                "code": code,
                "market": market,
                "shares": shares,
                "cost": cost,
                "note": payload.get("note", ""),
            })
        save(pf)
        return pf


def update_holding(index: int, payload: dict) -> dict:
    with _lock:
        pf = load()
        if index < 0 or index >= len(pf["holdings"]):
            raise IndexError("holding index out of range")
        h = pf["holdings"][index]
        if "shares" in payload:
            h["shares"] = float(payload["shares"])
        if "cost" in payload:
            h["cost"] = float(payload["cost"])
        if "note" in payload:
            h["note"] = payload["note"]
        save(pf)
        return pf


def remove_holding(index: int) -> dict:
    with _lock:
        pf = load()
        if index < 0 or index >= len(pf["holdings"]):
            raise IndexError("holding index out of range")
        pf["holdings"].pop(index)
        save(pf)
        return pf


def add_watch(payload: dict) -> dict:
    with _lock:
        pf = load()
        code = str(payload["code"]).strip()
        market = str(payload.get("market", "")).upper()
        if market:
            code, market = data_svc.parse_symbol(data_svc._full_code(code, market))
        else:
            code, market = data_svc.parse_symbol(code)
        for w in pf["watchlist"]:
            if w["code"] == code and w.get("market", "").upper() == market:
                save(pf)
                return pf
        pf["watchlist"].append({"code": code, "market": market})
        save(pf)
        return pf


def remove_watch(code: str, market: str = "") -> dict:
    with _lock:
        pf = load()
        code_u = code.strip().upper()
        market_u = market.strip().upper()
        pf["watchlist"] = [
            w for w in pf["watchlist"]
            if not (w["code"].upper() == code_u and (not market_u or w.get("market", "").upper() == market_u))
        ]
        save(pf)
        return pf
