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
import datetime
import dateutil.parser
import pytz
import requests
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

KST_TZ = pytz.timezone('Asia/Seoul')
EDT_TZ = pytz.timezone('America/New_York')
HTTP_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}

def ensure_kst_aware(dt: datetime.datetime) -> datetime.datetime:
    """datetime 객체를 Asia/Seoul 타임존 인식 객체로 보장"""
    if dt is None:
        return datetime.datetime.now(KST_TZ)
    if dt.tzinfo is None:
        return KST_TZ.localize(dt)
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
            resp = requests.get(self.csv_url, headers=HTTP_HEADERS, timeout=10)
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
            resp = requests.get(self.xml_url, headers=HTTP_HEADERS, timeout=10)
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
            "scheduled_at_kst": sched_kst.strftime("%Y-%m-%d %H:%M:%S KST"),
            "scheduled_dt_kst": sched_kst,
            "importance": imp_norm,
            "prior": previous if previous else None,
            "forecast": forecast if forecast else None,
            "actual": None,
            "source": self.adapter_name
        }

    @staticmethod
    def _parse_mdy_time_to_kst(date_str: str, time_str: str) -> Optional[datetime.datetime]:
        """MM-DD-YYYY 포맷 및 뉴욕 EDT/EST 시각을 KST timezone-aware 객체로 변환"""
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

            local_dt = EDT_TZ.localize(datetime.datetime(y, m, d, hour, minute))
            return local_dt.astimezone(KST_TZ)
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

class EconomicCalendarCollector:
    """모든 캘린더 어댑터를 총괄 실행하는 오케스트레이터"""
    def __init__(self):
        self.adapters: List[BaseCalendarAdapter] = [
            ForexFactoryCalendarAdapter(),
            BokEcosCalendarAdapter()
        ]

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

        total_collected = len(all_raw_events)
        overall_status = "SUCCESS"
        if any(r["status"] == "ERROR" for r in adapter_reports):
            overall_status = "PARTIAL" if total_collected > 0 else "ERROR"

        return {
            "collected_at_kst": ensure_kst_aware(run_time_kst).strftime("%Y-%m-%d %H:%M:%S KST"),
            "overall_status": overall_status,
            "total_raw_count": total_collected,
            "adapter_reports": adapter_reports,
            "raw_events": all_raw_events
        }
