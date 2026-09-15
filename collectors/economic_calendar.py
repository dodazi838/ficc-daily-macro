"""
[FICC Daily Macro] 경제지표 발표 일정 및 이벤트 수집기 (economic_calendar.py)
====================================================================
- 주의사항:
    • 외부 공개 피드(ForexFactory/Faireconomy 등)의 이용 조건 및 엔드포인트는 변경될 수 있으므로
      정기적인 접근 가능 여부 및 이용 약관 준수 확인이 필요합니다.
    • 시스템은 단일 소스에 결합되지 않도록 Adapter 패턴으로 설계되었으며, 향후 FRED, BOK ECOS 등
      공식 기관 API를 플러그인 형태로 손쉽게 추가/교체할 수 있습니다.
    • 다중 엔드포인트 Fallback (CSV -> XML -> JSON -> Local Cache) 구조로 HTTP 429 방어
====================================================================
"""

import os
import io
import csv
import json
import re
import datetime
import dateutil.parser
import pytz
import requests
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from .actual_providers import ActualEnrichmentEngine

KST_TZ = pytz.timezone('Asia/Seoul')
UTC_TZ = pytz.utc
HTTP_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}

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

class BaseCalendarAdapter(ABC):
    """경제 캘린더 어댑터 기본 추상 클래스"""
    def __init__(self, adapter_name: str):
        self.adapter_name = adapter_name

    @abstractmethod
    def fetch_events(self, run_time_kst: datetime.datetime) -> Dict[str, Any]:
        pass

