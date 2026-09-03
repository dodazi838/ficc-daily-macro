import sys
import os
import json
import unittest

# Windows 콘솔 UTF-8 출력 호환성
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# 프로젝트 루트 임포트 경로 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from processors.fact_validator import FactValidator

class TestDailyEventValidator(unittest.TestCase):
    def setUp(self):
        self.base_context = {
            "report_date": "2026-09-02",
            "cutoff_kst": "2026-09-02 16:30:00 KST",
            "market_data": {
                "categories": {
                    "EQUITY": [{"name": "코스피", "symbol": "^KS11", "current": 6562.72, "pct_change": -3.99}],
                    "FX": [{"name": "달러 인덱스 (DXY)", "symbol": "DX-Y.NYB", "current": 99.84, "pct_change": 0.17}],
                    "BOND": [{"name": "미국 국채 10년", "symbol": "US10Y", "current": 4.82, "bp_change": 2.0}],
                    "COMMODITY": [{"name": "WTI 원유", "symbol": "CL=F", "current": 90.47, "pct_change": 0.28}]
                }
            },
            "economic_calendar": {
                "day_review": [
                    {
                        "event_name": "French Gov Budget Balance",
                        "event_name_kor": "프랑스 정부 재정수지",
                        "scheduled_raw": "09-02-2026 6:45am",
                        "scheduled_at_utc": "2026-09-02 06:45:00 UTC",
                        "scheduled_at_kst": "2026-09-02 15:45:00 KST",
                        "scheduled_time_kst": "15:45",
                        "actual": None,
                        "forecast": None
                    },
                    {
                        "event_name": "Spanish Unemployment Change",
                        "event_name_kor": "스페인 실업자수 변동",
                        "scheduled_raw": "09-02-2026 7:00am",
                        "scheduled_at_utc": "2026-09-02 07:00:00 UTC",
                        "scheduled_at_kst": "2026-09-02 16:00:00 KST",
                        "scheduled_time_kst": "16:00",
                        "actual": None,
                        "forecast": "15.4K"
                    },
                    {
                        "event_name": "ISM Manufacturing PMI",
                        "event_name_kor": "미국 ISM 제조업 구매관리자지수(PMI)",
                        "scheduled_at_kst": "2026-09-01 23:00:00 KST",
                        "scheduled_time_kst": "23:00",
                        "actual": "47.2",
                        "forecast": "47.5"
                    }
                ],
                "today_night": [
                    {
                        "event_id": "EVT_20260902_001",
                        "country": "US",
                        "event_name": "ADP Non-Farm Employment Change",
                        "event_name_kor": "미국 ADP 비농업 부문 고용 변화",
                        "scheduled_raw": "09-02-2026 12:15pm",
                        "scheduled_at_utc": "2026-09-02 12:15:00 UTC",
                        "scheduled_at_kst": "2026-09-02 21:15:00 KST",
                        "scheduled_time_kst": "21:15",
                        "importance": "MEDIUM",
                        "forecast": "47K"
                    },
                    {
                        "event_id": "EVT_20260902_002",
                        "country": "CA",
                        "event_name": "BOC Rate Statement",
                        "event_name_kor": "캐나다 중앙은행(BOC) 통화정책 성명서",
                        "scheduled_raw": "09-02-2026 1:45pm",
                        "scheduled_at_utc": "2026-09-02 13:45:00 UTC",
                        "scheduled_at_kst": "2026-09-02 22:45:00 KST",
                        "scheduled_time_kst": "22:45",
                        "importance": "HIGH",
                        "forecast": None
                    },
                    {
                        "event_id": "EVT_20260902_003",
                        "country": "CA",
                        "event_name": "Overnight Rate",
                        "event_name_kor": "캐나다 기준금리 결정",
                        "scheduled_raw": "09-02-2026 1:45pm",
                        "scheduled_at_utc": "2026-09-02 13:45:00 UTC",
                        "scheduled_at_kst": "2026-09-02 22:45:00 KST",
                        "scheduled_time_kst": "22:45",
                        "importance": "HIGH",
                        "forecast": "2.25%"
                    },
                    {
                        "event_id": "EVT_20260902_004",
                        "country": "US",
                        "event_name": "Factory Orders m/m",
                        "event_name_kor": "미국 공장재 수주 (전월비)",
                        "scheduled_raw": "09-02-2026 2:00pm",
                        "scheduled_at_utc": "2026-09-02 14:00:00 UTC",
                        "scheduled_at_kst": "2026-09-02 23:00:00 KST",
                        "scheduled_time_kst": "23:00",
                        "importance": "LOW",
                        "forecast": "0.7%"
                    },
                    {
                        "event_id": "EVT_20260902_005",
                        "country": "CA",
                        "event_name": "BOC Press Conference",
                        "event_name_kor": "캐나다 중앙은행(BOC) 기자회견",
                        "scheduled_raw": "09-02-2026 2:30pm",
                        "scheduled_at_utc": "2026-09-02 14:30:00 UTC",
                        "scheduled_at_kst": "2026-09-02 23:30:00 KST",
                        "scheduled_time_kst": "23:30",
                        "importance": "HIGH",
                        "forecast": None
                    },
                    {
                        "event_id": "EVT_20260902_006",
                        "country": "US",
                        "event_name": "Crude Oil Inventories",
                        "event_name_kor": "미국 EIA 주간 원유재고",
                        "scheduled_raw": "09-02-2026 2:30pm",
                        "scheduled_at_utc": "2026-09-02 14:30:00 UTC",
                        "scheduled_at_kst": "2026-09-02 23:30:00 KST",
                        "scheduled_time_kst": "23:30",
                        "importance": "LOW",
                        "forecast": "-0.4M"
                    }
                ]
            }
        }

    def test_scenario_a_normal_upcoming_event_pass(self):
        """Test A: 정상 upcoming event -> 본문/표 일치 -> PASS (21:15, 22:45, 23:00, 23:30)"""
        valid_text = (
            "금일 야간에는 21:15 발표되는 미국 ADP 비농업 부문 고용 변화를 통해 노동시장 냉각 여부를 점검할 필요가 있다. "
            "이어 22:45 예정된 캐나다 중앙은행(BOC)의 기준금리 결정 및 통화정책 성명서 발표와 23:30 기자회견을 통해 통화정책 기조를 확인할 수 있다. "
            "아울러 23:00 미국 공장재 수주 지표와 23:30 발표되는 EIA 주간 원유재고를 점검하는 것이 핵심 관전 포인트다."
        )
        errors = FactValidator._validate_daily_event_section(valid_text, self.base_context)
        self.assertEqual(len(errors), 0, f"정상 텍스트에서 오류 적발됨: {errors}")

    def test_scenario_b_nonexistent_indicator_fail(self):
        """Test B: 본문에 없는 이벤트(JOLTS, ISM PMI 등) 추가 -> FAIL"""
        invalid_text = (
            "금일 21:15 미국 ADP 고용 변화와 함께 미국 JOLTS 구인건수 및 ISM 서비스업 PMI가 발표될 예정이다."
        )
        errors = FactValidator._validate_daily_event_section(invalid_text, self.base_context)
        self.assertGreater(len(errors), 0, "미존재 지표 인용이 적발되지 않음")
        self.assertTrue(any("JOLTS" in e or "ISM" in e for e in errors))

    def test_scenario_c_incorrect_time_fail(self):
        """Test C: 본문 이벤트 시각 변경 (예: canonical 21:15 대신 과거 잘못된 01:15 또는 19:30 인용) -> FAIL"""
        invalid_text = (
            "금일 01:15에 미국 ADP 비농업 고용 변화가 발표될 예정이다."
        )
        errors = FactValidator._validate_daily_event_section(invalid_text, self.base_context)
        self.assertGreater(len(errors), 0, "잘못된 발표 시각 인용이 적발되지 않음")
        self.assertTrue(any("01:15" in e for e in errors))

    def test_scenario_d_fabricated_forecast_fail(self):
        """Test D: expected 값 임의 변경 / 날조 (예: 예상치 55.2 또는 예상 7.33M) -> FAIL"""
        invalid_text = (
            "금일 야간 21:15 미국 ADP 비농업 부문 고용 변화는 시장 예상치 55.2K를 상회할지 주목된다."
        )
        errors = FactValidator._validate_daily_event_section(invalid_text, self.base_context)
        self.assertGreater(len(errors), 0, "날조된 예상치(55.2)가 적발되지 않음")
        self.assertTrue(any("55.2" in e for e in errors))

    def test_scenario_e_day_review_and_upcoming_combination_pass(self):
        """Test E: 당일 기발표 주요 지표(프랑스 재정수지, ISM PMI) 리뷰 + 야간 예정 지표(ADP 고용) 결합 서술 -> PASS"""
        valid_combo_text = (
            "금일 15:45 발표된 프랑스 정부 재정수지와 전일 ISM 제조업 PMI를 통해 제조업 경기 흐름이 점검됨. "
            "이어 21:15에는 미국 ADP 비농업 부문 고용 변화가 예정되어 있어 노동시장 냉각 여부를 확인할 필요가 있음."
        )
        errors = FactValidator._validate_daily_event_section(valid_combo_text, self.base_context)
        self.assertEqual(len(errors), 0, f"당일 발표 리뷰 + 예정 지표 결합 서술에서 오류 발생: {errors}")

    def test_scenario_f_empty_events_handling(self):
        """Test F: 실제 이벤트가 없는 경우 -> 빈 목록 정상 통과 및 허위 작성 차단"""
        empty_context = dict(self.base_context)
        empty_context["economic_calendar"] = {"day_review": [], "today_night": []}

        # 1. 빈 목록 정상 텍스트
        clean_text = "금일 16:30 이후에는 시장의 이목을 끌 만한 주요 경제지표 발표 일정이 부재하다."
        errors = FactValidator._validate_daily_event_section(clean_text, empty_context)
        self.assertEqual(len(errors), 0, f"빈 목록 정상 텍스트에서 오류 적발: {errors}")

        # 2. 빈 목록인데 허위 발표 일정을 작성한 경우 -> FAIL
        hallucinated_text = "금일 야간 미국 주요 경제지표가 발표될 예정이며 투자자들의 관심이 집중되고 있다."
        errors_hal = FactValidator._validate_daily_event_section(hallucinated_text, empty_context)
        self.assertGreater(len(errors_hal), 0, "빈 목록 상태에서 허위 일정 작성이 적발되지 않음")

if __name__ == "__main__":
    unittest.main(verbosity=2)
