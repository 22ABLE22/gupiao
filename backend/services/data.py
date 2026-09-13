"""Market data via free public sources (akshare / East Money)."""
from __future__ import annotations

import datetime as dt
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

_cache: dict[str, tuple[float, Any]] = {}
_CACHE_TTL = 60.0  # seconds
_CACHE_MAX_ENTRIES = 512
_cache_lock = threading.Lock()


def cache_fresh(prefix: str) -> bool:
    """True only if a *non-expired* entry with this prefix exists.

    The previous implementation checked key existence only, so an expired
    entry still counted as "warm" and triggered a full 20s snapshot refetch.
    """
    now = time.time()
    with _cache_lock:
        for k, (ts, _v) in _cache.items():
            if k.startswith(prefix) and now - ts < _CACHE_TTL:
                return True
    return False


def _prune_cache() -> None:
    """Drop expired entries; hard-cap size so long runs don't leak memory."""
    now = time.time()
    with _cache_lock:
        expired = [k for k, (ts, _) in _cache.items() if now - ts > _CACHE_TTL * 30]
        for k in expired:
            _cache.pop(k, None)
        if len(_cache) > _CACHE_MAX_ENTRIES:
            for k, _ in sorted(_cache.items(), key=lambda kv: kv[1][0]):
                _cache.pop(k, None)
                if len(_cache) <= _CACHE_MAX_ENTRIES:
                    break


def _is_empty(val) -> bool:
    """Empty frames/lists must never be cached: a transient upstream failure
    would otherwise pin the symbol to "no data" for the whole TTL."""
    if val is None:
        return True
    if isinstance(val, pd.DataFrame):
        return len(val) == 0
    if isinstance(val, (list, tuple, dict, str)):
        return len(val) == 0
    return False


def _cached(key: str, ttl: float = _CACHE_TTL, skip_empty: bool = True):
    def deco(fn):
        def wrapper(*args, **kwargs):
            ck = key + ":" + repr((args, sorted(kwargs.items())))
            now = time.time()
            with _cache_lock:
                hit = _cache.get(ck)
                if hit and now - hit[0] < ttl:
                    return hit[1]
            val = fn(*args, **kwargs)
            if not (skip_empty and _is_empty(val)):
                with _cache_lock:
                    _cache[ck] = (now, val)
                if len(_cache) > _CACHE_MAX_ENTRIES:
                    _prune_cache()
            return val
        return wrapper
    return deco


class CircuitBreaker:
    """Skip a known-bad upstream during cooldown instead of paying its timeout.

    East Money rate-limits aggressively; without this every call waits for the
    connection reset before falling back to sina/tencent.
    """

    def __init__(self, name: str, fail_threshold: int = 3, cooldown: float = 90.0):
        self.name = name
        self.fail_threshold = fail_threshold
        self.cooldown = cooldown
        self._fails = 0
        self._open_until = 0.0
        self._lock = threading.Lock()

    def allow(self) -> bool:
        with self._lock:
            if self._fails >= self.fail_threshold and time.time() < self._open_until:
                return False
            return True

    def record_success(self) -> None:
        with self._lock:
            self._fails = 0
            self._open_until = 0.0

    def record_failure(self) -> None:
        with self._lock:
            self._fails += 1
            if self._fails >= self.fail_threshold:
                self._open_until = time.time() + self.cooldown
                logger.warning(
                    "circuit open: %s skipped for %.0fs after %d failures",
                    self.name, self.cooldown, self._fails,
                )

    def status(self) -> dict:
        with self._lock:
            return {
                "name": self.name,
                "fails": self._fails,
                "open": self._fails >= self.fail_threshold and time.time() < self._open_until,
                "retry_in_sec": max(0, round(self._open_until - time.time(), 1)),
            }


_em_breaker = CircuitBreaker("eastmoney", fail_threshold=2, cooldown=120.0)


