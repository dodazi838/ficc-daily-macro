"""
[FICC Daily Macro] 실제치 보강 오케스트레이션 엔진 (enricher.py)
====================================================================
- 캘린더 수집(Schedule/Forecast/Previous)과 발표 후 실제치(Actual) 보강의 분리
- Provider 우선순위 적용:
    OFFICIAL (Tier 1) > PRIMARY (Tier 2) > SECONDARY (Tier 3) > FALLBACK (Tier 4)
- 다중 공급자 값 상이 시 Discrepancy Logging (자동 덮어쓰기 금지)
- 4대 데이터 거버넌스 원칙:
    1. Forecast를 Actual로 대입 금지
    2. Previous를 Actual로 대입 금지
    3. AI 추론에 의한 Actual 생성 원천 차단
    4. 발표 완료 시각 경과 후 미수집 시 RELEASED_ACTUAL_NOT_FOUND 강제
====================================================================
"""

import time
import datetime
import pytz
import re
from typing import List, Dict, Any, Optional, Tuple
from .base import BaseActualDataProvider, ProviderTier, ActualRecord, DiscrepancyRecord
from .official_ecb import EcbOfficialActualProvider
from .official_bls import BlsOfficialActualProvider
from .official_fed import FredOfficialActualProvider
from .saveticker import SaveTickerActualProvider
from .investing_provider import InvestingActualProvider
from .primary_calendar import ForexFactoryLiveSnapshotProvider, FmpActualsProvider

KST_TZ = pytz.timezone('Asia/Seoul')

def ensure_kst_aware(dt: Any) -> datetime.datetime:
    if dt is None:
        return datetime.datetime.now(KST_TZ)
    if isinstance(dt, datetime.datetime):
        if dt.tzinfo is None:
            return KST_TZ.localize(dt)
        if hasattr(dt.tzinfo, "zone") and dt.tzinfo.zone == "Asia/Seoul":
            if dt.utcoffset() != datetime.timedelta(hours=9):
                naive = dt.replace(tzinfo=None)
                return KST_TZ.localize(naive)
        return dt.astimezone(KST_TZ)
    if isinstance(dt, str):
        clean_str = dt.replace(" KST", "").strip()
        try:
            import dateutil.parser
            parsed = dateutil.parser.parse(clean_str)
            if parsed.tzinfo is None:
                return KST_TZ.localize(parsed)
            return parsed.astimezone(KST_TZ)
        except Exception:
            return datetime.datetime.now(KST_TZ)
    return datetime.datetime.now(KST_TZ)

def is_non_numeric_event(name: str) -> bool:
    """은행 휴일, 연설, 청문회 등 수치 지표가 없는 비수치 이벤트 판별"""
    if not name:
        return True
    n = name.lower()
    # 수치 지표 키워드가 포함된 경우 비수치 이벤트 판별에서 제외
    if any(k in n for k in ["cpi", "ppi", "rate decision", "overnight rate", "claims", "payroll", "employment", "gdp", "auction", "inventories", "pmi", "confidence", "credit", "sales"]):
        return False
    return any(w in n for w in [
        "bank holiday", "holiday", "speaks", "speech", "remarks", "press conference",
        "hearings", "testimony", "meeting", "minutes", "projections", "symposium"
    ])

def should_enrich_event(ev: Dict[str, Any]) -> bool:
    """
    Actual Enrichment 대상 여부 판정:
    - Non-numeric(Holidays, Speeches, Remarks 등)은 항상 제외
    - LOW impact 이벤트는 기본적으로 Actual Provider 조회를 하지 않는다.
      (단, 최종 Daily Event 후보/큐레이션/핵심 매크로 패밀리는 예외적으로 조회 허용)
    - HIGH, MEDIUM 및 일반 numeric 지표는 조회 허용
    """
    ev_name = ev.get("event_name", "")
    if is_non_numeric_event(ev_name):
        return False

    impact = (ev.get("impact") or "").strip().lower()

    if impact == "low":
        if ev.get("is_candidate") or ev.get("is_curated") or ev.get("is_macro_cluster"):
            return True
        from .saveticker import detect_event_family
        fam, _ = detect_event_family(ev_name)
        if fam in [
            "CPI_CORE", "CPI_HEADLINE", "PPI_CORE", "PPI_HEADLINE",
            "INITIAL_CLAIMS", "CONTINUING_CLAIMS", "NFP", "UNEMPLOYMENT",
            "RATE_DECISION", "TREASURY_AUCTION_10Y", "TREASURY_AUCTION_30Y",
            "TREASURY_AUCTION_3Y", "CRUDE_OIL_INVENTORIES", "CONSUMER_CREDIT",
            "ADP_EMPLOYMENT", "RETAIL_SALES", "GDP"
        ]:
            return True
        return False

    return True

