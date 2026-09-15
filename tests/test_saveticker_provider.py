"""
[FICC Daily Macro] SaveTicker Actual Provider, 우선순위, 중복 병합 및 엄격한 Curation 단위 테스트
(test_saveticker_provider.py)
"""

import os
import sys
import unittest
import datetime
import pytz
from typing import Dict, Any, List

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from collectors.actual_providers.saveticker import SaveTickerActualProvider, extract_canonical_category
from collectors.actual_providers.enricher import ActualEnrichmentEngine
from collectors.actual_providers.base import ActualRecord, ProviderTier
from processors.event_processor import MacroEventProcessor, ensure_kst_aware

KST_TZ = pytz.timezone("Asia/Seoul")


class TestSaveTickerProvider(unittest.TestCase):
    def setUp(self):
        self.provider = SaveTickerActualProvider()
        self.run_time_2100 = datetime.datetime(2026, 9, 9, 21, 0, 0, tzinfo=KST_TZ)

    def test_01_canonical_category_extraction(self):
        """1. 한글/영문 지표명에서 표준 카테고리 추출 검증"""
        cases = [
            ("CPI y/y", "CPI"),
            ("중국 소비자물가지수 (YoY)", "CPI"),
            ("8월 CPI상승률", "CPI"),
            ("Core CPI m/m", "CPI"),
            ("PPI y/y", "PPI"),
            ("중국 생산자물가지수 (YoY)", "PPI"),
            ("Non-Farm Employment Change", "NFP"),
            ("비농업 고용지수", "NFP"),
            ("ADP Weekly Employment Change", "ADP_EMPLOYMENT"),
            ("Crude Oil Inventories", "CRUDE_OIL_INVENTORIES"),
            ("원유재고", "CRUDE_OIL_INVENTORIES"),
            ("ECB Main Refinancing Rate", "RATE_DECISION"),
            ("Federal Funds Rate", "RATE_DECISION"),
            ("기준금리 결정", "RATE_DECISION"),
        ]
        for name, expected in cases:
            cat = extract_canonical_category(name)
            self.assertEqual(cat, expected, f"Category for '{name}' should be '{expected}', got '{cat}'")

    def test_02_saveticker_matching_and_enrichment(self):
        """2. SaveTicker provider가 캐시/데이터를 통해 올바르게 매칭되는지 검증"""
        mock_st_item = {
            "id": "st_test_china_cpi",
            "title": "8월 중국 소비자물가지수(CPI) ★★",
            "clean_title": "8월 중국 소비자물가지수(CPI)",
            "rating": 2,
            "importance": "MEDIUM",
            "country": "CN",
            "canonical_category": "CPI",
            "event_date": "2026-09-09T10:30:00",
            "actual": "0.8%",
            "forecast": "0.8%",
            "previous": "0.5%",
            "unit": "%"
        }
        self.provider._events_cache = [mock_st_item]

        target_event = {
            "event_name": "CPI y/y",
            "country": "CN",
            "currency": "CNY",
            "scheduled_at_kst": "2026-09-09 10:30:00 KST",
            "scheduled_dt_kst": datetime.datetime(2026, 9, 9, 10, 30, tzinfo=KST_TZ),
            "forecast": "0.8%",
            "prior": "0.5%",
            "actual": None
        }

        matched = self.provider.lookup_actual(target_event, self.run_time_2100)
        self.assertIsNotNone(matched)
        self.assertEqual(matched.actual, "0.8%")
        self.assertEqual(matched.source_provider, "SaveTicker")

    def test_03_saveticker_priority_over_forexfactory(self):
        """3. Provider Priority: SaveTicker (sub-rank 1)가 ForexFactory (sub-rank 3)보다 높은 우선순위 적용"""
        event = {
            "event_name": "CPI y/y",
            "country": "CN",
            "currency": "CNY",
            "scheduled_at_kst": "2026-09-09 10:30:00 KST",
            "scheduled_dt_kst": datetime.datetime(2026, 9, 9, 10, 30, tzinfo=KST_TZ),
            "forecast": "0.8%",
            "prior": "0.5%",
            "actual": None
        }

        st_provider = SaveTickerActualProvider()
        st_provider._events_cache = [{
            "id": "st_test_cpi",
            "clean_title": "8월 중국 소비자물가지수",
            "country": "CN",
            "canonical_category": "CPI",
            "event_date": "2026-09-09T10:30:00",
            "actual": "0.8%"
        }]

        engine = ActualEnrichmentEngine(providers=[st_provider])
        engine.enrich_events([event], self.run_time_2100)
        self.assertEqual(event["actual"], "0.8%")
        self.assertEqual(event["actual_source"], "SaveTicker")

    def test_04_discrepancy_logging(self):
        """4. 서로 다른 Provider가 상이한 Actual을 보고할 때 discrepancy_logs에 기록되는지 확인"""
        event = {
            "event_name": "Test Indicator",
            "country": "US",
            "scheduled_at_kst": "2026-09-09 10:00:00 KST",
            "scheduled_dt_kst": datetime.datetime(2026, 9, 9, 10, 0, tzinfo=KST_TZ),
            "actual": None
        }

        rec1 = ActualRecord(
            event_name="Test Indicator", country="US", actual="1.5%",
            release_time_kst=datetime.datetime(2026, 9, 9, 10, 0, tzinfo=KST_TZ),
            source_provider="SaveTicker", provider_tier=ProviderTier.PRIMARY
        )
        rec2 = ActualRecord(
            event_name="Test Indicator", country="US", actual="1.4%",
            release_time_kst=datetime.datetime(2026, 9, 9, 10, 0, tzinfo=KST_TZ),
            source_provider="ForexFactory", provider_tier=ProviderTier.PRIMARY
        )

        class MockP1:
            def lookup_actual(self, ev, dt): return rec1
        class MockP2:
            def lookup_actual(self, ev, dt): return rec2

        engine = ActualEnrichmentEngine(providers=[MockP1(), MockP2()])
        engine.enrich_events([event], self.run_time_2100)

        self.assertEqual(event["actual"], "1.5%")  # SaveTicker preferred over ForexFactory
        self.assertEqual(len(engine.discrepancy_logs), 1)
        log = engine.discrepancy_logs[0]
        self.assertEqual(log["selected_provider"], "SaveTicker")
        self.assertEqual(log["selected_value"], "1.5%")
        self.assertIn("ForexFactory", log["provider_values"])

    def test_05_event_deduplication(self):
        """5. 중복 이벤트(ADP 21:15 vs 21:16) 병합 및 canonical 식별자/merged_source_ids 검증"""
        raw_events = [
            {
                "event_id": "EVT_ADP_15",
                "country": "US",
                "event_name": "ADP Weekly Employment Change",
                "scheduled_at_kst": "2026-09-09 21:15:00 KST",
                "forecast": "15.0K",
                "prior": "11.8K"
            },
            {
                "event_id": "EVT_ADP_16",
                "country": "US",
                "event_name": "ADP Weekly Employment Change",
                "scheduled_at_kst": "2026-09-09 21:16:00 KST",
                "forecast": "15.0K",
                "prior": "11.8K"
            },
            # Headline CPI vs Core CPI는 절대 병합되면 안 됨
            {
                "event_id": "EVT_CPI_HEADLINE",
                "country": "US",
                "event_name": "CPI m/m",
                "scheduled_at_kst": "2026-09-11 21:30:00 KST"
            },
            {
                "event_id": "EVT_CPI_CORE",
                "country": "US",
                "event_name": "Core CPI m/m",
                "scheduled_at_kst": "2026-09-11 21:30:00 KST"
            }
        ]

        deduped = MacroEventProcessor.deduplicate_events(raw_events)
        # 4 events should become 3 (2 ADP merged into 1, CPI & Core CPI kept separate)
        self.assertEqual(len(deduped), 3)

        adp_events = [e for e in deduped if "adp" in e.get("event_name", "").lower()]
        self.assertEqual(len(adp_events), 1)
        self.assertIn("EVT_ADP_15", adp_events[0].get("merged_source_ids", []))
        self.assertIn("EVT_ADP_16", adp_events[0].get("merged_source_ids", []))

        cpi_events = [e for e in deduped if "cpi" in e.get("event_name", "").lower()]
        self.assertEqual(len(cpi_events), 2, "Headline CPI and Core CPI must remain separate!")

    def test_06_strict_curation_no_tier3_filling(self):
        """6. 엄격한 큐레이션: 이벤트가 1개뿐이어도 Tier 3(발언, 소비자신용 등)로 억지 채우지 않음"""
        pool = [
            {
                "event_id": "EVT_01",
                "event_name": "Crude Oil Inventories",
                "country": "US",
                "scheduled_at_kst": "2026-09-09 23:30:00 KST",
                "importance": "MEDIUM"
            },
            {
                "event_id": "EVT_SPEECH",
                "event_name": "Fed Governor Waller Speaks",
                "country": "US",
                "scheduled_at_kst": "2026-09-09 22:00:00 KST",
                "importance": "LOW"
            },
            {
                "event_id": "EVT_CREDIT",
                "event_name": "Consumer Credit m/m",
                "country": "US",
                "scheduled_at_kst": "2026-09-10 04:00:00 KST",
                "importance": "LOW"
            }
        ]

        curated = MacroEventProcessor.curate_today_night_events(pool, self.run_time_2100)
        # Only Crude Oil Inventories (Tier 2) should be selected; Speeches and Consumer Credit excluded!
        self.assertEqual(len(curated), 1)
        self.assertEqual(curated[0]["event_name"], "Crude Oil Inventories")


if __name__ == "__main__":
    unittest.main(verbosity=2)
