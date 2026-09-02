"""
[FICC Daily Macro] 데이터 저장 관리자 (Storage Saver)
====================================================================
- data/raw/
    • YYYY-MM-DD_HHMMSS_{MODE}_market.json   (시장 28개 지표 원천 스냅샷)
    • YYYY-MM-DD_HHMMSS_{MODE}_news.json     (원천 뉴스 리스트 & 소스별 상태)
    • YYYY-MM-DD_HHMMSS_{MODE}_calendar.json (원천 경제 캘린더 피드)
- data/processed/
    • YYYY-MM-DD.json (28개 지표 + 클러스터링된 뉴스 + 3-Way 경제 캘린더 통합본)
====================================================================
"""

import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

def json_serial_fallback(obj):
    """JSON 직렬화 불가능한 datetime 객체 문자열 변환 폴백"""
    if isinstance(obj, datetime):
        return obj.strftime("%Y-%m-%d %H:%M:%S")
    return str(obj)

class DataSaver:
    """일자별 수집 및 가공 데이터 영구 저장 관리자"""

    def __init__(self, base_data_dir: str = "data"):
        self.base_data_dir = base_data_dir
        self.raw_dir = os.path.join(base_data_dir, "raw")
        self.processed_dir = os.path.join(base_data_dir, "processed")
        self._ensure_directories()

    def _ensure_directories(self):
        """저장 디렉토리 존재 보장"""
        os.makedirs(self.raw_dir, exist_ok=True)
        os.makedirs(self.processed_dir, exist_ok=True)

    def _get_filename_prefix(self, run_time_kst: datetime, is_post_1630: bool) -> str:
        time_suffix = run_time_kst.strftime("%Y-%m-%d_%H%M%S")
        mode_suffix = "CONFIRMED" if is_post_1630 else "TEST"
        return f"{time_suffix}_{mode_suffix}"

    def save_raw_market(self, raw_records: List[Dict[str, Any]], run_time_kst: datetime, is_post_1630: bool) -> str:
        """시장 28개 지표 원천 수집 데이터 JSON 저장"""
        prefix = self._get_filename_prefix(run_time_kst, is_post_1630)
        file_name = f"{prefix}_market.json"
        file_path = os.path.join(self.raw_dir, file_name)

        payload = {
            "report_date": run_time_kst.strftime("%Y-%m-%d"),
            "run_time_kst": run_time_kst.strftime("%Y-%m-%d %H:%M:%S KST"),
            "execution_mode": "DAILY_CONFIRMED" if is_post_1630 else "PRE_1630_TEST",
            "data_type": "MARKET_INDICATORS",
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_count": len(raw_records),
            "records": raw_records
        }

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=json_serial_fallback)

        return file_path

    def save_raw_news(self, news_collector_report: Dict[str, Any], run_time_kst: datetime, is_post_1630: bool) -> str:
        """원천 뉴스 피드 및 소스별 수집 상태 JSON 저장"""
        prefix = self._get_filename_prefix(run_time_kst, is_post_1630)
        file_name = f"{prefix}_news.json"
        file_path = os.path.join(self.raw_dir, file_name)

        payload = {
            "report_date": run_time_kst.strftime("%Y-%m-%d"),
            "run_time_kst": run_time_kst.strftime("%Y-%m-%d %H:%M:%S KST"),
            "execution_mode": "DAILY_CONFIRMED" if is_post_1630 else "PRE_1630_TEST",
            "data_type": "RAW_MACRO_NEWS",
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            **news_collector_report
        }

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=json_serial_fallback)

        return file_path

    def save_raw_calendar(self, calendar_collector_report: Dict[str, Any], run_time_kst: datetime, is_post_1630: bool) -> str:
        """원천 경제지표 캘린더 피드 JSON 저장"""
        prefix = self._get_filename_prefix(run_time_kst, is_post_1630)
        file_name = f"{prefix}_calendar.json"
        file_path = os.path.join(self.raw_dir, file_name)

        payload = {
            "report_date": run_time_kst.strftime("%Y-%m-%d"),
            "run_time_kst": run_time_kst.strftime("%Y-%m-%d %H:%M:%S KST"),
            "execution_mode": "DAILY_CONFIRMED" if is_post_1630 else "PRE_1630_TEST",
            "data_type": "RAW_ECONOMIC_CALENDAR",
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            **calendar_collector_report
        }

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=json_serial_fallback)

        return file_path

    def save_processed(self, 
                       market_data: Dict[str, Any], 
                       processed_news: Dict[str, Any],
                       processed_events: Dict[str, Any],
                       run_time_kst: datetime, 
                       is_post_1630: bool, 
                       raw_snapshots: Dict[str, str]) -> str:
        """
        가공 완료된 28개 지표 + 뉴스 클러스터 + 3-Way 경제 캘린더 통합 JSON 저장
        AI/블로그 생성 파이프라인에서 최종 입력으로 사용
        """
        date_str = run_time_kst.strftime("%Y-%m-%d")
        file_path = os.path.join(self.processed_dir, f"{date_str}.json")

        payload = {
            "report_date": date_str,
            "run_time_kst": run_time_kst.strftime("%Y-%m-%d %H:%M:%S KST"),
            "execution_mode": "DAILY_CONFIRMED" if is_post_1630 else "PRE_1630_TEST",
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source_raw_snapshots": {k: os.path.basename(v) for k, v in raw_snapshots.items()},
            "market_data": {
                "summary_stats": market_data.get("summary_stats", {}),
                "spreads": market_data.get("spreads", []),
                "categories": market_data.get("categories", {})
            },
            "news_events": {
                "total_unique_articles": processed_news.get("total_unique", 0),
                "total_event_clusters": processed_news.get("total_clusters", 0),
                "event_clusters": processed_news.get("event_clusters", [])
            },
            "economic_events": {
                "total_events": processed_events.get("total_events", 0),
                "counts_by_window": processed_events.get("counts_by_window", {}),
                "day_review_events": processed_events.get("day_review_events", []),
                "today_night_events": processed_events.get("today_night_events", []),
                "upcoming_week_events": processed_events.get("upcoming_week_events", [])
            }
        }

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=json_serial_fallback)

        return file_path
