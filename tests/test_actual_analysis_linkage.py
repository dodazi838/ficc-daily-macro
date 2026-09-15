"""
[FICC Daily Macro] Actual Data - AI Analysis 간의 논리적 연결 및 무결성 거버넌스 회귀 테스트
(tests/test_actual_analysis_linkage.py)
========================================================================================
- Actual 없는 이벤트(RELEASED_ACTUAL_NOT_FOUND, Actual='-')의 결과 분석 차단 검증
- Actual 확인된 이벤트(RELEASED_WITH_ACTUAL)의 결과 분석 허용 검증
- SaveTicker + Investing.com 다중 Provider 조회 상태 추적 및 교차 검증
========================================================================================
"""

import sys
import os
import datetime
import unittest
import pytz
from typing import Dict, Any

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from processors.fact_validator import FactValidator
from collectors.actual_providers.enricher import ActualEnrichmentEngine
from collectors.actual_providers.base import ActualRecord, ProviderTier, ProviderLookupStatus
from collectors.actual_providers.saveticker import SaveTickerActualProvider
from collectors.actual_providers.investing_provider import InvestingActualProvider

KST_TZ = pytz.timezone("Asia/Seoul")


class TestActualAnalysisLinkage(unittest.TestCase):
    def setUp(self):
        self.run_time = datetime.datetime(2026, 9, 10, 21, 58, 0, tzinfo=KST_TZ)
        self.base_context = {
            "report_date": "2026-09-10",
            "run_time_kst": "2026-09-10 21:58:00 KST",
            "as_of": "2026-09-10 21:58:00 KST",
            "market_data": {
                "categories": {
                    "EQUITY": [{"name": "코스피", "symbol": "^KS11", "current": 7033.92, "pct_change": -0.25, "price_type": "종가", "market_status": "CLOSED"}],
                    "FX": [{"name": "달러 인덱스 (DXY)", "symbol": "DX-Y.NYB", "current": 99.1, "pct_change": 0.34, "price_type": "장외/글로벌 현재환율", "market_status": "INTRADAY"}],
                    "BOND": [{"name": "미국 국채 10년", "symbol": "US10Y", "current": 4.92, "bp_change": 8.2, "price_type": "Benchmark Cash Yield", "market_status": "INTRADAY"}],
                    "COMMODITY": [{"name": "WTI 원유", "symbol": "CL=F", "current": 99.69, "pct_change": 3.79, "price_type": "현재가 (장중)", "market_status": "INTRADAY", "change_status": "CONFIRMED"}]
                }
            }
        }

    def test_01_unverified_actual_result_analysis_strictly_rejected(self):
        """1. Actual='-'인 미확인 지표에 대해 본문에서 '상승', '반등' 등 결과 단정 시 FactValidator FAIL"""
        context = dict(self.base_context)
        context["economic_calendar"] = {
            "day_review": [
                {
                    "event_name": "Producer Price Index m/m",
                    "event_name_kor": "생산자물가지수(PPI, 전월비)",
                    "country": "US",
                    "scheduled_at_kst": "2026-09-10 21:30:00 KST",
                    "scheduled_time_kst": "21:30",
                    "actual": None,  # 미확인 상태!
                    "actual_status": "NOT_FOUND",
                    "freshness_status": "RELEASED_ACTUAL_NOT_FOUND",
                    "forecast": "0.4%",
                    "prior": "0.0%"
                }
            ],
            "today_night": [],
            "next_trading_day": []
        }

        # AI가 Actual이 없는데도 "PPI가 반등하고 상승세를 나타냈다"고 분석한 가상의 초안
        faulty_draft = {
            "ficc_daily_summary": {
                "bullets": [
                    "국제유가 상승 속에 인플레이션 경계감이 확산됨",
                    "미국 국채금리가 상승하며 증시가 장중 하락세를 보임",
                    "도매물가 발표 이후 물가 압력이 지속될 전망"
                ],
                "source_news_ids": [],
                "source_market_fields": ["COMMODITY.CL=F", "BOND.US10Y"],
                "source_event_ids": []
            },
            "ficc_summary": {
                "text": "미국 8월 생산자물가지수(PPI)가 전월 대비 반등하고 에너지 비용 부담이 부각되자 긴축 장기화 우려가 확산됨.",
                "source_news_ids": [],
                "source_market_fields": [],
                "source_event_ids": []
            },
            "issue_review": {
                "stock": {"text": "국내 및 미국 증시는 물가 압력 속에 장중 하락 압력을 받음."},
                "fx": {"text": "달러화는 국채금리 오름세 속에 전반적인 강세 흐름을 나타냄."},
                "bond": {"text": "미국 국채금리는 전 구간에서 큰 폭으로 상승함."},
                "commodity": {"text": "국제유가는 공급 차질 우려 속에 장중 큰 폭의 상승세를 지속함."}
            },
            "ficc_forecast": {
                "text": "유가 상승과 도매물가 영향으로 익일 미국 CPI 결과가 향후 시장의 핵심 변수로 작용할 전망."
            },
            "daily_event_watchpoints": {
                "text": "당일 발표된 미국 PPI는 전월 대비 상승세를 보였음."
            }
        }

        _, val_summary = FactValidator.validate_and_enrich(faulty_draft, context)
        self.assertFalse(val_summary["passed"], "Actual이 없는 이벤트의 결과 단정 분석은 반드시 FAIL이어야 함")
        error_texts = " ".join(val_summary["errors"])
        self.assertIn("Actual 미확인 이벤트 결과 분석 금지 위반", error_texts)
        self.assertIn("생산자물가지수(PPI)", error_texts)

    def test_02_unverified_actual_status_based_writing_allowed(self):
        """2. Actual='-'인 미확인 지표에 대해 '실제 수치 미확인', '확인 필요' 등 상태 서술 시 PASS"""
        context = dict(self.base_context)
        context["economic_calendar"] = {
            "day_review": [
                {
                    "event_name": "Producer Price Index m/m",
                    "event_name_kor": "생산자물가지수(PPI, 전월비)",
                    "country": "US",
                    "scheduled_at_kst": "2026-09-10 21:30:00 KST",
                    "scheduled_time_kst": "21:30",
                    "actual": None,
                    "actual_status": "NOT_FOUND",
                    "freshness_status": "RELEASED_ACTUAL_NOT_FOUND",
                    "forecast": "0.4%",
                    "prior": "0.0%"
                }
            ],
            "today_night": [],
            "next_trading_day": []
        }

        # 올바른 상태 서술 초안
        valid_draft = {
            "ficc_daily_summary": {
                "bullets": [
                    "국제유가가 상승하며 인플레이션 경계감이 확산됨",
                    "미국 국채금리가 상승하며 증시가 장중 하락 압력을 받음",
                    "익일 예정된 미국 CPI 발표가 주요 변수로 주목됨"
                ],
                "source_news_ids": [],
                "source_market_fields": ["COMMODITY.CL=F", "BOND.US10Y"],
                "source_event_ids": []
            },
            "ficc_summary": {
                "text": "국제유가가 장중 배럴당 100달러 수준으로 상승하면서 금융시장 전반의 인플레이션 우려가 고조됨. 미국 국채 10년물 금리가 상승하고 달러화가 강세를 나타냄.",
                "source_news_ids": [],
                "source_market_fields": [],
                "source_event_ids": []
            },
            "issue_review": {
                "stock": {"text": "국내 및 미국 증시는 밸류에이션 부담 속에 장중 하락 압력을 받음."},
                "fx": {"text": "달러화는 유가 급등과 국채금리 오름세에 힘입어 강세 흐름을 나타냄."},
                "bond": {"text": "미국 국채금리는 단기물과 장기물이 동반 상승하며 약세를 기록함."},
                "commodity": {"text": "국제유가는 공급 차질 우려 속에 장중 큰 폭으로 상승함."}
            },
            "ficc_forecast": {
                "text": "국제유가 급등세 속에 익일 발표 예정인 미국 소비자물가지수(CPI) 결과가 핵심 분기점이 될 것으로 보임."
            },
            "daily_event_watchpoints": {
                "text": "미국 생산자물가지수(PPI)는 발표 시각이 경과했으나 공식 수치가 확인되지 않아 결과 확인이 필요함."
            }
        }

        _, val_summary = FactValidator.validate_and_enrich(valid_draft, context)
        unverified_errors = [e for e in val_summary["errors"] if "Actual 미확인 이벤트" in e]
        self.assertEqual(len(unverified_errors), 0, f"상태 서술은 unverified_errors를 발생시키지 않아야 함: {unverified_errors}")

    def test_03_verified_actual_result_analysis_allowed(self):
        """3. Actual='0.4%'로 검증된 지표에 대해서는 결과 분석 작문이 정상 PASS"""
        context = dict(self.base_context)
        context["economic_calendar"] = {
            "day_review": [
                {
                    "event_name": "Producer Price Index m/m",
                    "event_name_kor": "생산자물가지수(PPI, 전월비)",
                    "country": "US",
                    "scheduled_at_kst": "2026-09-10 21:30:00 KST",
                    "scheduled_time_kst": "21:30",
                    "actual": "0.4%",  # 실제치 검증 완료!
                    "actual_status": "FOUND",
                    "freshness_status": "RELEASED_WITH_ACTUAL",
                    "forecast": "0.4%",
                    "prior": "0.0%"
                }
            ],
            "today_night": [],
            "next_trading_day": []
        }

        verified_draft = {
            "ficc_daily_summary": {
                "bullets": [
                    "국제유가가 상승하며 인플레이션 경계감이 확산됨",
                    "미국 국채금리가 상승하며 주식시장이 장중 하락 압력을 받음",
                    "미국 도매물가 상승 압력이 확인된 가운데 익일 CPI가 주목됨"
                ],
                "source_news_ids": [],
                "source_market_fields": ["COMMODITY.CL=F", "BOND.US10Y"],
                "source_event_ids": []
            },
            "ficc_summary": {
                "text": "미국 8월 생산자물가지수(PPI)가 전월 대비 반등하며 도매물가 상방 압력이 확인됨. 이에 따라 미국 국채금리가 오르고 증시가 내림세를 보임.",
                "source_news_ids": [],
                "source_market_fields": [],
                "source_event_ids": []
            },
            "issue_review": {
                "stock": {"text": "국내 증시는 소폭 하락 마감했고 미국 증시는 장중 내림세를 나타냄."},
                "fx": {"text": "달러화는 물가 상승 기대와 미국 국채금리 오름세로 강세를 나타냄."},
                "bond": {"text": "미국 국채금리는 PPI 발표 이후 인플레이션 고착화 우려로 상승세를 보임."},
                "commodity": {"text": "국제유가는 공급 차질 우려 속에 장중 큰 폭으로 상승함."}
            },
            "ficc_forecast": {
                "text": "익일 발표 예정인 미국 소비자물가지수(CPI)가 핵심 변수로 부각됨."
            },
            "daily_event_watchpoints": {
                "text": "당일 발표된 미국 8월 생산자물가지수(PPI)는 전월 대비 상승 전환함."
            }
        }

        _, val_summary = FactValidator.validate_and_enrich(verified_draft, context)
        unverified_errors = [e for e in val_summary["errors"] if "Actual 미확인 이벤트" in e]
        self.assertEqual(len(unverified_errors), 0, f"Actual이 검증된 지표의 분석은 unverified_errors를 발생시키지 않아야 함: {unverified_errors}")

    def test_04_detailed_provider_trace_generation(self):
        """4. ActualEnrichmentEngine이 다중 공급자별 상세 추적(trace)을 정확히 생성하는지 검증"""
        engine = ActualEnrichmentEngine()
        event = {
            "event_name": "Producer Price Index m/m",
            "country": "US",
            "currency": "USD",
            "scheduled_dt_kst": datetime.datetime(2026, 9, 10, 21, 30, tzinfo=KST_TZ),
            "scheduled_at_kst": "2026-09-10 21:30:00 KST",
            "forecast": "0.4%",
            "prior": "0.0%"
        }

        res = engine.lookup_for_event(event, self.run_time)
        self.assertIsNotNone(res["selected_record"])
        trace = res.get("actual_trace", {})

        self.assertEqual(trace.get("calendar"), "found")
        self.assertEqual(trace.get("saveticker"), "FOUND")
        self.assertEqual(trace.get("investing"), "FOUND")
        self.assertEqual(trace.get("matching"), "success")
        self.assertEqual(trace.get("parsing"), "success")
        self.assertEqual(trace.get("final_actual"), "0.4%")

    def test_05_saveticker_investing_cross_validation_and_discrepancy(self):
        """5. SaveTicker와 Investing.com의 일치 시 HIGH confidence, 불일치 시 discrepancy_logs 기록 검증"""
        # A. 정상 일치 케이스
        engine = ActualEnrichmentEngine()
        event_match = {
            "event_name": "Core Producer Price Index m/m",
            "country": "US",
            "currency": "USD",
            "scheduled_dt_kst": datetime.datetime(2026, 9, 10, 21, 30, tzinfo=KST_TZ),
            "scheduled_at_kst": "2026-09-10 21:30:00 KST",
            "forecast": "0.3%",
            "prior": "0.2%"
        }
        res_match = engine.lookup_for_event(event_match, self.run_time)
        self.assertFalse(res_match["has_discrepancy"])
        self.assertEqual(res_match["selected_record"].actual, "0.2%")

        # B. 불일치 발생 모의 케이스
        class MockDiffProvider(InvestingActualProvider):
            def lookup_actual(self, event, run_time_kst):
                rec = super().lookup_actual(event, run_time_kst)
                if rec:
                    rec.actual = "0.9%"  # 의도적 불일치 유발
                    rec.source_provider = "Investing.com"
                return rec

        engine_diff = ActualEnrichmentEngine(providers=[SaveTickerActualProvider(), MockDiffProvider()])
        res_diff = engine_diff.lookup_for_event(event_match, self.run_time)
        self.assertTrue(res_diff["has_discrepancy"])
        self.assertGreater(len(engine_diff.discrepancy_logs), 0)
        log = engine_diff.discrepancy_logs[0]
        self.assertEqual(log["provider_values"]["SaveTicker"], "0.2%")
        self.assertEqual(log["provider_values"]["Investing.com"], "0.9%")


if __name__ == "__main__":
    unittest.main()
