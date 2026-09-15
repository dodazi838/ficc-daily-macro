"""
Unit tests for Real-time Freshness & Data Consistency
Covers 8 core test cases:
1. BLS adapter parsing
2. EconomicCalendar enrichment with actual and revised prior
3. Event processor metadata preservation
4. ContextBuilder schema integrity
5. BlogFormatter table and text rendering with (수정)
6. FactValidator acceptance of enriched actuals
7. FactValidator detection of tense mismatch (released event described as upcoming)
8. FactValidator detection of fake actuals
"""

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime
import pytz

from collectors.economic_calendar import (
    BlsActualsAdapter, EconomicCalendarCollector,
    extract_event_reference_period, get_consecutive_prior_period,
    validate_release_date_consistency
)
from processors.event_processor import MacroEventProcessor
from generators.context_builder import AIContextBuilder
from generators.blog_formatter import NaverBlogFormatter
from processors.fact_validator import FactValidator
from collectors.fx import FxCollector

KST_TZ = pytz.timezone("Asia/Seoul")

class TestFreshnessEnrichment(unittest.TestCase):

    def setUp(self):
        self.mock_bls_response = {
            "status": "REQUEST_SUCCEEDED",
            "Results": {
                "series": [
                    {
                        "seriesID": "CES0000000001",
                        "data": [
                            {"year": "2026", "period": "M08", "value": "159200"},
                            {"year": "2026", "period": "M07", "value": "159178"},
                            {"year": "2026", "period": "M06", "value": "159157"}
                        ]
                    },
                    {
                        "seriesID": "LNS14000000",
                        "data": [
                            {"year": "2026", "period": "M08", "value": "4.3"},
                            {"year": "2026", "period": "M07", "value": "4.3"}
                        ]
                    }
                ]
            }
        }

    @patch("requests.post")
    def test_1_bls_adapter_fetches_and_parses(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = self.mock_bls_response
        mock_post.return_value = mock_resp

        adapter = BlsActualsAdapter()
        data = adapter.fetch_bls_labor_data(2026)

        self.assertIn("nfp", data)
        self.assertIn("unemployment_rate", data)
        self.assertEqual(data["nfp"]["latest_change"], 22.0)
        self.assertEqual(data["unemployment_rate"]["latest_rate_str"], "4.3%")

    @patch.object(BlsActualsAdapter, "fetch_bls_labor_data")
    def test_2_economic_calendar_enrichment(self, mock_fetch):
        mock_fetch.return_value = {
            "nfp": {
                "latest_period": "M08",
                "latest_change": 22.0,
                "latest_change_str": "+22K",
                "prior_revised": 21.0,
                "prior_revised_str": "+21K"
            },
            "unemployment_rate": {
                "latest_period": "M08",
                "latest_rate": 4.3,
                "latest_rate_str": "4.3%"
            }
        }

        collector = EconomicCalendarCollector()
        raw_events = [
            {
                "country": "US",
                "event_name": "Non-Farm Employment Change",
                "scheduled_dt_kst": datetime(2026, 9, 4, 21, 30, tzinfo=KST_TZ),
                "scheduled_at_kst": "2026-09-04 21:30:00 KST",
                "importance": "HIGH",
                "forecast": "165K",
                "previous": "89K",
                "prior": "89K",
                "actual": None
            },
            {
                "country": "US",
                "event_name": "Unemployment Rate",
                "scheduled_dt_kst": datetime(2026, 9, 4, 21, 30, tzinfo=KST_TZ),
                "scheduled_at_kst": "2026-09-04 21:30:00 KST",
                "importance": "HIGH",
                "forecast": "4.2%",
                "previous": "4.3%",
                "prior": "4.3%",
                "actual": None
            }
        ]

        # Simulating run at 22:00 KST (after 21:30 release)
        run_time_kst = datetime(2026, 9, 4, 22, 0, tzinfo=KST_TZ)
        enriched = collector.enrich_events_with_actuals(raw_events, run_time_kst)

        nfp = enriched[0]
        self.assertEqual(nfp["actual"], "+22K")
        self.assertEqual(nfp["prior"], "+21K")
        self.assertTrue(nfp["is_revised_prior"])
        self.assertEqual(nfp["freshness_status"], "RELEASED_WITH_ACTUAL")

        unemp = enriched[1]
        self.assertEqual(unemp["actual"], "4.3%")
        self.assertEqual(unemp["freshness_status"], "RELEASED_WITH_ACTUAL")

    def test_3_event_processor_preserves_freshness_metadata(self):
        enriched_events = [
            {
                "country": "US",
                "event_name": "Non-Farm Employment Change",
                "scheduled_dt_kst": datetime(2026, 9, 4, 21, 30, tzinfo=KST_TZ),
                "scheduled_at_kst": "2026-09-04 21:30:00 KST",
                "importance": "HIGH",
                "forecast": "165K",
                "prior": "21K",
                "actual": "+22K",
                "is_revised_prior": True,
                "actual_source": "BLS API (CES0000000001)",
                "freshness_status": "RELEASED_WITH_ACTUAL"
            }
        ]

        run_time_kst = datetime(2026, 9, 4, 22, 0, tzinfo=KST_TZ)
        processed = MacroEventProcessor.process_calendar_events(enriched_events, run_time_kst)

        day_review = processed["day_review_events"]
        self.assertEqual(len(day_review), 1)
        item = day_review[0]
        self.assertEqual(item["actual"], "+22K")
        self.assertEqual(item["prior"], "21K")
        self.assertTrue(item["is_revised_prior"])
        self.assertEqual(item["actual_source"], "BLS API (CES0000000001)")
        self.assertEqual(item["freshness_status"], "RELEASED_WITH_ACTUAL")

    def test_4_context_builder_includes_actual_and_revisions(self):
        processed_data = {
            "run_time_kst": "2026-09-04 22:00:00 KST",
            "report_date": "2026-09-04",
            "market_data": {"categories": {}, "spreads": []},
            "news_events": {"event_clusters": []},
            "economic_events": {
                "day_review_events": [
                    {
                        "event_id": "EV_001",
                        "country": "US",
                        "event_name": "Non-Farm Employment Change",
                        "scheduled_at_kst": "2026-09-04 21:30:00 KST",
                        "importance": "HIGH",
                        "forecast": "165K",
                        "prior": "+21K",
                        "actual": "+22K",
                        "is_revised_prior": True,
                        "actual_source": "BLS API",
                        "freshness_status": "RELEASED_WITH_ACTUAL",
                        "impact_category": "LABOR"
                    }
                ],
                "today_night_events": []
            }
        }

        context = AIContextBuilder.build_context(processed_data)
        cal = context["economic_calendar"]
        self.assertEqual(len(cal["day_review"]), 1)
        ev = cal["day_review"][0]
        self.assertEqual(ev["actual"], "+22K")
        self.assertEqual(ev["prior"], "+21K")
        self.assertTrue(ev["is_revised_prior"])
        self.assertEqual(ev["freshness_status"], "RELEASED_WITH_ACTUAL")

    def test_5_blog_formatter_renders_actual_and_revised_prior(self):
        report_data = {
            "report_date": "2026-09-04",
            "run_time_kst": "2026-09-04 22:00:00 KST",
            "final_passed": True,
            "content": {
                "ficc_daily_summary": {"bullets": ["요약1", "요약2", "요약3"]},
                "ficc_summary": {"text": "종합 요약"},
                "issue_review": {
                    "stock": {"text": "증시 리뷰"},
                    "fx": {"text": "환율 리뷰"},
                    "bond": {"text": "채권 리뷰"},
                    "commodity": {"text": "원자재 리뷰"}
                },
                "ficc_forecast": {"text": "전망"},
                "daily_event_watchpoints": {"text": "이벤트 리뷰"}
            }
        }

        processed_market_data = {
            "run_time_kst": "2026-09-04 22:00:00 KST",
            "market_data": {"categories": {}, "spreads": []},
            "economic_events": {
                "day_review_events": [
                    {
                        "event_id": "EV_001",
                        "country": "US",
                        "event_name": "Non-Farm Employment Change",
                        "scheduled_at_kst": "2026-09-04 21:30:00 KST",
                        "importance": "HIGH",
                        "forecast": "165K",
                        "prior": "+21K",
                        "actual": "+22K",
                        "is_revised_prior": True
                    }
                ],
                "today_night_events": []
            }
        }

        html = NaverBlogFormatter.format_blog_html(report_data, processed_market_data)
        text = NaverBlogFormatter.format_blog_text(report_data, processed_market_data)

        # Check HTML rendering of 7-column table with actual and revised prior
        self.assertIn("+22K", html)
        self.assertIn("+21K (수정)", html)
        self.assertIn("당일 주요 발표", html)

        # Check plain text rendering
        self.assertIn("+22K", text)
        self.assertIn("+21K(수정)", text)

    def test_6_fact_validator_allows_enriched_actuals(self):
        context = {
            "report_date": "2026-09-04",
            "run_time_kst": "2026-09-04 22:00:00 KST",
            "as_of": "22:00 KST 기준",
            "market_data": {"fx": [], "bonds": [], "commodities": [], "equities": [], "spreads": []},
            "verified_macro_news": [],
            "economic_calendar": {
                "day_review": [
                    {
                        "event_id": "EV_001",
                        "country": "US",
                        "event_name": "Non-Farm Employment Change",
                        "event_name_kor": "미국 비농업 고용지수(NFP)",
                        "scheduled_at": "2026-09-04 21:30:00 KST",
                        "scheduled_time_kst": "21:30",
                        "importance": "HIGH",
                        "forecast": "165K",
                        "prior": "21K",
                        "actual": "22K",
                        "is_revised_prior": True
                    }
                ],
                "today_night": []
            }
        }

        content = {
            "ficc_daily_summary": {
                "bullets": [
                    "미국 8월 비농업 부문 고용은 2.2만 건 증가에 그쳐 시장 예상치 16.5만 건을 대폭 하회함.",
                    "국채 금리는 고용 둔화에 따른 기준금리 인하 기대로 급락세를 나타냄.",
                    "달러화는 주요 통화 대비 약세를 지속함."
                ],
                "source_news_ids": [],
                "source_market_fields": [],
                "source_event_ids": ["EV_001"]
            },
            "ficc_summary": {
                "text": "미국 비농업 고용이 2.2만 건 증가에 그치며 노동시장 냉각 흐름이 재확인됨. 이에 따라 미 국채 금리는 하락하고 달러화는 약세를 시현함.",
                "source_news_ids": [],
                "source_market_fields": [],
                "source_event_ids": ["EV_001"]
            },
            "issue_review": {
                "stock": {"text": "증시는 금리 하락에도 불구하고 경기 둔화 우려 속에 혼조세를 나타냄.", "source_news_ids": [], "source_market_fields": [], "source_event_ids": []},
                "fx": {"text": "달러화는 고용 충격에 약세를 보임.", "source_news_ids": [], "source_market_fields": [], "source_event_ids": []},
                "bond": {"text": "국채 금리는 단기물을 중심으로 큰 폭 하락함.", "source_news_ids": [], "source_market_fields": [], "source_event_ids": []},
                "commodity": {"text": "국제유가는 수요 둔화 가능성에 하락함.", "source_news_ids": [], "source_market_fields": [], "source_event_ids": []}
            },
            "ficc_forecast": {"text": "향후 연준 위원들의 통화정책 발언에 주목할 필요가 있음."},
            "daily_event_watchpoints": {
                "text": "미국 8월 비농업 고용은 실제 2.2만 건으로 시장 예상 16.5만 건을 대폭 하회하였으며, 7월 수치도 2.1만 건으로 하향 수정되어 노동시장 둔화가 확인됨. 금일 실행 시각 이후 주요 발표 예정 지표는 부재함.",
                "source_news_ids": [],
                "source_market_fields": [],
                "source_event_ids": ["EV_001"]
            }
        }

        _, val_summary = FactValidator.validate_and_enrich(content, context)
        self.assertTrue(val_summary["passed"], f"Validation failed with errors: {val_summary.get('errors')}")

    def test_7_fact_validator_detects_tense_mismatch(self):
        context = {
            "report_date": "2026-09-04",
            "run_time_kst": "2026-09-04 22:00:00 KST",
            "as_of": "22:00 KST 기준",
            "market_data": {"fx": [], "bonds": [], "commodities": [], "equities": [], "spreads": []},
            "verified_macro_news": [],
            "economic_calendar": {
                "day_review": [
                    {
                        "event_id": "EV_001",
                        "country": "US",
                        "event_name": "Non-Farm Employment Change",
                        "event_name_kor": "미국 비농업 고용지수",
                        "scheduled_at": "2026-09-04 21:30:00 KST",
                        "scheduled_time_kst": "21:30",
                        "importance": "HIGH",
                        "forecast": "165K",
                        "actual": "22K"
                    }
                ],
                "today_night": []
            }
        }

        # Faulty content: Describing already-released NFP as upcoming ("발표를 앞두고")
        faulty_content = {
            "ficc_daily_summary": {"bullets": ["요약1", "요약2", "요약3"], "source_news_ids": [], "source_market_fields": [], "source_event_ids": []},
            "ficc_summary": {"text": "종합 요약", "source_news_ids": [], "source_market_fields": [], "source_event_ids": []},
            "issue_review": {
                "stock": {"text": "증시", "source_news_ids": [], "source_market_fields": [], "source_event_ids": []},
                "fx": {"text": "외환", "source_news_ids": [], "source_market_fields": [], "source_event_ids": []},
                "bond": {"text": "채권", "source_news_ids": [], "source_market_fields": [], "source_event_ids": []},
                "commodity": {"text": "원자재", "source_news_ids": [], "source_market_fields": [], "source_event_ids": []}
            },
            "ficc_forecast": {"text": "전망"},
            "daily_event_watchpoints": {
                "text": "미국 비농업 고용지수 발표를 앞두고 시장의 관망세가 짙게 형성됨.",
                "source_news_ids": [],
                "source_market_fields": [],
                "source_event_ids": ["EV_001"]
            }
        }

        _, val_summary = FactValidator.validate_and_enrich(faulty_content, context)
        self.assertFalse(val_summary["passed"])
        errors_str = " ".join(val_summary["errors"])
        self.assertIn("시제 왜곡(tense mismatch)", errors_str)

    def test_8_fact_validator_detects_fake_actual(self):
        context = {
            "report_date": "2026-09-04",
            "run_time_kst": "2026-09-04 16:30:00 KST",
            "as_of": "16:30 KST 기준",
            "market_data": {"fx": [], "bonds": [], "commodities": [], "equities": [], "spreads": []},
            "verified_macro_news": [],
            "economic_calendar": {
                "day_review": [
                    {
                        "event_id": "EV_002",
                        "country": "US",
                        "event_name": "Non-Farm Employment Change",
                        "event_name_kor": "미국 비농업 고용지수",
                        "scheduled_at": "2026-09-04 21:30:00 KST",
                        "scheduled_time_kst": "21:30",
                        "importance": "HIGH",
                        "forecast": "165K",
                        "actual": None  # Not released yet!
                    }
                ],
                "today_night": []
            }
        }

        # Faulty content: actual is None in SSOT, but text invents a fake actual (160K)
        faulty_content = {
            "ficc_daily_summary": {"bullets": ["요약1", "요약2", "요약3"], "source_news_ids": [], "source_market_fields": [], "source_event_ids": []},
            "ficc_summary": {"text": "종합 요약", "source_news_ids": [], "source_market_fields": [], "source_event_ids": []},
            "issue_review": {
                "stock": {"text": "증시", "source_news_ids": [], "source_market_fields": [], "source_event_ids": []},
                "fx": {"text": "외환", "source_news_ids": [], "source_market_fields": [], "source_event_ids": []},
                "bond": {"text": "채권", "source_news_ids": [], "source_market_fields": [], "source_event_ids": []},
                "commodity": {"text": "원자재", "source_news_ids": [], "source_market_fields": [], "source_event_ids": []}
            },
            "ficc_forecast": {"text": "전망"},
            "daily_event_watchpoints": {
                "text": "미국 비농업 고용지수 실제치는 160K로 발표됨.",
                "source_news_ids": [],
                "source_market_fields": [],
                "source_event_ids": ["EV_002"]
            }
        }

        _, val_summary = FactValidator.validate_and_enrich(faulty_content, context)
        self.assertFalse(val_summary["passed"])
        errors_str = " ".join(val_summary["errors"])
        self.assertTrue("가상 actual 날조 오류" in errors_str or "unverified" in errors_str.lower() or "수치" in errors_str)

    # -------------------------------------------------------------
    # 14 Detailed Requirements Test Cases
    # -------------------------------------------------------------
    def test_reference_period_exact_match(self):
        """1. test_reference_period_exact_match: 이벤트의 대상월(2026-M08)과 BLS 2026-M08 관측치가 정확히 매칭되어 actual 주입"""
        adapter = BlsActualsAdapter()
        mock_data = {
            "series_data": {
                "CES0000000001": {
                    (2026, "M08"): 159200.0,
                    (2026, "M07"): 159038.0,
                    (2026, "M06"): 159017.0
                }
            }
        }
        with patch.object(adapter, "fetch_bls_labor_data", return_value=mock_data):
            events = [
                {
                    "country": "US",
                    "event_name": "Non-Farm Employment Change (Aug)",
                    "scheduled_dt_kst": datetime(2026, 9, 4, 21, 30, tzinfo=KST_TZ),
                    "scheduled_at_kst": "2026-09-04 21:30:00 KST",
                    "prior": "89K",
                    "forecast": "55K",
                    "actual": None
                }
            ]
            run_time_kst = datetime(2026, 9, 4, 22, 0, tzinfo=KST_TZ)
            adapter.enrich_events(events, run_time_kst)

            ev = events[0]
            self.assertEqual(ev["actual"], "+162K")
            self.assertEqual(ev["reference_period"], "2026-M08")
            self.assertEqual(ev["freshness_status"], "RELEASED_WITH_ACTUAL")

    def test_stale_bls_data_rejection(self):
        """2. test_stale_bls_data_rejection: 8월 이벤트에 대해 BLS API가 7월 데이터까지만 가진 경우 stale 매핑 차단 (actual = None, PENDING_ACTUAL)"""
        adapter = BlsActualsAdapter()
        # BLS only has data up to M07, M08 is missing
        mock_data = {
            "series_data": {
                "CES0000000001": {
                    (2026, "M07"): 159038.0,
                    (2026, "M06"): 159017.0
                }
            }
        }
        with patch.object(adapter, "fetch_bls_labor_data", return_value=mock_data):
            events = [
                {
                    "country": "US",
                    "event_name": "Non-Farm Employment Change (Aug)",
                    "scheduled_dt_kst": datetime(2026, 9, 4, 21, 30, tzinfo=KST_TZ),
                    "scheduled_at_kst": "2026-09-04 21:30:00 KST",
                    "prior": "89K",
                    "forecast": "55K",
                    "actual": None
                }
            ]
            run_time_kst = datetime(2026, 9, 4, 22, 0, tzinfo=KST_TZ)
            adapter.enrich_events(events, run_time_kst)

            ev = events[0]
            self.assertIsNone(ev["actual"])
            self.assertEqual(ev["freshness_status"], "PENDING_ACTUAL")

    def test_explicit_month_in_title(self):
        """3. test_explicit_month_in_title: 이벤트 제목의 (Aug), (Jul), 한글 8월 등 명시적 월 표기 우선 추출"""
        ev1 = {"event_name": "(Aug) Nonfarm Payrolls", "scheduled_dt_kst": datetime(2026, 9, 4, 21, 30, tzinfo=KST_TZ)}
        self.assertEqual(extract_event_reference_period(ev1), (2026, "M08"))

        ev2 = {"event_name": "미국 8월 비농업 고용지수", "scheduled_dt_kst": datetime(2026, 9, 4, 21, 30, tzinfo=KST_TZ)}
        self.assertEqual(extract_event_reference_period(ev2), (2026, "M08"))

        ev3 = {"event_name": "Nonfarm Payrolls (Jul)", "scheduled_dt_kst": datetime(2026, 9, 4, 21, 30, tzinfo=KST_TZ)}
        self.assertEqual(extract_event_reference_period(ev3), (2026, "M07"))

    def test_january_cross_year_period(self):
        """4. test_january_cross_year_period: 1월 발표 고용보고서의 전년도 12월 매핑 및 연속 직전월 연도 경계 지원"""
        ev_jan = {"event_name": "Non-Farm Employment Change", "scheduled_dt_kst": datetime(2026, 1, 9, 22, 30, tzinfo=KST_TZ)}
        self.assertEqual(extract_event_reference_period(ev_jan), (2025, "M12"))

        # get_consecutive_prior_period check
        self.assertEqual(get_consecutive_prior_period(2026, "M01"), (2025, "M12"))
        self.assertEqual(get_consecutive_prior_period(2026, "M02"), (2026, "M01"))

    def test_revised_prior_consecutive_month_validation(self):
        """5. test_revised_prior_consecutive_month_validation: 직전 연속월(M-1)의 수정 여부를 검증하고 기존 prior와 다를 때만 is_revised_prior=True"""
        adapter = BlsActualsAdapter()
        mock_data = {
            "series_data": {
                "CES0000000001": {
                    (2026, "M08"): 159200.0,
                    (2026, "M07"): 159038.0,
                    (2026, "M06"): 159017.0  # M07 change = 159038 - 159017 = +21K
                }
            }
        }
        with patch.object(adapter, "fetch_bls_labor_data", return_value=mock_data):
            # Case A: Calendar prior is 89K (differs from revised 21K) -> is_revised_prior = True
            ev_a = {
                "country": "US",
                "event_name": "Non-Farm Employment Change (Aug)",
                "scheduled_dt_kst": datetime(2026, 9, 4, 21, 30, tzinfo=KST_TZ),
                "prior": "89K",
                "actual": None
            }
            adapter.enrich_events([ev_a], datetime(2026, 9, 4, 22, 0, tzinfo=KST_TZ))
            self.assertTrue(ev_a["is_revised_prior"])
            self.assertEqual(ev_a["prior"], "+21K")

            # Case B: Calendar prior is already +21K (not modified) -> is_revised_prior = False
            ev_b = {
                "country": "US",
                "event_name": "Non-Farm Employment Change (Aug)",
                "scheduled_dt_kst": datetime(2026, 9, 4, 21, 30, tzinfo=KST_TZ),
                "prior": "+21K",
                "actual": None
            }
            adapter.enrich_events([ev_b], datetime(2026, 9, 4, 22, 0, tzinfo=KST_TZ))
            self.assertFalse(ev_b["is_revised_prior"])

    def test_release_date_mismatch_rejection(self):
        """6. test_release_date_mismatch_rejection: 대상월보다 앞서 발표되도록 잘못 지정된 릴리스 일자는 정합성 위반으로 차단"""
        # 8월 고용보고서인데 일정이 8월 1일로 잡힌 경우 (대상월 종료 전 발표 불가)
        dt_invalid = datetime(2026, 8, 1, 21, 30, tzinfo=KST_TZ)
        self.assertFalse(validate_release_date_consistency(dt_invalid, 2026, "M08"))

        # 정상적인 9월 4일 발표
        dt_valid = datetime(2026, 9, 4, 21, 30, tzinfo=KST_TZ)
        self.assertTrue(validate_release_date_consistency(dt_valid, 2026, "M08"))

    def test_past_event_with_actual(self):
        """7. test_past_event_with_actual: 과거 이벤트 + SSOT에 actual 존재 -> blog_formatter에 actual 정상 렌더링"""
        report_data = {
            "report_date": "2026-09-04",
            "run_time_kst": "2026-09-04 22:00:00 KST",
            "final_passed": True,
            "content": {
                "ficc_daily_summary": {"bullets": ["요약1", "요약2", "요약3"]},
                "ficc_summary": {"text": "요약"},
                "issue_review": {"stock": {"text": "증시"}, "fx": {"text": "외환"}, "bond": {"text": "채권"}, "commodity": {"text": "원자재"}},
                "ficc_forecast": {"text": "전망"},
                "daily_event_watchpoints": {"text": "이벤트 리뷰"}
            }
        }
        processed = {
            "run_time_kst": "2026-09-04 22:00:00 KST",
            "market_data": {"categories": {}, "spreads": []},
            "economic_events": {
                "day_review_events": [
                    {"event_name": "Non-Farm Employment Change", "country": "US", "actual": "+162K", "forecast": "55K", "prior": "+21K", "is_revised_prior": True}
                ],
                "today_night_events": []
            }
        }
        html = NaverBlogFormatter.format_blog_html(report_data, processed)
        self.assertIn("+162K", html)
        self.assertIn("+21K (수정)", html)

    def test_past_event_without_actual(self):
        """8. test_past_event_without_actual: 과거 이벤트 + actual 없음 -> 임의값 생성하지 않고 '-' 처리"""
        report_data = {
            "report_date": "2026-09-04",
            "run_time_kst": "2026-09-04 22:00:00 KST",
            "final_passed": True,
            "content": {
                "ficc_daily_summary": {"bullets": ["요약1", "요약2", "요약3"]},
                "ficc_summary": {"text": "요약"},
                "issue_review": {"stock": {"text": "증시"}, "fx": {"text": "외환"}, "bond": {"text": "채권"}, "commodity": {"text": "원자재"}},
                "ficc_forecast": {"text": "전망"},
                "daily_event_watchpoints": {"text": "이벤트 리뷰"}
            }
        }
        processed = {
            "run_time_kst": "2026-09-04 22:00:00 KST",
            "market_data": {"categories": {}, "spreads": []},
            "economic_events": {
                "day_review_events": [
                    {"event_name": "German Industrial Production", "country": "EU", "actual": None, "forecast": "0.5%", "prior": "-0.1%"}
                ],
                "today_night_events": []
            }
        }
        text = NaverBlogFormatter.format_blog_text(report_data, processed)
        self.assertIn("-", text)

    def test_future_event_no_actual(self):
        """9. test_future_event_no_actual: 미래 이벤트는 actual 연결 금지 (None 강제)"""
        adapter = BlsActualsAdapter()
        events = [
            {
                "country": "US",
                "event_name": "Non-Farm Employment Change (Aug)",
                "scheduled_dt_kst": datetime(2026, 9, 4, 21, 30, tzinfo=KST_TZ),
                "actual": "162K"  # erroneously populated beforehand
            }
        ]
        # Run at 21:00 KST (before 21:30 release)
        run_time_kst = datetime(2026, 9, 4, 21, 0, tzinfo=KST_TZ)
        adapter.enrich_events(events, run_time_kst)
        self.assertIsNone(events[0]["actual"])
        self.assertEqual(events[0]["freshness_status"], "UPCOMING")

    def test_run_time_2301_nfp_released(self):
        """10. test_run_time_2301_nfp_released: 23:01 실행 기준 21:30 NFP는 발표 완료 이벤트로 처리되어 actual, revised prior 주입"""
        adapter = BlsActualsAdapter()
        mock_data = {
            "series_data": {
                "CES0000000001": {
                    (2026, "M08"): 159200.0,
                    (2026, "M07"): 159038.0,
                    (2026, "M06"): 159017.0
                },
                "LNS14000000": {
                    (2026, "M08"): 4.1
                }
            }
        }
        with patch.object(adapter, "fetch_bls_labor_data", return_value=mock_data):
            events = [
                {
                    "country": "US",
                    "event_name": "Non-Farm Employment Change",
                    "scheduled_dt_kst": datetime(2026, 9, 4, 21, 30, tzinfo=KST_TZ),
                    "scheduled_at_kst": "2026-09-04 21:30:00 KST",
                    "prior": "89K",
                    "forecast": "55K",
                    "actual": None
                },
                {
                    "country": "US",
                    "event_name": "Unemployment Rate",
                    "scheduled_dt_kst": datetime(2026, 9, 4, 21, 30, tzinfo=KST_TZ),
                    "scheduled_at_kst": "2026-09-04 21:30:00 KST",
                    "prior": "4.3%",
                    "forecast": "4.2%",
                    "actual": None
                }
            ]
            run_time_kst = datetime(2026, 9, 4, 23, 1, tzinfo=KST_TZ)
            adapter.enrich_events(events, run_time_kst)

            nfp = events[0]
            unemp = events[1]
            self.assertEqual(nfp["actual"], "+162K")
            self.assertEqual(nfp["prior"], "+21K")
            self.assertTrue(nfp["is_revised_prior"])
            self.assertEqual(unemp["actual"], "4.1%")

    def test_equity_price_type_distinction(self):
        """11. test_equity_price_type_distinction: 국내 종가와 미국 장중 현재가 구분 및 FactValidator의 장중 미국 지수 '마감' 오표기 검출"""
        context = {
            "report_date": "2026-09-04",
            "market_data": {
                "equities": [
                    {"name": "코스피", "field_id": "EQUITY.^KS11", "current": 2600.0, "market_status": "CLOSED", "price_type": "종가"},
                    {"name": "S&P 500", "field_id": "EQUITY.^GSPC", "current": 5500.0, "market_status": "INTRADAY", "price_type": "현재가 (장중)"}
                ]
            },
            "economic_calendar": {"day_review": [], "today_night": []},
            "verified_macro_news": []
        }
        # Faulty content: S&P 500 described as closed
        faulty_content = {
            "ficc_daily_summary": {"bullets": ["요약1", "요약2", "요약3"]},
            "ficc_summary": {"text": "미국 증시는 상승 마감함."},
            "issue_review": {"stock": {"text": "S&P 500은 상승 마감함."}}
        }
        _, summary = FactValidator.validate_and_enrich(faulty_content, context)
        self.assertFalse(summary["passed"])
        self.assertTrue(any("미국 장중 지수 세션 왜곡" in e for e in summary["errors"]))

    def test_usd_krw_session_distinction(self):
        """12. test_usd_krw_session_distinction: USD/KRW 야간 장외 현재환율을 서울시장 '하락 마감'으로 오표기 시 FactValidator 검출"""
        context = {
            "report_date": "2026-09-04",
            "market_data": {
                "fx": [
                    {"name": "원/달러 환율 (USD/KRW)", "field_id": "FX.KRW=X", "current": 1347.38, "market_status": "INTRADAY", "price_type": "장외/글로벌 현재환율"}
                ]
            },
            "economic_calendar": {"day_review": [], "today_night": []},
            "verified_macro_news": []
        }
        # Faulty content: stating USD/KRW closed down
        faulty_content = {
            "ficc_daily_summary": {"bullets": ["요약1", "요약2", "요약3"]},
            "ficc_summary": {"text": "원/달러 환율은 1,347.38원으로 하락 마감함."}
        }
        _, summary = FactValidator.validate_and_enrich(faulty_content, context)
        self.assertFalse(summary["passed"])
        self.assertTrue(any("USD/KRW 장외 현재환율 세션 왜곡" in e for e in summary["errors"]))

    def test_fact_validator_stale_event_detection(self):
        """13. test_fact_validator_stale_event_detection: 이벤트 대상월과 BLS 관측기간이 불일치할 때 FactValidator 검출"""
        context = {
            "report_date": "2026-09-04",
            "market_data": {"fx": [], "bonds": [], "commodities": [], "equities": []},
            "economic_calendar": {
                "day_review": [
                    {
                        "event_name": "Non-Farm Employment Change",
                        "reference_period": "2026-M08",
                        "actual_source": "BLS API (CES0000000001, 2026-M07)",  # Stale mismatch!
                        "actual": "+22K"
                    }
                ],
                "today_night": []
            },
            "verified_macro_news": []
        }
        content = {
            "ficc_daily_summary": {"bullets": ["요약1", "요약2", "요약3"]},
            "ficc_summary": {"text": "요약"}
        }
        _, summary = FactValidator.validate_and_enrich(content, context)
        self.assertFalse(summary["passed"])
        self.assertTrue(any("이벤트 대상월(2026-M08)과 BLS 관측기간(2026-M07) 불일치" in e for e in summary["errors"]))

    def test_intraday_commodity_price_type(self):
        """14. test_intraday_commodity_price_type: 원자재 장중 선물 가격을 종가처럼 '하락 마감'으로 오표기 시 FactValidator 검출"""
        context = {
            "report_date": "2026-09-04",
            "market_data": {
                "commodities": [
                    {"name": "WTI 원유", "field_id": "COMMODITY.CL=F", "current": 89.5, "market_status": "INTRADAY", "price_type": "현재가 (장중)"}
                ]
            },
            "economic_calendar": {"day_review": [], "today_night": []},
            "verified_macro_news": []
        }
        faulty_content = {
            "ficc_daily_summary": {"bullets": ["요약1", "요약2", "요약3"]},
            "ficc_summary": {"text": "국제유가는 수요 둔화 우려에 하락 마감함."}
        }
        _, summary = FactValidator.validate_and_enrich(faulty_content, context)
        self.assertFalse(summary["passed"])
        self.assertTrue(any("원자재 장중 선물 세션 왜곡" in e for e in summary["errors"]))


    def test_usd_krw_boundary_times(self):
        """15. USD/KRW 세션 경계조건(00:00, 00:31, 08:59, 09:00, 15:29, 15:30, 16:00, 23:59) price_type 검증"""
        collector = FxCollector()
        boundary_cases = [
            (datetime(2026, 9, 5, 0, 0, tzinfo=KST_TZ), "장외/글로벌 현재환율"),
            (datetime(2026, 9, 5, 0, 31, tzinfo=KST_TZ), "장외/글로벌 현재환율"),
            (datetime(2026, 9, 5, 8, 59, tzinfo=KST_TZ), "장외/글로벌 현재환율"),
            (datetime(2026, 9, 5, 9, 0, tzinfo=KST_TZ), "서울 외환시장 현재환율"),
            (datetime(2026, 9, 5, 15, 29, tzinfo=KST_TZ), "서울 외환시장 현재환율"),
            (datetime(2026, 9, 5, 15, 30, tzinfo=KST_TZ), "장외/글로벌 현재환율"),
            (datetime(2026, 9, 5, 16, 0, tzinfo=KST_TZ), "장외/글로벌 현재환율"),
            (datetime(2026, 9, 5, 23, 59, tzinfo=KST_TZ), "장외/글로벌 현재환율"),
        ]

        import pandas as pd
        mock_hist = pd.DataFrame({"Close": [1340.0, 1345.0]}, index=[pd.Timestamp("2026-09-03"), pd.Timestamp("2026-09-04")])

        with patch("yfinance.Ticker") as mock_ticker:
            instance = MagicMock()
            instance.history.return_value = mock_hist
            mock_ticker.return_value = instance

            for dt_test, expected_pt in boundary_cases:
                records = collector.collect(dt_test, is_post_1630=True)
                krw_record = next(r for r in records if r["symbol"] == "KRW=X")
                self.assertEqual(
                    krw_record["price_type"], expected_pt,
                    f"At {dt_test.strftime('%H:%M')}, expected {expected_pt} but got {krw_record['price_type']}"
                )

    def test_past_event_no_actual_forbids_pending_release(self):
        """16. 과거 이벤트 + actual 부재 시 '발표 대기' 표현 사용 금지 및 FactValidator 검출"""
        context = {
            "report_date": "2026-09-05",
            "run_time_kst": "2026-09-05 00:31:00 KST",
            "market_data": {"fx": [], "bonds": [], "commodities": [], "equities": []},
            "economic_calendar": {
                "day_review": [
                    {
                        "event_name": "Employment Change",
                        "country": "CA",
                        "scheduled_time_kst": "21:30",
                        "actual": None,
                        "forecast": "15.1K",
                        "prior": "75.1K"
                    }
                ],
                "today_night": []
            },
            "verified_macro_news": []
        }
        # Faulty content using '발표 대기' for past event
        faulty_content = {
            "ficc_daily_summary": {"bullets": ["요약1", "요약2", "요약3"]},
            "ficc_summary": {"text": "요약"},
            "daily_event_watchpoints": {
                "text": "캐나다 8월 고용 변동 및 실업률 지표는 발표 대기 흐름을 나타냄."
            }
        }
        _, summary = FactValidator.validate_and_enrich(faulty_content, context)
        self.assertFalse(summary["passed"])
        self.assertTrue(any("발표 대기" in e for e in summary["errors"]))

    def test_past_event_no_actual_allows_unconfirmed(self):
        """17. 과거 이벤트 + actual 부재 시 '공식 수치 미확인' 또는 '실제치 확인 필요' 허용"""
        context = {
            "report_date": "2026-09-05",
            "run_time_kst": "2026-09-05 00:31:00 KST",
            "market_data": {"fx": [], "bonds": [], "commodities": [], "equities": []},
            "economic_calendar": {
                "day_review": [
                    {
                        "event_name": "Employment Change",
                        "country": "CA",
                        "scheduled_time_kst": "21:30",
                        "actual": None,
                        "forecast": "15.1K",
                        "prior": "75.1K"
                    }
                ],
                "today_night": []
            },
            "verified_macro_news": []
        }
        valid_content = {
            "ficc_daily_summary": {"bullets": ["요약1", "요약2", "요약3"]},
            "ficc_summary": {"text": "요약"},
            "daily_event_watchpoints": {
                "text": "캐나다 8월 고용 변동 지표는 공식 수치 미확인 상태로 실제치 확인이 필요함."
            }
        }
        _, summary = FactValidator.validate_and_enrich(valid_content, context)
        self.assertTrue(summary["passed"], f"Validation failed: {summary.get('errors')}")

    def test_future_event_allows_scheduled_expression(self):
        """18. 미래 예정 이벤트에 대해 '발표 예정' 표현 허용"""
        context = {
            "report_date": "2026-09-05",
            "run_time_kst": "2026-09-05 00:31:00 KST",
            "market_data": {"fx": [], "bonds": [], "commodities": [], "equities": []},
            "economic_calendar": {
                "day_review": [],
                "today_night": [
                    {
                        "event_name": "FOMC Member Goolsbee Speaks",
                        "country": "US",
                        "scheduled_time_kst": "07:00",
                        "forecast": None,
                        "actual": None
                    }
                ]
            },
            "verified_macro_news": []
        }
        valid_content = {
            "ficc_daily_summary": {"bullets": ["요약1", "요약2", "요약3"]},
            "ficc_summary": {"text": "요약"},
            "daily_event_watchpoints": {
                "text": "익일 07:00 예정된 미국 FOMC 굴스비 위원 발언을 통해 연준 통화정책 기조를 점검할 예정임."
            }
        }
        _, summary = FactValidator.validate_and_enrich(valid_content, context)
        self.assertTrue(summary["passed"], f"Validation failed: {summary.get('errors')}")

if __name__ == "__main__":
    unittest.main()