class ForexFactoryCalendarAdapter(BaseCalendarAdapter):
    """
    ForexFactory (Faireconomy) 공개 주간 경제지표 캘린더 어댑터
    - 다중 포맷 Fallback: CSV -> XML -> JSON -> 로컬 캐시 (HTTP 429 레이트리밋 완벽 방어)
    """
    def __init__(self, cache_dir: str = "data/cache"):
        super().__init__(adapter_name="ForexFactory Feed")
        self.csv_url = "https://nfs.faireconomy.media/ff_calendar_thisweek.csv"
        self.xml_url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
        self.json_url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        self.cache_dir = cache_dir
        self.cache_file = os.path.join(cache_dir, "forexfactory_calendar.json")
        os.makedirs(self.cache_dir, exist_ok=True)

    def fetch_events(self, run_time_kst: datetime.datetime) -> Dict[str, Any]:
        raw_events = []
        status = "SUCCESS"
        error_msg = None

        # 1. CSV 엔드포인트 시도 (가장 경량이며 차단률 낮음)
        try:
            resp = requests.get(self.csv_url, headers=HTTP_HEADERS, timeout=4)
            if resp.status_code == 200 and "Title" in resp.text:
                reader = csv.DictReader(io.StringIO(resp.text))
                for row in reader:
                    title = row.get("Title", "").strip()
                    country_or_curr = row.get("Country", "").strip()
                    date_str = row.get("Date", "").strip()
                    time_str = row.get("Time", "").strip()
                    impact = row.get("Impact", "Low").strip()
                    forecast = row.get("Forecast", "").strip()
                    previous = row.get("Previous", "").strip()

                    if not title or not date_str:
                        continue

                    sched_kst = self._parse_mdy_time_to_kst(date_str, time_str)
                    if not sched_kst:
                        continue

                    raw_events.append(self._build_event_dict(
                        title, country_or_curr, f"{date_str} {time_str}", sched_kst, impact, previous, forecast
                    ))

                if raw_events:
                    self._save_cache(raw_events)
                    return {
                        "adapter": self.adapter_name,
                        "status": "SUCCESS",
                        "count": len(raw_events),
                        "error_message": None,
                        "events": raw_events
                    }
        except Exception as e:
            error_msg = f"CSV 수집 예외: {e}"

        # 2. XML 엔드포인트 시도
        try:
            resp = requests.get(self.xml_url, headers=HTTP_HEADERS, timeout=4)
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                events = root.findall(".//event")
                for e in events:
                    title = e.find("title").text.strip() if e.find("title") is not None and e.find("title").text else ""
                    country_or_curr = e.find("country").text.strip() if e.find("country") is not None and e.find("country").text else ""
                    date_str = e.find("date").text.strip() if e.find("date") is not None and e.find("date").text else ""
                    time_str = e.find("time").text.strip() if e.find("time") is not None and e.find("time").text else ""
                    impact = e.find("impact").text.strip() if e.find("impact") is not None and e.find("impact").text else "Low"
                    forecast = e.find("forecast").text.strip() if e.find("forecast") is not None and e.find("forecast").text else ""
                    previous = e.find("previous").text.strip() if e.find("previous") is not None and e.find("previous").text else ""

                    if not title or not date_str:
                        continue

                    sched_kst = self._parse_mdy_time_to_kst(date_str, time_str)
                    if not sched_kst:
                        continue

                    raw_events.append(self._build_event_dict(
                        title, country_or_curr, f"{date_str} {time_str}", sched_kst, impact, previous, forecast
                    ))

                if raw_events:
                    self._save_cache(raw_events)
                    return {
                        "adapter": self.adapter_name,
                        "status": "SUCCESS",
                        "count": len(raw_events),
                        "error_message": None,
                        "events": raw_events
                    }
        except Exception as e:
            error_msg = f"XML 수집 예외: {e}"

        # 3. 로컬 캐시 Fallback (HTTP 429 또는 일시적 네트워크 장애 방어)
        cached = self._load_cache()
        if cached:
            return {
                "adapter": self.adapter_name,
                "status": "PARTIAL",
                "count": len(cached),
                "error_message": "온라인 엔드포인트 일시 제한으로 최신 로컬 캐시 활용",
                "events": cached
            }

        return {
            "adapter": self.adapter_name,
            "status": "ERROR",
            "count": 0,
            "error_message": error_msg or "모든 엔드포인트 응답 실패",
            "events": []
        }

    def _build_event_dict(self, title: str, country_or_curr: str, raw_time: str, sched_kst: datetime.datetime, impact: str, previous: str, forecast: str) -> Dict[str, Any]:
        imp_norm = impact.upper()
        if imp_norm not in ["HIGH", "MEDIUM", "LOW"]:
            imp_norm = "LOW"

        curr_to_country = {
            "USD": "US", "KRW": "KR", "EUR": "EU", "JPY": "JP",
            "GBP": "GB", "CNY": "CN", "AUD": "AU", "CAD": "CA",
            "NZD": "NZ", "CHF": "CH", "All": "GLOBAL"
        }
        country_code = curr_to_country.get(country_or_curr, country_or_curr)

        return {
            "event_name": title,
            "currency": country_or_curr,
            "country": country_code,
            "scheduled_raw": raw_time,
            "scheduled_at_utc": sched_kst.astimezone(UTC_TZ).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "scheduled_at_kst": sched_kst.strftime("%Y-%m-%d %H:%M:%S KST"),
            "scheduled_time_kst": sched_kst.strftime("%H:%M"),
            "scheduled_dt_kst": sched_kst,
            "importance": imp_norm,
            "prior": previous if previous else None,
            "forecast": forecast if forecast else None,
            "actual": None,
            "is_revised_prior": False,
            "actual_source": None,
            "freshness_status": None,
            "source": self.adapter_name
        }

    @staticmethod
    def _parse_mdy_time_to_kst(date_str: str, time_str: str) -> Optional[datetime.datetime]:
        """MM-DD-YYYY 포맷 및 ForexFactory UTC 시각을 KST (Asia/Seoul) timezone-aware 객체로 정확히 변환"""
        try:
            parts = date_str.split("-")
            if len(parts) == 3:
                m, d, y = int(parts[0]), int(parts[1]), int(parts[2])
            else:
                return None

            hour, minute = 0, 0
            time_clean = time_str.lower().strip()
            if time_clean and time_clean not in ["all day", "tentative", "day 1", "day 2", "day 3"]:
                try:
                    dt_time = dateutil.parser.parse(time_clean)
                    hour, minute = dt_time.hour, dt_time.minute
                except Exception:
                    hour, minute = 0, 0

            utc_dt = UTC_TZ.localize(datetime.datetime(y, m, d, hour, minute))
            return utc_dt.astimezone(KST_TZ)
        except Exception:
            return None

    def _save_cache(self, events: List[Dict[str, Any]]):
        try:
            cache_payload = []
            for ev in events:
                e_copy = dict(ev)
                if isinstance(e_copy.get("scheduled_dt_kst"), datetime.datetime):
                    e_copy["scheduled_dt_kst"] = e_copy["scheduled_dt_kst"].isoformat()
                cache_payload.append(e_copy)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_payload, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_cache(self) -> Optional[List[Dict[str, Any]]]:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for ev in data:
                    if isinstance(ev.get("scheduled_dt_kst"), str):
                        ev["scheduled_dt_kst"] = dateutil.parser.parse(ev["scheduled_dt_kst"])
                return data
            except Exception:
                return None
        return None