def _full_code(code: str, market: str) -> str:
    code = code.strip().upper()
    if code.endswith(".SH") or code.endswith(".SZ") or code.endswith(".BJ"):
        return code
    market = (market or "").upper()
    if market in ("SH", "SS"):
        return f"{code}.SH"
    if market == "SZ":
        return f"{code}.SZ"
    if market == "BJ":
        return f"{code}.BJ"
    # heuristic
    if code.startswith(("5", "6", "9")):
        return f"{code}.SH"
    if code.startswith(("0", "1", "2", "3")):
        return f"{code}.SZ"
    return f"{code}.SZ"


def parse_symbol(symbol: str) -> tuple[str, str]:
    """Return (code, market) e.g. 159516.SZ -> (159516, SZ)."""
    symbol = symbol.strip().upper()
    if "." in symbol:
        code, market = symbol.rsplit(".", 1)
        return code, market
    code = symbol
    if code.startswith(("5", "6", "9")):
        return code, "SH"
    return code, "SZ"


def _is_etf(code: str, market: str) -> bool:
    if market == "SH" and code.startswith("5"):
        return True
    if market == "SZ" and code.startswith("1"):
        return True
    return False


@_cached("etf_spot", 90)
def _etf_spot_df() -> pd.DataFrame:
    if not _em_breaker.allow():
        return pd.DataFrame()
    try:
        import akshare as ak
        df = ak.fund_etf_spot_em()
        if df is None or len(df) == 0:
            _em_breaker.record_failure()
            return pd.DataFrame()
        _em_breaker.record_success()
        return df
    except Exception as e:
        _em_breaker.record_failure()
        logger.warning("EM etf spot unavailable: %s", e)
        return pd.DataFrame()


@_cached("stock_spot", 90)
def _stock_spot_df() -> pd.DataFrame:
    if not _em_breaker.allow():
        return pd.DataFrame()
    try:
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
        if df is None or len(df) == 0:
            _em_breaker.record_failure()
            return pd.DataFrame()
        _em_breaker.record_success()
        return df
    except Exception as e:
        _em_breaker.record_failure()
        logger.warning("EM stock spot unavailable: %s", e)
        return pd.DataFrame()


def _quote_em_spot(code: str, market: str, full: str) -> dict | None:
    try:
        if _is_etf(code, market):
            df = _etf_spot_df()
        else:
            df = _stock_spot_df()
        if df is None or len(df) == 0 or len(df.columns) == 0:
            return None
        col_code = "代码" if "代码" in df.columns else df.columns[0]
        row = df[df[col_code].astype(str).str.zfill(6) == code.zfill(6)]
        if row is None or len(row) == 0:
            return None
        r = row.iloc[0].to_dict()

        def pick(*names, default=None):
            for n in names:
                if n in r and r[n] is not None and str(r[n]) != "nan":
                    return r[n]
            return default

        price = float(pick("最新价", "当前价", default=0) or 0)
        prev = float(pick("昨收", "昨收价", default=0) or 0)
        chg = float(pick("涨跌额", default=0) or 0)
        chg_pct = float(pick("涨跌幅", default=0) or 0)
        if not chg and price and prev:
            chg = price - prev
        if not chg_pct and price and prev:
            chg_pct = (price - prev) / prev * 100
        if not price:
            return None
        return {
            "code": code,
            "market": market,
            "full": full,
            "name": str(pick("名称", default=full)),
            "price": price,
            "open": float(pick("今开", default=0) or 0),
            "high": float(pick("最高", default=0) or 0),
            "low": float(pick("最低", default=0) or 0),
            "prev_close": prev,
            "change": chg,
            "change_pct": chg_pct,
            "volume": float(pick("成交量", default=0) or 0),
            "amount": float(pick("成交额", default=0) or 0),
            "turnover": float(pick("换手率", default=0) or 0),
            "pe": _to_float(pick("市盈率-动态", "市盈率(动态)", "市盈率")),
            "pb": _to_float(pick("市净率")),
            "total_mv": _to_float(pick("总市值")),
            "circ_mv": _to_float(pick("流通市值")),
            "type": "etf" if _is_etf(code, market) else "stock",
            "source": "spot",
        }
    except Exception as e:
        logger.debug("em spot quote %s: %s", full, e)
        return None


