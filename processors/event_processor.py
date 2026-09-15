"""
[FICC Daily Macro] 경제지표 캘린더 가공, 중앙은행 정책 클러스터링 및 다구간 타임 윈도우 큐레이터 (event_processor.py)
"""

import datetime
import pytz
import re
from typing import List, Dict, Any, Optional, Tuple

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
    # pytz LMT 오프셋(예: 8시간 28분) 변칙 방어
    if hasattr(dt.tzinfo, "zone") and dt.tzinfo.zone == "Asia/Seoul":
        if dt.utcoffset() != datetime.timedelta(hours=9):
            naive = dt.replace(tzinfo=None)
            return KST_TZ.localize(naive)
    return dt.astimezone(KST_TZ)

def normalize_policy_event(event_name: str, country: str = "") -> Optional[Dict[str, Any]]:
    """
    ECB, FED, BOJ, BOE 등 주요 중앙은행의 정책결정 구성 요소 식별 및 정규화
    - institution: ECB, FED, BOJ, BOE
    - component_type: RATE_DECISION, STATEMENT, PRESS_CONFERENCE, PROJECTIONS, POLICY_REMARKS
    - representative_name: 대표 이벤트명
    """
    if not event_name:
        return None

    name_lower = event_name.lower()
    c_upper = (country or "").upper()

    # 1. ECB (유럽중앙은행)
    is_ecb_candidate = (
        c_upper in ["EU", "EUR"] or 
        "ecb" in name_lower or 
        "european central bank" in name_lower or
        "lagarde" in name_lower
    )
    if is_ecb_candidate:
        if any(w in name_lower for w in [
            "main refinancing rate", "deposit facility rate", "marginal lending",
            "ecb interest rate", "ecb rate decision", "ecb monetary policy decision",
            "refinancing rate", "interest rate decision", "rate decision"
        ]):
            return {
                "institution": "ECB",
                "component_type": "RATE_DECISION",
                "representative_name": "ECB 통화정책 결정",
                "country": "EU",
                "currency": "EUR"
            }
        if any(w in name_lower for w in [
            "monetary policy statement", "ecb statement", "rate statement", "policy statement"
        ]):
            return {
                "institution": "ECB",
                "component_type": "STATEMENT",
                "representative_name": "ECB 통화정책 결정",
                "country": "EU",
                "currency": "EUR"
            }
        if any(w in name_lower for w in ["ecb press conference", "press conference"]):
            return {
                "institution": "ECB",
                "component_type": "PRESS_CONFERENCE",
                "representative_name": "ECB 통화정책 결정",
                "country": "EU",
                "currency": "EUR"
            }
        if any(w in name_lower for w in [
            "macroeconomic projections", "staff projections", "economic projections", "staff macroeconomic"
        ]):
            return {
                "institution": "ECB",
                "component_type": "PROJECTIONS",
                "representative_name": "ECB 통화정책 결정",
                "country": "EU",
                "currency": "EUR"
            }
        if any(w in name_lower for w in ["lagarde speaks", "president lagarde speaks"]):
            return {
                "institution": "ECB",
                "component_type": "POLICY_REMARKS",
                "representative_name": "ECB 통화정책 결정",
                "country": "EU",
                "currency": "EUR"
            }

    # 2. Fed (연준 / FOMC)
    is_fed_candidate = (
        c_upper in ["US", "USD"] or 
        "fed" in name_lower or 
        "fomc" in name_lower or
        "powell" in name_lower
    )
    if is_fed_candidate:
        if any(w in name_lower for w in [
            "federal funds rate", "fomc rate decision", "fomc policy decision",
            "funds rate", "fed interest rate", "rate decision"
        ]):
            return {
                "institution": "FED",
                "component_type": "RATE_DECISION",
                "representative_name": "FOMC 기준금리 결정",
                "country": "US",
                "currency": "USD"
            }
        if any(w in name_lower for w in [
            "fomc statement", "fed statement", "monetary policy statement"
        ]):
            return {
                "institution": "FED",
                "component_type": "STATEMENT",
                "representative_name": "FOMC 기준금리 결정",
                "country": "US",
                "currency": "USD"
            }
        if any(w in name_lower for w in [
            "fomc press conference", "fed press conference", "powell press conference", "chair press conference"
        ]):
            return {
                "institution": "FED",
                "component_type": "PRESS_CONFERENCE",
                "representative_name": "FOMC 기준금리 결정",
                "country": "US",
                "currency": "USD"
            }
        if any(w in name_lower for w in [
            "sep", "summary of economic projections", "fomc economic projections"
        ]):
            return {
                "institution": "FED",
                "component_type": "PROJECTIONS",
                "representative_name": "FOMC 기준금리 결정",
                "country": "US",
                "currency": "USD"
            }
        if any(w in name_lower for w in ["powell speaks"]):
            return {
                "institution": "FED",
                "component_type": "POLICY_REMARKS",
                "representative_name": "FOMC 기준금리 결정",
                "country": "US",
                "currency": "USD"
            }

    # 3. BOJ (일본은행)
    is_boj_candidate = (
        c_upper in ["JP", "JPY"] or 
        "boj" in name_lower or 
        "bank of japan" in name_lower or
        "ueda" in name_lower
    )
    if is_boj_candidate:
        if any(w in name_lower for w in [
            "boj policy rate", "monetary policy rate", "boj interest rate", "boj rate decision", "policy rate"
        ]):
            return {
                "institution": "BOJ",
                "component_type": "RATE_DECISION",
                "representative_name": "BOJ 금융정책결정회의",
                "country": "JP",
                "currency": "JPY"
            }
        if any(w in name_lower for w in [
            "monetary policy statement", "boj statement"
        ]):
            return {
                "institution": "BOJ",
                "component_type": "STATEMENT",
                "representative_name": "BOJ 금융정책결정회의",
                "country": "JP",
                "currency": "JPY"
            }
        if any(w in name_lower for w in [
            "boj press conference", "governor ueda press conference", "ueda press conference", "press conference"
        ]):
            return {
                "institution": "BOJ",
                "component_type": "PRESS_CONFERENCE",
                "representative_name": "BOJ 금융정책결정회의",
                "country": "JP",
                "currency": "JPY"
            }
        if any(w in name_lower for w in [
            "outlook report", "boj outlook report", "economic outlook"
        ]):
            return {
                "institution": "BOJ",
                "component_type": "PROJECTIONS",
                "representative_name": "BOJ 금융정책결정회의",
                "country": "JP",
                "currency": "JPY"
            }
        if any(w in name_lower for w in ["ueda speaks", "governor ueda speaks"]):
            return {
                "institution": "BOJ",
                "component_type": "POLICY_REMARKS",
                "representative_name": "BOJ 금융정책결정회의",
                "country": "JP",
                "currency": "JPY"
            }

    # 4. BOE (영국중앙은행)
    is_boe_candidate = (
        c_upper in ["GB", "GBP"] or 
        "boe" in name_lower or 
        "bank of england" in name_lower or
        "bailey" in name_lower
    )
    if is_boe_candidate:
        if any(w in name_lower for w in [
            "official bank rate", "bank rate", "boe rate decision", "boe bank rate"
        ]):
            return {
                "institution": "BOE",
                "component_type": "RATE_DECISION",
                "representative_name": "BOE 통화정책 결정",
                "country": "GB",
                "currency": "GBP"
            }
        if any(w in name_lower for w in [
            "monetary policy summary", "mpc summary", "mpc minutes", "mpc votes"
        ]):
            return {
                "institution": "BOE",
                "component_type": "STATEMENT",
                "representative_name": "BOE 통화정책 결정",
                "country": "GB",
                "currency": "GBP"
            }
        if any(w in name_lower for w in [
            "boe press conference", "governor bailey speaks", "bailey speaks"
        ]):
            return {
                "institution": "BOE",
                "component_type": "PRESS_CONFERENCE",
                "representative_name": "BOE 통화정책 결정",
                "country": "GB",
                "currency": "GBP"
            }
        if any(w in name_lower for w in [
            "monetary policy report", "boe inflation report"
        ]):
            return {
                "institution": "BOE",
                "component_type": "PROJECTIONS",
                "representative_name": "BOE 통화정책 결정",
                "country": "GB",
                "currency": "GBP"
            }

    return None

