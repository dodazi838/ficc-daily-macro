"""
[FICC Daily Macro] 데이터 저장 관리자 (Storage Saver)
====================================================================
- data/raw/YYYY-MM-DD/
    • market.json     (시장 28개 지표 원천 스냅샷 + 메타데이터)
    • news.json       (원천 뉴스 피드 목록 & 수집 메타데이터)
    • events.json     (원천 경제 캘린더 피드 목록 & 발표시각)
    • history/        (동일 날짜 재실행 시 이전 원천 데이터 자동 아카이빙)
- data/processed/
    • YYYY-MM-DD.json (28개 지표 + 뉴스 클러스터 + 3-Way 캘린더 SSOT)
====================================================================
"""

import os
import json
import shutil
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

    def _archive_if_exists(self, file_path: str, date_dir: str, file_type: str):
        """동일 날짜에 이미 존재하는 파일이 있을 경우 history 폴더에 타임스탬프와 함께 백업 보존"""
        if os.path.exists(file_path):
            try:
                mtime = os.path.getmtime(file_path)
                mtime_str = datetime.fromtimestamp(mtime).strftime("%H%M%S")
                history_dir = os.path.join(date_dir, "history")
                os.makedirs(history_dir, exist_ok=True)
                backup_path = os.path.join(history_dir, f"{file_type}_{mtime_str}.json")
                shutil.copy2(file_path, backup_path)
            except Exception:
                pass

    def save_raw_market(self, raw_records: List[Dict[str, Any]], run_time_kst: datetime, is_post_1630: bool) -> str:
        """
        시장 28개 지표 원천 수집 데이터 JSON 저장
        저장 경로: data/raw/YYYY-MM-DD/market.json
        """
        date_str = run_time_kst.strftime("%Y-%m-%d")
        date_dir = os.path.join(self.raw_dir, date_str)
        os.makedirs(date_dir, exist_ok=True)
        file_path = os.path.join(date_dir, "market.json")

        # 기존 파일이 있다면 이력 백업
        self._archive_if_exists(file_path, date_dir, "market")

        payload = {
            "report_date": date_str,
            "data_type": "MARKET_INDICATORS",
            "source": "Yahoo Finance (4-tier Fallback Engine)",
            "execution_mode": "DAILY_CONFIRMED" if is_post_1630 else "PRE_1630_TEST",
            "run_time_kst": run_time_kst.strftime("%Y-%m-%d %H:%M:%S KST"),
            "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S KST"),
            "as_of": "16:30 KST (정규 마감)" if is_post_1630 else f"{run_time_kst.strftime('%H:%M')} KST (장중)",
            "basis": "국내/아시아 당일 종가, 해외 직전 현지 거래일 종가",
            "total_count": len(raw_records),
            "records": raw_records
        }

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=json_serial_fallback)

        return file_path

    def save_raw_news(self, news_collector_report: Dict[str, Any], run_time_kst: datetime, is_post_1630: bool) -> str:
        """
        원천 뉴스 피드 및 소스별 수집 상태 JSON 저장
        저장 경로: data/raw/YYYY-MM-DD/news.json
        """
        date_str = run_time_kst.strftime("%Y-%m-%d")
        date_dir = os.path.join(self.raw_dir, date_str)
        os.makedirs(date_dir, exist_ok=True)
        file_path = os.path.join(date_dir, "news.json")

        self._archive_if_exists(file_path, date_dir, "news")

        payload = {
            "report_date": date_str,
            "data_type": "RAW_MACRO_NEWS",
            "source": "Official RSS Feeds (Yonhap, Reuters, CNBC, WSJ, Bloomberg)",
            "execution_mode": "DAILY_CONFIRMED" if is_post_1630 else "PRE_1630_TEST",
            "run_time_kst": run_time_kst.strftime("%Y-%m-%d %H:%M:%S KST"),
            "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S KST"),
            "as_of": "16:30 KST",
            **news_collector_report
        }

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=json_serial_fallback)

        return file_path

    def save_raw_events(self, calendar_collector_report: Dict[str, Any], run_time_kst: datetime, is_post_1630: bool) -> str:
        """
        원천 경제지표 캘린더 피드 JSON 저장
        저장 경로: data/raw/YYYY-MM-DD/events.json
        """
        date_str = run_time_kst.strftime("%Y-%m-%d")
        date_dir = os.path.join(self.raw_dir, date_str)
        os.makedirs(date_dir, exist_ok=True)
        file_path = os.path.join(date_dir, "events.json")

        self._archive_if_exists(file_path, date_dir, "events")

        payload = {
            "report_date": date_str,
            "data_type": "RAW_ECONOMIC_EVENTS",
            "source": "ForexFactory Calendar Feed",
            "execution_mode": "DAILY_CONFIRMED" if is_post_1630 else "PRE_1630_TEST",
            "run_time_kst": run_time_kst.strftime("%Y-%m-%d %H:%M:%S KST"),
            "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S KST"),
            "as_of": "16:30 KST",
            **calendar_collector_report
        }

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=json_serial_fallback)

        return file_path

    def save_raw_calendar(self, calendar_collector_report: Dict[str, Any], run_time_kst: datetime, is_post_1630: bool) -> str:
        """save_raw_events의 하위 호환 별칭"""
        return self.save_raw_events(calendar_collector_report, run_time_kst, is_post_1630)

    def save_processed(self, 
                       market_data: Dict[str, Any], 
                       processed_news: Dict[str, Any],
                       processed_events: Dict[str, Any],
                       run_time_kst: datetime, 
                       is_post_1630: bool, 
                       raw_snapshots: Dict[str, str]) -> str:
        """
        가공 완료된 28개 지표 + 뉴스 클러스터 + 3-Way 경제 캘린더 통합 JSON 저장
        AI/블로그 생성 파이프라인의 Single Source of Truth (SSOT)로 활용
        저장 경로: data/processed/YYYY-MM-DD.json
        """
        date_str = run_time_kst.strftime("%Y-%m-%d")
        file_path = os.path.join(self.processed_dir, f"{date_str}.json")

        payload = {
            "report_date": date_str,
            "run_time_kst": run_time_kst.strftime("%Y-%m-%d %H:%M:%S KST"),
            "execution_mode": "DAILY_CONFIRMED" if is_post_1630 else "PRE_1630_TEST",
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S KST"),
            "source_raw_snapshots": {k: os.path.relpath(v, self.base_data_dir) if os.path.isabs(v) else v for k, v in raw_snapshots.items()},
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
