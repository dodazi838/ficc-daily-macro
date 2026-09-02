"""
[FICC Daily Macro] BaseCollector 및 공통 유틸리티
"""

import sys
import pytz
import pandas as pd
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime
from config.settings import TARGET_DAILY_TIME_STR, KST_TZ

class BaseCollector(ABC):
    """지표 수집기 공통 추상 기본 클래스"""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def collect(self, run_time_kst: datetime, is_post_1630: bool) -> List[Dict[str, Any]]:
        """
        데이터 수집을 수행하고 표준화된 딕셔너리 리스트를 반환합니다.
        
        표준 레코드 스키마:
        - category: 자산군 (EQUITY, FX, BOND, COMMODITY)
        - name: 지표명 (한국어)
        - symbol: 티커 또는 식별자
        - unit: 표시 단위 (pt, %, $, 원 등)
        - report_date: 리포트 일자 (YYYY-MM-DD)
        - target_time_kst: 16:30 KST
        - run_time_kst: 수집 실행 시각
        - market_as_of_date: 현지 시장 기준 거래일자
        - actual_as_of_kst: 원천 타임스탬프 기준 KST 환산 시각
        - raw_source_timestamp: 원천 데이터 타임스탬프 문자열
        - price_type: 가격 유형
        - session_type: 세션 상태
        - data_source: 데이터 소스 (Yahoo Finance, CNBC, KOFIA 등)
        - current: 현재가/금리
        - prev: 전일가/금리
        - change: 변동폭
        - pct_change: 등락률 (%)
        - bp_change: bp 변동폭 (채권 한정)
        - validation_status: DAILY_CONFIRMED / PRE_1630_TEST / DELAYED / ERROR
        - message: 비고/에러 메시지
        """
        pass

    @staticmethod
    def create_empty_record(meta: Dict[str, Any], run_time_kst: datetime, data_source: str) -> Dict[str, Any]:
        """기본 빈 레코드 생성"""
        report_date = run_time_kst.strftime("%Y-%m-%d")
        run_time_str = run_time_kst.strftime("%Y-%m-%d %H:%M:%S KST")
        
        return {
            "category": meta.get("category", "UNKNOWN"),
            "name": meta.get("name", ""),
            "symbol": meta.get("symbol", meta.get("code", "")),
            "unit": meta.get("unit", ""),
            "report_date": report_date,
            "target_time_kst": TARGET_DAILY_TIME_STR,
            "run_time_kst": run_time_str,
            "market_as_of_date": "N/A",
            "actual_as_of_kst": "N/A",
            "raw_source_timestamp": "PROVIDER_TIMESTAMP_UNAVAILABLE",
            "price_type": meta.get("price_type", ""),
            "session_type": "",
            "data_source": data_source,
            "current": None,
            "prev": None,
            "change": None,
            "pct_change": None,
            "bp_change": None,
            "validation_status": "ERROR",
            "message": ""
        }
