"""
[FICC Daily Macro] 뉴스-시장 매칭 엔진 단위 테스트 (test_market_news_matcher.py)
"""

import unittest
import datetime
import pytz
from processors.market_news_matcher import MarketNewsMatcher

KST = pytz.timezone('Asia/Seoul')

class TestMarketNewsMatcher(unittest.TestCase):

    def setUp(self):
        self.base_time = KST.localize(datetime.datetime(2026, 9, 11, 23, 58, 0))

    def test_noise_filtering(self):
        """개인 재테크, 은퇴 플랜 등 매크로 무관 노이즈 기사 필터링 검증"""
        self.assertTrue(MarketNewsMatcher.is_noise_article(
            "I'm the executor: My two siblings and I inherited an IRA. Can we just cash it out?"
        ))
        self.assertTrue(MarketNewsMatcher.is_noise_article(
            "On my late husband's birthday, I want to pay for every customer at his favorite restaurant."
        ))
        self.assertTrue(MarketNewsMatcher.is_noise_article(
            "I'm a single 58-year-old veteran in California with $1.5 million and a VA pension. Can I retire?"
        ))
        self.assertTrue(MarketNewsMatcher.is_noise_article(
            "The future of retirement? Work until you die."
        ))
        
        # 거시 지표가 포함된 기사는 노이즈로 오탐되지 않아야 함
        self.assertFalse(MarketNewsMatcher.is_noise_article(
            "August CPI report shows core inflation was hotter than expected"
        ))
        self.assertFalse(MarketNewsMatcher.is_noise_article(
            "Treasury yields surge to 34-month high on oil and PPI"
        ))

    def test_temporal_alignment_logic(self):
        """시간축 분석 및 causal_candidate 판정 검증"""
        market_time = self.base_time # 23:58 KST
        
        # 1. 시장 움직임 직전 1시간 전 발표 -> STRONG_LEAD & causal_candidate=True
        pub_strong = KST.localize(datetime.datetime(2026, 9, 11, 22, 58, 0))
        delta, rel, cand = MarketNewsMatcher.evaluate_temporal_alignment(pub_strong, market_time)
        self.assertEqual(rel, "STRONG_LEAD")
        self.assertTrue(cand)
        self.assertAlmostEqual(delta, 1.0, places=1)

        # 2. 시장 움직임 직후 동시 발표 -> HIGH_CONCURRENT & causal_candidate=True
        pub_conc = KST.localize(datetime.datetime(2026, 9, 11, 23, 50, 0))
        delta, rel, cand = MarketNewsMatcher.evaluate_temporal_alignment(pub_conc, market_time)
        self.assertEqual(rel, "HIGH_CONCURRENT")
        self.assertTrue(cand)

        # 3. 시장 움직임 한참 뒤(2시간 뒤) 발표 -> POST_MARKET_EXPLANATION & causal_candidate=False
        pub_post = KST.localize(datetime.datetime(2026, 9, 12, 2, 0, 0))
        delta, rel, cand = MarketNewsMatcher.evaluate_temporal_alignment(pub_post, market_time)
        self.assertEqual(rel, "POST_MARKET_EXPLANATION")
        self.assertFalse(cand)

        # 4. 40시간 전 발표 -> STALE & causal_candidate=False
        pub_stale = KST.localize(datetime.datetime(2026, 9, 10, 5, 0, 0))
        delta, rel, cand = MarketNewsMatcher.evaluate_temporal_alignment(pub_stale, market_time)
        self.assertEqual(rel, "STALE")
        self.assertFalse(cand)

    def test_source_and_causal_confidence_separation(self):
        """Source Confidence와 Causal Confidence의 분리 검증"""
        # 중앙은행 소스
        src_fed = MarketNewsMatcher.determine_source_confidence("Federal Reserve", tier=1)
        self.assertEqual(src_fed, "HIGH")

        # 티어1 주요 통신사
        src_wsj = MarketNewsMatcher.determine_source_confidence("The Wall Street Journal", tier=1)
        self.assertEqual(src_wsj, "HIGH")

        # 일반 금융 포털
        src_mw = MarketNewsMatcher.determine_source_confidence("MarketWatch", tier=2)
        self.assertEqual(src_mw, "MEDIUM")

        # 출처 신뢰도가 HIGH라도 시간축이 POST_MARKET_EXPLANATION이면 causal_confidence는 LOW여야 함
        causal_low = MarketNewsMatcher.determine_causal_confidence(
            source_conf="HIGH",
            temporal_rel="POST_MARKET_EXPLANATION",
            headline_relevance=0.8,
            coverage_count=2,
            has_direct_market_phrase=True
        )
        self.assertEqual(causal_low, "LOW")

        # 출처 신뢰도가 MEDIUM이라도 복수 소스 지지 및 시간축 STRONG_LEAD이면 causal_confidence는 HIGH
        causal_high = MarketNewsMatcher.determine_causal_confidence(
            source_conf="MEDIUM",
            temporal_rel="STRONG_LEAD",
            headline_relevance=0.7,
            coverage_count=2,
            has_direct_market_phrase=True
        )
        self.assertEqual(causal_high, "HIGH")

    def test_cause_category_classification(self):
        """10대 원인 카테고리 분류 정확도 검증"""
        self.assertEqual(MarketNewsMatcher.classify_cause_category("August CPI report shows core inflation hotter"), "Inflation")
        self.assertEqual(MarketNewsMatcher.classify_cause_category("Fed signals restrictive monetary policy stance"), "Central bank")
        self.assertEqual(MarketNewsMatcher.classify_cause_category("Nonfarm payrolls and unemployment rate release"), "Macro data")
        self.assertEqual(MarketNewsMatcher.classify_cause_category("Recession fears mount as manufacturing slows"), "Growth")
        self.assertEqual(MarketNewsMatcher.classify_cause_category("Treasury auction draws strong demand from foreign buyers"), "Fiscal policy")
        self.assertEqual(MarketNewsMatcher.classify_cause_category("Middle East conflict escalation raises tariff concerns"), "Geopolitics")
        self.assertEqual(MarketNewsMatcher.classify_cause_category("OPEC output cuts and crude inventory drop"), "Supply / demand")
        self.assertEqual(MarketNewsMatcher.classify_cause_category("Tech stocks rally on semiconductor earnings surge"), "Company / sector")
        self.assertEqual(MarketNewsMatcher.classify_cause_category("Short covering drives technical rebound at support level"), "Positioning / technical")

    def test_fact_vs_interpretation_separation(self):
        """사실(news_fact)과 해석(causal_interpretation) 분리 필드 검증"""
        raw_cluster = [{
            "event_id": "EVT_001",
            "total_coverage_count": 2,
            "representative_article": {
                "id": "NEWS_001",
                "headline": "10-Year Yield Holds Below 5% After Firm Inflation Data",
                "summary": "The yield on the 10-year note is steady after core consumer prices rose.",
                "source": "The Wall Street Journal",
                "source_tier": 1,
                "url": "https://wsj.com/article1",
                "published_dt_kst": KST.localize(datetime.datetime(2026, 9, 11, 21, 48, 0)),
                "published_at_kst": "2026-09-11 21:48:00 KST",
                "country": "US"
            }
        }]

        mock_market = {
            "categories": {
                "BOND": [
                    {"name": "미국 국채 2년", "current": 4.61, "bp_change": 6.1},
                    {"name": "미국 국채 10년", "current": 4.94, "bp_change": -0.4}
                ]
            }
        }

        res = MarketNewsMatcher.match_market_news(
            market_data=mock_market,
            news_events={"event_clusters": raw_cluster},
            economic_events={},
            run_time_kst=self.base_time
        )

        bond_matches = res.get("asset_matches", {}).get("bond", [])
        self.assertTrue(len(bond_matches) > 0)
        item = bond_matches[0]

        # 필수 필드 검증
        self.assertIn("news_fact", item)
        self.assertIn("causal_interpretation", item)
        self.assertIn("observed_market_move", item)
        self.assertIn("source_confidence", item)
        self.assertIn("causal_confidence", item)
        self.assertIn("news_to_market_time_delta_hours", item)

        self.assertEqual(item["news_fact"], "10-Year Yield Holds Below 5% After Firm Inflation Data")
        self.assertIn("물가지표", item["causal_interpretation"])
        self.assertEqual(item["source_confidence"], "HIGH")
        self.assertEqual(item["causal_confidence"], "HIGH")

    def test_fallback_when_no_news(self):
        """관련 뉴스가 전혀 없을 때 임의 날조 없이 Graceful Fallback 수행 검증"""
        mock_market = {
            "categories": {
                "EQUITY": [{"name": "코스피", "pct_change": 0.5}],
                "FX": [{"name": "달러 인덱스", "pct_change": -0.1}],
                "BOND": [{"name": "미국 국채 10년", "bp_change": 1.0}],
                "COMMODITY": [{"name": "WTI", "pct_change": 0.2}]
            }
        }

        res = MarketNewsMatcher.match_market_news(
            market_data=mock_market,
            news_events={"event_clusters": []},
            economic_events={},
            run_time_kst=self.base_time
        )

        self.assertEqual(res.get("primary_theme"), "거시 변수 점검 속 자산군별 차별화 전개")
        self.assertEqual(res.get("causal_confidence"), "MEDIUM")
        self.assertEqual(len(res.get("verified_macro_news", [])), 0)

        for asset in ["stock", "fx", "bond", "commodity"]:
            cat_info = res.get("asset_specific_catalysts", {}).get(asset, {})
            self.assertIsNone(cat_info.get("catalyst_news"))
            self.assertEqual(cat_info.get("causal_confidence"), "LOW")

if __name__ == '__main__':
    unittest.main()
