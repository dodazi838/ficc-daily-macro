"""
[Unit Tests] Macro Event Clustering, PPI Differentiation, and Freshness Tense Tests
"""
import unittest
import datetime
import pytz
from processors.event_processor import MacroEventProcessor, ensure_kst_aware
from generators.blog_formatter import NaverBlogFormatter
from generators.context_builder import AIContextBuilder

KST = pytz.timezone('Asia/Seoul')

class TestMacroClusteringAndFreshness(unittest.TestCase):
    def setUp(self):
        self.run_time = KST.localize(datetime.datetime(2026, 9, 10, 21, 58, 0))

    def test_ppi_translation_differentiation(self):
        """1. PPI Headline과 Core PPI가 서로 다른 한국어 canonical name으로 번역되는지 검증"""
        core_name = NaverBlogFormatter.translate_event_name("Core PPI m/m", "US")
        headline_name = NaverBlogFormatter.translate_event_name("PPI m/m", "US")

        self.assertIn("근원", core_name)
        self.assertIn("Core PPI", core_name)
        self.assertNotIn("근원", headline_name)
        self.assertEqual(headline_name, "생산자물가지수(PPI, 전월비)")
        self.assertNotEqual(core_name, headline_name)

    def test_cpi_clustering_next_trading_day(self):
        """2. 다음 거래일 미국 CPI 4개 세부항목이 단일 Macro Event Cluster로 묶이는지 검증"""
        raw_events = [
            {
                "event_id": "EVT_001",
                "event_name": "Core CPI m/m",
                "country": "US",
                "currency": "USD",
                "scheduled_at_kst": "2026-09-11 21:30:00 KST",
                "forecast": "0.2%",
                "prior": "0.1%"
            },
            {
                "event_id": "EVT_002",
                "event_name": "Core CPI y/y",
                "country": "US",
                "currency": "USD",
                "scheduled_at_kst": "2026-09-11 21:30:00 KST",
                "forecast": "2.4%",
                "prior": "2.3%"
            },
            {
                "event_id": "EVT_003",
                "event_name": "CPI m/m",
                "country": "US",
                "currency": "USD",
                "scheduled_at_kst": "2026-09-11 21:30:00 KST",
                "forecast": "0.4%",
                "prior": "0.2%"
            },
            {
                "event_id": "EVT_004",
                "event_name": "CPI y/y",
                "country": "US",
                "currency": "USD",
                "scheduled_at_kst": "2026-09-11 21:30:00 KST",
                "forecast": "3.4%",
                "prior": "3.3%"
            },
            {
                "event_id": "EVT_005",
                "event_name": "PPI y/y",
                "country": "JP",
                "currency": "JPY",
                "scheduled_at_kst": "2026-09-11 08:50:00 KST",
                "forecast": "7.4%",
                "prior": "7.0%"
            },
            {
                "event_id": "EVT_006",
                "event_name": "GDP m/m",
                "country": "GB",
                "currency": "GBP",
                "scheduled_at_kst": "2026-09-11 15:00:00 KST",
                "forecast": "0.0%",
                "prior": "0.1%"
            }
        ]
        res = MacroEventProcessor.process_calendar_events(raw_events, self.run_time)
        next_events = res["next_trading_day_events"]

        # CPI 4개는 1개의 클러스터로 축약되어 다음 거래일 후보는 총 3개(JP PPI, GB GDP, US CPI Cluster)
        self.assertEqual(len(next_events), 3)

        cpi_cluster = next((e for e in next_events if e.get("cluster_type") == "CPI_CLUSTER"), None)
        self.assertIsNotNone(cpi_cluster)
        self.assertEqual(cpi_cluster["representative_event"], "미국 소비자물가지수(CPI) 발표")
        self.assertEqual(len(cpi_cluster["components"]), 4)
        self.assertEqual(cpi_cluster["macro_priority"], 4)
        self.assertEqual(cpi_cluster["forecast"], "3.4%")

    def test_freshness_and_time_status_separation(self):
        """3. scheduled < run_time 인 과거 이벤트의 RELEASED_ACTUAL_NOT_FOUND 강제 검증"""
        raw_events = [
            {
                "event_id": "EVT_DAY_001",
                "event_name": "PPI m/m",
                "country": "US",
                "currency": "USD",
                "scheduled_at_kst": "2026-09-10 21:30:00 KST",
                "forecast": "0.4%",
                "actual": None
            },
            {
                "event_id": "EVT_NIGHT_001",
                "event_name": "Crude Oil Inventories",
                "country": "US",
                "currency": "USD",
                "scheduled_at_kst": "2026-09-11 01:00:00 KST",
                "forecast": "-1.4M",
                "actual": None
            }
        ]
        res = MacroEventProcessor.process_calendar_events(raw_events, self.run_time)
        day_events = res["day_review_events"]
        night_events = res["today_night_events"]

        self.assertEqual(len(day_events), 1)
        self.assertEqual(day_events[0]["time_status"], "RELEASED")
        self.assertEqual(day_events[0]["actual_status"], "NOT_FOUND")
        self.assertEqual(day_events[0]["freshness_status"], "RELEASED_ACTUAL_NOT_FOUND")

        self.assertEqual(len(night_events), 1)
        self.assertEqual(night_events[0]["time_status"], "UPCOMING")
        self.assertEqual(night_events[0]["actual_status"], "NOT_FOUND")
        self.assertEqual(night_events[0]["freshness_status"], "UPCOMING")

    def test_deduplication_different_forecasts_not_merged(self):
        """4. 동일 시각이라도 forecast나 prior가 다르면 deduplication에서 병합되지 않음 검증"""
        events = [
            {
                "event_id": "EVT_A",
                "event_name": "Producer Price Index m/m",
                "country": "US",
                "scheduled_at_kst": "2026-09-10 21:30:00 KST",
                "forecast": "0.3%",
                "prior": "0.2%"
            },
            {
                "event_id": "EVT_B",
                "event_name": "Producer Price Index m/m",
                "country": "US",
                "scheduled_at_kst": "2026-09-10 21:30:00 KST",
                "forecast": "0.4%",
                "prior": "0.0%"
            }
        ]
        deduped = MacroEventProcessor.deduplicate_events(events)
        self.assertEqual(len(deduped), 2, "forecast가 상이한 두 이벤트는 절대 병합되어서는 안 됩니다.")

if __name__ == "__main__":
    unittest.main()