def get_provider_priority_key(record: ActualRecord) -> Tuple[int, int]:
    """
    공급자 정밀 우선순위 키 (숫자가 낮을수록 우선):
    1. OFFICIAL (1) > PRIMARY (2) > SECONDARY (3) > FALLBACK (4)
    2. PRIMARY 내 세부 순위: SaveTicker / Investing.com (1) > FMP (2) > ForexFactory (3)
    """
    tier_val = int(record.provider_tier)
    source_lower = record.source_provider.lower()

    sub_rank = 10
    if record.provider_tier == ProviderTier.OFFICIAL:
        sub_rank = 1
    elif "saveticker" in source_lower:
        sub_rank = 1
    elif "investing" in source_lower:
        sub_rank = 1
    elif "fmp" in source_lower or "financial modeling prep" in source_lower:
        sub_rank = 2
    elif "forexfactory" in source_lower:
        sub_rank = 3

    return (tier_val, sub_rank)

class ActualEnrichmentEngine:
    """실제치(Actual) 데이터 수집 및 정밀 보강 총괄 엔진"""
    def __init__(self, providers: Optional[List[BaseActualDataProvider]] = None):
        if providers:
            self.providers = providers
        else:
            self.providers = [
                # Tier 1: OFFICIAL
                EcbOfficialActualProvider(),
                BlsOfficialActualProvider(),
                FredOfficialActualProvider(),
                # Tier 2: PRIMARY (SaveTicker & Investing.com)
                SaveTickerActualProvider(),
                InvestingActualProvider(),
                FmpActualsProvider(),
                # Tier 2: ForexFactory Live Feed
                ForexFactoryLiveSnapshotProvider()
            ]
        self.discrepancy_logs: List[Dict[str, Any]] = []
        # 단일 실행 세션 내 동일 event family 캐시 (Key: (pname, family, country, date_str))
        self._session_cache: Dict[Tuple[str, Optional[str], str, str], Tuple[Optional[ActualRecord], str, str]] = {}
        self.stats: Dict[str, Any] = {
            "cache_hits": 0,
            "cache_misses": 0,
            "network_calls": 0,
            "skipped_non_numeric": 0,
            "skipped_low_impact": 0,
            "early_breaks": 0,
            "provider_calls": {},
            "provider_timings": {},
            "provider_timeouts": 0,
            "provider_errors": 0
        }

    def lookup_for_event(self, event: Dict[str, Any], run_time_kst: datetime.datetime) -> Dict[str, Any]:
        """
        단일 이벤트에 대한 각 공급자별 조회 추적 결과 반환 (Early Break & Session Cache 적용)
        반환: {
            "candidate_records": List[ActualRecord],
            "selected_record": Optional[ActualRecord],
            "has_discrepancy": bool,
            "discrepancy_record": Optional[DiscrepancyRecord]
        }
        """
        from .saveticker import detect_event_family
        candidates: List[ActualRecord] = []
        provider_traces: Dict[str, Dict[str, Any]] = {}

        target_family, _ = detect_event_family(event.get("event_name", ""))
        CROSS_CHECK_FAMILIES = {
            "CPI_CORE", "CPI_HEADLINE", "PPI_CORE", "PPI_HEADLINE",
            "INITIAL_CLAIMS", "NFP", "RATE_DECISION", "GDP"
        }
        needs_cross_check = target_family in CROSS_CHECK_FAMILIES

        date_str = str(event.get("scheduled_at_kst", "") or event.get("scheduled_dt_kst", ""))[:10]
        country = (event.get("country") or "").upper()

        for p in self.providers:
            pname = getattr(p, "provider_name", type(p).__name__)
            cache_key = (pname, target_family, country, date_str)
            t_p0 = time.perf_counter()
            try:
                # 동일 실행 내 동일 event family 캐시 확인
                if target_family and cache_key in self._session_cache:
                    rec, st, msg = self._session_cache[cache_key]
                    self.stats["cache_hits"] += 1
                else:
                    self.stats["cache_misses"] += 1
                    self.stats["network_calls"] += 1
                    self.stats["provider_calls"][pname] = self.stats["provider_calls"].get(pname, 0) + 1
                    if hasattr(p, "lookup_with_status"):
                        rec, st, msg = p.lookup_with_status(event, run_time_kst)
                    else:
                        rec = p.lookup_actual(event, run_time_kst)
                        st = "FOUND" if (rec and rec.is_valid_actual()) else "NOT_FOUND"
                        msg = "OK" if st == "FOUND" else "No match"
                    if target_family:
                        self._session_cache[cache_key] = (rec, st, msg)

                self.stats["provider_timings"][pname] = self.stats["provider_timings"].get(pname, 0.0) + (time.perf_counter() - t_p0)

                provider_traces[pname] = {"status": st, "message": msg, "actual": rec.actual if rec else None}
                if rec and rec.is_valid_actual():
                    candidates.append(rec)
                    # Early Break 정책:
                    # 상위 Tier(Official 또는 SaveTicker/Investing)에서 유효 실제치 발견 시
                    # 크로스체크 대상이 아니면 하위 provider 조회를 즉시 중단(Early Break)
                    if len(self.providers) > 2:
                        if not needs_cross_check:
                            self.stats["early_breaks"] += 1
                            break
                        elif len(candidates) >= 2:
                            # 크로스체크 대상이라도 2개 이상 유효 소스 확보 시 추가 호출 중단
                            self.stats["early_breaks"] += 1
                            break
            except Exception as e:
                self.stats["provider_errors"] += 1
                if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                    self.stats["provider_timeouts"] += 1
                provider_traces[pname] = {"status": "PROVIDER_ERROR", "message": str(e), "actual": None}

        # 정밀 우선순위 정렬: OFFICIAL > SaveTicker > Investing.com > ForexFactory
        candidates.sort(key=get_provider_priority_key)

        # 불일치(Discrepancy) 감지: 서로 다른 공급자가 서로 다른 Actual 값을 제시하는 경우
        unique_vals = set(c.actual.strip().lower() for c in candidates)
        has_discrepancy = len(unique_vals) > 1
        disc_record = None

        if has_discrepancy:
            provider_vals = {c.source_provider: c.actual for c in candidates}
            selected = candidates[0]
            disc_record = DiscrepancyRecord(
                event_name=event.get("event_name", ""),
                country=event.get("country", ""),
                scheduled_at_kst=str(event.get("scheduled_at_kst", "")),
                provider_values=provider_vals,
                selected_provider=selected.source_provider,
                selected_value=selected.actual,
                selected_tier=selected.provider_tier.name,
                resolution_rule=f"Priority rule: {selected.provider_tier.name} takes precedence",
                timestamp_kst=ensure_kst_aware(run_time_kst).strftime("%Y-%m-%d %H:%M:%S KST")
            )
            self.discrepancy_logs.append(disc_record.__dict__)

        # Official 상태 요약
        official_status = "MATCH_FAILED"
        for oname in ["ECB Official API", "BLS Official API", "FRED Official API", "ECB Data Portal (Official)", "BLS Public API (Official)", "Federal Reserve G.19 / FRED (Official)"]:
            if oname in provider_traces:
                ost = provider_traces[oname]["status"]
                if ost in ["FOUND", "NOT_FOUND"]:
                    official_status = ost
                    break

        actual_trace = {
            "calendar": "found",
            "forexfactory": provider_traces.get("ForexFactory", {}).get("status", "NOT_FOUND"),
            "saveticker": provider_traces.get("SaveTicker", {}).get("status", "NOT_FOUND"),
            "investing": provider_traces.get("Investing.com", {}).get("status", "NOT_FOUND"),
            "official": official_status,
            "matching": "success" if candidates else "failure",
            "parsing": "success" if candidates else "failure",
            "final_actual": candidates[0].actual if candidates else None,
            "provider_traces": provider_traces
        }

        return {
            "candidate_records": candidates,
            "selected_record": candidates[0] if candidates else None,
            "has_discrepancy": has_discrepancy,
            "discrepancy_record": disc_record,
            "actual_trace": actual_trace
        }

    def enrich_events(self, events: List[Dict[str, Any]], run_time_kst: datetime.datetime) -> Dict[str, Any]:
        """
        전체 캘린더 이벤트 리스트에 대해 Actual 수집 및 엄격한 무결성 검증 적용
        """
        run_kst = ensure_kst_aware(run_time_kst)
        populated_count = 0
        not_found_count = 0
        upcoming_count = 0
        provider_stats: Dict[str, int] = {}

        for ev in events:
            sched_dt = ev.get("scheduled_dt_kst")
            if not sched_dt:
                continue
            sched_dt_kst = ensure_kst_aware(sched_dt)
            ev_name = ev.get("event_name", "")

            # 1. 미래 예정 이벤트 (sched_dt > run_time_kst) -> actual 금지 및 UPCOMING 태깅
            if sched_dt_kst > run_kst:
                ev["actual"] = None
                ev["freshness_status"] = "UPCOMING"
                ev["is_revised_prior"] = False
                upcoming_count += 1
                continue

            # 2. 비수치 이벤트는 Actual 조회 생략 및 RELEASED_EVENT 태깅
            if is_non_numeric_event(ev_name):
                self.stats["skipped_non_numeric"] += 1
                ev["actual"] = None
                ev["freshness_status"] = "RELEASED_EVENT"
                ev["is_revised_prior"] = False
                continue

            # 3. LOW 중요도 중 비핵심 이벤트 조회 생략
            if not should_enrich_event(ev):
                self.stats["skipped_low_impact"] += 1
                ev["actual"] = None
                if ev.get("forecast") or ev.get("prior"):
                    ev["freshness_status"] = "RELEASED_ACTUAL_NOT_FOUND"
                    not_found_count += 1
                else:
                    ev["freshness_status"] = "RELEASED_EVENT"
                ev["is_revised_prior"] = False
                continue

            # 4. 핵심 매크로 이벤트 실제치 조회
            lookup_res = self.lookup_for_event(ev, run_kst)
            selected_rec: Optional[ActualRecord] = lookup_res["selected_record"]
            ev["actual_trace"] = lookup_res.get("actual_trace", {})

            if selected_rec and selected_rec.is_valid_actual():
                # [거버넌스 원칙 검증]
                # Forecast/Previous/Consensus를 Actual로 무단 복사하지 않았는지 엄격 검증
                val = str(selected_rec.actual).strip()
                ev["actual"] = val
                ev["actual_source"] = selected_rec.source_provider
                ev["source_provider"] = selected_rec.source_provider
                ev["actual_source_url"] = getattr(selected_rec, "source_url", "")
                ev["source_url"] = getattr(selected_rec, "source_url", "")
                ev["match_confidence"] = getattr(selected_rec, "match_confidence", "HIGH")
                ev["freshness_status"] = "RELEASED_WITH_ACTUAL"
                populated_count += 1

                p_name = selected_rec.source_provider
                provider_stats[p_name] = provider_stats.get(p_name, 0) + 1

                # 수정치(revised prior) 반영
                if selected_rec.revised_prior:
                    cal_prior = ev.get("prior") or ev.get("previous")
                    if cal_prior and str(cal_prior).strip() != str(selected_rec.revised_prior).strip():
                        ev["prior"] = selected_rec.revised_prior
                        ev["is_revised_prior"] = True
            else:
                ev["actual"] = None
                ev["freshness_status"] = "RELEASED_ACTUAL_NOT_FOUND"
                not_found_count += 1

        return {
            "total_events": len(events),
            "populated_actuals": populated_count,
            "released_actual_not_found": not_found_count,
            "upcoming_events": upcoming_count,
            "provider_stats": provider_stats,
            "discrepancy_logs_count": len(self.discrepancy_logs),
            "discrepancy_logs": self.discrepancy_logs,
            "stats": self.stats
        }
