"""A-share market clock (Asia/Shanghai)."""
from __future__ import annotations

import datetime as dt
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

CN_TZ = ZoneInfo("Asia/Shanghai")

MORNING = (time(9, 30), time(11, 30))
AFTERNOON = (time(13, 0), time(15, 0))
# pre-open auction window useful for "即将开盘" state
PRE_OPEN = (time(9, 15), time(9, 30))

# Official 2026 SH/SZ/BJ closure dates.
# Source: 上证公告〔2025〕45号 + 各交易所分假期补充公告.
# Weekends are already handled separately, but they are listed too where the
# exchange closed them as part of a holiday block for readability.
HOLIDAYS_2026 = {
    # 元旦 1/1(四)-1/3(六), 1/5(一) 开市
    dt.date(2026, 1, 1), dt.date(2026, 1, 2),
    # 春节 2/15(日)-2/23(一), 2/24(二) 开市
    dt.date(2026, 2, 16), dt.date(2026, 2, 17), dt.date(2026, 2, 18),
    dt.date(2026, 2, 19), dt.date(2026, 2, 20), dt.date(2026, 2, 23),
    # 清明节 4/4(六)-4/6(一), 4/7(二) 开市
    dt.date(2026, 4, 6),
    # 劳动节 5/1(五)-5/5(二), 5/6(三) 开市
    dt.date(2026, 5, 1), dt.date(2026, 5, 4), dt.date(2026, 5, 5),
    # 端午节 6/19(五)-6/21(日), 6/22(一) 开市
    dt.date(2026, 6, 19),
    # 中秋节 9/25(五)-9/27(日), 9/28(一) 开市
    dt.date(2026, 9, 25),
    # 国庆节 10/1(四)-10/7(三), 10/8(四) 开市
    dt.date(2026, 10, 1), dt.date(2026, 10, 2), dt.date(2026, 10, 5),
    dt.date(2026, 10, 6), dt.date(2026, 10, 7),
}
# 2027 起的安排尚未公布；届时补录。未覆盖的年份只按周末判断。
HOLIDAYS: set[dt.date] = set(HOLIDAYS_2026)


def is_holiday(day: dt.date) -> bool:
    return day in HOLIDAYS


def is_trading_day(day: dt.date) -> bool:
    """Weekday and not an exchange holiday."""
    return day.weekday() < 5 and not is_holiday(day)


def now_cn() -> datetime:
    return datetime.now(CN_TZ)


def _in_window(t: datetime, start: time, end: time) -> bool:
    return start <= t.time() <= end


def market_phase(moment: datetime | None = None) -> dict:
    t = moment or now_cn()
    weekday = t.weekday()  # Mon=0
    is_weekday = weekday < 5
    hm = t.time()
    holiday = is_holiday(t.date())

    phase = "closed"
    detail = "休市"
    if holiday:
        # A weekday the exchange is officially shut (春节/国庆 etc.).
        # Without this the monitor would poll a closed market all day.
        detail = "节假日休市"
    elif is_weekday:
        if _in_window(t, *PRE_OPEN):
            phase, detail = "pre_open", "集合竞价"
        elif _in_window(t, MORNING[0], MORNING[1]):
            phase, detail = "trading", "上午交易中"
        elif MORNING[1] < hm < AFTERNOON[0]:
            phase, detail = "lunch", "午间休市"
        elif _in_window(t, AFTERNOON[0], AFTERNOON[1]):
            phase, detail = "trading", "下午交易中"
        elif hm < PRE_OPEN[0]:
            phase, detail = "before", "开盘前"
        else:
            phase, detail = "after", "已收盘"
    else:
        detail = "周末休市"

    return {
        "now": t.isoformat(),
        "phase": phase,
        "detail": detail,
        "is_trading": phase == "trading",
        "is_holiday": holiday,
        "weekday": t.strftime("%A"),
    }


def should_monitor(dt: datetime | None = None) -> bool:
    """True during continuous trading hours on real trading days."""
    return market_phase(dt)["is_trading"]
