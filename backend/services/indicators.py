"""Technical indicators and classic trading signals."""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    ema_fast = ema(close, fast)
    ema_slow = ema(close, slow)
    dif = ema_fast - ema_slow
    dea = ema(dif, signal)
    hist = (dif - dea) * 2
    return pd.DataFrame({"dif": dif, "dea": dea, "hist": hist})


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI.

    Warmup rows stay NaN instead of 100: an unmeasurable RSI must never be read
    as "fully overbought" (the old fillna(100) did exactly that, and
    signal_engine turns RSI>=75 into a -8 penalty). A genuine zero-loss stretch
    still returns 100, and a perfectly flat series returns a neutral 50.
    """
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    no_loss = (avg_loss == 0) & (avg_gain > 0)          # real 100: only gains
    flat = (avg_loss == 0) & (avg_gain == 0)            # undefined: no movement
    out = out.where(~no_loss, 100.0)
    out = out.where(~flat, 50.0)
    return out


def bollinger(close: pd.Series, window: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    mid = sma(close, window)
    std = close.rolling(window=window, min_periods=window).std()
    return pd.DataFrame({
        "mid": mid,
        "upper": mid + num_std * std,
        "lower": mid - num_std * std,
    })


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Add MA / MACD / RSI / BOLL columns to OHLCV frame."""
    out = df.copy()
    close = out["close"]
    for w in (5, 10, 20, 60):
        out[f"ma{w}"] = sma(close, w)
    m = macd(close)
    out["macd_dif"] = m["dif"]
    out["macd_dea"] = m["dea"]
    out["macd_hist"] = m["hist"]
    out["rsi6"] = rsi(close, 6)
    out["rsi14"] = rsi(close, 14)
    b = bollinger(close)
    out["boll_mid"] = b["mid"]
    out["boll_upper"] = b["upper"]
    out["boll_lower"] = b["lower"]
    return out


def detect_signals(df: pd.DataFrame) -> list[dict]:
    """Classic indicator signals on the last few bars."""
    if df is None or len(df) < 30:
        return []

    out = enrich(df)
    signals: list[dict] = []
    n = len(out)

    def add(idx: int, kind: str, name: str, detail: str, strength: str = "中") -> None:
        row = out.iloc[idx]
        signals.append({
            "date": str(row["date"]) if "date" in row.index else str(idx),
            "close": float(row["close"]),
            "kind": kind,  # buy | sell | neutral
            "name": name,
            "detail": detail,
            "strength": strength,
        })

    # MA5 / MA20 golden / death cross (last 30 bars)
    window = min(30, max(5, n - 1))
    for i in range(n - window, n):
        if i < 1:
            continue
        ma5 = out["ma5"].iloc[i]
        ma20 = out["ma20"].iloc[i]
        ma5_p = out["ma5"].iloc[i - 1]
        ma20_p = out["ma20"].iloc[i - 1]
        if pd.isna(ma5) or pd.isna(ma20) or pd.isna(ma5_p) or pd.isna(ma20_p):
            continue
        if ma5_p <= ma20_p and ma5 > ma20:
            add(i, "buy", "MA金叉", "MA5 上穿 MA20，短期趋势转强", "强")
        elif ma5_p >= ma20_p and ma5 < ma20:
            add(i, "sell", "MA死叉", "MA5 下穿 MA20，短期趋势转弱", "强")

    # MACD cross
    for i in range(n - window, n):
        if i < 1:
            continue
        dif, dea = out["macd_dif"].iloc[i], out["macd_dea"].iloc[i]
        dif_p, dea_p = out["macd_dif"].iloc[i - 1], out["macd_dea"].iloc[i - 1]
        if any(pd.isna(x) for x in (dif, dea, dif_p, dea_p)):
            continue
        if dif_p <= dea_p and dif > dea:
            add(i, "buy", "MACD金叉", f"DIF 上穿 DEA（DIF={dif:.4f}）", "中")
        elif dif_p >= dea_p and dif < dea:
            add(i, "sell", "MACD死叉", f"DIF 下穿 DEA（DIF={dif:.4f}）", "中")

    # RSI extremes in recent window
    rsi_span = min(15, max(5, window // 2))
    for i in range(n - rsi_span, n):
        rsi14 = out["rsi14"].iloc[i]
        if pd.isna(rsi14):
            continue
        if rsi14 <= 30:
            add(i, "buy", "RSI超卖", f"RSI14={rsi14:.1f}，可能进入超卖区", "中")
        elif rsi14 >= 70:
            add(i, "sell", "RSI超买", f"RSI14={rsi14:.1f}，可能进入超买区", "中")

    # Price vs BOLL (latest)
    last = out.iloc[-1]
    if not pd.isna(last.get("boll_lower")) and last["close"] <= last["boll_lower"]:
        add(n - 1, "buy", "触及布林下轨", "价格触及或跌破布林下轨", "弱")
    elif not pd.isna(last.get("boll_upper")) and last["close"] >= last["boll_upper"]:
        add(n - 1, "sell", "触及布林上轨", "价格触及或突破布林上轨", "弱")

    # Deduplicate by (date, name), keep order
    seen = set()
    uniq = []
    for s in signals:
        key = (s["date"], s["name"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(s)
    return uniq[-20:]


def summarize_trend(df: pd.DataFrame) -> dict:
    """Plain-language trend summary for beginners."""
    if df is None or len(df) < 20:
        return {"label": "数据不足", "tone": "neutral", "points": []}

    out = enrich(df)
    last = out.iloc[-1]
    close = float(last["close"])
    points: list[str] = []
    buy_votes = 0
    sell_votes = 0

    ma5, ma20, ma60 = last.get("ma5"), last.get("ma20"), last.get("ma60")
    if not pd.isna(ma5) and not pd.isna(ma20):
        if ma5 > ma20:
            points.append("短期均线在中期均线之上，短线偏强")
            buy_votes += 1
        else:
            points.append("短期均线在中期均线之下，短线偏弱")
            sell_votes += 1

    if not pd.isna(ma60):
        if close > ma60:
            points.append("价格站上60日均线，中线结构尚可")
            buy_votes += 1
        else:
            points.append("价格在60日均线之下，中线偏弱")
            sell_votes += 1

    if not pd.isna(last.get("macd_dif")) and not pd.isna(last.get("macd_dea")):
        if last["macd_dif"] > last["macd_dea"]:
            points.append("MACD 多头排列")
            buy_votes += 1
        else:
            points.append("MACD 空头排列")
            sell_votes += 1

    rsi_v = last.get("rsi14")
    if not pd.isna(rsi_v):
        if rsi_v >= 70:
            points.append(f"RSI14={rsi_v:.1f}，偏超买")
            sell_votes += 1
        elif rsi_v <= 30:
            points.append(f"RSI14={rsi_v:.1f}，偏超卖")
            buy_votes += 1
        else:
            points.append(f"RSI14={rsi_v:.1f}，处于中性区间")

    if buy_votes > sell_votes + 1:
        label, tone = "偏多", "up"
    elif sell_votes > buy_votes + 1:
        label, tone = "偏空", "down"
    else:
        label, tone = "震荡", "neutral"

    return {"label": label, "tone": tone, "points": points, "buy_votes": buy_votes, "sell_votes": sell_votes}