def get_quote(code: str, market: str = "") -> dict[str, Any]:
    """Latest quote for stock or ETF. Prefer fast sina, enrich with EM when warm."""
    if market:
        code, market = parse_symbol(_full_code(code, market))
    else:
        code, market = parse_symbol(code)
    full = _full_code(code, market)

    # Fast path first (individual symbol, ~200ms)
    fast = _quote_sina_hq(code, market, full)
    if fast:
        # Tencent single-symbol call is cheap and carries PE/PB/市值/换手率.
        # Sina hq does not, so without this the fundamentals page stays empty.
        if fast.get("pe") is None and fast.get("pb") is None:
            tx = _quote_tencent(code, market, full)
            if tx:
                for k in ("pe", "pb", "total_mv", "circ_mv", "turnover"):
                    if tx.get(k) is not None and fast.get(k) is None:
                        fast[k] = tx[k]
                if tx.get("name") and fast.get("name") in (None, "", full):
                    fast["name"] = tx["name"]
        # Optionally enrich from EM only when a *fresh* full snapshot exists.
        cache_key_prefix = "etf_spot:" if _is_etf(code, market) else "stock_spot:"
        if cache_fresh(cache_key_prefix):
            extra = _quote_em_spot(code, market, full)
            if extra:
                for k in ("pe", "pb", "total_mv", "circ_mv", "turnover"):
                    if extra.get(k) is not None and fast.get(k) is None:
                        fast[k] = extra[k]
        return fast

    em = _quote_em_spot(code, market, full)
    if em:
        return em
    return _quote_fallback_hist(code, market, full)


# Bond / money ETFs sometimes missing from EM stock-style ETF spot list
_NAME_HINTS = {
    "159516": "半导体设备ETF",
    "511260": "十年国债ETF",
    "511010": "国债ETF",
    "511030": "公司债ETF",
    "511220": "城投债ETF",
    "511380": "可转债ETF",
    "511880": "银华日利",
    "511990": "华宝添益",
    "511660": "建信添益",
}


def _name_from_spot(code: str, market: str) -> str | None:
    try:
        if _is_etf(code, market):
            df = _etf_spot_df()
        else:
            df = _stock_spot_df()
        if df is None or len(df) == 0 or len(df.columns) == 0:
            return _NAME_HINTS.get(code)
        col_code = "代码" if "代码" in df.columns else df.columns[0]
        col_name = "名称" if "名称" in df.columns else df.columns[1]
        row = df[df[col_code].astype(str).str.zfill(6) == code.zfill(6)]
        if len(row):
            return str(row.iloc[0][col_name])
    except Exception:
        pass
    return _NAME_HINTS.get(code)


def _to_float(v) -> float | None:
    if v is None:
        return None
    try:
        s = str(v).replace(",", "").strip()
        if s in ("", "-", "nan", "None"):
            return None
        return float(s)
    except Exception:
        return None


def _quote_sina_hq(code: str, market: str, full: str) -> dict | None:
    """Fast sina realtime quote; good for bond ETFs missing from EM spot."""
    try:
        import requests
        prefix = "sh" if market == "SH" else "sz"
        url = f"https://hq.sinajs.cn/list={prefix}{code}"
        headers = {
            "Referer": "https://finance.sina.com.cn",
            "User-Agent": "Mozilla/5.0",
        }
        r = requests.get(url, headers=headers, timeout=6)
        r.raise_for_status()
        text = r.text
        # gbk encoded typically
        try:
            text = r.content.decode("gbk", errors="replace")
        except Exception:
            pass
        payload = text.split('="', 1)[-1].rsplit('"', 1)[0]
        parts = payload.split(",")
        if len(parts) < 32:
            return None
        name = parts[0].strip()
        if code in _NAME_HINTS and (not name or len(name) < 5):
            name = _NAME_HINTS[code]
        open_ = float(parts[1] or 0)
        prev = float(parts[2] or 0)
        price = float(parts[3] or 0)
        high = float(parts[4] or 0)
        low = float(parts[5] or 0)
        volume = float(parts[8] or 0)
        amount = float(parts[9] or 0)
        if not price:
            return None
        chg = price - prev if prev else 0
        chg_pct = (chg / prev * 100) if prev else 0
        return {
            "code": code,
            "market": market,
            "full": full,
            "name": name or full,
            "price": price,
            "open": open_,
            "high": high,
            "low": low,
            "prev_close": prev,
            "change": chg,
            "change_pct": chg_pct,
            "volume": volume,
            "amount": amount,
            "type": "etf" if _is_etf(code, market) else "stock",
            "source": "sina",
        }
    except Exception as e:
        logger.debug("sina hq %s: %s", full, e)
        return None


