"""
[FICC Daily Macro] 미국 노동통계국(BLS) 공식 API 공급자 (official_bls.py)
====================================================================
- Tier: OFFICIAL (Tier 1)
- collectors.economic_calendar.BlsActualsAdapter 위임 연동
- 엔드포인트: https://api.bls.gov/publicAPI/v1/timeseries/data/
- CES0000000001: Total Nonfarm Employment (NFP 변동치 K)
- LNS14000000: Unemployment Rate (실업률 %)
- 4대 정밀 검증 (대상월, 관측기간, 발표일 정합성, 컷오프) 적용
====================================================================
"""

import datetime
from typing import Dict, Any, Optional
from .base import BaseActualDataProvider, ProviderTier, ActualRecord

class BlsOfficialActualProvider(BaseActualDataProvider):
    """미국 노동통계국(BLS) 공식 지표 제공자"""
    def __init__(self, cache_dir: str = "data/cache"):
        super().__init__(provider_name="BLS Public API (Official)", tier=ProviderTier.OFFICIAL)
        from collectors.economic_calendar import BlsActualsAdapter
        self.bls_adapter = BlsActualsAdapter(cache_dir=cache_dir)

    def lookup_actual(self, event: Dict[str, Any], run_time_kst: datetime.datetime) -> Optional[ActualRecord]:
        country = (event.get("country") or "").upper()
        name = (event.get("event_name") or "").lower()

        if country not in ["US", "USD"]:
            return None

        is_nfp = any(w in name for w in ["non-farm employment", "non-farm payroll", "nonfarm payroll", "nfp"])
        is_unemp = "unemployment rate" in name
        if not is_nfp and not is_unemp:
            return None

        # BlsActualsAdapter에 복사본 전달하여 4대 검증 및 데이터 주입 실행
        ev_copy = dict(event)
        self.bls_adapter.enrich_events([ev_copy], run_time_kst)

        act = ev_copy.get("actual")
        if act is not None and str(act).strip() not in ["", "-", "None"]:
            revised_str = None
            if ev_copy.get("is_revised_prior"):
                revised_str = ev_copy.get("prior")

            return ActualRecord(
                event_name=event.get("event_name", ""),
                country="US",
                actual=str(act),
                prior=ev_copy.get("prior"),
                revised_prior=revised_str,
                reference_period=ev_copy.get("reference_period"),
                source_provider=ev_copy.get("actual_source") or self.provider_name,
                provider_tier=self.tier
            )

        return None
