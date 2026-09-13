"""Professional multi-factor signal engine for SH/SZ learning desk.

Rules-based (transparent). Not investment advice.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from . import indicators as ind
from . import data as data_svc


def _finite(x) -> bool:
    try:
        return x is not None and np.isfinite(float(x))
    except Exception:
        return False


def _f(x, default=0.0) -> float:
    try:
        if x is None or (isinstance(x, float) and not np.isfinite(x)):
            return default
        return float(x)
    except Exception:
        return default


def score_symbol(
    code: str,
    market: str = "",
    cost: float | None = None,
    shares: float | None = None,
    days: int = 120,
) -> dict[str, Any]:
    """Composite score + actionable observation for one symbol."""
    df = data_svc.get_history(code, market, days=days)
    if df is None or len(df) < 30:
        return {
            "code": code,
            "market": market,
            "ok": False,
            "error": "历史数据不足",
        }

    out = ind.enrich(df)
    last = out.iloc[-1]
    prev = out.iloc[-2]
    quote = data_svc.get_quote(code, market)
    price = _f(quote.get("price") or last["close"], _f(last["close"]))

    factors: list[dict] = []
    score = 50.0  # 0 bearish ... 100 bullish

    def bump(delta: float, name: str, detail: str, weight: str = "中") -> None:
        nonlocal score
        score += delta
        factors.append({
            "name": name,
            "detail": detail,
            "delta": round(delta, 1),
            "weight": weight,
        })

    # --- Trend structure ---
    ma5, ma10, ma20, ma60 = last.get("ma5"), last.get("ma10"), last.get("ma20"), last.get("ma60")
    if all(_finite(x) for x in (ma5, ma10, ma20)):
        if ma5 > ma10 > ma20:
            bump(12, "均线多头排列", "MA5>MA10>MA20，短中期趋势向上", "强")
        elif ma5 < ma10 < ma20:
            bump(-12, "均线空头排列", "MA5<MA10<MA20，短中期趋势向下", "强")
        elif ma5 > ma20:
            bump(4, "短线站上中期均线", "MA5 在 MA20 上方", "弱")
        else:
            bump(-4, "短线跌破中期均线", "MA5 在 MA20 下方", "弱")

    if _finite(ma60):
        if price > ma60:
            bump(6, "站上60日线", f"价格高于 MA60（{ma60:.3f}）", "中")
        else:
            bump(-6, "跌破60日线", f"价格低于 MA60（{ma60:.3f}）", "中")

    # --- MACD ---
    dif, dea, hist = last.get("macd_dif"), last.get("macd_dea"), last.get("macd_hist")
    dif_p, dea_p = prev.get("macd_dif"), prev.get("macd_dea")
    if all(_finite(x) for x in (dif, dea, dif_p, dea_p)):
        if dif_p <= dea_p and dif > dea:
            bump(10, "MACD金叉", "DIF 上穿 DEA", "强")
        elif dif_p >= dea_p and dif < dea:
            bump(-10, "MACD死叉", "DIF 下穿 DEA", "强")
        elif dif > dea:
            bump(4, "MACD多头", "DIF 在 DEA 上方", "中")
        else:
            bump(-4, "MACD空头", "DIF 在 DEA 下方", "中")
        if _finite(hist) and hist > 0 and _finite(prev.get("macd_hist")) and hist > _f(prev.get("macd_hist")):
            bump(2, "MACD柱增强", "红柱放大", "弱")

    # --- RSI ---
    rsi14, rsi6 = last.get("rsi14"), last.get("rsi6")
    if _finite(rsi14):
        if rsi14 >= 75:
            bump(-8, "RSI超买", f"RSI14={rsi14:.1f}，追高风险", "中")
        elif rsi14 >= 65:
            bump(-2, "RSI偏强", f"RSI14={rsi14:.1f}", "弱")
        elif rsi14 <= 30:
            bump(8, "RSI超卖", f"RSI14={rsi14:.1f}，或有反弹观察价值", "中")
        elif rsi14 <= 40:
            bump(2, "RSI偏弱", f"RSI14={rsi14:.1f}", "弱")

    # --- BOLL position ---
    upper, mid, lower = last.get("boll_upper"), last.get("boll_mid"), last.get("boll_lower")
    if all(_finite(x) for x in (upper, mid, lower)):
        width = (upper - lower) / mid if mid else 0
        if price <= lower:
            bump(6, "触及布林下轨", "价格贴近/跌破下轨，可看反弹确认", "中")
        elif price >= upper:
            bump(-6, "触及布林上轨", "价格贴近/突破上轨，注意回落", "中")
        elif price > mid:
            bump(2, "布林中轨上方", "价格在中轨上运行", "弱")
        else:
            bump(-2, "布林中轨下方", "价格在中轨下运行", "弱")
        if width < 0.03:
            bump(0, "布林收口", "波动收窄，可能临近方向选择", "弱")

    # --- Volume confirmation ---
    if "volume" in out.columns and len(out) >= 20:
        vol_ma5 = out["volume"].rolling(5).mean().iloc[-1]
        vol_ma20 = out["volume"].rolling(20).mean().iloc[-1]
        v_now = _f(last.get("volume"))
        if _finite(vol_ma5) and _finite(vol_ma20) and vol_ma20 > 0:
            ratio = vol_ma5 / vol_ma20
            if ratio >= 1.3 and price >= _f(prev.get("close")):
                bump(4, "放量上行", f"近5日量比20日约 {ratio:.2f}x", "中")
            elif ratio >= 1.3 and price < _f(prev.get("close")):
                bump(-5, "放量下跌", f"近5日量比20日约 {ratio:.2f}x", "中")
            elif ratio <= 0.7:
                bump(0, "缩量", "成交清淡，信号可靠性下降", "弱")

    # --- Short-term momentum ---
    if len(out) >= 6:
        chg5 = (price / _f(out["close"].iloc[-6], price) - 1) * 100 if _f(out["close"].iloc[-6]) else 0
        if chg5 <= -8:
            bump(3, "短线超跌", f"近5日约 {chg5:.1f}%，或有均值回归观察", "弱")
        elif chg5 >= 10:
            bump(-3, "短线过热", f"近5日约 +{chg5:.1f}%，注意追高", "弱")

    # --- User position overlay (holdings only) ---
    pos_note = None
    if cost and cost > 0:
        pnl_pct = (price / cost - 1) * 100
        if pnl_pct <= -10:
            bump(-4, "持仓亏损扩大", f"相对成本 {pnl_pct:.1f}%，审视止损纪律", "中")
            pos_note = f"浮亏 {pnl_pct:.1f}%"
        elif pnl_pct >= 15:
            bump(0, "持仓盈利较多", f"相对成本 +{pnl_pct:.1f}%，可考虑止盈规则", "中")
            pos_note = f"浮盈 +{pnl_pct:.1f}%"
        else:
            pos_note = f"相对成本 {pnl_pct:+.1f}%"

    score = max(0.0, min(100.0, score))

    # Action band
    if score >= 72:
        action, tone = "买入关注", "buy"
        advice = "多项因子转强，可列入买入观察；务必等回踩确认并设好止损。"
    elif score >= 58:
        action, tone = "偏多持有/小仓试错", "buy"
        advice = "偏多但未全面走强，更适合已有仓位持有，或极小仓试探。"
    elif score >= 42:
        action, tone = "观望", "neutral"
        advice = "多空交织，以观望为主，避免频繁进出。"
    elif score >= 30:
        action, tone = "谨慎/不加仓", "sell"
        advice = "偏弱，不建议追买；已有仓位可按纪律评估减仓。"
    else:
        action, tone = "减仓/止损关注", "sell"
        advice = "空头因子偏多，优先控制风险，而不是抄底。"

    # Suggested educational levels (not orders)
    atr_proxy = None
    try:
        tr = pd.concat(
            [
                out["high"] - out["low"],
                (out["high"] - out["close"].shift()).abs(),
                (out["low"] - out["close"].shift()).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr_proxy = _f(tr.rolling(14).mean().iloc[-1], 0)
    except Exception:
        atr_proxy = 0

    stop = price - 1.5 * atr_proxy if atr_proxy else price * 0.97
    target = price + 2.0 * atr_proxy if atr_proxy else price * 1.05

    # Recent classic events
    recent = ind.detect_signals(df)

    confidence = int(min(92, max(35, 50 + abs(score - 50) * 1.2)))

    parsed_code, parsed_mkt = (
        data_svc.parse_symbol(data_svc._full_code(code, market))
        if market
        else data_svc.parse_symbol(code)
    )
    full = quote.get("full") or data_svc._full_code(parsed_code, parsed_mkt)

    return {
        "ok": True,
        "code": parsed_code,
        "market": parsed_mkt,
        "full": full,
        "name": quote.get("name") or parsed_code,
        "type": quote.get("type", "stock"),
        "price": price,
        "change_pct": quote.get("change_pct"),
        "score": round(score, 1),
        "confidence": confidence,
        "action": action,
        "tone": tone,
        "advice": advice,
        "stop_hint": round(stop, 4),
        "target_hint": round(target, 4),
        "pos_note": pos_note,
        "factors": factors,
        "recent_signals": recent[-6:],
        "cost": cost,
        "shares": shares,
    }


def score_universe(symbols: list[tuple[str, str, float | None, float | None]]) -> list[dict]:
    """Score symbols concurrently; per-symbol cost is dominated by HTTP fetch."""
    from concurrent.futures import ThreadPoolExecutor

    def one(row):
        code, market, cost, shares = row
        try:
            return score_symbol(code, market, cost=cost, shares=shares)
        except Exception as e:
            return {"ok": False, "code": code, "market": market, "error": str(e)}

    if len(symbols) <= 1:
        results = [one(r) for r in symbols]
    else:
        with ThreadPoolExecutor(max_workers=min(6, len(symbols))) as ex:
            results = list(ex.map(one, symbols))
    results.sort(key=lambda x: (-(x.get("score") if x.get("ok") else -1), x.get("code") or ""))
    return results