def _quote_tencent(code: str, market: str, full: str) -> dict | None:
    """Tencent realtime quote — supplies PE/PB/市值/换手率 when EM is limited.

    Market caps are reported in 亿元 here, so they are scaled to 元 to match
    the EM field convention consumed by _fmt_mv.
    """
    try:
        import requests
        prefix = "sh" if market == "SH" else "sz"
        url = f"https://qt.gtimg.cn/q={prefix}{code}"
        r = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"},
            timeout=6,
        )
        r.raise_for_status()
        text = r.content.decode("gbk", errors="replace")
        parts = text.split("~")
        if len(parts) < 47:
            return None
        price = _to_float(parts[3])
        if not price:
            return None
        prev = _to_float(parts[4]) or 0
        chg = price - prev if prev else 0
        chg_pct = (chg / prev * 100) if prev else 0
        mv_yi = _to_float(parts[45])
        circ_yi = _to_float(parts[44])
        name = parts[1].strip() or _NAME_HINTS.get(code) or full
        pb = _to_float(parts[46])
        return {
            "code": code,
            "market": market,
            "full": full,
            "name": name,
            "price": price,
            "open": _to_float(parts[5]) or 0,
            "high": _to_float(parts[33]) or 0,
            "low": _to_float(parts[34]) or 0,
            "prev_close": prev,
            "change": chg,
            "change_pct": chg_pct,
            "volume": (_to_float(parts[6]) or 0) * 100,   # 手 -> 股
            "amount": (_to_float(parts[37]) or 0) * 1e4,   # 万元 -> 元
            "turnover": _to_float(parts[38]),
            "pe": _to_float(parts[39]),
            "pb": pb if pb else None,
            "total_mv": mv_yi * 1e8 if mv_yi else None,
            "circ_mv": circ_yi * 1e8 if circ_yi else None,
            "type": "etf" if _is_etf(code, market) else "stock",
            "source": "tencent",
        }
    except Exception as e:
        logger.debug("tencent quote %s: %s", full, e)
        return None


def _quote_fallback_hist(code: str, market: str, full: str) -> dict:
    try:
        hist = get_history(code, market, days=120)
        if hist is None or len(hist) == 0:
            return {"code": code, "market": market, "full": full, "name": full, "price": 0, "source": "empty"}
        last = hist.iloc[-1]
        prev = hist.iloc[-2] if len(hist) > 1 else last
        price = float(last["close"])
        prev_close = float(prev["close"])
        chg = price - prev_close
        chg_pct = (chg / prev_close * 100) if prev_close else 0
        name = _name_from_spot(code, market) or full
        return {
            "code": code,
            "market": market,
            "full": full,
            "name": name,
            "price": price,
            "open": float(last.get("open", 0) or 0),
            "high": float(last.get("high", 0) or 0),
            "low": float(last.get("low", 0) or 0),
            "prev_close": prev_close,
            "change": chg,
            "change_pct": chg_pct,
            "volume": float(last.get("volume", 0) or 0),
            "amount": float(last.get("amount", 0) or 0),
            "type": "etf" if _is_etf(code, market) else "stock",
            "source": "hist",
        }
    except Exception as e:
        logger.error("hist fallback failed %s: %s", full, e)
        return {"code": code, "market": market, "full": full, "name": full, "price": 0, "error": str(e)}


