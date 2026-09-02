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
                        "event_name": "ISM Manufacturing PMI",
                        "event_name_kor": "미국 ISM 제조업 구매관리자지수(PMI)",
                        "scheduled_at": "2026-09-01 23:00:00",
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
                        "scheduled_time_kst": "01:15",
                        "scheduled_at": "2026-09-03 01:15:00",
                        "importance": "MEDIUM",
                        "forecast": "47K"
                    },
                    {
                        "event_id": "EVT_20260902_002",
                        "country": "CA",
                        "event_name": "Overnight Rate",
                        "event_name_kor": "캐나다 기준금리 결정",
                        "scheduled_time_kst": "02:45",
                        "scheduled_at": "2026-09-03 02:45:00",
                        "importance": "HIGH",
                        "forecast": "2.25%"
                    },
                    {
                        "event_id": "EVT_20260902_003",
                        "country": "US",
                        "event_name": "Factory Orders m/m",
                        "event_name_kor": "미국 공장재 수주 (전월비)",
                        "scheduled_time_kst": "03:00",
                        "scheduled_at": "2026-09-03 03:00:00",
                        "importance": "LOW",
                        "forecast": "0.7%"
                    },
                    {
                        "event_id": "EVT_20260902_004",
                        "country": "US",
                        "event_name": "Crude Oil Inventories",
                        "event_name_kor": "미국 EIA 주간 원유재고",
                        "scheduled_time_kst": "03:30",
                        "scheduled_at": "2026-09-03 03:30:00",
                        "importance": "LOW",
                        "forecast": "-0.4M"
                    }
                ]
            }
        }

    def test_scenario_a_normal_upcoming_event_pass(self):
        """Test A: 정상 upcoming event -> 본문/표 일치 -> PASS"""
        valid_text = (
            "금일 야간에는 미국 8월 ADP 비농업 부문 고용 변화(예상치 47K)와 7월 공장재 수주(예상치 0.7%), "
            "EIA 주간 원유재고(예상치 -0.4M)가 발표될 예정이다. 아울러 캐나다 중앙은행의 기준금리 결정(예상치 2.25%)이 예정되어 있다."
        )
        errors = FactValidator._validate_daily_event_section(valid_text, self.base_context)
        self.assertEqual(len(errors), 0, f"정상 텍스트에서 오류 적발됨: {errors}")

    def test_scenario_b_nonexistent_indicator_fail(self):
        """Test B: 본문에 없는 이벤트(JOLTS, ISM PMI 등) 추가 -> FAIL"""
        invalid_text = (
            "금일 밤에는 미국 ADP 고용 변화(예상치 47K)와 함께 미국 JOLTS 구인건수 및 ISM 서비스업 PMI가 발표될 예정이다."
        )
        errors = FactValidator._validate_daily_event_section(invalid_text, self.base_context)
        self.assertGreater(len(errors), 0, "미존재 지표 인용이 적발되지 않음")
        self.assertTrue(any("JOLTS" in e or "ISM" in e for e in errors))

    def test_scenario_c_incorrect_time_fail(self):
        """Test C: 본문 이벤트 시각 변경 (예: canonical 01:15 대신 22:30 인용) -> FAIL"""
        invalid_text = (
            "금일 22:30에 미국 ADP 비농업 고용 변화(예상치 47K)가 발표될 예정이다."
        )
        errors = FactValidator._validate_daily_event_section(invalid_text, self.base_context)
        self.assertGreater(len(errors), 0, "잘못된 발표 시각 인용이 적발되지 않음")
        self.assertTrue(any("22:30" in e for e in errors))

    def test_scenario_d_fabricated_forecast_fail(self):
        """Test D: expected 값 임의 변경 / 날조 (예: 예상치 55.2 또는 예상 7.33M) -> FAIL"""
        invalid_text = (
            "금일 야간 미국 ADP 비농업 부문 고용 변화는 시장 예상치 55.2K를 상회할지 주목된다."
        )
        errors = FactValidator._validate_daily_event_section(invalid_text, self.base_context)
        self.assertGreater(len(errors), 0, "날조된 예상치(55.2)가 적발되지 않음")
        self.assertTrue(any("55.2" in e for e in errors))

    def test_scenario_e_past_event_as_upcoming_fail(self):
        """Test E: 16:30 이전 이미 발표된 과거 지표(ISM 제조업 PMI)를 upcoming으로 삽입 -> FAIL"""
        invalid_text = (
            "금일 밤에는 미국 ISM 제조업 PMI 발표를 앞두고 관망세가 짙어질 것으로 보인다."
        )
        errors = FactValidator._validate_daily_event_section(invalid_text, self.base_context)
        self.assertGreater(len(errors), 0, "과거 지표(ISM 제조업 PMI) upcoming 인용이 적발되지 않음")
        self.assertTrue(any("ISM" in e for e in errors))

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