def is_macro_event_override(event_name: str, country: str = "", importance: str = "LOW", policy_info: Optional[Dict[str, Any]] = None) -> bool:
    """
    주요 중앙은행 정책결정 및 핵심 거시경제 지표를 무조건 Tier A 후보로 승격하는 Macro Event Override
    """
    if policy_info and policy_info.get("component_type") in ["RATE_DECISION", "STATEMENT", "PRESS_CONFERENCE", "PROJECTIONS"]:
        return True

    name_lower = (event_name or "").lower()
    c_upper = (country or "").upper()

    # 1. 미국 핵심 물가지표 (CPI, PPI, PCE)
    if c_upper == "US":
        if any(w in name_lower for w in ["cpi", "core cpi", "ppi", "core ppi", "pce", "core pce"]):
            return True
        # 2. 미국 핵심 고용지표 (Non-farm, Unemployment rate, Jobless claims, ADP, JOLTS)
        if any(w in name_lower for w in [
            "non-farm payroll", "non-farm employment", "adp", "unemployment rate", 
            "unemployment claims", "jobless claims", "jolts"
        ]):
            return True
        # 3. 미국 핵심 경기지표 (ISM, GDP 속보/잠정치, 소매판매)
        if any(w in name_lower for w in ["ism manufacturing", "ism services", "retail sales"]):
            return True
        if "gdp" in name_lower and not any(w in name_lower for w in ["revised", "final"]):
            return True

    # 4. 기타 주요국 금리결정
    if any(w in name_lower for w in ["rate statement", "overnight rate", "interest rate decision", "monetary policy decision"]):
        return True

    return False