def _standardize_ohlcv(df: pd.DataFrame, days: int | None = None) -> pd.DataFrame:
    if df is None or len(df) == 0:
        return pd.DataFrame()
    rename = {
        "日期": "date",
        "date": "date",
        "开盘": "open",
        "开盘价": "open",
        "open": "open",
        "收盘": "close",
        "收盘价": "close",
        "close": "close",
        "最高": "high",
        "最高价": "high",
        "high": "high",
        "最低": "low",
        "最低价": "low",
        "low": "low",
        "成交量": "volume",
        "volume": "volume",
        "成交额": "amount",
        "amount": "amount",
        "振幅": "amplitude",
        "涨跌幅": "change_pct",
        "pct_chg": "change_pct",
        "涨跌额": "change",
        "换手率": "turnover",
        "turnover": "turnover",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    for col in ("open", "high", "low", "close", "volume", "amount"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "date" not in df.columns:
        return pd.DataFrame()
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df = df.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
    if days and len(df) > days:
        df = df.tail(days).reset_index(drop=True)
    return df


def _fetch_hist_em(code: str, market: str, start_s: str, end_s: str, adjust: str) -> pd.DataFrame:
    if not _em_breaker.allow():
        return pd.DataFrame()
    import akshare as ak
    try:
        if _is_etf(code, market):
            df = ak.fund_etf_hist_em(
                symbol=code, period="daily", start_date=start_s, end_date=end_s, adjust=adjust
            )
        else:
            df = ak.stock_zh_a_hist(
                symbol=code, period="daily", start_date=start_s, end_date=end_s, adjust=adjust
            )
    except Exception:
        _em_breaker.record_failure()
        raise
    if df is None or len(df) == 0:
        _em_breaker.record_failure()
        return pd.DataFrame()
    _em_breaker.record_success()
    return df


def _fetch_hist_sina(code: str, market: str, adjust: str = "qfq") -> pd.DataFrame:
    import akshare as ak
    prefix = market.lower()
    if _is_etf(code, market):
        return ak.fund_etf_hist_sina(symbol=f"{prefix}{code}")
    return ak.stock_zh_a_daily(symbol=f"{prefix}{code}", adjust=adjust or "qfq")


def _fetch_hist_tencent(code: str, market: str) -> pd.DataFrame:
    """Tencent daily K as last-resort fallback.

    Note: Tencent reports volume in 手 (lots), so it is scaled to shares to stay
    consistent with the EM/sina sources. Tencent does not return 成交额, so
    amount is left as 0 rather than being aliased to volume.
    """
    import requests
    prefix = "sh" if market == "SH" else "sz"
    symbol = f"{prefix}{code}"
    url = (
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        f"?param={symbol},day,,,320,qfq"
    )
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"}
    r = requests.get(url, headers=headers, timeout=12)
    r.raise_for_status()
    js = r.json()
    node = js.get("data", {}).get(symbol, {})
    bars = node.get("qfqday") or node.get("day") or []
    rows = []
    for b in bars:
        if len(b) < 6:
            continue
        try:
            rows.append({
                "date": b[0],
                "open": float(b[1]),
                "close": float(b[2]),
                "high": float(b[3]),
                "low": float(b[4]),
                "volume": float(b[5]) * 100,  # 手 -> 股
                "amount": 0.0,                # not provided by this endpoint
            })
        except (TypeError, ValueError):
            continue
    return pd.DataFrame(rows)


@_cached("hist", 180)
def _history_normalized(code: str, market: str, days: int, adjust: str) -> pd.DataFrame:
    """Fetch history for an already-normalized (code, market) pair."""
    end = dt.date.today()
    start = end - dt.timedelta(days=int(days * 1.6) + 30)
    start_s = start.strftime("%Y%m%d")
    end_s = end.strftime("%Y%m%d")

    def try_sources():
        # EM once (rich fields); fail fast to sina/tencent
        try:
            df = _standardize_ohlcv(_fetch_hist_em(code, market, start_s, end_s, adjust or "qfq"), days)
            if len(df):
                return df
        except Exception as e:
            logger.warning("EM hist %s.%s: %s", code, market, e)
        # Sina
        try:
            df = _standardize_ohlcv(_fetch_hist_sina(code, market, adjust or "qfq"), days)
            if len(df):
                return df
        except Exception as e:
            logger.warning("Sina hist %s.%s: %s", code, market, e)
        # Tencent
        try:
            df = _standardize_ohlcv(_fetch_hist_tencent(code, market), days)
            if len(df):
                return df
        except Exception as e:
            logger.warning("Tencent hist %s.%s: %s", code, market, e)
        return pd.DataFrame()

    df = try_sources()
    if df is None or len(df) == 0:
        return pd.DataFrame()
    return df


# Frontend asks for 120/250/500; snap to tiers so one cached frame serves all.
_HISTORY_TIERS = (60, 120, 250, 500)


def _snap_days(days: int) -> int:
    for tier in _HISTORY_TIERS:
        if days <= tier:
            return tier
    return max(_HISTORY_TIERS[-1], int(days))


def get_history(code: str, market: str = "", days: int = 250, adjust: str = "qfq") -> pd.DataFrame:
    """Daily OHLCV history with multi-source fallback.

    Symbols are normalized before caching so '159516'+'SZ' and '159516.SZ'
    share one cache entry instead of fetching twice.
    """
    code, market = parse_symbol(_full_code(code, market))
    tier = _snap_days(int(days))
    df = _history_normalized(code, market, tier, adjust or "qfq")
    if df is None or len(df) == 0:
        return pd.DataFrame()
    if len(df) > int(days):
        df = df.tail(int(days)).reset_index(drop=True)
    return df


def get_name(code: str, market: str = "") -> str:
    q = get_quote(code, market)
    return q.get("name") or _full_code(*parse_symbol(code if market else code))


def _market_from_prefix(symbol: str) -> str:
    s = symbol.strip().lower()
    if s.startswith("sh"):
        return "SH"
    if s.startswith("sz"):
        return "SZ"
    if s.startswith("bj"):
        return "BJ"
    return ""


# sina suggest types worth surfacing: A-shares and exchange-traded funds.
_SINA_TYPE_MAP = {"11": "stock", "12": "stock", "203": "etf"}


@_cached("search", 300)
def _search_sina(q: str) -> list[dict]:
    """Sina suggest — one light request, works while EM is rate-limited."""
    import requests
    url = f"https://suggest3.sinajs.cn/suggest/key={q}"
    r = requests.get(
        url,
        headers={
            "Referer": "https://finance.sina.com.cn",
            "User-Agent": "Mozilla/5.0",
        },
        timeout=8,
    )
    r.raise_for_status()
    text = r.content.decode("gbk", errors="replace")
    inner = text.split('="', 1)[-1].rsplit('"', 1)[0]
    out: list[dict] = []
    seen = set()
    for row in inner.split(";"):
        row = row.strip()
        if not row:
            continue
        f = row.split(",")
        if len(f) < 5:
            continue
        kind = _SINA_TYPE_MAP.get(f[1].strip())
        if not kind:
            continue
        code = f[2].strip()
        market = _market_from_prefix(f[3])
        if not code or not market:
            continue
        key = (code, market)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "code": code,
            "market": market,
            "full": _full_code(code, market),
            "name": (f[4] or f[0] or code).strip(),
            "type": kind,
        })
    return out


