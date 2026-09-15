"""
[FICC Daily Macro] 실제치(Actual) 데이터 공급자 기본 추상 계층 (base.py)
====================================================================
- 캘린더 일정 수집과 사후 실제값 수집의 분리를 위한 기본 인터페이스
- Provider 우선순위 정의: OFFICIAL (Tier 1) > PRIMARY (Tier 2) > SECONDARY (Tier 3) > FALLBACK (Tier 4)
- 엄격한 데이터 품질 원칙:
    1. Forecast를 Actual로 대입 금지
    2. Previous를 Actual로 대입 금지
    3. AI 추론에 의한 수치 생성 금지
    4. 미수집 시 RELEASED_ACTUAL_NOT_FOUND 부여
====================================================================
"""

import datetime
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, Any, Optional, List

class ProviderTier(IntEnum):
    """
    공급자 신뢰도 및 우선순위 (숫자가 낮을수록 최우선)
    OFFICIAL (1) > PRIMARY (2) > SECONDARY (3) > FALLBACK (4)
    """
    OFFICIAL = 1       # 중앙은행, 노동통계국, 통계청 등 공식 정부/기관 API
    PRIMARY = 2        # API 기반 전문 경제캘린더 공급자 (FMP, 내장 검증 피드 등)
    SECONDARY = 3      # 보조 캘린더 피드 및 로컬 스냅샷 저장소
    FALLBACK = 4       # 최후의 웹 스크래핑/캐시 대체

@dataclass
class ActualRecord:
    """단일 실제치(Actual) 수집 레코드"""
    event_name: str
    country: str
    actual: str
    forecast: Optional[str] = None
    prior: Optional[str] = None
    revised_prior: Optional[str] = None
    unit: Optional[str] = None
    reference_period: Optional[str] = None
    release_time_kst: Optional[datetime.datetime] = None
    source_provider: str = ""
    source_url: str = ""
    match_confidence: str = "HIGH"
    provider_tier: ProviderTier = ProviderTier.PRIMARY
    raw_data: Optional[Dict[str, Any]] = field(default_factory=dict)

    def is_valid_actual(self) -> bool:
        """유효한 Actual 수치인지 검증 (빈 문자열, '-', 'None' 배제)"""
        if self.actual is None:
            return False
        clean = str(self.actual).strip()
        return clean not in ["", "-", "None", "null", "N/A"]

@dataclass
class DiscrepancyRecord:
    """복수 공급자 간 수치 불일치 기록 모델"""
    event_name: str
    country: str
    scheduled_at_kst: str
    provider_values: Dict[str, str]       # {provider_name: value}
    selected_provider: str
    selected_value: str
    selected_tier: str
    resolution_rule: str
    timestamp_kst: str

class ProviderLookupStatus:
    """공급자 조회 상태 추적 분류"""
    FOUND = "FOUND"                    # HTTP 200, 페이지 존재, 이벤트 매칭 성공, 실제값 파싱 성공
    NOT_FOUND = "NOT_FOUND"            # 페이지 존재, 이벤트 매칭 성공, 실제값 필드 부재/발표대기
    MATCH_FAILED = "MATCH_FAILED"      # 이벤트 자체를 찾지 못함
    PROVIDER_ERROR = "PROVIDER_ERROR"  # 페이지 접근 실패 / 네트워크 오류 / 파싱 에러
    NOT_APPLICABLE = "NOT_APPLICABLE"  # 미래 이벤트 등 조회 불필요

class BaseActualDataProvider(ABC):
    """실제치 데이터 공급자 추상 기본 클래스"""
    def __init__(self, provider_name: str, tier: ProviderTier):
        self.provider_name = provider_name
        self.tier = tier

    @abstractmethod
    def lookup_actual(self, event: Dict[str, Any], run_time_kst: datetime.datetime) -> Optional[ActualRecord]:
        """
        개별 캘린더 이벤트에 대해 매칭되는 실제치를 조회하여 반환.
        매칭되지 않거나 미발표 상태인 경우 None 반환.
        """
        pass

    def lookup_with_status(self, event: Dict[str, Any], run_time_kst: datetime.datetime) -> tuple[Optional[ActualRecord], str, str]:
        """
        이벤트에 대해 실제치 및 조회 상태/상세 메시지 반환
        반환: (record, status, message)
        """
        rec = self.lookup_actual(event, run_time_kst)
        if rec and rec.is_valid_actual():
            return rec, ProviderLookupStatus.FOUND, "OK"
        return None, ProviderLookupStatus.MATCH_FAILED, "No match or pending"

    def fetch_records_for_window(self, start_kst: datetime.datetime, end_kst: datetime.datetime) -> List[ActualRecord]:
        """지정된 기간 내 모든 실제치 레코드 일괄 조회 (지원 시 구현)"""
        return []