class MacroEventProcessor:
    """
    금융시장 영향력 기반 매크로 이벤트 스코어링, 중요도 계층화 및 중앙은행 정책결정 클러스터링 엔진
    """

    @classmethod
    def score_macro_event(cls, ev: Dict[str, Any]) -> int:
        """
        금융시장 영향력 기반 매크로 이벤트 스코어링 (0~100점)
        우선순위 계층:
        1. 중앙은행 정책결정 (ECB, FOMC, BOJ, BOE): 85~95점
        2. 주요 물가 / 고용 (US CPI, PPI, PCE, Non-Farm, Unemployment Rate, Claims, ADP): 75~85점
        3. 주요 경기지표 (ISM Mfg/Services, US GDP, Retail Sales): 65~75점
        4. 국채시장 핵심 이벤트 (US Treasury Auctions 10Y/30Y/3Y, Benchmark Auctions): 45~55점
        5. 주요 원자재 재고 / 공급 이벤트 (Crude Oil Inventories): 45~55점
        6. 일반 중앙은행 발언 (Nagel, Waller, Lagarde on non-policy day): 35~40점
        7. 기타 일반 지표 (Consumer Credit, Trade Balance, Factory Orders): 25~35점
        """
        name = ev.get("event_name", "")
        name_lower = name.lower()
        country = (ev.get("country") or "").upper()
        importance = (ev.get("importance") or "LOW").upper()

        # 완전 제외 항목 (0점)
        if any(w in name_lower for w in ["challenger job cuts", "natural gas storage", "holiday", "bank holiday"]):
            return 0
        if any(w in name_lower for w in ["italian services", "spanish services", "spanish manufacturing", "french final", "german final"]):
            return 0

        # 정책 클러스터 자체는 최고 점수
        if ev.get("cluster_type") == "CENTRAL_BANK_POLICY":
            return 95

        # 1. 중앙은행 정책결정 이벤트 (Priority 1)
        pol_info = normalize_policy_event(name, country)
        if pol_info and pol_info.get("component_type") in ["RATE_DECISION", "STATEMENT", "PRESS_CONFERENCE", "PROJECTIONS"]:
            return 90

        # Macro Override 항목은 최소 75점 보장
        is_override = ev.get("macro_event_override", False) or is_macro_event_override(name, country, importance, pol_info)

        score = 0

        # 2. 미국 핵심 지표 및 고용/물가 (Priority 2)
        if country == "US":
            if any(w in name_lower for w in ["cpi", "core cpi", "ppi", "core ppi", "pce", "core pce"]):
                score = 80
            elif any(w in name_lower for w in [
                "non-farm payroll", "non-farm employment", "adp", "unemployment rate", 
                "unemployment claims", "jobless claims", "jolts"
            ]):
                score = 80
            # 3. 미국 주요 경기지표 (Priority 3)
            elif any(w in name_lower for w in ["ism manufacturing", "ism services", "retail sales", "gdp"]):
                score = 70
            elif any(w in name_lower for w in ["fomc", "federal funds rate", "rate decision"]):
                score = 85
            # 4. 국채시장 핵심 이벤트 (Priority 4)
            elif any(w in name_lower for w in ["auction", "bond auction", "note auction", "tbill", "treasury auction"]):
                score = 50
            # 5. 원자재 재고 (Priority 5)
            elif any(w in name_lower for w in ["crude oil inventories"]):
                score = 50
            # 6. 연준 주요 인사 발언 (Priority 6)
            elif any(w in name_lower for w in ["powell speaks", "waller speaks", "williams speaks", "cook speaks", "bowman speaks", "goolsbee speaks", "hammack speaks", "speaks", "beige book"]):
                score = 38
            # 7. 기타 지표 (Priority 7)
            elif any(w in name_lower for w in ["consumer credit", "factory orders", "trade balance", "consumer confidence", "consumer sentiment"]):
                score = 30
            else:
                score = 25
        elif country in ["CA", "EU", "GB", "JP", "CN", "GLOBAL"]:
            if any(w in name_lower for w in ["rate statement", "overnight rate", "monetary policy", "interest rate", "ecb", "boe", "boj", "rbnz"]):
                score = 80
            elif any(w in name_lower for w in ["cpi", "ppi", "gdp", "employment change"]):
                score = 65
            elif any(w in name_lower for w in ["auction", "bond auction"]):
                score = 45
            elif any(w in name_lower for w in ["press conference", "gov speaks", "president speaks", "speaks"]):
                score = 38
            elif any(w in name_lower for w in ["trade balance", "retail sales", "industrial production"]):
                score = 30
            else:
                score = 20
        else:
            score = 15

        # 중요도 보정
        if importance == "HIGH":
            score += 15
        elif importance == "MEDIUM":
            score += 8

        if is_override:
            score = max(score, 75)

        return min(score, 100)

    @classmethod
    def get_macro_priority(cls, ev: Dict[str, Any]) -> int:
        """
        매크로 이벤트 5성급 우선순위 체계:
        - ★★★★★ (prio = 5): 중앙은행 정책결정 (기준금리 결정, 성명서, 기자회견, 경제전망, 정책 클러스터)
        - ★★★★ (prio = 4): CPI, Core CPI, PCE, Core PCE, PPI, Core PPI, 핵심 고용(NFP, ADP, 실업률, 실업수당청구), GDP 속보치
        - ★★★ (prio = 3): PMI / ISM (제조업/서비스업), 소매판매, 주요 심리지수(소비자신뢰, 미시간), 원유재고(EIA), JOLTS, 주요국 핵심 지표
        - ★★ (prio = 2): 주요 국채 입찰 (US 10Y/30Y/3Y, 벤치마크 국채 입찰), 주요 중앙은행 총재/위원 발언
        - ★ (prio = 1): 기타 지표 (소비자신용 Consumer Credit, 공장재수주, 무역수지, 도매재고, 세부 확정치/수정치, Final PMI 등)
        - 제외 (prio = -1): Challenger 감원, 천연가스 재고, 단순 공휴일 등
        """
        name = ev.get("event_name", "")
        name_lower = name.lower()
        country = (ev.get("country") or "").upper()
        importance = (ev.get("importance") or "LOW").upper()

        # 확정치/수정치(Final CPI, Final PMI, Revised GDP 등) 및 개별 하위 지표는 1성급(prio = 1)으로 분류
        if any(w in name_lower for w in [
            "final cpi", "revised cpi", "final pmi", "final services", "final manufacturing",
            "german final", "french final", "italian final", "spanish final",
            "german industrial production", "french industrial", "italian industrial", "spanish industrial",
            "revised gdp", "final employment change", "revised employment", "final employment",
            "leading indicators", "coincident index", "leading index", "선행지수", "동행지수"
        ]):
            return 1

        # 1. Priority 5 (★★★★★): 중앙은행 정책결정
        if ev.get("cluster_type") == "CENTRAL_BANK_POLICY":
            return 5

        pol_info = normalize_policy_event(name, country)
        if pol_info and pol_info.get("component_type") in ["RATE_DECISION", "STATEMENT", "PRESS_CONFERENCE", "PROJECTIONS"]:
            return 5

        if any(w in name_lower for w in [
            "refinancing rate", "interest rate decision", "rate decision", "monetary policy decision",
            "overnight rate", "official bank rate", "federal funds rate", "fomc statement",
            "ecb rate", "boe rate", "boj rate"
        ]):
            return 5

        # 2. Priority 4 (★★★★): 물가, 고용, GDP
        # 물가지표 (CPI, Core CPI, PPI, Core PPI, PCE, Core PCE, HICP)
        if any(w in name_lower for w in ["cpi", "core cpi", "ppi", "core ppi", "pce", "core pce", "hicp"]):
            return 4

        # 고용지표 (Non-farm, ADP, 실업률, 신규 실업수당 청구)
        if any(w in name_lower for w in [
            "non-farm payroll", "non-farm employment", "nonfarm payroll", "adp",
            "unemployment rate", "unemployment claims", "jobless claims"
        ]):
            return 4

        # GDP 속보치/잠정치
        if "gdp" in name_lower and not any(w in name_lower for w in ["revised", "final"]):
            return 4

        # 3. Priority 3 (★★★): 경기(PMI/ISM), 소매판매, 심리/신뢰도, 원유재고, JOLTS
        if any(w in name_lower for w in [
            "ism manufacturing", "ism services", "retail sales",
            "consumer confidence", "consumer sentiment", "michigan",
            "crude oil inventories", "jolts"
        ]):
            return 3

        if any(w in name_lower for w in ["flash manufacturing pmi", "flash services pmi", "manufacturing pmi", "services pmi", "pmi"]) and not any(w in name_lower for w in ["final"]):
            return 3

        # 주요국(유로존, 중국, 일본, 영국, 독일, 캐나다 등) 핵심 물가/성장/고용
        if country in ["EU", "CN", "JP", "GB", "DE", "CA"]:
            if any(w in name_lower for w in ["employment change", "industrial production"]):
                return 3

        # 4. Priority 2 (★★): 주요 국채 입찰 및 핵심 중앙은행 총재 발언
        if any(w in name_lower for w in ["auction", "bond auction", "note auction", "tbill", "treasury auction"]):
            return 2

        # 핵심 중앙은행 총재(파월, 라가르드, 우에다, 베일리) 또는 HIGH 중요도 발언만 2성급
        if any(w in name_lower for w in ["powell speaks", "lagarde speaks", "ueda speaks", "bailey speaks"]):
            return 2
        if importance == "HIGH" and any(w in name_lower for w in ["speaks", "speech"]):
            return 2

        # 5. Priority 1 (★): 기타 일반 지표 (Consumer Credit, Factory Orders, Trade Balance, 일반 위원 발언 등)
        return 1

    @classmethod
    def cluster_policy_events(cls, events: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        동일 날짜·동일 중앙은행(ECB, FED, BOJ, BOE) 정책결정 이벤트를 CENTRAL_BANK_POLICY 클러스터로 번들링
        반환: (clusters, clustered_event_ids)
        """
        from collections import defaultdict
        grouped = defaultdict(list)

        for ev in events:
            name = ev.get("event_name", "")
            country = ev.get("country", "")
            pol_info = normalize_policy_event(name, country)
            if pol_info:
                sched_dt = ev.get("scheduled_dt_kst")
                if not sched_dt and ev.get("scheduled_at_kst"):
                    sched_dt = ensure_kst_aware(ev.get("scheduled_at_kst"))
                if sched_dt:
                    policy_date = sched_dt.strftime("%Y-%m-%d")
                    inst = pol_info.get("institution")
                    grouped[(inst, policy_date)].append((ev, pol_info))

        clusters = []
        clustered_ids = set()

        for (inst, policy_date), items in grouped.items():
            # 최소 하나의 결정/성명서/기자회견/전망이 포함되어야 정책결정일 클러스터로 성립
            has_core_decision = any(
                pinfo["component_type"] in ["RATE_DECISION", "STATEMENT", "PRESS_CONFERENCE", "PROJECTIONS"]
                for _, pinfo in items
            )
            if not has_core_decision:
                continue

            components = []
            rep_name = items[0][1]["representative_name"]
            country = items[0][1]["country"]
            currency = items[0][1]["currency"]

            rate_decision_dt = None
            rate_decision_time = None
            rate_forecast = None
            rate_prior = None
            rate_actual = None

            for ev, pinfo in items:
                clustered_ids.add(ev.get("event_id"))
                comp_dt = ev.get("scheduled_dt_kst") or ensure_kst_aware(ev.get("scheduled_at_kst"))
                time_str = ev.get("scheduled_time_kst") or comp_dt.strftime("%H:%M")
                
                comp_item = {
                    "event_id": ev.get("event_id"),
                    "event_name": ev.get("event_name"),
                    "scheduled_at_kst": ev.get("scheduled_at_kst") or comp_dt.strftime("%Y-%m-%d %H:%M:%S KST"),
                    "scheduled_time_kst": time_str,
                    "scheduled_dt_kst": comp_dt,
                    "component_type": pinfo.get("component_type"),
                    "forecast": ev.get("forecast"),
                    "prior": ev.get("prior") or ev.get("previous"),
                    "actual": ev.get("actual")
                }
                components.append(comp_item)

                if pinfo["component_type"] == "RATE_DECISION" and not rate_decision_dt:
                    rate_decision_dt = comp_dt
                    rate_decision_time = time_str
                    rate_forecast = ev.get("forecast")
                    rate_prior = ev.get("prior") or ev.get("previous")
                    rate_actual = ev.get("actual")

            components.sort(key=lambda x: x["scheduled_dt_kst"])

            # 대표 시각: 기준금리 결정 시각 우선, 없으면 첫 번째 컴포넌트 시각
            sched_dt = rate_decision_dt or components[0]["scheduled_dt_kst"]
            sched_time_str = rate_decision_time or components[0]["scheduled_time_kst"]

            cluster_id = f"CLUSTER_{inst}_POLICY_{policy_date.replace('-', '')}"
            cluster_dict = {
                "cluster_type": "CENTRAL_BANK_POLICY",
                "cluster_id": cluster_id,
                "event_id": cluster_id,
                "institution": inst,
                "policy_date": policy_date,
                "importance": "HIGH",
                "tier": "A",
                "macro_priority": 5,
                "macro_event_override": True,
                "representative_event": rep_name,
                "event_name": rep_name,
                "event_name_kor": rep_name,
                "country": country,
                "currency": currency,
                "scheduled_at_kst": sched_dt.strftime("%Y-%m-%d %H:%M:%S KST"),
                "scheduled_time_kst": sched_time_str,
                "scheduled_dt_kst": sched_dt,
                "forecast": rate_forecast,
                "prior": rate_prior,
                "previous": rate_prior,
                "actual": rate_actual,
                "is_revised_prior": False,
                "impact_category": "MONETARY_POLICY",
                "related_assets": ["US10Y", "EUR/USD" if inst == "ECB" else "DXY", "EURO STOXX 50" if inst == "ECB" else "S&P 500"],
                "source": "CentralBankPolicyCluster",
                "components": components
            }
            clusters.append(cluster_dict)

        return clusters, list(clustered_ids)

    @classmethod
    def cluster_cpi_events(cls, events: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        동일 날짜·동일 국가의 CPI 세부 항목들(Core m/m, Core y/y, Headline m/m, Headline y/y 등)을
        단일 '미국 소비자물가지수(CPI) 발표' Macro Event Cluster로 번들링
        """
        from collections import defaultdict
        grouped = defaultdict(list)

        for ev in events:
            name_lower = (ev.get("event_name") or "").lower()
            if "cpi" in name_lower and not any(w in name_lower for w in ["ppi", "pce"]):
                sched_dt = ev.get("scheduled_dt_kst")
                if not sched_dt and ev.get("scheduled_at_kst"):
                    sched_dt = ensure_kst_aware(ev.get("scheduled_at_kst"))
                if sched_dt:
                    c_date = sched_dt.strftime("%Y-%m-%d")
                    country = (ev.get("country") or "US").upper()
                    grouped[(country, c_date)].append(ev)

        clusters = []
        clustered_ids = set()

        for (country, c_date), items in grouped.items():
            if len(items) < 2:
                continue

            components = []
            rep_name = "미국 소비자물가지수(CPI) 발표" if country == "US" else f"{country} 소비자물가지수(CPI) 발표"
            currency = items[0].get("currency") or "USD"

            headline_yy_fc = None
            headline_mm_fc = None
            headline_yy_act = None
            headline_mm_act = None
            rep_prior = None
            rep_trace = None
            rep_actual_source = None

            for ev in items:
                clustered_ids.add(ev.get("event_id"))
                comp_dt = ev.get("scheduled_dt_kst") or ensure_kst_aware(ev.get("scheduled_at_kst"))
                time_str = ev.get("scheduled_time_kst") or comp_dt.strftime("%H:%M")
                ev_name = ev.get("event_name", "")
                ev_name_lower = ev_name.lower()

                if "core" in ev_name_lower:
                    d_type = "Core y/y" if "y/y" in ev_name_lower else ("Core m/m" if "m/m" in ev_name_lower else "Core")
                else:
                    d_type = "Headline y/y" if "y/y" in ev_name_lower else ("Headline m/m" if "m/m" in ev_name_lower else "Headline")

                if d_type == "Headline y/y":
                    headline_yy_fc = ev.get("forecast")
                    headline_yy_act = ev.get("actual")
                    rep_prior = ev.get("prior") or ev.get("previous")
                    if ev.get("actual_trace"):
                        rep_trace = ev.get("actual_trace")
                    if ev.get("actual_source"):
                        rep_actual_source = ev.get("actual_source")
                elif d_type == "Headline m/m":
                    headline_mm_fc = ev.get("forecast")
                    headline_mm_act = ev.get("actual")
                    if not rep_trace and ev.get("actual_trace"):
                        rep_trace = ev.get("actual_trace")
                    if not rep_actual_source and ev.get("actual_source"):
                        rep_actual_source = ev.get("actual_source")

                from generators.blog_formatter import NaverBlogFormatter
                comp_item = {
                    "event_id": ev.get("event_id"),
                    "event_name": ev.get("event_name"),
                    "event_name_kor": NaverBlogFormatter.translate_event_name(ev.get("event_name", ""), country),
                    "detail_type": d_type,
                    "scheduled_at_kst": ev.get("scheduled_at_kst") or comp_dt.strftime("%Y-%m-%d %H:%M:%S KST"),
                    "scheduled_time_kst": time_str,
                    "scheduled_dt_kst": comp_dt,
                    "forecast": ev.get("forecast"),
                    "prior": ev.get("prior") or ev.get("previous"),
                    "actual": ev.get("actual")
                }
                components.append(comp_item)

            components.sort(key=lambda x: (0 if "Headline" in x["detail_type"] else 1, x["scheduled_dt_kst"]))

            sched_dt = items[0].get("scheduled_dt_kst") or ensure_kst_aware(items[0].get("scheduled_at_kst"))
            sched_time_str = items[0].get("scheduled_time_kst") or sched_dt.strftime("%H:%M")
            rep_forecast = headline_yy_fc or headline_mm_fc or items[0].get("forecast")
            rep_actual = headline_yy_act or headline_mm_act or next((ev.get("actual") for ev in items if ev.get("actual")), None)
            if not rep_trace:
                rep_trace = next((ev.get("actual_trace") for ev in items if ev.get("actual_trace")), None)
            if not rep_actual_source:
                rep_actual_source = next((ev.get("actual_source") for ev in items if ev.get("actual_source")), None)

            cluster_id = f"CLUSTER_{country}_CPI_{c_date.replace('-', '')}"
            cluster_dict = {
                "cluster_type": "CPI_CLUSTER",
                "cluster_id": cluster_id,
                "event_id": cluster_id,
                "policy_date": c_date,
                "importance": "HIGH",
                "tier": "A",
                "macro_priority": 4,
                "macro_event_override": True,
                "representative_event": rep_name,
                "event_name": rep_name,
                "event_name_kor": rep_name,
                "country": country,
                "currency": currency,
                "scheduled_at_kst": sched_dt.strftime("%Y-%m-%d %H:%M:%S KST"),
                "scheduled_time_kst": sched_time_str,
                "scheduled_dt_kst": sched_dt,
                "forecast": rep_forecast,
                "prior": rep_prior,
                "previous": rep_prior,
                "actual": rep_actual,
                "actual_source": rep_actual_source,
                "actual_status": "FOUND" if rep_actual and str(rep_actual).strip() not in ["", "-", "None"] else "NOT_FOUND",
                "freshness_status": ("RELEASED_WITH_ACTUAL" if rep_actual and str(rep_actual).strip() not in ["", "-", "None"] else "RELEASED_ACTUAL_NOT_FOUND") if sched_dt <= ensure_kst_aware(None) else "UPCOMING",
                "actual_trace": rep_trace or items[0].get("actual_trace"),
                "is_revised_prior": False,
                "impact_category": "INFLATION",
                "related_assets": ["US10Y", "US2Y", "DXY", "S&P 500", "Gold"],
                "source": "MacroEventCluster",
                "components": components
            }
            clusters.append(cluster_dict)

        return clusters, list(clustered_ids)

    @classmethod
    def get_next_trading_day_range(cls, run_kst: datetime.datetime) -> Tuple[datetime.date, datetime.datetime, datetime.datetime]:
        """실행 시각 기준 다음 거래일(영업일) 날짜 및 시작/종료 범위(KST) 반환"""
        weekday = run_kst.weekday()  # 0: Mon, ..., 4: Fri, 5: Sat, 6: Sun
        if weekday == 4:    # 금요일 -> 월요일 (+3일)
            next_date = (run_kst + datetime.timedelta(days=3)).date()
        elif weekday == 5:  # 토요일 -> 월요일 (+2일)
            next_date = (run_kst + datetime.timedelta(days=2)).date()
        else:               # 일~목 -> 익일 (+1일)
            next_date = (run_kst + datetime.timedelta(days=1)).date()

        next_start = KST_TZ.localize(datetime.datetime.combine(next_date, datetime.time(0, 0, 0)))
        next_end = KST_TZ.localize(datetime.datetime.combine(next_date, datetime.time(23, 59, 59)))
        return next_date, next_start, next_end

    @classmethod
    def curate_day_review_events(cls, events: List[Dict[str, Any]], run_time_kst: Any = None, clusters: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """
        당일 주요 발표 이벤트 (Past Events) 선별:
        - 실행 시각 이전 발표된 이벤트
        - 엄격한 prio >= 2 (2성급 이상) 필터링
        - prio == 1 (Consumer Credit 등) 절대 포함하지 않음 (테이블 억지 채우기 금지)
        - prio 내림차순 최우선 정렬 (낮은 중요도가 높은 중요도를 절대 밀어내지 못함)
        - 핵심 이벤트가 2개라면 2개만 출력 (항상 4개를 채우지 않음)
        """
        if not events and not clusters:
            return []

        run_kst = ensure_kst_aware(run_time_kst)
        today_start = run_kst.replace(hour=0, minute=0, second=0, microsecond=0)
        today_str = run_kst.strftime("%Y-%m-%d")

        today_candidates = []
        for ev in events:
            sched_dt = ev.get("scheduled_dt_kst") or ev.get("scheduled_at_kst")
            if sched_dt:
                sched_dt_kst = ensure_kst_aware(sched_dt)
                if today_start <= sched_dt_kst <= run_kst:
                    today_candidates.append(ev)
            elif ev.get("time_window") == "DAY_REVIEW":
                today_candidates.append(ev)

        pool = today_candidates if today_candidates else list(events)

        scored_pool = []
        if clusters:
            for c in clusters:
                c_date = c.get("policy_date")
                sched_dt = c.get("scheduled_dt_kst")
                sched_dt_kst = ensure_kst_aware(sched_dt) if sched_dt else None
                if c_date == today_str and sched_dt_kst and sched_dt_kst <= run_kst:
                    prio = c.get("macro_priority", 4)
                    act_val = c.get("actual")
                    has_actual = 1 if (act_val is not None and str(act_val).strip() not in ["", "-", "None"]) else 0
                    fc_or_pr = 1 if (c.get("forecast") or c.get("prior") or c.get("previous")) else 0
                    sort_tuple = (prio, has_actual, fc_or_pr, 100)
                    scored_pool.append((sort_tuple, c))

        for ev in pool:
            sc = cls.score_macro_event(ev)
            prio = cls.get_macro_priority(ev)
            is_ov = ev.get("macro_event_override", False)

            # 엄격한 2성급 이상 필터링 (1성급 minor 지표는 전면 배제)
            if not is_ov and prio < 2:
                continue

            act_val = ev.get("actual")
            has_actual = 1 if (act_val is not None and str(act_val).strip() not in ["", "-", "None"]) else 0
            fc_or_pr = 1 if (ev.get("forecast") or ev.get("prior") or ev.get("previous")) else 0

            # 정렬 우선순위: 1순위 prio (5->4->3->2), 2순위 has_actual, 3순위 sc
            sort_tuple = (prio, has_actual, fc_or_pr, sc)
            scored_pool.append((sort_tuple, ev))

        if not scored_pool:
            return []

        scored_pool.sort(key=lambda x: x[0], reverse=True)
        # 핵심 이벤트만 선별 (최대 4개, 후보가 적으면 적은 수만 반환)
        curated_count = min(len(scored_pool), 4)
        curated = [x[1] for x in scored_pool[:curated_count]]
        curated.sort(key=lambda x: x.get("scheduled_at_kst", ""))
        return curated

    @classmethod
    def curate_today_night_events(cls, events: List[Dict[str, Any]], run_time_kst: Any = None, clusters: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """
        당일 밤 발표 예정 이벤트 (TODAY_NIGHT: 실행시각 ~ 익일 06:00 KST) 선별
        - 엄격한 prio >= 2 필터링 (1성급 지표 제외)
        - prio 내림차순 최우선 정렬 (낮은 중요도가 높은 중요도를 절대 밀어내지 못함)
        - 핵심 이벤트가 2개라면 2개만 출력 (항상 4개를 채우지 않음)
        """
        if not events and not clusters:
            return []

        run_kst = ensure_kst_aware(run_time_kst)
        today_start = run_kst.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_0600 = today_start.replace(hour=6, minute=0, second=0) + datetime.timedelta(days=1)
        today_str = run_kst.strftime("%Y-%m-%d")

        scored_night = []
        if clusters:
            for c in clusters:
                c_date = c.get("policy_date")
                sched_dt = c.get("scheduled_dt_kst")
                sched_dt_kst = ensure_kst_aware(sched_dt) if sched_dt else None
                if c_date == today_str and sched_dt_kst and run_kst < sched_dt_kst <= tomorrow_0600:
                    prio = c.get("macro_priority", 4)
                    scored_night.append(((1, prio, 100), c))

        for ev in events:
            sc = cls.score_macro_event(ev)
            prio = cls.get_macro_priority(ev)
            is_ov = ev.get("macro_event_override", False)

            # 엄격한 필터링: prio >= 2
            if not is_ov and prio < 2:
                continue

            # 1순위: prio (5->4->3->2), 2순위: sc
            scored_night.append(((1 if is_ov else 0, prio, sc), ev))

        if not scored_night:
            return []

        scored_night.sort(key=lambda x: x[0], reverse=True)
        # 핵심 이벤트만 선별 (최대 4개, 2개면 2개만 반환)
        curated_count = min(len(scored_night), 4)
        curated = [x[1] for x in scored_night[:curated_count]]
        curated.sort(key=lambda x: x.get("scheduled_at_kst", ""))
        return curated

    @classmethod
    def curate_next_trading_day_events(
        cls, 
        events: List[Dict[str, Any]], 
        clusters: List[Dict[str, Any]], 
        run_time_kst: Any = None
    ) -> List[Dict[str, Any]]:
        """
        NEXT_TRADING_DAY_CORE_EVENTS:
        실행 시각 이후 다음 거래일(영업일)에 예정된 초대형 Macro 핵심 이벤트
        - prio >= 2 필터링
        - prio 내림차순 정렬 (5성급 정책결정 클러스터 -> 4성급 PPI/고용)
        - 낮은 중요도가 높은 중요도를 절대 밀어내지 못함
        """
        run_kst = ensure_kst_aware(run_time_kst)
        today_start = run_kst.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_0600 = today_start.replace(hour=6, minute=0, second=0) + datetime.timedelta(days=1)
        next_date, next_start, next_end = cls.get_next_trading_day_range(run_kst)
        next_date_str = next_date.strftime("%Y-%m-%d")

        # 야간 윈도우(TODAY_NIGHT, ~06:00)와 중복 노출을 방지하기 위해 06:00 이후를 시작 시점으로 설정
        next_core_start = max(next_start, tomorrow_0600)

        candidates = []

        # 1. 다음 거래일 클러스터(중앙은행 정책 5성급, CPI Macro 클러스터 4성급) 포함
        for c in clusters:
            if c.get("policy_date") == next_date_str:
                prio = c.get("macro_priority", 5)
                candidates.append((prio, 100, c))

        # 2. 다음 거래일 일반 이벤트 중 prio >= 2 핵심 지표 선별 (야간 이벤트 중복 방지)
        for ev in events:
            if ev.get("is_clustered"):
                continue
            sched_dt = ev.get("scheduled_dt_kst")
            if not sched_dt and ev.get("scheduled_at_kst"):
                sched_dt = ensure_kst_aware(ev.get("scheduled_at_kst"))
            if not sched_dt:
                continue

            if next_core_start <= sched_dt <= next_end:
                sc = cls.score_macro_event(ev)
                prio = cls.get_macro_priority(ev)
                is_ov = ev.get("macro_event_override", False)

                if is_ov or prio >= 2:
                    candidates.append((prio, sc, ev))

        if not candidates:
            return []

        # 정렬: 1순위 prio (5->4->3->2), 2순위 sc
        candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
        # 최대 4개 선별 (Macro Event Cluster 기준 핵심 이벤트 1~4개만 선별)
        curated_count = min(len(candidates), 4)
        curated = [x[2] for x in candidates[:curated_count]]
        curated.sort(key=lambda x: x.get("scheduled_at_kst", ""))
        return curated

    @classmethod
    def normalize_dedup_key(cls, name: str) -> str:
        """중복 식별을 위한 지표명 정규화 (핵심 수식어 core, m/m, y/y 보존)"""
        n = (name or "").lower().strip()
        n = re.sub(r'[^a-zA-Z0-9\s/]', '', n)
        tokens = n.split()
        return " ".join(tokens)

    @classmethod
    def deduplicate_events(cls, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        동일 국가 + 동일 정규화 지표명 + 30분 이내 시각의 중복 이벤트 병합
        - 예: 21:14 ADP Weekly vs 21:15 ADP Weekly -> 공식 표준시각 21:15로 병합
        - CPI headline vs Core CPI, m/m vs y/y 등 독립 지표는 절대 병합하지 않음
        - 대표 이벤트에 병합하고 merged_source_ids에 원본 ID 보존
        """
        deduped = []
        for ev in events:
            # 개별 이벤트 ADP canonical scheduled time 사전 보정 (21:14/21:16 -> 21:15)
            name_lower = (ev.get("event_name") or "").lower()
            sched_dt = ev.get("scheduled_dt_kst") or ev.get("scheduled_at_kst")
            ev_dt = ensure_kst_aware(sched_dt) if sched_dt else None

            if ev_dt and "adp" in name_lower and ("employment" in name_lower or "payrolls" in name_lower):
                if ev_dt.hour == 21 and ev_dt.minute in [13, 14, 15, 16, 17]:
                    ev_dt = ev_dt.replace(minute=15, second=0, microsecond=0)
                    ev["scheduled_dt_kst"] = ev_dt
                    ev["scheduled_time_kst"] = "21:15"
                    ev["scheduled_at_kst"] = ev_dt.strftime("%Y-%m-%d %H:%M:%S KST")

            ev_key = cls.normalize_dedup_key(ev.get("event_name", ""))
            ev_country = (ev.get("country") or "").upper()

            matched_idx = None
            if ev_dt and ev_key:
                for idx, ex in enumerate(deduped):
                    ex_sched = ex.get("scheduled_dt_kst") or ex.get("scheduled_at_kst")
                    ex_dt = ensure_kst_aware(ex_sched) if ex_sched else None
                    ex_key = cls.normalize_dedup_key(ex.get("event_name", ""))
                    ex_country = (ex.get("country") or "").upper()

                    if ex_dt and ex_country == ev_country and ex_key == ev_key:
                        time_diff = abs((ev_dt - ex_dt).total_seconds())
                        if time_diff <= 1800:
                            # 같은 시각 + 같은 제목이라도 forecast / prior가 다르면 무조건 병합 금지
                            ex_fc = str(ex.get("forecast") or "").strip()
                            ev_fc = str(ev.get("forecast") or "").strip()
                            if ex_fc and ev_fc and ex_fc != ev_fc:
                                continue
                            ex_pr = str(ex.get("prior") or ex.get("previous") or "").strip()
                            ev_pr = str(ev.get("prior") or ev.get("previous") or "").strip()
                            if ex_pr and ev_pr and ex_pr != ev_pr:
                                continue
                            matched_idx = idx
                            break

            if matched_idx is not None:
                ex = deduped[matched_idx]
                ex_sched = ex.get("scheduled_dt_kst") or ex.get("scheduled_at_kst")
                ex_dt = ensure_kst_aware(ex_sched) if ex_sched else None

                # 표준 시각 선호 규칙: minute % 5 == 0 인 시각을 canonical time으로 우선 채택
                if ev_dt and ex_dt:
                    if (ex_dt.minute % 5 != 0) and (ev_dt.minute % 5 == 0):
                        ex["scheduled_dt_kst"] = ev_dt
                        ex["scheduled_at_kst"] = ev.get("scheduled_at_kst") or ev_dt.strftime("%Y-%m-%d %H:%M:%S KST")
                        ex["scheduled_time_kst"] = ev.get("scheduled_time_kst") or ev_dt.strftime("%H:%M")
                        if ev.get("scheduled_raw"):
                            ex["scheduled_raw"] = ev["scheduled_raw"]
                        if ev.get("scheduled_at_utc"):
                            ex["scheduled_at_utc"] = ev["scheduled_at_utc"]

                # ADP canonical 시간 확정: 21:15
                if "adp" in ev_key:
                    canon_dt = (ex.get("scheduled_dt_kst") or ex_dt)
                    if canon_dt and canon_dt.hour == 21 and canon_dt.minute in [13, 14, 15, 16, 17]:
                        canon_dt = canon_dt.replace(minute=15, second=0, microsecond=0)
                        ex["scheduled_dt_kst"] = canon_dt
                        ex["scheduled_time_kst"] = "21:15"
                        ex["scheduled_at_kst"] = canon_dt.strftime("%Y-%m-%d %H:%M:%S KST")

                if not ex.get("forecast") and ev.get("forecast"):
                    ex["forecast"] = ev["forecast"]
                if not ex.get("prior") and ev.get("prior"):
                    ex["prior"] = ev["prior"]
                    ex["previous"] = ev.get("previous") or ev.get("prior")
                if not ex.get("actual") and ev.get("actual"):
                    ex["actual"] = ev["actual"]
                    ex["freshness_status"] = ev.get("freshness_status")
                    ex["actual_source"] = ev.get("actual_source")
                    ex["source_provider"] = ev.get("source_provider") or ev.get("actual_source")
                    ex["source_url"] = ev.get("source_url") or ev.get("actual_source_url")
                    ex["match_confidence"] = ev.get("match_confidence")
                    ex["actual_trace"] = ev.get("actual_trace")
                merged_ids = ex.get("merged_source_ids", [])
                if not merged_ids:
                    orig_id = ex.get("event_id")
                    if orig_id:
                        merged_ids.append(orig_id)
                new_id = ev.get("event_id")
                if new_id and new_id not in merged_ids:
                    merged_ids.append(new_id)
                ex["merged_source_ids"] = merged_ids
            else:
                item_copy = dict(ev)
                orig_id = item_copy.get("event_id")
                if orig_id:
                    item_copy["merged_source_ids"] = [orig_id]
                deduped.append(item_copy)

        return deduped

    @classmethod
    def process_calendar_events(cls, raw_events: List[Dict[str, Any]], run_time_kst: datetime.datetime) -> Dict[str, Any]:
        """
        경제 캘린더 전체 파이프라인:
        RAW -> DEDUPLICATION -> NORMALIZATION -> TIME WINDOW -> MACRO OVERRIDE -> POLICY CLUSTERING -> FINAL CANDIDATES
        """
        if not raw_events:
            return {
                "total_events": 0,
                "counts_by_window": {"DAY_REVIEW": 0, "TODAY_NIGHT": 0, "NEXT_TRADING_DAY": 0, "UPCOMING_WEEK": 0, "OTHER": 0},
                "day_review_events": [],
                "today_night_events": [],
                "next_trading_day_events": [],
                "upcoming_week_events": [],
                "policy_clusters": [],
                "all_processed_events": []
            }

        run_kst = ensure_kst_aware(run_time_kst)
        today_start = run_kst.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start = today_start - datetime.timedelta(days=1)
        tomorrow_0600 = today_start.replace(hour=6, minute=0, second=0) + datetime.timedelta(days=1)
        next_week = run_kst + datetime.timedelta(days=7)
        next_date, next_start, next_end = cls.get_next_trading_day_range(run_kst)

        # -------------------------------------------------------------
        # 0. DEDUPLICATION
        # -------------------------------------------------------------
        deduped_raw_events = cls.deduplicate_events(raw_events)

        # -------------------------------------------------------------
        # 1. NORMALIZATION & PRE-PROCESSING
        # -------------------------------------------------------------
        all_processed = []
        override_count = 0

        for idx, ev in enumerate(deduped_raw_events):
            sched_dt = ev.get("scheduled_dt_kst") or ev.get("scheduled_at_kst")
            if not sched_dt:
                continue
            sched_dt = ensure_kst_aware(sched_dt)

            event_name = ev.get("event_name", "")
            country = ev.get("country", "GLOBAL")
            currency = ev.get("currency", "")
            importance = ev.get("importance", "LOW")
            name_lower = event_name.lower()

            pol_info = normalize_policy_event(event_name, country)
            is_override = is_macro_event_override(event_name, country, importance, pol_info)
            if is_override:
                override_count += 1
                importance = "HIGH"
                tier = "A"
            else:
                tier = "A" if importance == "HIGH" else ("B" if importance == "MEDIUM" else "C")

            impact_cat = "GENERAL"
            if pol_info or any(w in name_lower for w in ["rate", "policy", "monetary", "interest", "fomc", "rba", "rbnz", "boe", "ecb", "boj"]):
                impact_cat = "MONETARY_POLICY"
            elif any(w in name_lower for w in ["cpi", "ppi", "inflation", "price", "pce", "wpi"]):
                impact_cat = "INFLATION"
            elif any(w in name_lower for w in ["payroll", "employment", "job", "unemployment", "claims", "labor", "adp"]):
                impact_cat = "LABOR"
            elif any(w in name_lower for w in ["gdp", "growth", "output"]):
                impact_cat = "GROWTH"
            elif any(w in name_lower for w in ["pmi", "manufacturing", "services", "sentiment", "confidence"]):
                impact_cat = "SURVEY_PMI"
            elif any(w in name_lower for w in ["trade", "export", "import", "current account"]):
                impact_cat = "TRADE"
            elif any(w in name_lower for w in ["auction", "bond auction"]):
                impact_cat = "TREASURY"

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

            if impact_cat in ["INFLATION", "MONETARY_POLICY", "TREASURY"]:
                related_assets.extend(["Gold", "US10Y"])
            related_assets = list(dict.fromkeys(related_assets))

            # 타임 윈도우 판정
            time_window = "OTHER"
            if yesterday_start <= sched_dt <= run_kst:
                time_window = "DAY_REVIEW"
            elif run_kst < sched_dt <= tomorrow_0600:
                time_window = "TODAY_NIGHT"
            elif next_start <= sched_dt <= next_end:
                time_window = "NEXT_TRADING_DAY"
            elif tomorrow_0600 < sched_dt <= next_week:
                time_window = "UPCOMING_WEEK"

            date_str = sched_dt.strftime("%Y%m%d")
            event_id = ev.get("event_id") or f"EVT_{date_str}_{currency}_{idx+1:03d}"

            act_val = ev.get("actual")
            has_act = (act_val is not None and str(act_val).strip() not in ["", "-", "None"])
            time_status = "RELEASED" if sched_dt <= run_kst else "UPCOMING"
            actual_status = "FOUND" if has_act else "NOT_FOUND"
            if time_status == "RELEASED":
                freshness_status = "RELEASED_WITH_ACTUAL" if actual_status == "FOUND" else "RELEASED_ACTUAL_NOT_FOUND"
            else:
                freshness_status = "UPCOMING"

            item = {
                "event_id": event_id,
                "merged_source_ids": ev.get("merged_source_ids", [event_id]),
                "event_name": event_name,
                "country": country,
                "currency": currency,
                "scheduled_raw": ev.get("scheduled_raw", ""),
                "scheduled_at_utc": ev.get("scheduled_at_utc", ""),
                "scheduled_at_kst": ev.get("scheduled_at_kst") or sched_dt.strftime("%Y-%m-%d %H:%M:%S KST"),
                "scheduled_time_kst": ev.get("scheduled_time_kst", "") or sched_dt.strftime("%H:%M"),
                "scheduled_dt_kst": sched_dt,
                "importance": importance,
                "tier": tier,
                "macro_event_override": is_override,
                "macro_priority": cls.get_macro_priority(ev),
                "time_window": time_window,
                "time_status": time_status,
                "actual_status": actual_status,
                "freshness_status": freshness_status,
                "prior": ev.get("prior") or ev.get("previous"),
                "previous": ev.get("prior") or ev.get("previous"),
                "forecast": ev.get("forecast"),
                "actual": ev.get("actual"),
                "target_period": ev.get("target_period") or ev.get("reference_period"),
                "reference_period": ev.get("reference_period") or ev.get("target_period"),
                "is_revised_prior": ev.get("is_revised_prior", False),
                "actual_source": ev.get("actual_source"),
                "source_provider": ev.get("source_provider") or ev.get("actual_source"),
                "source_url": ev.get("source_url") or ev.get("actual_source_url"),
                "match_confidence": ev.get("match_confidence") or "HIGH",
                "actual_trace": ev.get("actual_trace"),
                "impact_category": impact_cat,
                "related_assets": related_assets,
                "source": ev.get("source", "ForexFactory")
            }
            all_processed.append(item)

        # -------------------------------------------------------------
        # 2. POLICY & MACRO CLUSTERING (Central Bank Policy + CPI)
        # -------------------------------------------------------------
        policy_clusters, policy_clustered_ids = cls.cluster_policy_events(all_processed)
        cpi_clusters, cpi_clustered_ids = cls.cluster_cpi_events(all_processed)

        all_clusters = policy_clusters + cpi_clusters
        all_clustered_ids = set(policy_clustered_ids + cpi_clustered_ids)

        for item in all_processed:
            item["is_clustered"] = item["event_id"] in all_clustered_ids

        # -------------------------------------------------------------
        # 3. POOL SEGREGATION
        # -------------------------------------------------------------
        day_review_pool = [it for it in all_processed if it["time_window"] == "DAY_REVIEW" and not it["is_clustered"]]
        today_night_pool = [it for it in all_processed if it["time_window"] == "TODAY_NIGHT" and not it["is_clustered"]]
        upcoming_week_list = [it for it in all_processed if it["time_window"] == "UPCOMING_WEEK" and not it["is_clustered"] and it["importance"] in ["HIGH", "MEDIUM"]]

        # -------------------------------------------------------------
        # 4. CURATION
        # -------------------------------------------------------------
        curated_day_review = cls.curate_day_review_events(day_review_pool, run_kst, all_clusters)
        curated_today_night = cls.curate_today_night_events(today_night_pool, run_kst, all_clusters)
        curated_next_trading_day = cls.curate_next_trading_day_events(all_processed, all_clusters, run_kst)

        # 디버그 로그 출력 (요구사항 [9])
        print(f"\n[Event Processor Pipeline Debug Count]")
        print(f" * 1. RAW EVENTS             : {len(raw_events)}")
        print(f" * 2. AFTER NORMALIZATION    : {len(all_processed)}")
        print(f" * 3. AFTER TIME WINDOW      : DAY_REVIEW={len(day_review_pool)}, TODAY_NIGHT={len(today_night_pool)}, NEXT_TRADING_DAY={len([it for it in all_processed if it['time_window'] == 'NEXT_TRADING_DAY'])}, UPCOMING_WEEK={len(upcoming_week_list)}")
        print(f" * 4. AFTER MACRO OVERRIDE   : {override_count} overrides applied")
        print(f" * 5. AFTER CLUSTERING       : {len(all_clusters)} clusters created (Policy: {len(policy_clusters)}, CPI: {len(cpi_clusters)}, clustered items: {len(all_clustered_ids)})")
        print(f" * 6. FINAL CANDIDATES       : DAY_REVIEW={len(curated_day_review)}, TODAY_NIGHT={len(curated_today_night)}, NEXT_TRADING_DAY={len(curated_next_trading_day)}")

        return {
            "total_events": len(all_processed),
            "counts_by_window": {
                "DAY_REVIEW": len(curated_day_review),
                "TODAY_NIGHT": len(curated_today_night),
                "NEXT_TRADING_DAY": len(curated_next_trading_day),
                "UPCOMING_WEEK": len(upcoming_week_list),
                "OTHER": len(all_processed) - (len(curated_day_review) + len(curated_today_night) + len(curated_next_trading_day) + len(upcoming_week_list))
            },
            "day_review_events": curated_day_review,
            "today_night_events": curated_today_night,
            "next_trading_day_events": curated_next_trading_day,
            "upcoming_week_events": upcoming_week_list,
            "policy_clusters": policy_clusters,
            "macro_clusters": cpi_clusters,
            "all_clusters": all_clusters,
            "all_processed_events": all_processed
        }
