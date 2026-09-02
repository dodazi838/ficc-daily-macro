"""
[FICC Daily Macro] 경제지표 캘린더 가공 및 16:30 KST 기준 3-Way 타임 윈도우 분류기 (event_processor.py)
"""

import datetime
import pytz
from typing import List, Dict, Any

KST_TZ = pytz.timezone('Asia/Seoul')

def ensure_kst_aware(dt: datetime.datetime) -> datetime.datetime:
    """datetime 객체를 Asia/Seoul 타임존 인식 객체로 보장"""
    if dt is None:
        return datetime.datetime.now(KST_TZ)
    if dt.tzinfo is None:
        return KST_TZ.localize(dt)
    return dt.astimezone(KST_TZ)

class MacroEventProcessor:
    """경제 지표 캘린더를 16:30 KST 기준으로 DAY_REVIEW / TODAY_NIGHT / UPCOMING_WEEK로 3분할 가공"""

    @classmethod
    def process_calendar_events(cls, raw_events: List[Dict[str, Any]], run_time_kst: datetime.datetime) -> Dict[str, Any]:
        if not raw_events:
            return {
                "total_events": 0,
                "counts_by_window": {"DAY_REVIEW": 0, "TODAY_NIGHT": 0, "UPCOMING_WEEK": 0, "OTHER": 0},
                "day_review_events": [],
                "today_night_events": [],
                "upcoming_week_events": [],
                "all_processed_events": []
            }

        run_kst = ensure_kst_aware(run_time_kst)
        today_1630 = run_kst.replace(hour=16, minute=30, second=0, microsecond=0)
        yesterday_1630 = today_1630 - datetime.timedelta(days=1)
        tomorrow_0600 = today_1630.replace(hour=6, minute=0, second=0) + datetime.timedelta(days=1)
        next_week = today_1630 + datetime.timedelta(days=7)

        day_review_list = []
        today_night_list = []
        upcoming_week_list = []
        all_processed = []

        for idx, ev in enumerate(raw_events):
            sched_dt = ev.get("scheduled_dt_kst")
            if not sched_dt:
                continue
            sched_dt = ensure_kst_aware(sched_dt)

            event_name = ev.get("event_name", "")
            country = ev.get("country", "GLOBAL")
            currency = ev.get("currency", "")
            importance = ev.get("importance", "LOW")
            name_lower = event_name.lower()

            # 1. 지표 영향 카테고리 (impact_category) 판정
            impact_cat = "GENERAL"
            if any(w in name_lower for w in ["rate", "policy", "monetary", "interest", "fomc", "rba", "rbnz", "boe", "ecb", "boj"]):
                impact_cat = "MONETARY_POLICY"
            elif any(w in name_lower for w in ["cpi", "ppi", "inflation", "price", "pce", "wpi"]):
                impact_cat = "INFLATION"
            elif any(w in name_lower for w in ["payroll", "employment", "job", "unemployment", "claims", "labor"]):
                impact_cat = "LABOR"
            elif any(w in name_lower for w in ["gdp", "growth", "output"]):
                impact_cat = "GROWTH"
            elif any(w in name_lower for w in ["pmi", "manufacturing", "services", "sentiment", "confidence"]):
                impact_cat = "SURVEY_PMI"
            elif any(w in name_lower for w in ["trade", "export", "import", "current account"]):
                impact_cat = "TRADE"

            # 2. 관련 자산군 매핑
            related_assets = []
            if currency == "USD" or country == "US":
                related_assets.extend(["US10Y", "US2Y", "DXY", "S&P 500"])
            elif currency == "KRW" or country == "KR":
                related_assets.extend(["KTB 3y", "KTB10y", "USD/KRW", "KOSPI"])
            elif currency == "EUR" or country == "EU":
                related_assets.extend(["EUR/USD", "DE10Y-DE", "EURO STOXX 50"])
            elif currency == "JPY" or country == "JP":
                related_assets.extend(["USD/JPY", "JP10Y-JP", "Nikkei"])
            elif currency == "CNY" or country == "CN":
                related_assets.extend(["USD/CNH", "상해종합", "WTI", "Copper"])

            if impact_cat in ["INFLATION", "MONETARY_POLICY"]:
                related_assets.extend(["Gold", "US10Y"])
            related_assets = list(dict.fromkeys(related_assets))

            # 3. 16:30 KST 기준 3-Way 타임 윈도우 분류
            time_window = "OTHER"
            if yesterday_1630 <= sched_dt <= today_1630:
                time_window = "DAY_REVIEW"
            elif today_1630 < sched_dt <= tomorrow_0600:
                time_window = "TODAY_NIGHT"
            elif tomorrow_0600 < sched_dt <= next_week:
                time_window = "UPCOMING_WEEK"

            date_str = sched_dt.strftime("%Y%m%d")
            event_id = f"EVT_{date_str}_{currency}_{idx+1:03d}"

            item = {
                "event_id": event_id,
                "event_name": event_name,
                "country": country,
                "currency": currency,
                "scheduled_raw": ev.get("scheduled_raw", ""),
                "scheduled_at_utc": ev.get("scheduled_at_utc", ""),
                "scheduled_at_kst": ev.get("scheduled_at_kst", ""),
                "scheduled_time_kst": ev.get("scheduled_time_kst", "") or sched_dt.strftime("%H:%M"),
                "importance": importance,
                "time_window": time_window,
                "prior": ev.get("prior"),
                "forecast": ev.get("forecast"),
                "actual": ev.get("actual"),
                "impact_category": impact_cat,
                "related_assets": related_assets,
                "source": ev.get("source", "ForexFactory")
            }

            all_processed.append(item)

            if time_window == "DAY_REVIEW":
                day_review_list.append(item)
            elif time_window == "TODAY_NIGHT":
                today_night_list.append(item)
            elif time_window == "UPCOMING_WEEK" and importance in ["HIGH", "MEDIUM"]:
                upcoming_week_list.append(item)

        return {
            "total_events": len(all_processed),
            "counts_by_window": {
                "DAY_REVIEW": len(day_review_list),
                "TODAY_NIGHT": len(today_night_list),
                "UPCOMING_WEEK": len(upcoming_week_list),
                "OTHER": len(all_processed) - (len(day_review_list) + len(today_night_list) + len(upcoming_week_list))
            },
            "day_review_events": day_review_list,
            "today_night_events": today_night_list,
            "upcoming_week_events": upcoming_week_list,
            "all_processed_events": all_processed
        }
