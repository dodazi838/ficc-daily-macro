"""
[Tests] US Market Holiday, Past Event Tense, and Unsupported Causality Tests
=============================================================================
- TEST 1: 미국 공휴일(노동절 등) 및 국채시장 휴장일 판정 로직 검증
- TEST 2: Collector 수집 결과의 US equity / Treasury price_type 및 market_status 검증 (PREVIOUS_CLOSE / CLOSED)
- TEST 3: FactValidator에서 미국 증시/국채 휴장 중 '장중 약세' 및 '당일 금리 상승' 적발 검증
- TEST 4: FactValidator에서 과거 발표 이벤트의 '발표 대기', '대기 흐름', '예정' 적발 및 '공식 수치 미확인' 허용 검증
- TEST 5: FactValidator에서 SSOT 미근거 변수 및 수급 인과관계 날조 적발 검증
"""

import datetime
import pytz
import unittest
from config.holidays import is_us_equity_holiday, is_us_bond_holiday
from collectors.equity import EquityCollector
from collectors.bond import BondCollector
from processors.fact_validator import FactValidator
from generators.context_builder import AIContextBuilder

class TestHolidayTenseCausality(unittest.TestCase):

    def setUp(self):
        self.kst = pytz.timezone("Asia/Seoul")
        self.labor_day_dt = self.kst.localize(datetime.datetime(2026, 9, 7, 22, 50, 35))

        self.mock_proc_data = {
            "report_date": "2026-09-07",
            "run_time_kst": "2026-09-07 22:50:35 KST",
            "as_of": "22:50 기준",
            "market_data": {
                "categories": {
                    "EQUITY": [
                        {
                            "category": "EQUITY",
                            "name": "S&P 500",
                            "symbol": "^GSPC",
                            "current": 7718.60,
                            "prev": 7747.71,
                            "pct_change": -0.38,
                            "unit": "pt",
                            "actual_as_of_kst": "2026-09-05 (미국 휴장: Labor Day)",
                            "price_type": "PREVIOUS_CLOSE",
                            "market_status": "CLOSED",
                            "session_type": "미국 증시 휴장 (Labor Day) 직전 종가",
                            "is_holiday": True,
                            "holiday_name": "Labor Day"
                        }
                    ],
                    "BOND": [
                        {
                            "category": "BOND",
                            "name": "미국 국채 10년",
                            "symbol": "US10Y",
                            "current": 4.78,
                            "prev": 4.758,
                            "bp_change": 2.2,
                            "unit": "%",
                            "actual_as_of_kst": "2026-09-05 (미국 휴장: Labor Day)",
                            "price_type": "PREVIOUS_CLOSE",
                            "market_status": "CLOSED",
                            "session_type": "미국 국채시장 휴장 (Labor Day) 직전 종가",
                            "is_holiday": True,
                            "holiday_name": "Labor Day"
                        }
                    ],
                    "FX": [],
                    "COMMODITY": []
                },
                "spreads": []
            },
            "news_events": {"event_clusters": []},
            "economic_events": {
                "day_review_events": [
                    {
                        "event_id": "EVT_20260907_JPY_001",
                        "country": "JP",
                        "event_name": "Leading Indicators",
                        "scheduled_at_kst": "2026-09-07 14:00:00 KST",
                        "actual": None,
                        "forecast": "117.9%",
                        "prior": "116.4%"
                    },
                    {
                        "event_id": "EVT_20260907_EUR_002",
                        "country": "EU",
                        "event_name": "German Industrial Production m/m",
                        "scheduled_at_kst": "2026-09-07 15:00:00 KST",
                        "actual": None,
                        "forecast": "0.1%",
                        "prior": "0.2%"
                    },
                    {
                        "event_id": "EVT_20260907_EUR_003",
                        "country": "EU",
                        "event_name": "Final Employment Change q/q",
                        "scheduled_at_kst": "2026-09-07 18:00:00 KST",
                        "actual": None,
                        "forecast": "0.1%",
                        "prior": "0.1%"
                    },
                    {
                        "event_id": "EVT_20260907_EUR_004",
                        "country": "EU",
                        "event_name": "Revised GDP q/q",
                        "scheduled_at_kst": "2026-09-07 18:00:00 KST",
                        "actual": None,
                        "forecast": "0.4%",
                        "prior": "0.4%"
                    }
                ],
                "today_night_events": []
            }
        }
        self.context = AIContextBuilder.build_context(self.mock_proc_data)

    def test_1_us_holiday_detection(self):
        """TEST 1: 미국 공휴일(노동절 등) 및 국채시장 휴장일 판정 로직 검증"""
        # 2026-09-07은 9월 첫째주 월요일 = Labor Day
        is_eq_hol, eq_name = is_us_equity_holiday(datetime.date(2026, 9, 7))
        self.assertTrue(is_eq_hol)
        self.assertEqual(eq_name, "Labor Day")

        is_bd_hol, bd_name = is_us_bond_holiday(datetime.date(2026, 9, 7))
        self.assertTrue(is_bd_hol)
        self.assertEqual(bd_name, "Labor Day")

        # 2026-09-08 화요일 = 정상 거래일
        is_eq_norm, _ = is_us_equity_holiday(datetime.date(2026, 9, 8))
        self.assertFalse(is_eq_norm)

    def test_2_collector_holiday_attributes(self):
        """TEST 2: Collector 수집 결과의 US equity / Treasury price_type 및 market_status 검증"""
        eq_items = EquityCollector().collect(self.labor_day_dt, is_post_1630=True)
        us_eq = [x for x in eq_items if x.get("symbol") in ["^GSPC", "^DJI", "^IXIC", "^VIX"]]
        self.assertTrue(len(us_eq) >= 3)
        for item in us_eq:
            self.assertIn(item.get("market_status"), ["CLOSED", "MARKET_CLOSED"])
            self.assertEqual(item.get("price_type"), "PREVIOUS_CLOSE")
            self.assertEqual(item.get("return_basis"), "PREVIOUS_TRADING_DAY")
            self.assertTrue(item.get("is_holiday"))
            self.assertEqual(item.get("holiday_name"), "Labor Day")
            self.assertIn("휴장", item.get("session_type"))

        bond_items = BondCollector().collect(self.labor_day_dt, is_post_1630=True)
        us_bonds = [x for x in bond_items if "미국" in x.get("name", "")]
        self.assertTrue(len(us_bonds) >= 2)
        for item in us_bonds:
            self.assertIn(item.get("market_status"), ["CLOSED", "MARKET_CLOSED"])
            self.assertEqual(item.get("price_type"), "PREVIOUS_CLOSE")
            self.assertEqual(item.get("return_basis"), "PREVIOUS_TRADING_DAY")
            self.assertTrue(item.get("is_holiday"))
            self.assertEqual(item.get("holiday_name"), "Labor Day")
            self.assertIn("휴장", item.get("session_type"))

        # 범용 스키마 검증: 비휴장 자산(한국 주식/채권 등)도 동일한 필드 구조를 공유함
        kr_eq = [x for x in eq_items if "KOSPI" in x.get("symbol", "") or "코스피" in x.get("name", "")]
        for item in kr_eq:
            self.assertIn("market_status", item)
            self.assertIn("price_type", item)
            self.assertIn("session_type", item)
            self.assertIn("is_holiday", item)
            self.assertFalse(item.get("is_holiday"))
            self.assertIn("holiday_name", item)
            self.assertIn("return_basis", item)

        kr_bonds = [x for x in bond_items if "국고채" in x.get("name", "")]
        for item in kr_bonds:
            self.assertIn("market_status", item)
            self.assertIn("price_type", item)
            self.assertIn("session_type", item)
            self.assertIn("is_holiday", item)
            self.assertFalse(item.get("is_holiday"))
            self.assertIn("holiday_name", item)
            self.assertIn("return_basis", item)

    def test_3_fact_validator_catches_holiday_trading_assertions(self):
        """TEST 3: FactValidator에서 미국 증시/국채 휴장 중 '장중 약세' 및 '당일 금리 상승' 적발 검증"""
        bad_stock_text = "미국 주요 지수는 금리 부담 속에 다우와 S&P500이 장중 약세를 나타냄."
        errors = FactValidator._validate_market_session_representation("issue_review_stock", bad_stock_text, self.context)
        self.assertTrue(any("미국 증시 휴장" in e for e in errors), f"Expected holiday error, got: {errors}")

        bad_bond_text = "미국 국채 금리 역시 10년물이 4.78%대로 오름세를 유지하며 상승 압력을 받음."
        b_errors = FactValidator._validate_market_session_representation("issue_review_bond", bad_bond_text, self.context)
        self.assertTrue(any("미국 국채시장 휴장" in e for e in b_errors), f"Expected holiday error, got: {b_errors}")

        # 정당한 휴장 표현은 통과해야 함
        good_stock_text = "미국 증시가 노동절로 휴장한 가운데 직전 거래일 종가 기준 소폭 하락세가 유지됨."
        good_errors = FactValidator._validate_market_session_representation("issue_review_stock", good_stock_text, self.context)
        self.assertEqual(len(good_errors), 0)

    def test_4_1_past_event_pending_fails(self):
        """TEST 4-1: past event + '발표 대기' → FAIL"""
        past_context = dict(self.context)
        past_context["economic_calendar"] = {
            "day_review": [
                {
                    "event_id": "EVT_20260907_JP_001",
                    "country": "JP",
                    "event_name": "Leading Indicators",
                    "event_name_kor": "일본 선행지수",
                    "scheduled_at": "2026-09-07 14:00:00 KST",
                    "scheduled_time_kst": "14:00",
                    "forecast": "117.9%",
                    "prior": "116.4%",
                    "actual": None,
                    "freshness_status": "PENDING_ACTUAL"
                },
                {
                    "event_id": "EVT_20260907_EU_002",
                    "country": "EU",
                    "event_name": "German Industrial Production m/m",
                    "event_name_kor": "독일 산업생산",
                    "scheduled_at": "2026-09-07 15:00:00 KST",
                    "scheduled_time_kst": "15:00",
                    "forecast": "0.1%",
                    "prior": "0.2%",
                    "actual": None,
                    "freshness_status": "PENDING_ACTUAL"
                }
            ],
            "today_night": []
        }
        bad_event_text = (
            "당일 발표 일정 중 일본 선행지수와 유로존 8월 독일 산업생산은 발표 대기 흐름을 보였음. "
            "금일 실행 시각 이후 주요 발표 예정 지표는 부재함."
        )
        errors = FactValidator._validate_daily_event_section(bad_event_text, past_context)
        self.assertTrue(any("시제 왜곡" in e for e in errors), f"Expected tense mismatch error, got: {errors}")

    def test_4_2_past_event_scheduled_fails(self):
        """TEST 4-2: past event + '발표 예정' → FAIL"""
        past_context = dict(self.context)
        past_context["economic_calendar"] = {
            "day_review": [
                {
                    "event_id": "EVT_20260907_JP_001",
                    "country": "JP",
                    "event_name": "Leading Indicators",
                    "event_name_kor": "일본 선행지수",
                    "scheduled_at": "2026-09-07 14:00:00 KST",
                    "scheduled_time_kst": "14:00",
                    "forecast": "117.9%",
                    "prior": "116.4%",
                    "actual": None,
                    "freshness_status": "PENDING_ACTUAL"
                }
            ],
            "today_night": []
        }
        bad_event_text = (
            "당일 발표 일정 중 일본 선행지수는 오늘 14:00에 발표 예정임. "
            "금일 실행 시각 이후 주요 발표 예정 지표는 부재함."
        )
        errors = FactValidator._validate_daily_event_section(bad_event_text, past_context)
        self.assertTrue(any("시제 왜곡" in e for e in errors), f"Expected tense mismatch error, got: {errors}")

    def test_4_3_past_event_unconfirmed_actual_passes(self):
        """TEST 4-3: past event + '공식 수치 미확인' → PASS"""
        past_context = dict(self.context)
        past_context["economic_calendar"] = {
            "day_review": [
                {
                    "event_id": "EVT_20260907_JP_001",
                    "country": "JP",
                    "event_name": "Leading Indicators",
                    "event_name_kor": "일본 선행지수",
                    "scheduled_at": "2026-09-07 14:00:00 KST",
                    "scheduled_time_kst": "14:00",
                    "forecast": "117.9%",
                    "prior": "116.4%",
                    "actual": None,
                    "freshness_status": "PENDING_ACTUAL"
                },
                {
                    "event_id": "EVT_20260907_EU_002",
                    "country": "EU",
                    "event_name": "German Industrial Production m/m",
                    "event_name_kor": "독일 산업생산",
                    "scheduled_at": "2026-09-07 15:00:00 KST",
                    "scheduled_time_kst": "15:00",
                    "forecast": "0.1%",
                    "prior": "0.2%",
                    "actual": None,
                    "freshness_status": "PENDING_ACTUAL"
                }
            ],
            "today_night": []
        }
        good_event_text = (
            "당일 발표 일정 중 일본 선행지수(예상 117.9%, 전월 116.4%)와 독일 산업생산(예상 0.1%, 전월 0.2%)은 공식 수치 확인이 필요한 상태임. "
            "금일 실행 시각 이후 주요 발표 예정 지표는 부재함."
        )
        good_errors = FactValidator._validate_daily_event_section(good_event_text, past_context)
        self.assertEqual(len(good_errors), 0, f"Expected 0 errors for good text, got: {good_errors}")

    def test_4_4_upcoming_event_scheduled_passes(self):
        """TEST 4-4: upcoming event + '발표 예정' → PASS"""
        upcoming_context = dict(self.context)
        upcoming_context["economic_calendar"] = {
            "day_review": [],
            "today_night": [
                {
                    "event_id": "EVT_20260907_USD_999",
                    "country": "US",
                    "event_name": "Consumer Price Index",
                    "event_name_kor": "소비자물가지수",
                    "scheduled_at": "2026-09-07 23:30:00 KST",
                    "scheduled_time_kst": "23:30",
                    "forecast": "0.2%",
                    "prior": "0.2%",
                    "freshness_status": "UPCOMING"
                }
            ]
        }
        valid_upcoming_text = (
            "미국 소비자물가지수(예상 0.2%)는 오늘 밤 23:30에 발표될 예정임."
        )
        errors = FactValidator._validate_daily_event_section(valid_upcoming_text, upcoming_context)
        self.assertEqual(len(errors), 0, f"Expected 0 errors for valid upcoming text, got: {errors}")

    def test_5_fact_validator_catches_unsupported_causality(self):
        """TEST 5: FactValidator에서 SSOT 미근거 변수 및 수급 인과관계 날조 적발 검증"""
        test_cases = [
            ("실질금리 부담이 커지면서 금 가격이 하락함.", "실질금리 부담"),
            ("기술주 전반에 차익실현 매물이 유입되며 주가가 밀림.", "차익실현"),
            ("안전자산 수요와 인플레이션 헤지 심리가 유입되면서 금 가격이 상승함.", "안전자산 수요와 인플레이션 헤지 심리"),
            ("공급 부담이 금리 상승 압력으로 작용함.", "공급 부담"),
            ("국내 증시 급등에 연동되어 원/달러 환율이 하락함.", "미근거 연동 인과관계"),
            ("엔/달러 환율은 7개월 만의 최고치 수준을 기록함.", "기간 최고치 비교"),
            ("원/달러 환율은 올해 들어 가장 높은 수준을 나타냄.", "연중 최고치 비교"),
            ("금 가격은 사상 최고치를 경신함.", "사상 최고치 비교"),
            ("시장에서는 연준의 금리 인하 기대가 약화된 것으로 평가했다.", "시장 평가 단정"),
            ("수요 둔화에 따른 영향으로 판단된다.", "미근거 인과관계 판단"),
            ("미국 금융시장 휴장으로 주요 지표 발표가 제한됨.", "휴장과 지표 발표 인과관계 왜곡")
        ]

        for text, desc in test_cases:
            errors = FactValidator._validate_unsupported_causality("test_sec", text, self.context)
            self.assertTrue(len(errors) > 0, f"Expected error for '{desc}', but passed. Text: {text}")
            self.assertIn("SSOT 미근거", errors[0])

        # 관측된 사실 중심의 정당한 문장은 통과해야 함 (동시 발생 분리 서술)
        clean_text = "원/달러 환율은 1,345원선으로 낮아짐. 같은 시간 국내 증시는 큰 폭으로 상승함."
        clean_errors = FactValidator._validate_unsupported_causality("test_sec", clean_text, self.context)
        self.assertEqual(len(clean_errors), 0, f"Clean text failed with: {clean_errors}")

    def test_6_daily_event_significance_curation(self):
        """TEST 6: Daily Event 중요도 선별 (Tier A/B 유지, Tier C 제외)"""
        from processors.event_processor import MacroEventProcessor
        events = self.mock_proc_data["economic_events"]["day_review_events"]
        curated = MacroEventProcessor.curate_day_review_events(events, "2026-09-07 22:50:35 KST")
        self.assertEqual(len(curated), 0, f"Tier C indicators should be excluded, but got: {curated}")

        mixed_events = list(events) + [
            {
                "event_id": "EVT_US_NFP",
                "country": "US",
                "event_name": "Non-Farm Employment Change",
                "scheduled_at_kst": "2026-09-07 21:30:00 KST",
                "actual": "162K",
                "forecast": "55K",
                "prior": "21K"
            },
            {
                "event_id": "EVT_CA_EMP",
                "country": "CA",
                "event_name": "Employment Change",
                "scheduled_at_kst": "2026-09-07 21:30:00 KST",
                "actual": "-3.8K",
                "forecast": "25.0K",
                "prior": "40.8K"
            }
        ]
        curated_mixed = MacroEventProcessor.curate_day_review_events(mixed_events, "2026-09-07 22:50:35 KST")
        self.assertEqual(len(curated_mixed), 2)
        curated_names = [x["event_name"] for x in curated_mixed]
        self.assertIn("Non-Farm Employment Change", curated_names)
        self.assertIn("Employment Change", curated_names)

    def test_7_country_independent_holiday_resolution(self):
        """TEST 7: 국가별 휴장 판정의 완전한 독립성 검증 (US=휴장, Germany/Japan=정상거래)"""
        bond_items = BondCollector().collect(self.labor_day_dt, is_post_1630=True)

        # 1. 미국 국채 -> 휴장 (MARKET_CLOSED, return_basis=PREVIOUS_TRADING_DAY)
        us_bonds = [x for x in bond_items if "미국" in x.get("name", "")]
        for ub in us_bonds:
            self.assertTrue(ub.get("is_holiday"))
            self.assertEqual(ub.get("market_status"), "MARKET_CLOSED")
            self.assertEqual(ub.get("return_basis"), "PREVIOUS_TRADING_DAY")
            self.assertEqual(ub.get("holiday_name"), "Labor Day")

        # 2. 독일 국채 -> 정상 거래일 (is_holiday=False, holiday_name=None, session_type에 휴장 없음)
        de_bonds = [x for x in bond_items if "독일" in x.get("name", "")]
        self.assertTrue(len(de_bonds) > 0)
        for db in de_bonds:
            self.assertFalse(db.get("is_holiday"), "Germany bond should NOT be marked as holiday")
            self.assertIsNone(db.get("holiday_name"))
            self.assertNotIn("휴장", db.get("session_type", ""))
            self.assertIn(db.get("market_status"), ["INTRADAY", "CLOSED"])
            self.assertNotEqual(db.get("market_status"), "MARKET_CLOSED")

        # 3. 일본 국채 -> 정상 거래일 (is_holiday=False, holiday_name=None)
        jp_bonds = [x for x in bond_items if "일본" in x.get("name", "")]
        self.assertTrue(len(jp_bonds) > 0)
        for jb in jp_bonds:
            self.assertFalse(jb.get("is_holiday"), "Japan bond should NOT be marked as holiday")
            self.assertIsNone(jb.get("holiday_name"))
            self.assertNotIn("휴장", jb.get("session_type", ""))

        # 4. Formatter 렌더링 결과에서 독일 국채가 (휴장)으로 표기되지 않는지 검증
        from generators.blog_formatter import NaverBlogFormatter
        mock_proc = {
            "report_date": "2026-09-07",
            "run_time_kst": "2026-09-07 22:50:35 KST",
            "market_data": {
                "categories": {
                    "EQUITY": [],
                    "FX": [],
                    "BOND": bond_items,
                    "COMMODITY": []
                },
                "spreads": []
            },
            "economic_events": {"day_review_events": []}
        }
        mock_rep = {
            "report_date": "2026-09-07",
            "run_time_kst": "2026-09-07 22:50:35 KST",
            "final_passed": True,
            "content": {"ficc_daily_summary": {"bullets": []}, "ficc_summary": {}, "issue_review": {}, "ficc_forecast": {}, "daily_event_watchpoints": {}}
        }
        rendered_txt = NaverBlogFormatter.format_blog_text(mock_rep, mock_proc)
        self.assertIn("미국 국채 10년 (휴장)", rendered_txt)
        self.assertIn("독일 국채 10년", rendered_txt)
        self.assertNotIn("독일 국채 10년 (휴장)", rendered_txt, "Germany bond should NOT have (휴장) badge in text")

        rendered_html = NaverBlogFormatter.format_blog_html(mock_rep, mock_proc)
        self.assertIn("미국 국채 10년 <span style='font-size: 12px; color: #6c757d; font-weight: normal;'>(휴장)</span>", rendered_html)
        self.assertNotIn("독일 국채 10년 <span style='font-size: 12px; color: #6c757d; font-weight: normal;'>(휴장)</span>", rendered_html)

    def test_8_commodity_unavailable_vs_confirmed(self):
        """TEST 8: 원자재 0.00%의 의미 구분 (change_status=UNAVAILABLE vs CONFIRMED) 및 검증"""
        from collectors.commodity import CommodityCollector
        from generators.blog_formatter import NaverBlogFormatter
        from unittest.mock import MagicMock, patch
        import pandas as pd

        # 1. CommodityCollector에서 휴장일 변동 미발생 시 UNAVAILABLE 처리 로직 검증
        collector = CommodityCollector()
        mock_df = pd.DataFrame(
            {"Close": [91.48, 91.48]},
            index=[pd.Timestamp("2026-09-04", tz="America/New_York"), pd.Timestamp("2026-09-07", tz="America/New_York")]
        )
        with patch("yfinance.Ticker") as mock_ticker:
            instance = MagicMock()
            instance.history.side_effect = lambda period, interval: mock_df if interval == "1d" else pd.DataFrame()
            mock_ticker.return_value = instance

            items = collector.collect(self.labor_day_dt, is_post_1630=True)
            wti = [x for x in items if x.get("symbol") == "CL=F"][0]
            self.assertEqual(wti.get("change_status"), "UNAVAILABLE")
            self.assertIsNone(wti.get("pct_change"))
            self.assertEqual(wti.get("market_status"), "MARKET_CLOSED")
            self.assertEqual(wti.get("return_basis"), "PREVIOUS_TRADING_DAY")

        # 2. Formatter에서 UNAVAILABLE은 '-'로 렌더링되어야 함 (+0.00% 아님)
        mock_proc = {
            "report_date": "2026-09-07",
            "run_time_kst": "2026-09-07 22:50:35 KST",
            "market_data": {
                "categories": {
                    "EQUITY": [], "FX": [], "BOND": [],
                    "COMMODITY": [wti]
                },
                "spreads": []
            },
            "economic_events": {"day_review_events": []}
        }
        mock_rep = {
            "report_date": "2026-09-07",
            "run_time_kst": "2026-09-07 22:50:35 KST",
            "final_passed": True,
            "content": {"ficc_daily_summary": {"bullets": []}, "ficc_summary": {}, "issue_review": {}, "ficc_forecast": {}, "daily_event_watchpoints": {}}
        }
        rendered_txt = NaverBlogFormatter.format_blog_text(mock_rep, mock_proc)
        for line in rendered_txt.splitlines():
            if "WTI" in line:
                self.assertIn("-", line)
                self.assertNotIn("+0.00%", line)

        rendered_html = NaverBlogFormatter.format_blog_html(mock_rep, mock_proc)
        self.assertIn("$91.48", rendered_html)
        self.assertNotIn("+0.00%", rendered_html)

        # 3. FactValidator: UNAVAILABLE 자산에 '0% 변동/보합 마감' 왜곡 시 에러 발생 확인
        comm_context = {
            "market_data": {
                "commodities": [
                    {"name": "WTI", "symbol": "CL=F", "change_status": "UNAVAILABLE", "market_status": "MARKET_CLOSED"}
                ]
            }
        }
        bad_comm_text = "WTI는 0.00% 변동으로 보합세를 기록함."
        c_errors = FactValidator._validate_market_session_representation("issue_review_commodity", bad_comm_text, comm_context)
        self.assertTrue(any("원자재 정산가 미발표 왜곡" in e for e in c_errors), f"Expected UNAVAILABLE commodity error, got: {c_errors}")

    def test_9_data_to_sentence_alignment_and_sector_validation(self):
        """Data-to-Sentence Alignment, 객관적 수식어 기준, price_type 및 뉴스 근거 섹터 서술 검증"""
        sample_context = {
            "market_data": {
                "equities": [
                    {"name": "코스피", "symbol": "^KS11", "change_pct": 4.61, "price_type": "종가", "market_status": "CLOSED"},
                    {"name": "S&P 500", "symbol": "^GSPC", "change_pct": -0.32, "price_type": "현재가 (장중)", "market_status": "INTRADAY"}
                ],
                "fx": [
                    {"name": "USD/JPY", "symbol": "JPY=X", "change_pct": -0.82, "price_type": "장외/글로벌 현재환율", "market_status": "INTRADAY"},
                    {"name": "USD/KRW", "symbol": "KRW=X", "change_pct": -0.24, "price_type": "장외/글로벌 현재환율", "market_status": "INTRADAY"}
                ],
                "commodities": [
                    {"name": "WTI", "symbol": "CL=F", "change_pct": 1.39, "price_type": "현재가 (장중)", "market_status": "INTRADAY", "change_status": "CONFIRMED"}
                ]
            },
            "verified_macro_news": []
        }

        # 1. 복합문 절(clause) 분리 검증: "WTI는 상승한 가운데 USD/JPY는 하락." -> 각 자산 독립 검증 통과
        compound_text = "WTI는 1.39% 상승한 가운데 USD/JPY는 0.82% 하락함."
        comp_errs = FactValidator._validate_data_to_sentence_alignment("test", compound_text, sample_context)
        self.assertEqual(comp_errs, [], f"Compound sentence should pass independent clause validation, got: {comp_errs}")

        # 2. 수식어 과장 검출: -0.82% 변동에 "가파른 강세" 사용 시 에러
        exaggerated_fx = "엔/달러 환율이 154엔대로 하락하며 엔화의 가파른 강세가 관측됐고."
        exagg_errs = FactValidator._validate_data_to_sentence_alignment("test", exaggerated_fx, sample_context)
        self.assertTrue(any("등락폭 과장 수식어 오류" in e for e in exagg_errs), f"Expected modifier exaggeration error, got: {exagg_errs}")

        # 2-1. 절제된 표현 ("소폭 하락하며 엔화 강세") -> 통과
        proper_fx = "엔/달러 환율이 154엔대로 소폭 하락하며 엔화 강세를 보임."
        self.assertEqual(FactValidator._validate_data_to_sentence_alignment("test", proper_fx, sample_context), [])

        # 2-2. 2% 이상 변동 자산에 "큰 폭의 상승" -> 허용
        large_eq = "코스피는 4.61% 오르며 큰 폭의 상승세를 나타냄."
        self.assertEqual(FactValidator._validate_data_to_sentence_alignment("test", large_eq, sample_context), [])

        # 3. price_type 세션 오표기: 마감 자산(코스피)에 "장중" 사용 시 에러
        bad_session_text = "코스피는 장중 상승세를 유지함."
        session_errs = FactValidator._validate_data_to_sentence_alignment("test", bad_session_text, sample_context)
        self.assertTrue(any("마감 자산 세션 오표기 오류" in e for e in session_errs), f"Expected closed asset session error, got: {session_errs}")

        # 4. SSOT 뉴스 미근거 섹터 날조: 뉴스 없는데 AI 인프라 / 바이오 임상 실패 서술 시 에러
        fake_sector_text = "AI 하드웨어 인프라 관련 종목들이 강세를 보였고 제약·바이오 등 일부 업종의 임상 실패 소식이 지수를 압박함."
        sec_errs = FactValidator._validate_unsupported_sector_and_stock_claims("test", fake_sector_text, sample_context)
        self.assertTrue(any("SSOT 뉴스 미근거 개별 업종/종목 서술 오류" in e for e in sec_errs), f"Expected sector hallucination error, got: {sec_errs}")

        # 4-1. SSOT 뉴스에 해당 기사가 있는 경우 -> 허용
        news_context = dict(sample_context)
        news_context["verified_macro_news"] = [
            {"headline": "AI 하드웨어 인프라 및 반도체 업종 강세", "summary": "엔비디아 등 AI 인프라 수요 견조", "category": "MARKET"}
        ]
        ok_sector_text = "AI 하드웨어 인프라 종목들이 상대적 견조함을 보임."
        self.assertEqual(FactValidator._validate_unsupported_sector_and_stock_claims("test", ok_sector_text, news_context), [])

        # 5. 전망 클리셰 검출: "가격 재산정 과정", "불확실성이 상존" 검출
        cliche_text = "자산시장 전반의 가격 재산정 과정에 주목할 필요가 있으며 불확실성이 상존함."
        cliche_errs = FactValidator._validate_unsupported_causality("ficc_forecast", cliche_text, sample_context)
        self.assertTrue(any("클리셰" in e for e in cliche_errs), f"Expected cliché error, got: {cliche_errs}")


if __name__ == "__main__":
    unittest.main()

