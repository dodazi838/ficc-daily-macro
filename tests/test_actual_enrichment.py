"""
[FICC Daily Macro] 실제치(Actual) 데이터 공급자 및 보강 계층 단위 테스트 (test_actual_enrichment.py)
========================================================================================
- 5대 테스트 대상 이벤트 검증 (US Consumer Credit, China CPI, China PPI, ADP, ECB)
- 거버넌스 원칙 검증:
    • Forecast를 Actual로 대입 금지
    • Previous를 Actual로 대입 금지
    • 미매칭 과거 이벤트: RELEASED_ACTUAL_NOT_FOUND 강제
    • 미래 예정 이벤트: UPCOMING 및 Actual None 강제
    • Provider 우선순위 (OFFICIAL > PRIMARY > SECONDARY)
    • 다중 공급자 상이 시 Discrepancy Logging
========================================================================================
"""

import unittest
from datetime import datetime
import pytz
from collectors.actual_providers import (
    ProviderTier,
    ActualRecord,
    BaseActualDataProvider,
    ActualEnrichmentEngine,
    EcbOfficialActualProvider,
    FredOfficialActualProvider,
    ForexFactoryLiveSnapshotProvider
)
from collectors.economic_calendar import EconomicCalendarCollector

KST_TZ = pytz.timezone('Asia/Seoul')

