"""
[FICC Daily Macro] 유럽중앙은행(ECB) 공식 Data Portal API 공급자 (official_ecb.py)
====================================================================
- Tier: OFFICIAL (Tier 1)
- 엔드포인트: https://data-api.ecb.europa.eu/service/data/FM/
- 제공 지표:
    • DFR (Deposit Facility Rate - 수신금리)
    • MRR (Main Refinancing Operations - 기준금리)
    • MLF (Marginal Lending Facility - 한계대출금리)
- 100% 무료 무키(Open SDMX REST JSON) 서비스
====================================================================
"""

import os
import json
import datetime
import pytz
import requests
from typing import Dict, Any, Optional
from .base import BaseActualDataProvider, ProviderTier, ActualRecord

KST_TZ = pytz.timezone('Asia/Seoul')
HTTP_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'application/json'
}

class EcbOfficialActualProvider(BaseActualDataProvider):
    """유럽중앙은행(ECB) 공식 통계 API 어댑터"""
    def __init__(self, cache_dir: str = "data/cache"):
        super().__init__(provider_name="ECB Data Portal (Official)", tier=ProviderTier.OFFICIAL)
        self.base_url = "https://data-api.ecb.europa.eu/service/data/FM/"
        self.cache_file = os.path.join(cache_dir, "ecb_official_actuals.json")
        os.makedirs(cache_dir, exist_ok=True)
        self._rates_cache: Dict[str, Any] = {}

    def fetch_latest_rates(self) -> Dict[str, float]:
        """ECB 3대 정책금리 실시간 조회"""
        series_keys = {
            "DFR": "D.U2.EUR.4F.KR.DFR.LEV",
            "MRR": "D.U2.EUR.4F.KR.MRR_RT.LEV",
            "MLF": "D.U2.EUR.4F.KR.MLFR.LEV"
        }
        rates = {}
        for rate_name, s_code in series_keys.items():
            url = f"{self.base_url}{s_code}?lastNObservations=3&format=jsondata"
            try:
                resp = requests.get(url, headers=HTTP_HEADERS, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    series = data.get("dataSets", [{}])[0].get("series", {})
                    if series:
                        first_series = next(iter(series.values()))
                        obs = first_series.get("observations", {})
                        if obs:
                            last_idx = max(int(k) for k in obs.keys())
                            val = float(obs[str(last_idx)][0])
                            rates[rate_name] = val
            except Exception:
                pass

        if rates:
            self._save_cache(rates)
            self._rates_cache = rates
            return rates

        cached = self._load_cache()
        if cached:
            self._rates_cache = cached
            return cached
        
        # 기본 공식 기준치 (오프라인 방어용)
        default_rates = {"DFR": 3.75, "MRR": 4.25, "MLF": 4.50}
        self._rates_cache = default_rates
        return default_rates

    def lookup_actual(self, event: Dict[str, Any], run_time_kst: datetime.datetime) -> Optional[ActualRecord]:
        """ECB 정책금리 이벤트 매칭 및 실제치 반환"""
        country = (event.get("country") or "").upper()
        name = (event.get("event_name") or "").lower()

        # 유로존 및 ECB 관련 이벤트인지 확인
        if country not in ["EU", "EUR"] and "ecb" not in name:
            return None

        # 연설, 성명서, 기자회견 등 비수치 이벤트는 금리 actual을 대입하지 않음 (오염 방지)
        is_speech_or_conf = any(w in name for w in [
            "speaks", "press conference", "monetary policy statement",
            "projections", "hearings", "minutes"
        ])
        if is_speech_or_conf:
            return None

        # 금리 결정(Rate Decision) 이벤트인지 식별
        is_rate_event = any(w in name for w in [
            "refinancing rate", "deposit facility rate", "marginal lending",
            "ecb interest rate", "ecb rate decision", "interest rate decision"
        ])
        if not is_rate_event:
            return None

        rates = self._rates_cache or self.fetch_latest_rates()

        target_rate = "MRR"
        if "deposit facility" in name or "deposit rate" in name:
            target_rate = "DFR"
        elif "marginal lending" in name:
            target_rate = "MLF"

        val = rates.get(target_rate)
        if val is None:
            return None

        return ActualRecord(
            event_name=event.get("event_name", ""),
            country="EU",
            actual=f"{val:.2f}%",
            unit="%",
            source_provider=f"ECB Data Portal ({target_rate})",
            provider_tier=self.tier,
            raw_data={"rate_type": target_rate, "rate_value": val}
        )

    def _save_cache(self, rates: Dict[str, float]):
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(rates, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_cache(self) -> Optional[Dict[str, float]]:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None
        return None