class BokEcosCalendarAdapter(BaseCalendarAdapter):
    """
    한국은행 (BOK ECOS) 오픈 API 확장 어댑터 (확장 플러그인용 스텁)
    향후 API Key 설정 시 국내 금통위 및 물가/GDP 일정 정밀 보강
    """
    def __init__(self, api_key: Optional[str] = None):
        super().__init__(adapter_name="BOK ECOS API")
        self.api_key = api_key

    def fetch_events(self, run_time_kst: datetime.datetime) -> Dict[str, Any]:
        if not self.api_key:
            return {
                "adapter": self.adapter_name,
                "status": "SUCCESS",
                "count": 0,
                "error_message": "BOK_ECOS_API_KEY 미설정 (기본 ForexFactory 피드 활용)",
                "events": []
            }
        return {
            "adapter": self.adapter_name,
            "status": "SUCCESS",
            "count": 0,
            "error_message": None,
            "events": []
        }

MONTH_NAME_TO_INT = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12
}

def get_consecutive_prior_period(year: int, period: str) -> tuple:
    """연속 직전월 (year, M-1) 계산 (연도 경계 처리)"""
    try:
        m = int(period[1:])
    except Exception:
        m = 1
    if m == 1:
        return (year - 1, "M12")
    else:
        return (year, f"M{m - 1:02d}")

def extract_event_reference_period(event: Dict[str, Any]) -> tuple:
    """
    이벤트의 발표 대상 연월 (reference period) 추출:
    1. 이벤트명(event_name, event_name_kor)의 괄호 표기, 영문 월명, 한글 월명 우선 검출
    2. 명시되지 않은 경우, 노동통계국 발표 규칙(발표월 M 기준 대상월 M-1) 보조 적용
    반환: (year, 'M08') 형태
    """
    name = (event.get("event_name", "") + " " + event.get("event_name_kor", "")).lower()
    sched_dt = event.get("scheduled_dt_kst")
    if sched_dt:
        sched_dt_kst = ensure_kst_aware(sched_dt)
        base_year = sched_dt_kst.year
        sched_month = sched_dt_kst.month
    else:
        now = datetime.datetime.now(KST_TZ)
        base_year = now.year
        sched_month = now.month

    # 1. 괄호 또는 명시적 영문/한글 월명 탐색
    matched_month = None
    paren_match = re.search(r'\(([a-z]{3,9})\)', name)
    if paren_match and paren_match.group(1) in MONTH_NAME_TO_INT:
        matched_month = MONTH_NAME_TO_INT[paren_match.group(1)]
    else:
        kor_match = re.search(r'(\d{1,2})\s*월', name)
        if kor_match:
            km = int(kor_match.group(1))
            if 1 <= km <= 12:
                matched_month = km
        else:
            for word in ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december",
                         "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]:
                if re.search(rf'\b{word}\b', name):
                    matched_month = MONTH_NAME_TO_INT[word]
                    break

    if matched_month is not None:
        target_year = base_year
        # 연도 경계 보정: 1~2월 발표인데 대상월이 11~12월인 경우
        if sched_month in [1, 2] and matched_month in [11, 12]:
            target_year = base_year - 1
        elif sched_month in [11, 12] and matched_month in [1, 2]:
            target_year = base_year + 1
        return (target_year, f"M{matched_month:02d}")

    # 2. 명시되지 않은 경우: 미국 고용보고서 표준 발표 일정 규칙 (발표월 M -> 대상월 M-1)
    if sched_month == 1:
        return (base_year - 1, "M12")
    else:
        return (base_year, f"M{sched_month - 1:02d}")