class TestActualEnrichment(unittest.TestCase):
    def setUp(self):
        self.engine = ActualEnrichmentEngine()
        self.run_time_2100 = datetime(2026, 9, 9, 21, 0, tzinfo=KST_TZ)
        self.run_time_2120 = datetime(2026, 9, 9, 21, 20, tzinfo=KST_TZ)

    def test_1_us_consumer_credit_enrichment(self):
        """1. US Consumer Credit: 연준 G.19 공식 또는 PRIMARY 매칭 및 실제치(18.1B) 보강"""
        ev = {
            "event_name": "Consumer Credit m/m",
            "country": "US",
            "currency": "USD",
            "scheduled_at_kst": "2026-09-09 04:00:00 KST",
            "scheduled_dt_kst": datetime(2026, 9, 9, 4, 0, tzinfo=KST_TZ),
            "forecast": "11.9B",
            "prior": "14.2B",
            "actual": None
        }
        res = self.engine.lookup_for_event(ev, self.run_time_2100)
        self.assertIsNotNone(res["selected_record"])
        self.assertEqual(res["selected_record"].actual, "18.1B")
        self.assertEqual(res["selected_record"].provider_tier, ProviderTier.OFFICIAL)

        self.engine.enrich_events([ev], self.run_time_2100)
        self.assertEqual(ev["actual"], "18.1B")
        self.assertEqual(ev["freshness_status"], "RELEASED_WITH_ACTUAL")
        self.assertNotEqual(ev["actual"], ev["forecast"])

    def test_2_china_cpi_enrichment(self):
        """2. China CPI: 중국 8월 CPI 실제치(0.8%) 보강 및 예측치(0.8%)와의 독립성 검증"""
        ev = {
            "event_name": "CPI y/y",
            "country": "CN",
            "currency": "CNY",
            "scheduled_at_kst": "2026-09-09 10:30:00 KST",
            "scheduled_dt_kst": datetime(2026, 9, 9, 10, 30, tzinfo=KST_TZ),
            "forecast": "0.8%",
            "prior": "0.5%",
        }
        self.engine.enrich_events([ev], self.run_time_2100)
        self.assertEqual(ev["actual"], "0.8%")
        self.assertEqual(ev["freshness_status"], "RELEASED_WITH_ACTUAL")
        self.assertTrue(any(src in ev["actual_source"] for src in ["SaveTicker", "ForexFactory"]))

    def test_3_china_ppi_enrichment(self):
        """3. China PPI: 중국 8월 PPI 실제치(3.8%) 보강 (예측치 3.6%와 상이)"""
        ev = {
            "event_name": "PPI y/y",
            "country": "CN",
            "currency": "CNY",
            "scheduled_at_kst": "2026-09-09 10:30:00 KST",
            "scheduled_dt_kst": datetime(2026, 9, 9, 10, 30, tzinfo=KST_TZ),
            "forecast": "3.6%",
            "prior": "3.5%",
            "actual": None
        }
        self.engine.enrich_events([ev], self.run_time_2100)
        self.assertEqual(ev["actual"], "3.8%")
        self.assertEqual(ev["freshness_status"], "RELEASED_WITH_ACTUAL")

    def test_4_adp_weekly_employment_time_gating(self):
        """4. ADP Weekly Employment: 21:00에는 UPCOMING(유출차단), 21:20 발표 후에는 RELEASED_WITH_ACTUAL(10.0K)"""
        ev = {
            "event_name": "ADP Weekly Employment Change",
            "country": "US",
            "currency": "USD",
            "scheduled_at_kst": "2026-09-09 21:15:00 KST",
            "scheduled_dt_kst": datetime(2026, 9, 9, 21, 15, tzinfo=KST_TZ),
            "forecast": None,
            "prior": "11.8K",
            "actual": None
        }
        # 1) 21:00 실행 (발표 15분 전) -> UPCOMING 및 Actual None
        ev_2100 = dict(ev)
        self.engine.enrich_events([ev_2100], self.run_time_2100)
        self.assertIsNone(ev_2100["actual"])
        self.assertEqual(ev_2100["freshness_status"], "UPCOMING")

        # 2) 21:20 실행 (발표 5분 후) -> RELEASED_WITH_ACTUAL
        ev_2120 = dict(ev)
        self.engine.enrich_events([ev_2120], self.run_time_2120)
        self.assertEqual(ev_2120["actual"], "10.0K")
        self.assertEqual(ev_2120["freshness_status"], "RELEASED_WITH_ACTUAL")

    def test_5_ecb_policy_events(self):
        """5. ECB 정책 이벤트: 연설/기자회견 등 비수치 이벤트 격리 및 금리결정 시 공식 API 연동"""
        # 비수치 이벤트: 기자회견
        conf_ev = {
            "event_name": "ECB Press Conference",
            "country": "EU",
            "scheduled_at_kst": "2026-09-10 21:45:00 KST",
            "scheduled_dt_kst": datetime(2026, 9, 10, 21, 45, tzinfo=KST_TZ),
            "forecast": None,
            "prior": None,
            "actual": None
        }
        self.engine.enrich_events([conf_ev], self.run_time_2100)
        self.assertIsNone(conf_ev["actual"])
        self.assertEqual(conf_ev["freshness_status"], "UPCOMING")

        # 수치 이벤트: ECB 예치금리 결정
        rate_ev = {
            "event_name": "ECB Deposit Facility Rate",
            "country": "EU",
            "scheduled_at_kst": "2026-09-08 21:15:00 KST",
            "scheduled_dt_kst": datetime(2026, 9, 8, 21, 15, tzinfo=KST_TZ),
            "forecast": "3.75%",
            "prior": "3.75%",
            "actual": None
        }
        self.engine.enrich_events([rate_ev], self.run_time_2100)
        self.assertIsNotNone(rate_ev["actual"])
        self.assertEqual(rate_ev["freshness_status"], "RELEASED_WITH_ACTUAL")
        self.assertIn("ECB Data Portal", rate_ev["actual_source"])

    def test_6_released_actual_not_found(self):
        """6. 미수집 과거 수치 이벤트: RELEASED_ACTUAL_NOT_FOUND 강제 및 예측치/이전치 오염 방지"""
        unknown_ev = {
            "event_name": "Unobtainable Exotic Metric y/y",
            "country": "US",
            "scheduled_at_kst": "2026-09-09 08:00:00 KST",
            "scheduled_dt_kst": datetime(2026, 9, 9, 8, 0, tzinfo=KST_TZ),
            "forecast": "5.0%",
            "prior": "4.5%",
            "actual": None
        }
        self.engine.enrich_events([unknown_ev], self.run_time_2100)
        self.assertIsNone(unknown_ev["actual"])
        self.assertEqual(unknown_ev["freshness_status"], "RELEASED_ACTUAL_NOT_FOUND")
        self.assertNotEqual(unknown_ev["actual"], unknown_ev["forecast"])
        self.assertNotEqual(unknown_ev["actual"], unknown_ev["prior"])

    def test_7_provider_priority_and_discrepancy_logging(self):
        """7. 공급자 우선순위(OFFICIAL > PRIMARY) 및 불일치 발생 시 discrepancy_log 기록 검증"""
        class MockOfficial(BaseActualDataProvider):
            def __init__(self):
                super().__init__("Mock Official Fed", ProviderTier.OFFICIAL)
            def lookup_actual(self, event, run_time_kst):
                return ActualRecord(event_name=event["event_name"], country="US", actual="18.1B", source_provider=self.provider_name, provider_tier=self.tier)

        class MockPrimary(BaseActualDataProvider):
            def __init__(self):
                super().__init__("Mock Primary Feed", ProviderTier.PRIMARY)
            def lookup_actual(self, event, run_time_kst):
                return ActualRecord(event_name=event["event_name"], country="US", actual="18.9B", source_provider=self.provider_name, provider_tier=self.tier)

        custom_engine = ActualEnrichmentEngine(providers=[MockOfficial(), MockPrimary()])
        conflict_ev = {
            "event_name": "Conflict Metric",
            "country": "US",
            "scheduled_at_kst": "2026-09-09 08:00:00 KST",
            "scheduled_dt_kst": datetime(2026, 9, 9, 8, 0, tzinfo=KST_TZ),
            "forecast": "15.0B",
            "prior": "14.0B",
            "actual": None
        }
        report = custom_engine.enrich_events([conflict_ev], self.run_time_2100)

        # OFFICIAL(18.1B) 우선 채택 검증
        self.assertEqual(conflict_ev["actual"], "18.1B")
        self.assertEqual(conflict_ev["actual_source"], "Mock Official Fed")

        # Discrepancy Log 기록 확인
        self.assertEqual(report["discrepancy_logs_count"], 1)
        disc = report["discrepancy_logs"][0]
        self.assertEqual(disc["event_name"], "Conflict Metric")
        self.assertEqual(disc["selected_provider"], "Mock Official Fed")
        self.assertEqual(disc["selected_value"], "18.1B")
        self.assertIn("Priority rule", disc["resolution_rule"])

    def test_8_collector_integration(self):
        """8. EconomicCalendarCollector 통합 실행 및 보강 보고서/불일치 로그 반환 검증"""
        collector = EconomicCalendarCollector()
        events = [
            {
                "country": "CN",
                "currency": "CNY",
                "event_name": "CPI y/y",
                "scheduled_at_kst": "2026-09-09 10:30:00 KST",
                "scheduled_dt_kst": datetime(2026, 9, 9, 10, 30, tzinfo=KST_TZ),
                "forecast": "0.8%",
                "prior": "0.5%",
                "actual": None
            }
        ]
        collector.enrich_events_with_actuals(events, self.run_time_2100)
        self.assertEqual(events[0]["actual"], "0.8%")
        self.assertEqual(events[0]["freshness_status"], "RELEASED_WITH_ACTUAL")

if __name__ == "__main__":
    unittest.main()