def _search_spot_tables(q: str, limit: int) -> list[dict]:
    """Fallback: filter the cached EM snapshots (only cheap when already warm)."""
    results: list[dict] = []
    for df, kind in ((_etf_spot_df(), "etf"), (_stock_spot_df(), "stock")):
        if df is None or len(df) == 0 or len(df.columns) < 2:
            continue
        try:
            col_code = "代码" if "代码" in df.columns else df.columns[0]
            col_name = "名称" if "名称" in df.columns else df.columns[1]
            mask = (
                df[col_code].astype(str).str.contains(q, case=False, na=False)
                | df[col_name].astype(str).str.contains(q, case=False, na=False)
            )
            for _, r in df[mask].head(limit).iterrows():
                code = str(r[col_code]).zfill(6)
                market = "SH" if code.startswith(("5", "6", "9")) else "SZ"
                if any(x["code"] == code and x["market"] == market for x in results):
                    continue
                results.append({
                    "code": code,
                    "market": market,
                    "full": _full_code(code, market),
                    "name": str(r[col_name]),
                    "type": kind,
                })
        except Exception as e:
            logger.warning("%s search: %s", kind, e)
        if len(results) >= limit:
            break
    return results[:limit]


def search(query: str, limit: int = 8) -> list[dict]:
    """Symbol search. Sina suggest first (fast + survives EM throttling)."""
    q = query.strip()
    if not q:
        return []

    results: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def merge(items: list[dict]) -> None:
        for it in items:
            key = (it["code"], it["market"])
            if key in seen:
                continue
            seen.add(key)
            results.append(it)

    try:
        merge(_search_sina(q))
    except Exception as e:
        logger.warning("sina suggest search: %s", e)

    # A bare 6-digit code may be missing from suggest; resolve it directly.
    if not results and q.isdigit() and len(q) == 6:
        for market in ("SH", "SZ"):
            quote = _quote_sina_hq(q, market, _full_code(q, market))
            if quote and quote.get("price"):
                merge([{
                    "code": q,
                    "market": market,
                    "full": quote["full"],
                    "name": quote.get("name") or q,
                    "type": quote.get("type", "stock"),
                }])
                break

    if len(results) < limit and (cache_fresh("etf_spot:") or cache_fresh("stock_spot:")):
        merge(_search_spot_tables(q, limit - len(results)))

    return results[:limit]


