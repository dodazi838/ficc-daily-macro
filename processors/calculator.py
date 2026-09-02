"""
[FICC Daily Macro] 데이터 가공 및 매크로/채권 스프레드 계산기
"""

import pandas as pd
from typing import List, Dict, Any, Optional

def format_change(val: Optional[float], is_pct: bool = True, is_bp: bool = False, decimals: int = 2) -> str:
    """변동폭 수치에 부호(+/-) 및 단위 포맷 적용"""
    if val is None or pd.isna(val):
        return "N/A"
    if is_bp:
        return f"{val:+.1f} bp"
    elif is_pct:
        return f"{val:+.2f}%"
    else:
        return f"{val:+.{decimals}f}"

class MacroCalculator:
    """수집된 28개 원천 데이터를 가공하고 FICC 핵심 스프레드를 산출하는 가공기"""

    @classmethod
    def process_all(cls, raw_records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        전체 레코드를 분석하여 카테고리별 정렬, 스프레드 산출, 검증 통계를 포함한 정형 데이터셋을 구성합니다.
        """
        records_by_name = {r["name"]: r for r in raw_records}
        records_by_cat = {
            "EQUITY": [r for r in raw_records if r.get("category") == "EQUITY"],
            "FX": [r for r in raw_records if r.get("category") == "FX"],
            "BOND": [r for r in raw_records if r.get("category") == "BOND"],
            "COMMODITY": [r for r in raw_records if r.get("category") == "COMMODITY"]
        }

        # 채권 스프레드 산출
        spreads = cls.calculate_bond_spreads(records_by_name)

        # 데이터 정합성 통계
        status_counts = {"DAILY_CONFIRMED": 0, "PRE_1630_TEST": 0, "DELAYED": 0, "ERROR": 0}
        for r in raw_records:
            st = r.get("validation_status", "ERROR")
            status_counts[st] = status_counts.get(st, 0) + 1

        return {
            "summary_stats": {
                "total_indicators": len(raw_records),
                "status_counts": status_counts,
                "is_all_valid": status_counts["ERROR"] == 0
            },
            "spreads": spreads,
            "categories": records_by_cat,
            "items": raw_records
        }

    @classmethod
    def calculate_bond_spreads(cls, records_by_name: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """핵심 4대 채권 스프레드(장단기 금리차, 한미/독미 스프레드) 계산"""
        spread_definitions = [
            {
                "name": "미국 장단기 스프레드 (10Y - 2Y)",
                "long_name": "미국 국채 10년",
                "short_name": "미국 국채 2년",
                "type": "TERM_SPREAD",
                "description": "경기 침체 및 연준 통화정책 완화 선행지표"
            },
            {
                "name": "한국 장단기 스프레드 (10Y - 3Y)",
                "long_name": "한국 국고채 10년",
                "short_name": "한국 국고채 3년",
                "type": "TERM_SPREAD",
                "description": "국내 경기 전망 및 한은 기준금리 경로 선행지표"
            },
            {
                "name": "한-미 10년물 스프레드 (KR 10Y - US 10Y)",
                "long_name": "한국 국고채 10년",
                "short_name": "미국 국채 10년",
                "type": "CROSS_COUNTRY_SPREAD",
                "description": "외환시장(USD/KRW) 및 해외 자본유출입 영향"
            },
            {
                "name": "독-미 10년물 스프레드 (DE 10Y - US 10Y)",
                "long_name": "독일 국채 10년",
                "short_name": "미국 국채 10년",
                "type": "CROSS_COUNTRY_SPREAD",
                "description": "미국-유럽 경제 펀더멘털 및 통화정책 차이"
            }
        ]

        spread_results = []
        for s_def in spread_definitions:
            long_rec = records_by_name.get(s_def["long_name"])
            short_rec = records_by_name.get(s_def["short_name"])

            curr_spread_bp = None
            prev_spread_bp = None
            chg_bp = None
            status = "ERROR"

            if (long_rec and short_rec and 
                long_rec.get("current") is not None and short_rec.get("current") is not None and
                long_rec.get("prev") is not None and short_rec.get("prev") is not None):

                curr_spread_bp = (long_rec["current"] - short_rec["current"]) * 100.0
                prev_spread_bp = (long_rec["prev"] - short_rec["prev"]) * 100.0
                chg_bp = curr_spread_bp - prev_spread_bp

                # 두 자산의 검증 상태 중 더 낮은 단계 반영
                if long_rec["validation_status"] == "DAILY_CONFIRMED" and short_rec["validation_status"] == "DAILY_CONFIRMED":
                    status = "DAILY_CONFIRMED"
                elif "ERROR" in [long_rec["validation_status"], short_rec["validation_status"]]:
                    status = "ERROR"
                else:
                    status = "PRE_1630_TEST"

            spread_results.append({
                "name": s_def["name"],
                "type": s_def["type"],
                "description": s_def["description"],
                "current_bp": curr_spread_bp,
                "prev_bp": prev_spread_bp,
                "change_bp": chg_bp,
                "validation_status": status
            })

        return spread_results
