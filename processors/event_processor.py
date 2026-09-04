"""
[FICC Daily Macro] 경제지표 캘린더 가공 및 16:30 KST 기준 3-Way 타임 윈도우 분류기 (event_processor.py)
"""

import datetime
import pytz
from typing import List, Dict, Any

KST_TZ = pytz.timezone('Asia/Seoul')

def ensure_kst_aware(dt: Any) -> datetime.datetime:
    """datetime 객체 또는 날짜 문자열을 Asia/Seoul 타임존 인식 객체로 보장"""
    if dt is None:
        return datetime.datetime.now(KST_TZ)
    if isinstance(dt, str):
        clean_str = dt.replace(" KST", "").strip()
        try:
            import dateutil.parser
            parsed = dateutil.parser.parse(clean_str)
        except Exception:
            return datetime.datetime.now(KST_TZ)
        if parsed.tzinfo is None:
            return KST_TZ.localize(parsed)
        return parsed.astimezone(KST_TZ)
    if dt.tzinfo is None:
        return KST_TZ.localize(dt)
    return dt.astimezone(KST_TZ)

class MacroEventProcessor:
    @classmethod
    def score_macro_event(cls, ev: Dict[str, Any]) -> int:
        """금융시장 영향력 기반 매크로 이벤트 스코어링 (0~100점)"""
        name = ev.get("event_name", "")
        name_lower = name.lower()
        country = ev.get("country", "")
        importance = ev.get("importance", "LOW")

        # 1. 원칙적 제외 항목 (단순 Final PMI, 소규모 국가 지표, 채권 경매 등 시장 영향 제한 항목 -> 0점)
        if any(w in name_lower for w in ["auction", "bond auction", "bill auction", "tbill"]):
            return 0
        if any(w in name_lower for w in ["final services pmi", "final manufacturing pmi"]):
            return 0
        if any(w in name_lower for w in ["italian services", "spanish services", "spanish manufacturing", "french final", "german final"]):
            return 0
        if any(w in name_lower for w in ["challenger job cuts", "natural gas storage", "holiday", "bank holiday"]):
            return 0

        score = 0

        # 2. 미국 핵심 지표 및 연준 인사 발언 (Tier 1: 50~70점 기본 배점)
        if country == "US":
            if any(w in name_lower for w in ["non-farm payroll", "non-farm employment", "adp non-farm", "unemployment rate", "unemployment claims", "jobless claims", "jolts"]):
                score += 65
            elif any(w in name_lower for w in ["cpi", "core cpi", "ppi", "core ppi", "pce", "core pce"]):
                score += 65
            elif any(w in name_lower for w in ["ism manufacturing", "ism services", "retail sales", "gdp"]):
                score += 60
            elif any(w in name_lower for w in ["fomc", "federal funds rate", "rate decision"]):
                score += 70
            elif any(w in name_lower for w in ["powell speaks", "waller speaks", "williams speaks", "cook speaks", "bowman speaks", "goolsbee speaks", "hammack speaks", "speaks", "beige book"]):
                score += 50
            elif any(w in name_lower for w in ["crude oil inventories", "factory orders", "trade balance", "consumer confidence", "consumer sentiment"]):
                score += 45
            else:
                score += 20
        elif country in ["CA", "EU", "GB", "JP", "CN", "GLOBAL"]:
            if any(w in name_lower for w in ["rate statement", "overnight rate", "monetary policy", "interest rate", "ecb", "boe", "boj", "rbnz"]):
                score += 60
            elif any(w in name_lower for w in ["cpi", "ppi", "gdp", "employment change"]):
                score += 45
            elif any(w in name_lower for w in ["press conference", "gov speaks", "president speaks"]):
                score += 40
            else:
                score += 15

        # 3. 중요도 보정 (+10~30점)
        if importance == "HIGH":
            score += 30
        elif importance == "MEDIUM":
            score += 15

        return score

    @classmethod
    def get_macro_priority(cls, ev: Dict[str, Any]) -> int:
        """
        매크로 이벤트 정량/정책 우선순위 계층 판정:
        - Tier 4: 미국 핵심 고용(Non-farm, Unemployment rate, Jobless claims, ADP, JOLTS), 물가(CPI, PPI, PCE), ISM(제조업/서비스업), GDP, 소매판매, 중앙은행 금리결정(FOMC, BOC, ECB, BOJ, BOE 등)
        - Tier 3: 주요 글로벌(G7, 중국 등) CPI/GDP/고용 및 미국 원유재고(Crude Oil Inventories)
        - Tier 2: 중앙은행 주요 인사 발언(연준 의장, 이사, 통화정책 성명 등)
        - Tier 1: 기타 주요 지표(무역수지, 소비자심리지수, 공장재 수주 등)
        - Tier 0: 기타 지표
        """
        name = ev.get("event_name", "")
        name_lower = name.lower()
        country = ev.get("country", "")

        # 원칙적 제외 항목은 Tier -1
        if any(w in name_lower for w in ["auction", "bond auction", "bill auction", "tbill"]):
            return -1
        if any(w in name_lower for w in ["final services pmi", "final manufacturing pmi"]):
            return -1
        if any(w in name_lower for w in ["italian services", "spanish services", "spanish manufacturing", "french final", "german final"]):
            return -1
        if any(w in name_lower for w in ["challenger job cuts", "natural gas storage", "holiday", "bank holiday"]):
            return -1

        if country == "US":
            if any(w in name_lower for w in ["non-farm payroll", "non-farm employment", "adp non-farm", "unemployment rate", "unemployment claims", "jobless claims", "jolts"]):
                return 4
            if any(w in name_lower for w in ["cpi", "core cpi", "ppi", "core ppi", "pce", "core pce"]):
                return 4
            if any(w in name_lower for w in ["ism manufacturing", "ism services", "retail sales", "gdp"]):
                return 4
            if any(w in name_lower for w in ["fomc", "federal funds rate", "rate decision"]):
                return 4
            if any(w in name_lower for w in ["crude oil inventories"]):
                return 3
            if any(w in name_lower for w in ["powell speaks", "waller speaks", "williams speaks", "cook speaks", "bowman speaks", "goolsbee speaks", "hammack speaks", "speaks", "beige book"]):
                return 2
            if any(w in name_lower for w in ["factory orders", "trade balance", "consumer confidence", "consumer sentiment"]):
                return 1
            return 0
        elif country in ["CA", "EU", "GB", "JP", "CN", "GLOBAL"]:
            if any(w in name_lower for w in ["rate statement", "overnight rate", "monetary policy", "interest rate", "ecb", "boe", "boj", "rbnz"]):
                return 4
            if any(w in name_lower for w in ["cpi", "ppi", "gdp", "employment change"]):
                return 3
            if any(w in name_lower for w in ["press conference", "gov speaks", "president speaks"]):
                return 2
            return 1
        return 0

    @classmethod
    def curate_day_review_events(cls, events: List[Dict[str, Any]], run_time_kst: Any = None) -> List[Dict[str, Any]]:
        """
        당일 주요 발표 이벤트 (Past Events) 2~4개 선별:
        1. 실제 발표 결과(actual) 존재 여부 최우선
        2. canonical 매크로 우선순위(미국 핵심 고용·물가·ISM·GDP·소매판매·금리결정 등) 적용
        3. score_macro_event 점수 보조 기준 결합
        4. 시장 영향이 미미한 단순 이벤트 제외 후 상위 2~4개 엄선
        5. 시간순(scheduled_at_kst) 정렬
        """
        if not events:
            return []

        run_kst = ensure_kst_aware(run_time_kst)
        today_start = run_kst.replace(hour=0, minute=0, second=0, microsecond=0)

        # 1. 당일(today) 이벤트 우선 필터링
        today_candidates = []
        for ev in events:
            sched_dt = ev.get("scheduled_dt_kst") or ev.get("scheduled_at_kst")
            if sched_dt:
                sched_dt_kst = ensure_kst_aware(sched_dt)
                if today_start <= sched_dt_kst <= run_kst:
                    today_candidates.append(ev)
            elif ev.get("time_window") == "DAY_REVIEW":
                today_candidates.append(ev)

        # 당일 발표 이벤트가 충분치 않으면 전체 전달된 목록 풀 활용
        pool = today_candidates if len(today_candidates) >= 2 else events

        scored_pool = []
        for ev in pool:
            sc = cls.score_macro_event(ev)
            prio = cls.get_macro_priority(ev)
            if sc <= 0 or prio < 0:
                continue

            # actual 존재 여부 (공백, "-", "None" 제외)
            act_val = ev.get("actual")
            has_actual = 1 if (act_val is not None and str(act_val).strip() not in ["", "-", "None"]) else 0

            # 정량 지표 여부 (forecast나 prior가 있는 정규 발표 지표 우선)
            fc_or_pr = 1 if (ev.get("forecast") or ev.get("prior") or ev.get("previous")) else 0

            # 복합 우선순위 튜플: (actual 유무, 정량지표 유무, 매크로 우선순위 티어, 매크로 점수)
            sort_tuple = (has_actual, fc_or_pr, prio, sc)
            scored_pool.append((sort_tuple, ev))

        if not scored_pool:
            return []

        scored_pool.sort(key=lambda x: x[0], reverse=True)
        # 상위 2~4개 선별 (유효 지표가 4개 이상이면 4개, 최소 2개 이상)
        curated_count = min(max(2, min(4, len(scored_pool))), 4)
        curated = [x[1] for x in scored_pool[:curated_count]]
        # 시간순 정렬
        curated.sort(key=lambda x: x.get("scheduled_at_kst", ""))
        return curated

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
        today_start = run_kst.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start = today_start - datetime.timedelta(days=1)
        tomorrow_0600 = today_start.replace(hour=6, minute=0, second=0) + datetime.timedelta(days=1)
        next_week = run_kst + datetime.timedelta(days=7)

        day_review_list = []
        raw_today_night_list = []
        upcoming_week_list = []
        all_processed = []

        for idx, ev in enumerate(raw_events):
            sched_dt = ev.get("scheduled_dt_kst") or ev.get("scheduled_at_kst")
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

            # 3. 프로그램 실행 시각(run_kst) 기준 3-Way 타임 윈도우 분류
            time_window = "OTHER"
            if yesterday_start <= sched_dt <= run_kst:
                time_window = "DAY_REVIEW"
            elif run_kst < sched_dt <= tomorrow_0600:
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
                raw_today_night_list.append(item)
            elif time_window == "UPCOMING_WEEK" and importance in ["HIGH", "MEDIUM"]:
                upcoming_week_list.append(item)

        # 4. 당일 주요 발표 이벤트 (DAY_REVIEW) 큐레이션 (상위 2~4개 선별)
        curated_day_review = cls.curate_day_review_events(day_review_list, run_kst)

        # 5. TODAY_NIGHT 핵심 매크로 이벤트 선별 (금융시장 영향력 스코어 >= 35점, 최대 6개)
        scored_night = []
        for ev_item in raw_today_night_list:
            sc = cls.score_macro_event(ev_item)
            if sc >= 35:
                scored_night.append((sc, ev_item))

        scored_night.sort(key=lambda x: x[0], reverse=True)
        curated_today_night = [x[1] for x in scored_night[:6]]
        curated_today_night.sort(key=lambda x: x.get("scheduled_at_kst", ""))

        return {
            "total_events": len(all_processed),
            "counts_by_window": {
                "DAY_REVIEW": len(curated_day_review),
                "TODAY_NIGHT": len(curated_today_night),
                "UPCOMING_WEEK": len(upcoming_week_list),
                "OTHER": len(all_processed) - (len(curated_day_review) + len(curated_today_night) + len(upcoming_week_list))
            },
            "day_review_events": curated_day_review,
            "today_night_events": curated_today_night,
            "upcoming_week_events": upcoming_week_list,
            "all_processed_events": all_processed
        }
