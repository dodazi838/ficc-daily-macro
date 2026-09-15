"""
[FICC Daily Macro] Daily Event 큐레이션, 시간창 필터, 중요도 평가 및 정책 클러스터링 10대 단위 테스트
(test_daily_event_curation.py)
"""

import os
import sys
import datetime
import pytz
import unittest
from typing import Dict, Any, List

# Windows 콘솔 UTF-8 출력 호환성
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# 프로젝트 루트 임포트 경로 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from processors.event_processor import (
    MacroEventProcessor, ensure_kst_aware, normalize_policy_event, is_macro_event_override
)

KST_TZ = pytz.timezone("Asia/Seoul")


class TestDailyEventCuration(unittest.TestCase):
    def setUp(self):
        self.kst = KST_TZ
        self.run_time = self.kst.localize(datetime.datetime(2026, 9, 9, 21, 0, 0))

    def test_01_ecb_policy_decision_included_in_candidates(self):
        """TEST 1: ECB policy decision이 존재하면 Daily Event 후보에 반드시 포함된다."""
        events = [
            {
                "event_id": "EVT_ECB_001",
                "country": "EU",
                "event_name": "Main Refinancing Rate",
                "scheduled_at_kst": "2026-09-10 21:15:00 KST",
                "forecast": "2.65%",
                "prior": "2.40%",
                "importance": "HIGH"
            },
            {
                "event_id": "EVT_MINOR_002",
                "country": "EU",
                "event_name": "Italian Industrial Production m/m",
                "scheduled_at_kst": "2026-09-10 17:00:00 KST",
                "importance": "LOW"
            }
        ]
        res = MacroEventProcessor.process_calendar_events(events, self.run_time)
        all_candidates = res["today_night_events"] + res["next_trading_day_events"]
        cand_names = [e.get("event_name") for e in all_candidates]
        cand_types = [e.get("cluster_type") for e in all_candidates]

        self.assertTrue(
            any("ECB" in name or "Refinancing" in name for name in cand_names) or
            "CENTRAL_BANK_POLICY" in cand_types,
            f"ECB policy decision must be in candidates, got: {cand_names}"
        )

    def test_02_fomc_policy_decision_included_in_candidates(self):
        """TEST 2: FOMC policy decision도 동일하게 포함된다."""
        events = [
            {
                "event_id": "EVT_FOMC_001",
                "country": "US",
                "event_name": "Federal Funds Rate",
                "scheduled_at_kst": "2026-09-10 03:00:00 KST",
                "forecast": "5.25%",
                "prior": "5.50%",
                "importance": "HIGH"
            },
            {
                "event_id": "EVT_FOMC_002",
                "country": "US",
                "event_name": "FOMC Statement",
                "scheduled_at_kst": "2026-09-10 03:00:00 KST",
                "importance": "HIGH"
            }
        ]
        res = MacroEventProcessor.process_calendar_events(events, self.run_time)
        all_candidates = res["today_night_events"] + res["next_trading_day_events"]
        cand_names = [e.get("event_name") for e in all_candidates]

        self.assertTrue(
            any("FOMC" in name or "Federal Funds" in name for name in cand_names),
            f"FOMC policy decision must be in candidates, got: {cand_names}"
        )

    def test_03_no_speech_only_selection_when_policy_decision_exists(self):
        """TEST 3: 정책결정일에 단순 중앙은행 연설만 선택되고 policy decision이 빠지는 경우 FAIL."""
        events = [
            {
                "event_id": "EVT_ECB_SPEECH",
                "country": "EU",
                "event_name": "ECB President Lagarde Speaks",
                "scheduled_at_kst": "2026-09-10 02:00:00 KST",
                "importance": "LOW"
            },
            {
                "event_id": "EVT_ECB_RATE",
                "country": "EU",
                "event_name": "Main Refinancing Rate",
                "scheduled_at_kst": "2026-09-10 21:15:00 KST",
                "forecast": "2.65%",
                "prior": "2.40%",
                "importance": "HIGH"
            }
        ]
        res = MacroEventProcessor.process_calendar_events(events, self.run_time)
        next_cand = res["next_trading_day_events"]
        
        # 다음 거래일 후보군에 정책결정이 반드시 존재해야 하며, 단순 연설만 단독으로 채워지면 안 됨
        has_decision = any(
            e.get("cluster_type") == "CENTRAL_BANK_POLICY" or 
            "Refinancing" in e.get("event_name", "") or 
            "통화정책 결정" in e.get("event_name", "")
            for e in next_cand
        )
        self.assertTrue(has_decision, "Policy decision must NOT be missing on a policy decision date!")

    def test_04_ecb_policy_cluster_grouping(self):
        """TEST 4: ECB 동일 정책결정일 이벤트가 하나의 cluster로 묶이는지 확인.
        rate decision + press conference + macro projections -> 하나의 ECB_POLICY cluster
        """
        events = [
            {
                "event_id": "EVT_01",
                "country": "EU",
                "event_name": "Main Refinancing Rate",
                "scheduled_at_kst": "2026-09-10 21:15:00 KST",
                "forecast": "2.65%",
                "prior": "2.40%"
            },
            {
                "event_id": "EVT_02",
                "country": "EU",
                "event_name": "Monetary Policy Statement",
                "scheduled_at_kst": "2026-09-10 21:15:00 KST"
            },
            {
                "event_id": "EVT_03",
                "country": "EU",
                "event_name": "ECB Press Conference",
                "scheduled_at_kst": "2026-09-10 21:45:00 KST"
            },
            {
                "event_id": "EVT_04",
                "country": "EU",
                "event_name": "ECB Macroeconomic Projections",
                "scheduled_at_kst": "2026-09-10 22:45:00 KST"
            }
        ]
        clusters, clustered_ids = MacroEventProcessor.cluster_policy_events(events)
        self.assertEqual(len(clusters), 1, "Should create exactly 1 policy cluster")
        c = clusters[0]
        self.assertEqual(c["cluster_type"], "CENTRAL_BANK_POLICY")
        self.assertEqual(c["institution"], "ECB")
        self.assertEqual(c["policy_date"], "2026-09-10")
        self.assertEqual(len(c["components"]), 4, "All 4 policy components should be in cluster")

    def test_05_adp_in_today_night_candidates_at_2100(self):
        """TEST 5: 2026-09-09 21:00 실행 기준 21:15 ADP가 candidate에 존재하는지 확인."""
        events = [
            {
                "event_id": "EVT_ADP",
                "country": "US",
                "event_name": "ADP Weekly Employment Change",
                "scheduled_at_kst": "2026-09-09 21:15:00 KST",
                "prior": "11.8K",
                "importance": "LOW"
            },
            {
                "event_id": "EVT_API",
                "country": "US",
                "event_name": "API Weekly Statistical Bulletin",
                "scheduled_at_kst": "2026-09-10 05:30:00 KST",
                "importance": "LOW"
            }
        ]
        res = MacroEventProcessor.process_calendar_events(events, self.run_time)
        night_cand = res["today_night_events"]
        night_names = [e.get("event_name") for e in night_cand]
        self.assertIn("ADP Weekly Employment Change", night_names, f"ADP must be in today_night candidates, got: {night_names}")

    def test_06_eia_crude_in_today_night_candidates_at_2100(self):
        """TEST 6: 2026-09-09 21:00 실행 기준 23:30 EIA Crude Oil Inventories가 candidate에 존재하는지 확인."""
        events = [
            {
                "event_id": "EVT_EIA",
                "country": "US",
                "event_name": "Crude Oil Inventories",
                "scheduled_at_kst": "2026-09-09 23:30:00 KST",
                "prior": "-4.5M",
                "importance": "LOW"
            }
        ]
        res = MacroEventProcessor.process_calendar_events(events, self.run_time)
        night_cand = res["today_night_events"]
        night_names = [e.get("event_name") for e in night_cand]
        self.assertIn("Crude Oil Inventories", night_names, f"EIA Crude Oil Inventories must be in candidates, got: {night_names}")

    def test_07_past_events_not_in_upcoming_window(self):
        """TEST 7: 2026-09-09 21:00 실행 기준 00:00 / 02:00 / 04:00 이벤트가 향후 이벤트로 다시 들어가지 않는지 확인."""
        events = [
            {
                "event_id": "EVT_PAST_00",
                "country": "US",
                "event_name": "NY Fed Inflation Expectations",
                "scheduled_at_kst": "2026-09-09 00:00:00 KST",
                "actual": "3.6%",
                "importance": "HIGH"
            },
            {
                "event_id": "EVT_PAST_02",
                "country": "US",
                "event_name": "3-Year Note Auction",
                "scheduled_at_kst": "2026-09-09 02:00:00 KST",
                "actual": "4.474%",
                "importance": "MEDIUM"
            },
            {
                "event_id": "EVT_PAST_04",
                "country": "US",
                "event_name": "Consumer Credit m/m",
                "scheduled_at_kst": "2026-09-09 04:00:00 KST",
                "actual": "18.06B",
                "forecast": "16.0B",
                "importance": "LOW"
            }
        ]
        res = MacroEventProcessor.process_calendar_events(events, self.run_time)
        night_names = [e.get("event_name") for e in res["today_night_events"]]
        next_names = [e.get("event_name") for e in res["next_trading_day_events"]]

        for past_name in ["NY Fed Inflation Expectations", "3-Year Note Auction", "Consumer Credit m/m"]:
            self.assertNotIn(past_name, night_names, f"Past event '{past_name}' must NOT be in today_night")
            self.assertNotIn(past_name, next_names, f"Past event '{past_name}' must NOT be in next_trading_day")

        # 과거 이벤트는 day_review에 속해야 함
        day_names = [e.get("event_name") for e in res["day_review_events"]]
        self.assertTrue(len(day_names) > 0, "Past events should be curated into day_review")

    def test_08_next_trading_day_ecb_policy_cluster_detected(self):
        """TEST 8: 21:00 이후 next trading day ECB policy cluster가 별도 후보군으로 잡히는지 확인."""
        events = [
            {
                "event_id": "EVT_ECB_MRR",
                "country": "EU",
                "event_name": "Main Refinancing Rate",
                "scheduled_at_kst": "2026-09-10 21:15:00 KST",
                "forecast": "2.65%",
                "importance": "HIGH"
            },
            {
                "event_id": "EVT_ECB_PC",
                "country": "EU",
                "event_name": "ECB Press Conference",
                "scheduled_at_kst": "2026-09-10 21:45:00 KST",
                "importance": "HIGH"
            }
        ]
        res = MacroEventProcessor.process_calendar_events(events, self.run_time)
        next_events = res["next_trading_day_events"]
        self.assertTrue(len(next_events) >= 1, "Next trading day events must contain at least 1 candidate")
        has_ecb = any(
            e.get("cluster_type") == "CENTRAL_BANK_POLICY" or "ECB" in e.get("event_name", "")
            for e in next_events
        )
        self.assertTrue(has_ecb, f"ECB policy cluster must be captured in next_trading_day_events: {next_events}")

    def test_09_representative_event_preserves_detail_components(self):
        """TEST 9: 대표 이벤트를 뽑더라도 세부 일정 component가 metadata에서 유지되는지 확인."""
        events = [
            {
                "event_id": "EVT_RATE",
                "country": "EU",
                "event_name": "Main Refinancing Rate",
                "scheduled_at_kst": "2026-09-10 21:15:00 KST",
                "forecast": "2.65%",
                "prior": "2.40%"
            },
            {
                "event_id": "EVT_PRESS",
                "country": "EU",
                "event_name": "ECB Press Conference",
                "scheduled_at_kst": "2026-09-10 21:45:00 KST"
            }
        ]
        clusters, _ = MacroEventProcessor.cluster_policy_events(events)
        self.assertEqual(len(clusters), 1)
        cluster = clusters[0]
        self.assertIn("components", cluster)
        self.assertEqual(len(cluster["components"]), 2)
        comp_times = [c["scheduled_time_kst"] for c in cluster["components"]]
        self.assertIn("21:15", comp_times)
        self.assertIn("21:45", comp_times)

    def test_10_raw_events_not_arbitrarily_dropped_before_curation(self):
        """TEST 10: 원천 캘린더에 존재하는 이벤트가 curation 전에 임의로 사라지지 않는지 확인."""
        raw_events = [
            {"event_id": f"EVT_{i}", "event_name": f"Event {i}", "country": "US", "scheduled_at_kst": "2026-09-09 22:00:00 KST"}
            for i in range(15)
        ]
        res = MacroEventProcessor.process_calendar_events(raw_events, self.run_time)
        self.assertEqual(res["total_events"], 15, "all_processed_events must contain all 15 raw events")
        self.assertEqual(len(res["all_processed_events"]), 15, "Normalization must not discard raw events")

    def test_11_real_data_pipeline_trace_20260909_2100(self):
        """TEST 11: 실제 2026-09-09 21:00 KST 원천 데이터 파이프라인 정합성 검증
        - ADP: today_night 포함
        - ECB Policy: next_trading_day 클러스터 포함
        - Consumer Credit: day_review 포함 & today_night 미포함
        - 10Y 국채 입찰(독일, 미국): 보존 확인
        """
        import json
        raw_path = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "2026-09-09", "events.json")
        if not os.path.exists(raw_path):
            self.skipTest(f"Raw data file not found at {raw_path}")

        with open(raw_path, "r", encoding="utf-8") as f:
            raw_report = json.load(f)
        raw_events = raw_report.get("raw_events", [])

        res = MacroEventProcessor.process_calendar_events(raw_events, self.run_time)

        # 1. ADP 고용은 today_night에 반드시 존재
        night_names = [e.get("event_name", "") for e in res["today_night_events"]]
        self.assertTrue(any("ADP" in n for n in night_names), f"ADP must be in today_night, got: {night_names}")

        # 2. ECB 정책결정 클러스터는 next_trading_day에 반드시 존재
        next_cand = res["next_trading_day_events"]
        has_ecb_cluster = any(
            e.get("is_policy_cluster") or e.get("event_id") == "CLUSTER_ECB_POLICY_20260910" or "ECB" in e.get("event_name", "")
            for e in next_cand
        )
        self.assertTrue(has_ecb_cluster, f"ECB policy cluster must be in next_trading_day, got: {next_cand}")

        # 3. 과거 이벤트(Consumer Credit)는 day_review 윈도우에 속하지만, Tier 3이므로 curated_day_review 및 today_night에 없어야 함
        all_day_names = [e.get("event_name", "") for e in res["all_processed_events"] if e.get("time_window") == "DAY_REVIEW"]
        day_names = [e.get("event_name", "") for e in res["day_review_events"]]
        self.assertTrue(any("Consumer Credit" in n for n in all_day_names), "Consumer Credit must be classified as DAY_REVIEW time window")
        self.assertFalse(any("Consumer Credit" in n for n in day_names), "Consumer Credit (Tier 3) must NOT be in curated day_review")
        self.assertFalse(any("Consumer Credit" in n for n in night_names), "Consumer Credit must NOT be in today_night")

        # 4. 국채 입찰 보존
        day_and_night_names = day_names + night_names
        self.assertTrue(any("Bond Auction" in n for n in day_and_night_names), "Bond auctions must be preserved")


if __name__ == "__main__":
    unittest.main(verbosity=2)

