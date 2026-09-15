"""
[FICC Daily Macro] 미국 및 글로벌 금융시장 거래일 / 휴장일 판정 모듈 (holidays.py)
- 미국 현물 주식시장(NYSE, NASDAQ) 공식 휴장일
- 미국 국채시장(SIFMA 권고) 공식 휴장일
- 주말(토/일) 및 연방 공휴일(대체공휴일 포함) 정밀 판정
"""

import datetime
from typing import Tuple, Optional

def easter_date(year: int) -> datetime.date:
    """Meeus/Jones/Butcher 알고리즘을 사용한 부활절(Easter Sunday) 산출"""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return datetime.date(year, month, day)

def _get_nth_weekday(year: int, month: int, weekday: int, n: int) -> datetime.date:
    """해당 월의 n번째 특정 요일(0=월, 6=일) 반환"""
    count = 0
    for day in range(1, 32):
        try:
            d = datetime.date(year, month, day)
            if d.weekday() == weekday:
                count += 1
                if count == n:
                    return d
        except ValueError:
            break
    raise ValueError(f"{year}-{month}에 {n}번째 요일({weekday})이 존재하지 않습니다.")

def _get_last_weekday(year: int, month: int, weekday: int) -> datetime.date:
    """해당 월의 마지막 특정 요일(0=월, 6=일) 반환"""
    for day in range(31, 0, -1):
        try:
            d = datetime.date(year, month, day)
            if d.weekday() == weekday:
                return d
        except ValueError:
            pass
    raise ValueError(f"{year}-{month}에 마지막 요일({weekday})이 존재하지 않습니다.")

def _observe_fixed_holiday(year: int, month: int, day: int) -> datetime.date:
    """고정일 공휴일의 주말 대체공휴일(토->금, 일->월) 규칙 적용"""
    dt = datetime.date(year, month, day)
    if dt.weekday() == 5:  # 토요일 -> 금요일 대체
        return dt - datetime.timedelta(days=1)
    elif dt.weekday() == 6:  # 일요일 -> 월요일 대체
        return dt + datetime.timedelta(days=1)
    return dt

def is_us_equity_holiday(d: datetime.date) -> Tuple[bool, Optional[str]]:
    """
    미국 주식시장(NYSE/NASDAQ) 공식 휴장일 여부 및 휴장 명칭 반환
    """
    year = d.year

    # 주말
    if d.weekday() >= 5:
        return True, "Weekend"

    # 1. New Year's Day
    new_year = _observe_fixed_holiday(year, 1, 1)
    if d == new_year:
        return True, "New Year's Day"

    # 2. Martin Luther King Jr. Day (3rd Monday of Jan)
    mlk = _get_nth_weekday(year, 1, 0, 3)
    if d == mlk:
        return True, "Martin Luther King Jr. Day"

    # 3. Washington's Birthday / Presidents' Day (3rd Monday of Feb)
    presidents = _get_nth_weekday(year, 2, 0, 3)
    if d == presidents:
        return True, "Presidents' Day"

    # 4. Good Friday (Friday before Easter)
    easter = easter_date(year)
    good_friday = easter - datetime.timedelta(days=2)
    if d == good_friday:
        return True, "Good Friday"

    # 5. Memorial Day (Last Monday of May)
    memorial = _get_last_weekday(year, 5, 0)
    if d == memorial:
        return True, "Memorial Day"

    # 6. Juneteenth National Independence Day (June 19)
    juneteenth = _observe_fixed_holiday(year, 6, 19)
    if d == juneteenth:
        return True, "Juneteenth"

    # 7. Independence Day (July 4)
    independence = _observe_fixed_holiday(year, 7, 4)
    if d == independence:
        return True, "Independence Day"

    # 8. Labor Day (1st Monday of September)
    labor_day = _get_nth_weekday(year, 9, 0, 1)
    if d == labor_day:
        return True, "Labor Day"

    # 9. Thanksgiving Day (4th Thursday of November)
    thanksgiving = _get_nth_weekday(year, 11, 3, 4)
    if d == thanksgiving:
        return True, "Thanksgiving Day"

    # 10. Christmas Day (Dec 25)
    christmas = _observe_fixed_holiday(year, 12, 25)
    if d == christmas:
        return True, "Christmas Day"

    return False, None

def is_us_bond_holiday(d: datetime.date) -> Tuple[bool, Optional[str]]:
    """
    미국 국채시장(SIFMA 추천) 공식 전일 휴장일 여부 및 휴장 명칭 반환
    (주식시장 휴장일 + Columbus Day + Veterans Day)
    """
    # 주식시장 휴장일은 채권시장도 휴장
    is_eq_hol, name = is_us_equity_holiday(d)
    if is_eq_hol:
        return True, name

    year = d.year

    # 11. Columbus Day (2nd Monday of October)
    columbus = _get_nth_weekday(year, 10, 0, 2)
    if d == columbus:
        return True, "Columbus Day"

    # 12. Veterans Day (Nov 11)
    veterans = _observe_fixed_holiday(year, 11, 11)
    if d == veterans:
        return True, "Veterans Day"

    return False, None