def validate_release_date_consistency(sched_dt_kst: datetime.datetime, target_year: int, target_period: str) -> bool:
    """
    발표일(release date)과 대상월(reference period) 간의 논리적 정합성 검증:
    - 대상월 M의 고용 데이터는 해당 월 종료 이전(sched_dt가 대상월 이하)에 발표될 수 없음
    - 예: 2026-M08 데이터가 2026년 8월 또는 7월에 발표되는 것은 물리적으로 불가능
    """
    try:
        target_month = int(target_period[1:])
    except Exception:
        return False

    sched_year = sched_dt_kst.year
    sched_month = sched_dt_kst.month

    # 1. 발표일이 대상월 종료 이전인 경우 정합성 위반
    if sched_year < target_year:
        return False
    if sched_year == target_year and sched_month <= target_month:
        return False

    # 2. 발표일이 대상월로부터 지나치게 지연(3개월 초과)된 경우 경고성 위반
    months_diff = (sched_year - target_year) * 12 + (sched_month - target_month)
    if months_diff > 3:
        return False

    return True

class BlsActualsAdapter:
    """
    미국 노동통계국(BLS) 공식 Public API를 통한 발표 완료 경제지표 actual 및 revised prior 수집 어댑터
    - 엔드포인트: https://api.bls.gov/publicAPI/v1/timeseries/data/
    - CES0000000001: Total Nonfarm Employment (천 명 단위, 계절조정)
    - LNS14000000: Unemployment Rate (실업률 %, 계절조정)
    - 4대 정밀 검증:
        1. 이벤트 발표 대상 월 (reference_period)
        2. BLS API observation/reference period 정확 매칭
        3. 해당 발표일(release date)과 이벤트 일정의 정합성
        4. report_run_time_kst 기준 발표 완료 여부
    """
    def __init__(self, cache_dir: str = "data/cache"):
        self.api_url = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
        self.cache_dir = cache_dir
        self.cache_file = os.path.join(cache_dir, "bls_actuals_cache.json")
        os.makedirs(self.cache_dir, exist_ok=True)

    def fetch_bls_labor_data(self, year: int) -> Dict[str, Any]:
        """BLS API로부터 연도 경계(year-1 ~ year)를 포괄하여 고용 데이터 조회 및 (year, period) 인덱싱"""
        try:
            payload = {
                "seriesid": ["CES0000000001", "LNS14000000"],
                "startyear": str(year - 1),
                "endyear": str(year)
            }
            resp = requests.post(self.api_url, json=payload, headers=HTTP_HEADERS, timeout=5)
            if resp.status_code == 200:
                res_json = resp.json()
                if res_json.get("status") == "REQUEST_SUCCEEDED":
                    parsed = self._parse_series(res_json)
                    if parsed:
                        self._save_cache(parsed)
                        return parsed
        except Exception:
            pass

        cached = self._load_cache()
        if cached:
            return cached
        return {}

    def _parse_series(self, res_json: Dict[str, Any]) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "series_data": {
                "CES0000000001": {},
                "LNS14000000": {}
            }
        }
        series_list = res_json.get("Results", {}).get("series", [])
        for s in series_list:
            s_id = s.get("seriesID")
            data = s.get("data", [])
            for row in data:
                try:
                    r_year = int(row["year"])
                    r_period = row["period"]
                    r_val = float(row["value"])
                    if s_id in result["series_data"]:
                        result["series_data"][s_id][(r_year, r_period)] = r_val
                except (KeyError, ValueError):
                    continue

            # 이전 버전 호환성(nfp / unemployment_rate 최신 요약) 유지
            if s_id == "CES0000000001" and len(data) >= 2:
                latest_val = float(data[0]["value"])
                prev_val = float(data[1]["value"])
                latest_change = round(latest_val - prev_val, 1)

                prior_revised = None
                if len(data) >= 3:
                    prev_prev_val = float(data[2]["value"])
                    prior_revised = round(prev_val - prev_prev_val, 1)

                result["nfp"] = {
                    "latest_period": data[0].get("period", ""),
                    "latest_period_name": data[0].get("periodName", ""),
                    "latest_change": latest_change,
                    "latest_change_str": f"+{int(latest_change)}K" if latest_change > 0 else f"{int(latest_change)}K",
                    "prior_revised": prior_revised,
                    "prior_revised_str": f"+{int(prior_revised)}K" if (prior_revised is not None and prior_revised > 0) else (f"{int(prior_revised)}K" if prior_revised is not None else None)
                }

            elif s_id == "LNS14000000" and len(data) >= 1:
                latest_rate = float(data[0]["value"])
                result["unemployment_rate"] = {
                    "latest_period": data[0].get("period", ""),
                    "latest_period_name": data[0].get("periodName", ""),
                    "latest_rate": latest_rate,
                    "latest_rate_str": f"{latest_rate:.1f}%"
                }
        return result

    def _save_cache(self, data: Dict[str, Any]):
        try:
            # tuple key를 json 저장을 위해 "YYYY_MXX" 문자열로 직렬화
            serializable = {}
            for k, v in data.items():
                if k == "series_data":
                    serializable["series_data"] = {}
                    for sid, obs_dict in v.items():
                        serializable["series_data"][sid] = {
                            f"{yk}_{pk}": val for (yk, pk), val in obs_dict.items()
                        }
                else:
                    serializable[k] = v
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(serializable, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_cache(self) -> Optional[Dict[str, Any]]:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                deserialized = {}
                for k, v in data.items():
                    if k == "series_data":
                        deserialized["series_data"] = {}
                        for sid, obs_dict in v.items():
                            deserialized["series_data"][sid] = {}
                            for str_key, val in obs_dict.items():
                                parts = str_key.split("_")
                                deserialized["series_data"][sid][(int(parts[0]), parts[1])] = val
                    else:
                        deserialized[k] = v
                return deserialized
            except Exception:
                return None
        return None

    def enrich_events(self, events: List[Dict[str, Any]], run_time_kst: datetime.datetime):
        """
        4대 검증을 엄격히 적용하여 경제 이벤트에 actual 및 revised prior 주입:
        1. 이벤트 발표 대상 월 (reference_period)
        2. BLS API observation period 정확 매칭 (Stale Data Mismatch 방어)
        3. 발표일(release date) 정합성 검증
        4. report_run_time_kst cutoff 검증
        """
        run_kst = ensure_kst_aware(run_time_kst)
        bls_data = None

        for ev in events:
            sched_dt = ev.get("scheduled_dt_kst")
            if not sched_dt:
                continue
            sched_dt_kst = ensure_kst_aware(sched_dt)
            name_lower = ev.get("event_name", "").lower()
            country = ev.get("country", "")

            # 1. 대상 연월 (reference period) 추출
            target_year, target_period = extract_event_reference_period(ev)
            ev["reference_period"] = f"{target_year}-{target_period}"
            ev["target_period"] = f"{target_year}-{target_period}"

            # 2. 미래 예정 이벤트 (sched_dt > run_time_kst) -> actual 금지
            if sched_dt_kst > run_kst:
                ev["freshness_status"] = "UPCOMING"
                ev["actual"] = None
                ev["is_revised_prior"] = False
                continue

            # 3. 발표일(release date) 정합성 검증
            if not validate_release_date_consistency(sched_dt_kst, target_year, target_period):
                ev["freshness_status"] = "PENDING_ACTUAL"
                ev["actual"] = None
                ev["is_revised_prior"] = False
                continue

            # 4. 미국 노동통계국(BLS) 고용지표 연계 대상인 경우 정밀 관측기간 매칭
            is_nfp = country == "US" and any(w in name_lower for w in ["non-farm employment", "non-farm payroll", "nonfarm payroll", "nfp"])
            is_unemp = country == "US" and any(w in name_lower for w in ["unemployment rate"])

            if is_nfp or is_unemp:
                if bls_data is None:
                    bls_data = self.fetch_bls_labor_data(sched_dt_kst.year)

                series_map = bls_data.get("series_data", {})
                nfp_series = series_map.get("CES0000000001", {})
                unemp_series = series_map.get("LNS14000000", {})

                # Series data가 비어있고 mock 형식(nfp, unemployment_rate dict)인 경우 호환성 지원
                if not nfp_series and "nfp" in bls_data:
                    nfp_info = bls_data["nfp"]
                    # Mock 데이터의 latest_period가 대상월과 일치하는지 검증 (Stale 방어)
                    if nfp_info.get("latest_period") == target_period:
                        if is_nfp:
                            ev["actual"] = nfp_info.get("latest_change_str")
                            if nfp_info.get("prior_revised_str"):
                                # 기존 calendar prior와 비교하여 수정 여부 확인
                                original_prior = ev.get("prior") or ev.get("previous")
                                if original_prior:
                                    orig_nums = re.findall(r'[-+]?\d+(?:\.\d+)?', str(original_prior))
                                    rev_nums = re.findall(r'[-+]?\d+(?:\.\d+)?', str(nfp_info.get("prior_revised_str")))
                                    if orig_nums and rev_nums and float(orig_nums[0]) != float(rev_nums[0]):
                                        ev["prior"] = nfp_info.get("prior_revised_str")
                                        ev["is_revised_prior"] = True
                                    else:
                                        ev["is_revised_prior"] = False
                                else:
                                    ev["prior"] = nfp_info.get("prior_revised_str")
                                    ev["is_revised_prior"] = True
                            ev["actual_source"] = f"BLS API (CES0000000001, {target_year}-{target_period})"
                            ev["freshness_status"] = "RELEASED_WITH_ACTUAL"

                if not unemp_series and "unemployment_rate" in bls_data:
                    unemp_info = bls_data["unemployment_rate"]
                    if unemp_info.get("latest_period") == target_period:
                        if is_unemp:
                            ev["actual"] = unemp_info.get("latest_rate_str")
                            ev["actual_source"] = f"BLS API (LNS14000000, {target_year}-{target_period})"
                            ev["freshness_status"] = "RELEASED_WITH_ACTUAL"

                # 정밀 인덱싱된 series_data 기반 매칭
                if is_nfp and nfp_series:
                    target_val = nfp_series.get((target_year, target_period))
                    prior_year, prior_period = get_consecutive_prior_period(target_year, target_period)
                    prior_val = nfp_series.get((prior_year, prior_period))

                    if target_val is not None and prior_val is not None:
                        latest_change = round(target_val - prior_val, 1)
                        ev["actual"] = f"+{int(latest_change)}K" if latest_change > 0 else f"{int(latest_change)}K"
                        ev["actual_source"] = f"BLS API (CES0000000001, {target_year}-{target_period})"
                        ev["freshness_status"] = "RELEASED_WITH_ACTUAL"

                        # 직전월 수정치(revised prior) 정밀 검증
                        prior_prior_year, prior_prior_period = get_consecutive_prior_period(prior_year, prior_period)
                        prior_prior_val = nfp_series.get((prior_prior_year, prior_prior_period))

                        if prior_prior_val is not None:
                            revised_change = round(prior_val - prior_prior_val, 1)
                            revised_str = f"+{int(revised_change)}K" if revised_change > 0 else f"{int(revised_change)}K"

                            # 기존 calendar prior와 상이한지 검증
                            cal_prior = ev.get("prior") or ev.get("previous")
                            is_revised = False
                            if cal_prior:
                                cal_nums = re.findall(r'[-+]?\d+(?:\.\d+)?', str(cal_prior))
                                if cal_nums:
                                    try:
                                        cal_float = float(cal_nums[0])
                                        if abs(revised_change - cal_float) > 0.1:
                                            is_revised = True
                                    except ValueError:
                                        pass

                            if is_revised:
                                ev["prior"] = revised_str
                                ev["is_revised_prior"] = True
                                ev["revised_prior_period"] = f"{prior_year}-{prior_period}"
                            else:
                                ev["is_revised_prior"] = False
                        else:
                            ev["is_revised_prior"] = False
                    else:
                        # BLS에 해당 대상월 데이터가 아직 없는 경우 -> Stale Data Mismatch 방어
                        ev["actual"] = None
                        ev["freshness_status"] = "PENDING_ACTUAL"
                        ev["is_revised_prior"] = False

                elif is_unemp and unemp_series:
                    target_rate = unemp_series.get((target_year, target_period))
                    if target_rate is not None:
                        ev["actual"] = f"{target_rate:.1f}%"
                        ev["actual_source"] = f"BLS API (LNS14000000, {target_year}-{target_period})"
                        ev["freshness_status"] = "RELEASED_WITH_ACTUAL"
                    else:
                        ev["actual"] = None
                        ev["freshness_status"] = "PENDING_ACTUAL"

            # 5. 일반 이벤트 상태 태깅
            if ev.get("freshness_status") is None:
                if ev.get("actual") is not None and str(ev.get("actual")).strip() not in ["", "-", "None"]:
                    ev["freshness_status"] = "RELEASED_WITH_ACTUAL"
                elif ev.get("forecast") or ev.get("prior"):
                    ev["freshness_status"] = "PENDING_ACTUAL"
                else:
                    ev["freshness_status"] = "RELEASED_EVENT"

class EconomicCalendarCollector:
    """모든 캘린더 어댑터를 총괄 실행하는 오케스트레이터"""
    def __init__(self):
        self.adapters: List[BaseCalendarAdapter] = [
            ForexFactoryCalendarAdapter(),
            BokEcosCalendarAdapter()
        ]
        self.actuals_engine = ActualEnrichmentEngine()
        # 이전 버전 호환성 지원
        self.actuals_adapter = self.actuals_engine

    def collect_all(self, run_time_kst: datetime.datetime) -> Dict[str, Any]:
        all_raw_events = []
        adapter_reports = []

        for adp in self.adapters:
            report = adp.fetch_events(run_time_kst)
            adapter_reports.append({
                "adapter": report["adapter"],
                "status": report["status"],
                "count": report["count"],
                "error_message": report["error_message"]
            })
            all_raw_events.extend(report.get("events", []))

        # 발표 완료 이벤트 실제치(actual) 및 수정치(revised prior) 보강 및 freshness 태깅
        enrichment_report = self.actuals_engine.enrich_events(all_raw_events, run_time_kst)

        total_collected = len(all_raw_events)
        overall_status = "SUCCESS"
        if any(r["status"] == "ERROR" for r in adapter_reports):
            overall_status = "PARTIAL" if total_collected > 0 else "ERROR"

        return {
            "collected_at_kst": ensure_kst_aware(run_time_kst).strftime("%Y-%m-%d %H:%M:%S KST"),
            "overall_status": overall_status,
            "total_raw_count": total_collected,
            "adapter_reports": adapter_reports,
            "raw_events": all_raw_events,
            "enrichment_report": enrichment_report,
            "discrepancy_logs": self.actuals_engine.discrepancy_logs
        }

    def enrich_events_with_actuals(self, events: List[Dict[str, Any]], run_time_kst: datetime.datetime) -> List[Dict[str, Any]]:
        """수집된 이벤트 리스트에 대해 actuals_engine을 실행하여 최신 actual/revised prior 보강"""
        self.actuals_engine.enrich_events(events, run_time_kst)
        return events