def get_fundamentals(code: str, market: str = "") -> dict:
    """Best-effort fundamentals from free sources."""
    code, market = parse_symbol(code if not market else _full_code(code, market))
    full = _full_code(code, market)
    quote = get_quote(code, market)
    # Pull richer EM fields on demand (this page can wait)
    em = _quote_em_spot(code, market, full)
    if em:
        for k, v in em.items():
            if quote.get(k) in (None, "", 0) and v not in (None, ""):
                quote[k] = v
        if em.get("name") and (not quote.get("name") or quote.get("name") == full):
            quote["name"] = em["name"]
    out = {
        "code": code,
        "market": market,
        "full": full,
        "name": quote.get("name", full),
        "type": quote.get("type", "stock"),
        "price": quote.get("price"),
        "pe": quote.get("pe"),
        "pb": quote.get("pb"),
        "total_mv": quote.get("total_mv"),
        "circ_mv": quote.get("circ_mv"),
        "turnover": quote.get("turnover"),
        "items": [],
    }

    def item(label, value, hint=""):
        if value is None or value == "":
            return
        out["items"].append({"label": label, "value": value, "hint": hint})

    item("最新价", quote.get("price"), "元")
    item("涨跌幅", quote.get("change_pct"), "%")
    item("市盈率(动态)", quote.get("pe"), "倍")
    item("市净率", quote.get("pb"), "倍")
    item("总市值", _fmt_mv(quote.get("total_mv")), "")
    item("流通市值", _fmt_mv(quote.get("circ_mv")), "")
    item("换手率", quote.get("turnover"), "%")

    # Extra stock fundamentals via spot already covers most; try individual info for stocks
    if out["type"] == "stock":
        try:
            import akshare as ak
            info = ak.stock_individual_info_em(symbol=code)
            if info is not None and len(info):
                kv = {}
                for _, row in info.iterrows():
                    k = str(row.iloc[0])
                    v = row.iloc[1]
                    kv[k] = v
                item("行业", kv.get("行业", kv.get("所属行业")))
                item("上市时间", kv.get("上市时间"))
                item("总股本", kv.get("总股本"))
                item("流通股", kv.get("流通股"))
        except Exception as e:
            logger.debug("individual info: %s", e)

    # 52w range from history
    try:
        hist = get_history(code, market, days=250)
        if hist is not None and len(hist):
            item("区间最高(约1年)", float(hist["high"].max()))
            item("区间最低(约1年)", float(hist["low"].min()))
            item("近20日均价", float(hist["close"].tail(20).mean()))
    except Exception:
        pass

    return out


def _fmt_mv(v) -> str | None:
    if v is None:
        return None
    try:
        x = float(v)
    except Exception:
        return str(v)
    if x >= 1e12:
        return f"{x / 1e12:.2f} 万亿"
    if x >= 1e8:
        return f"{x / 1e8:.2f} 亿"
    if x >= 1e4:
        return f"{x / 1e4:.2f} 万"
    return f"{x:.0f}"
