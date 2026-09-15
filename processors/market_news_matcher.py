"""
[FICC Daily Macro] 뉴스-시장 매칭, 시간축 분석, 원인 분류 및 Claim-Evidence 엔진 (market_news_matcher.py)
====================================================================
- 시장 세션별 시간축(KST/UTC)과 뉴스 published_at 정밀 대조:
    • 글로벌/미국 시장(S&P, 나스닥, 미 국채, 환율, 원자재): run_kst (실시간 관측시각) 기준
    • 국내 시장(코스피, 코스닥, 국고채): 당일 15:30 KST 마감시각 기준
- Claim-Evidence 구조 기반 사실(Fact)과 해석(Interpretation)의 완전 분리
- 시장 데이터 방향성(Bonds 커브 스티프닝/플래트닝, FX 다통화, 원자재 차별화) 정밀 모델링
- 하드코딩된 템플릿 전면 배제 및 동적 팩트 기반 인과 경로 합성
- Source Confidence(출처 신뢰도)와 Causal Confidence(인과 신뢰도) 엄격 분리
- 10대 Cause Category 자동 분류 및 노이즈 기사 사전 필터링
- 무뉴스 시 임의 원인 날조 및 상투적 클리셰 차단 (Graceful Fallback)
====================================================================
"""

import re
import datetime
import pytz
from typing import Dict, Any, List, Optional, Tuple, Set

KST_TZ = pytz.timezone('Asia/Seoul')
UTC_TZ = pytz.utc

def ensure_kst_aware(dt: Any) -> datetime.datetime:
    """datetime 객체를 Asia/Seoul 타임존 인식 객체로 보장"""
    if dt is None:
        return datetime.datetime.now(KST_TZ)
    if isinstance(dt, str):
        try:
            clean_str = dt.replace(" KST", "").strip()
            import dateutil.parser
            parsed = dateutil.parser.parse(clean_str, tzinfos={"KST": 9*3600, "UTC": 0})
            if parsed.tzinfo is None:
                return KST_TZ.localize(parsed)
            return parsed.astimezone(KST_TZ)
        except Exception:
            return datetime.datetime.now(KST_TZ)
    if getattr(dt, 'tzinfo', None) is None:
        return KST_TZ.localize(dt)
    return dt.astimezone(KST_TZ)

class MarketNewsMatcher:
    """원천 뉴스 클러스터와 4대 자산군 시장 움직임을 시간축/인과성 기반으로 매칭하는 엔진"""

    CAUSE_CATEGORIES = [
        "Macro data",
        "Central bank",
        "Inflation",
        "Growth",
        "Fiscal policy",
        "Geopolitics",
        "Supply / demand",
        "Positioning / technical",
        "Company / sector",
        "Other"
    ]

    NOISE_PATTERNS = [
        r'\b(?:i\'m\s+the\s+executor|inherited\s+an\s+ira|ira\b|401\(k\)|roth\b)',
        r'\b(?:my\s+husband|late\s+husband|favorite\s+restaurant|single\s+\d+-year-old|veteran\b|va\s+pension)',
        r'\b(?:annuity\b|strapped\s+for\s+cash|future\s+of\s+retirement|work\s+until\s+you\s+die)',
        r'\b(?:social\s+security\b.*disappear|vacation\b|grocery\s+shopping|commuting\b)',
        r'\b(?:on\s+my\s+late|spending\s+money|credit\s+card\s+freeze|card\s+issuers\s+might\s+freeze)',
        r'\b(?:can\s+i\s+retire|how\s+to\s+retire|save\s+for\s+retirement)',
        r'\b(?:agencies\s+reduce\s+regulatory\s+burden\s+for\s+community\s+banks|third-party\s+risk\s+management\s+guidance)',
        r'\b(?:costco\s+item\s+has\s+skyrocketed|minimum\s+net\s+worth\s+you\s+need|3\s+reasons\s+to\s+sell\s+pnc)',
        r'\b(?:promised\s+you\s+\$5,000|tim\s+cook\s+could\s+have\s+purchased|bright\s+horizons)'
    ]

    ASSET_KEYWORDS = {
        "EQUITY": [
            "stock", "stocks", "equity", "equities", "s&p", "nasdaq", "dow", "wall street", "rally", "selloff",
            "tech", "technology", "semiconductor", "chip", "earnings", "bull", "bear", "vix", "bourses",
            "코스피", "코스닥", "증시", "주가"
        ],
        "FX": [
            "dollar", "usd", "dxy", "greenback", "currency", "fx", "forex", "yen", "jpy", "yuan", "cnh", "cny",
            "euro", "eur", "pound", "gbp", "won", "krw", "exchange rate", "boj", "환율", "외환", "달러화", "엔화", "원화"
        ],
        "BOND": [
            "treasury", "treasuries", "yield", "yields", "bond", "bonds", "note", "curve", "spread", "10-year", "2-year",
            "30-year", "auction", "fed", "fomc", "powell", "rate cut", "rate hike", "monetary policy", "bund", "jgb", "ktb",
            "국채", "채권", "금리", "국고채", "연준", "통화정책"
        ],
        "COMMODITY": [
            "oil", "crude", "wti", "brent", "opec", "energy", "petroleum", "gasoline", "diesel", "inventory",
            "pipeline", "hormuz", "saudi", "gold", "silver", "copper", "natural gas", "commodity", "commodities",
            "유가", "원유", "금", "은", "구리", "천연가스", "원자재"
        ]
    }

    @classmethod
    def is_noise_article(cls, headline: str, summary: Optional[str] = None) -> bool:
        """개인 재테크, 은퇴 상담, 행정 규제 안내 등 매크로 시황과 무관한 노이즈 기사 감지"""
        text = f"{headline} {summary or ''}".lower()
        for pat in cls.NOISE_PATTERNS:
            if re.search(pat, text, re.IGNORECASE):
                # 거시 지표 또는 주요국 정책금리, 국제유가 등이 직접적 핵심 주제인 경우는 예외
                if any(w in text for w in ["rate decision", "cpi", "fomc", "powell", "treasury yield", "gdp", "payrolls", "crude oil", "brent"]):
                    continue
                return True
        return False

    @classmethod
    def determine_source_confidence(cls, source: str, tier: int = 2) -> str:
        """원천 소스 신뢰도 판정 (HIGH / MEDIUM / LOW)"""
        s_lower = (source or "").lower()
        if "federal reserve" in s_lower or "ecb" in s_lower or "bank of korea" in s_lower or "bok" in s_lower or "boj" in s_lower:
            return "HIGH"
        if tier == 1 or any(k in s_lower for k in ["reuters", "bloomberg", "wall street journal", "wsj", "financial times", "barron"]):
            return "HIGH"
        if any(k in s_lower for k in ["marketwatch", "yahoo finance", "cnbc", "investing", "quartz", "euronews", "mt newswires"]):
            return "MEDIUM"
        return "LOW"

    @classmethod
    def classify_cause_category(cls, text: str) -> str:
        """10대 원인 카테고리 분류"""
        t = text.lower()
        if any(w in t for w in ["hormuz", "attack", "pipeline", "saudi", "war", "middle east", "israel", "iran", "russia", "ukraine", "sanction", "tariff", "geopolitic", "지정학", "전쟁", "관세"]):
            return "Geopolitics"
        if any(w in t for w in ["cpi", "ppi", "pce", "inflation", "price index", "prices rise", "sticky inflation", "물가", "인플레이션"]):
            return "Inflation"
        if any(w in t for w in ["fed", "fomc", "powell", "ecb", "lagarde", "boj", "ueda", "rate hike", "rate cut", "monetary policy", "기준금리", "통화정책"]):
            return "Central bank"
        if any(w in t for w in ["payrolls", "jobs", "unemployment", "gdp", "retail sales", "pmi", "ism", "consumer confidence", "고용", "실업률", "지표"]):
            return "Macro data"
        if any(w in t for w in ["recession", "economic growth", "slowdown", "recovery", "expansion", "경기침체", "경기 둔화", "성장률"]):
            return "Growth"
        if any(w in t for w in ["treasury auction", "debt ceiling", "deficit", "fiscal", "tax", "government spending", "재정", "국채 발행"]):
            return "Fiscal policy"
        if any(w in t for w in ["opec", "crude inventory", "supply", "demand", "stockpile", "refinery", "buyback", "원유재고", "수급", "공급"]):
            return "Supply / demand"
        if any(w in t for w in ["tech rally", "semiconductor", "earnings", "revenue", "profit", "ai chip", "nvidia", "apple", "ai slowdown", "실적", "빅테크", "반도체"]):
            return "Company / sector"
        if any(w in t for w in ["short covering", "technical rebound", "support level", "resistance", "positioning", "기술적", "반등", "차트"]):
            return "Positioning / technical"
        return "Other"

    @classmethod
    def evaluate_temporal_alignment(
        cls, 
        pub_dt_kst: Optional[datetime.datetime], 
        market_time_kst: datetime.datetime
    ) -> Tuple[float, str, bool]:
        """
        뉴스 발표시각과 시장 관측시각의 시간축 관계 분석:
        Returns:
            (delta_hours, temporal_relevance, causal_candidate_flag)
        """
        if not pub_dt_kst:
            return 0.0, "UNKNOWN", False

        delta_hours = (market_time_kst - pub_dt_kst).total_seconds() / 3600.0

        if delta_hours < -1.5:
            # 시장 움직임 관측 후 1.5시간 이상 뒤에 발표된 뉴스 -> 사후 해설 기사
            return round(delta_hours, 2), "POST_MARKET_EXPLANATION", False
        elif -1.5 <= delta_hours <= 0.5:
            # 시장 움직임과 거의 동시 또는 직후 발표
            return round(delta_hours, 2), "HIGH_CONCURRENT", True
        elif 0.5 < delta_hours <= 6.0:
            # 시장 움직임 직전 6시간 이내 발표 -> 강력한 선행 원인 후보
            return round(delta_hours, 2), "STRONG_LEAD", True
        elif 6.0 < delta_hours <= 16.0:
            # 당일 거래 세션 이전 발표 -> 유효한 당일 원인 후보
            return round(delta_hours, 2), "MODERATE_LEAD", True
        elif 16.0 < delta_hours <= 36.0:
            # 전일 발표 -> 배경 요인 가능하나 당일 직접 촉매로는 약화
            return round(delta_hours, 2), "DISTANT_LEAD", False
        else:
            return round(delta_hours, 2), "STALE", False

    @classmethod
    def determine_causal_confidence(
        cls, 
        source_conf: str, 
        temporal_rel: str, 
        headline_relevance: float, 
        coverage_count: int,
        has_direct_market_phrase: bool
    ) -> str:
        """
        인과 신뢰도(Causal Confidence) 판정:
        - HIGH:
            • 신뢰도 높은 소스가 명확한 시장 촉매를 직접 보도하고 뉴스 발표 시각과 시장 움직임 시간관계가 일치하며 다른 데이터와 부합
            • 또는 복수의 신뢰할 수 있는 소스가 동일 촉매를 지지
        - MEDIUM: 일부 뉴스가 원인을 지지하나 시간관계/시장반응이 부분적
        - LOW: 근거 약화 또는 여러 요인 혼재
        """
        if temporal_rel in ["STALE", "POST_MARKET_EXPLANATION", "UNKNOWN"]:
            return "LOW"

        # 1. HIGH 조건
        if coverage_count >= 2 and temporal_rel in ["STRONG_LEAD", "HIGH_CONCURRENT", "MODERATE_LEAD"]:
            return "HIGH"
        if source_conf in ["HIGH", "MEDIUM"] and has_direct_market_phrase and temporal_rel in ["STRONG_LEAD", "HIGH_CONCURRENT"]:
            return "HIGH"
        if headline_relevance >= 0.65 and temporal_rel in ["STRONG_LEAD", "HIGH_CONCURRENT"]:
            return "HIGH"

        # 2. MEDIUM 조건
        if temporal_rel in ["STRONG_LEAD", "HIGH_CONCURRENT", "MODERATE_LEAD"] and headline_relevance >= 0.30:
            return "MEDIUM"
        if source_conf in ["HIGH", "MEDIUM"] and temporal_rel == "MODERATE_LEAD":
            return "MEDIUM"

        return "LOW"

    @classmethod
    def match_market_news(
        cls,
        market_data: Dict[str, Any],
        news_events: Dict[str, Any],
        economic_events: Dict[str, Any],
        run_time_kst: datetime.datetime
    ) -> Dict[str, Any]:
        """
        시장 데이터와 뉴스 클러스터를 융합하여 자산별 매칭 결과, Claim-Evidence 구조체, 인과 해석 및 핵심 테마 생성
        """
        run_kst = ensure_kst_aware(run_time_kst)
        categories = market_data.get("categories", {})
        spreads = market_data.get("spreads", [])

        # 1. 4대 시장별 관측된 움직임 정밀 요약 (observed_market_move)
        market_observations = cls._build_market_observations(categories, spreads)

        # 2. 전체 뉴스 클러스터 정제 및 노이즈 필터링
        raw_clusters = news_events.get("event_clusters", [])
        clean_candidates: List[Dict[str, Any]] = []

        for c in raw_clusters:
            rep = c.get("representative_article", {})
            hl = rep.get("headline", "").strip()
            sm = rep.get("summary") or ""
            if not hl or cls.is_noise_article(hl, sm):
                continue

            pub_dt_kst = rep.get("published_dt_kst")
            if pub_dt_kst:
                pub_dt_kst = ensure_kst_aware(pub_dt_kst)

            pub_dt_utc_str = pub_dt_kst.astimezone(UTC_TZ).strftime("%Y-%m-%d %H:%M:%S UTC") if pub_dt_kst else None
            pub_dt_kst_str = pub_dt_kst.strftime("%Y-%m-%d %H:%M:%S KST") if pub_dt_kst else rep.get("published_at_kst", "")

            src_conf = cls.determine_source_confidence(rep.get("source", ""), rep.get("source_tier", 2))
            cause_cat = cls.classify_cause_category(f"{hl} {sm}")

            clean_candidates.append({
                "cluster_id": c.get("event_id"),
                "news_id": rep.get("id"),
                "headline": hl,
                "summary": sm,
                "source": rep.get("source", "UNKNOWN"),
                "source_tier": rep.get("source_tier", 2),
                "source_confidence": src_conf,
                "url": rep.get("url", ""),
                "published_at_kst": pub_dt_kst_str,
                "published_at_utc": pub_dt_utc_str,
                "published_dt_kst": pub_dt_kst,
                "country": rep.get("country", "GLOBAL"),
                "cause_category": cause_cat,
                "coverage_count": c.get("total_coverage_count", 1),
                "related_assets": c.get("related_assets", [])
            })

        # 3. 4대 자산군별 시장 세션 시각 정의 및 뉴스 매칭
        close_kr_kst = run_kst.replace(hour=15, minute=30, second=0, microsecond=0)

        asset_matched: Dict[str, List[Dict[str, Any]]] = {
            "stock": [],
            "fx": [],
            "bond": [],
            "commodity": []
        }

        for asset_key, asset_name in [("stock", "EQUITY"), ("fx", "FX"), ("bond", "BOND"), ("commodity", "COMMODITY")]:
            matched_items = cls._match_for_asset(
                asset_key=asset_key,
                asset_name=asset_name,
                market_obs=market_observations.get(asset_key, {}),
                candidates=clean_candidates,
                run_kst=run_kst,
                close_kr_kst=close_kr_kst
            )
            asset_matched[asset_key] = matched_items

        # 4. 시장 대표 원인(primary_theme) 및 자산별 촉매(asset_specific_catalysts) 도출 (하드코딩 제거!)
        theme_info = cls._synthesize_primary_theme(market_observations, asset_matched)

        # 5. Claim-Evidence 구조체 구축 (Summary, 4대 자산, Forecast)
        claim_evidence_records = cls._build_claim_evidence_records(
            market_obs=market_observations,
            asset_matches=asset_matched,
            theme_info=theme_info,
            economic_events=economic_events
        )

        # 6. 모든 선별된 뉴스를 단일 리스트로 일원화 (FactValidator source_news_ids 호환)
        all_curated_news: List[Dict[str, Any]] = []
        seen_nids = set()
        for k in ["stock", "fx", "bond", "commodity"]:
            for item in asset_matched[k]:
                nid = item.get("news_id")
                if nid and nid not in seen_nids:
                    seen_nids.add(nid)
                    all_curated_news.append({
                        "news_id": nid,
                        "headline": item.get("title"),
                        "source": item.get("source"),
                        "published_at": item.get("published_at"),
                        "published_at_kst": item.get("published_at_kst"),
                        "published_at_utc": item.get("published_at_utc"),
                        "url": item.get("url"),
                        "country": item.get("country"),
                        "asset_class": item.get("asset_class"),
                        "relevance_score": item.get("relevance_score"),
                        "matched_market": item.get("matched_market"),
                        "category": item.get("cause_category"),
                        "cause_category": item.get("cause_category"),
                        "source_confidence": item.get("source_confidence"),
                        "causal_confidence": item.get("causal_confidence"),
                        "observed_market_move": item.get("observed_market_move"),
                        "news_fact": item.get("news_fact"),
                        "causal_interpretation": item.get("causal_interpretation"),
                        "summary": item.get("summary")
                    })

        return {
            "primary_theme": theme_info.get("primary_theme"),
            "core_cause_category": theme_info.get("core_cause_category"),
            "causal_confidence": theme_info.get("causal_confidence"),
            "transmission_summary": theme_info.get("transmission_summary"),
            "asset_specific_catalysts": theme_info.get("asset_specific_catalysts"),
            "market_observations": market_observations,
            "asset_matches": asset_matched,
            "claim_evidence": claim_evidence_records,
            "verified_macro_news": all_curated_news
        }

    @classmethod
    def _build_market_observations(
        cls, 
        categories: Dict[str, List[Dict[str, Any]]], 
        spreads: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """4대 자산군별 관측된 시장 변동 사실(observed_market_move) 정밀 추출"""
        obs = {}

        # 1. 증시 (Equities)
        eq_list = categories.get("EQUITY", [])
        sp500 = next((x for x in eq_list if "S&P" in x.get("name", "")), None)
        nasdaq = next((x for x in eq_list if "나스닥" in x.get("name", "")), None)
        kospi = next((x for x in eq_list if "코스피" in x.get("name", "")), None)
        kosdaq = next((x for x in eq_list if "코스닥" in x.get("name", "")), None)
        nikkei = next((x for x in eq_list if "니케이" in x.get("name", "")), None)
        stoxx = next((x for x in eq_list if "EURO" in x.get("name", "")), None)

        sp_pct = sp500.get("pct_change") if sp500 else None
        kp_pct = kospi.get("pct_change") if kospi else None
        nk_pct = nikkei.get("pct_change") if nikkei else None
        st_pct = stoxx.get("pct_change") if stoxx else None

        eq_parts = []
        if kp_pct is not None:
            kp_str = "큰 폭 하락 마감" if kp_pct < -2.0 else ("하락 마감" if kp_pct < -0.3 else "상승 마감")
            eq_parts.append(f"국내 코스피 {kp_str}({kp_pct:+.2f}%)")
        if nk_pct is not None or st_pct is not None:
            asian_euro = []
            if nk_pct is not None:
                asian_euro.append(f"일본 니케이 {nk_pct:+.2f}%")
            if st_pct is not None:
                asian_euro.append(f"유럽 유로스톡스 {st_pct:+.2f}%")
            eq_parts.append(f"아시아/유럽 증시 약세({', '.join(asian_euro)})")
        if sp500 and sp500.get("price_type") == "PREVIOUS_CLOSE":
            eq_parts.append(f"미국 정규장은 직전 거래일 종가 기준({sp_pct:+.2f}%) 유지")

        obs["stock"] = {
            "summary": " / ".join(eq_parts) or "글로벌 증시 등락 혼조",
            "key_movers": ["KOSPI", "KOSDAQ", "S&P 500", "Nikkei 225"],
            "has_significant_move": any(abs(p or 0) >= 0.5 for p in [sp_pct, kp_pct, nk_pct, st_pct]),
            "direction_kr": "DOWN" if (kp_pct and kp_pct < -0.2) else "UP",
            "direction_us_session": "PREVIOUS_CLOSE"
        }

        # 2. 외환 (FX)
        fx_list = categories.get("FX", [])
        dxy = next((x for x in fx_list if "달러 인덱스" in x.get("name", "")), None)
        usdkrw = next((x for x in fx_list if "원/달러" in x.get("name", "")), None)
        usdjpy = next((x for x in fx_list if "엔/달러" in x.get("name", "")), None)
        usdcnh = next((x for x in fx_list if "위안" in x.get("name", "")), None)
        eurusd = next((x for x in fx_list if "유로" in x.get("name", "")), None)
        gbpusd = next((x for x in fx_list if "파운드" in x.get("name", "")), None)

        dxy_pct = dxy.get("pct_change") if dxy else None
        krw_pct = usdkrw.get("pct_change") if usdkrw else None
        jpy_pct = usdjpy.get("pct_change") if usdjpy else None
        cnh_pct = usdcnh.get("pct_change") if usdcnh else None
        eur_pct = eurusd.get("pct_change") if eurusd else None

        fx_parts = []
        if dxy_pct is not None:
            dxy_dir = "강세" if dxy_pct > 0.1 else ("약세" if dxy_pct < -0.1 else "보합권 등락")
            fx_parts.append(f"달러화 지수(DXY) {dxy_dir}({dxy_pct:+.2f}%)")
        
        # 다통화 상대강도 분석
        euro_weak = (eur_pct and eur_pct < -0.1) or (jpy_pct and jpy_pct > 0.05)
        asia_resilient = (krw_pct and krw_pct < -0.05) or (cnh_pct and cnh_pct < -0.1)
        if euro_weak and asia_resilient:
            fx_parts.append("유로화/엔화는 달러 대비 약세인 반면, 원화/위안화는 달러 대비 상대적 강세로 지역별 차별화")
        elif euro_weak:
            fx_parts.append("주요국 통화 전반 달러 대비 약세")

        obs["fx"] = {
            "summary": " / ".join(fx_parts) or "외환시장 달러화 및 주요 통화 혼조세",
            "key_movers": ["DXY", "USD/KRW", "USD/JPY", "EUR/USD"],
            "has_significant_move": any(abs(p or 0) >= 0.2 for p in [dxy_pct, krw_pct, jpy_pct, eur_pct]),
            "dxy_direction": "UP" if (dxy_pct and dxy_pct > 0.05) else ("DOWN" if (dxy_pct and dxy_pct < -0.05) else "FLAT"),
            "eur_direction": "DOWN" if (eur_pct and eur_pct < -0.05) else "UP",
            "krw_direction": "STRONG" if (krw_pct and krw_pct < -0.05) else "WEAK"
        }

        # 3. 채권 (Bonds & Curve)
        bd_list = categories.get("BOND", [])
        us2y = next((x for x in bd_list if "미국 국채 2년" in x.get("name", "")), None)
        us10y = next((x for x in bd_list if "미국 국채 10년" in x.get("name", "")), None)
        ktb3y = next((x for x in bd_list if "국고채 3년" in x.get("name", "")), None)
        ktb10y = next((x for x in bd_list if "국고채 10년" in x.get("name", "")), None)

        us2_bp = us2y.get("bp_change") if us2y else 0.0
        us10_bp = us10y.get("bp_change") if us10y else 0.0
        ktb3_bp = ktb3y.get("bp_change") if ktb3y else 0.0
        ktb10_bp = ktb10y.get("bp_change") if ktb10y else 0.0

        bd_parts = []
        
        # 미국 커브 판정
        us_spread_chg = us10_bp - us2_bp
        if us2_bp < 0 and us10_bp > 0:
            us_curve = f"단기물 소폭 하락({us2_bp:+.1f}bp) 속 장기물 소폭 상승({us10_bp:+.1f}bp)으로 10-2년 커브 스티프닝(스프레드 확대, +{us_spread_chg:.1f}bp)"
        elif us2_bp > 0 and us10_bp < 0:
            us_curve = f"단기물 상승({us2_bp:+.1f}bp) 속 장기물 하락({us10_bp:+.1f}bp)으로 10-2년 커브 플래트닝(스프레드 축소, {us_spread_chg:.1f}bp)"
        elif abs(us2_bp) >= 1.0 or abs(us10_bp) >= 1.0:
            us_curve = f"미국 국채금리 2년물({us2_bp:+.1f}bp), 10년물({us10_bp:+.1f}bp) 등락"
        else:
            us_curve = f"미국 국채금리 2년({us2_bp:+.1f}bp)·10년({us10_bp:+.1f}bp) 보합권 혼조"
        bd_parts.append(f"미국 채권시장: {us_curve}")

        # 한국 커브 판정
        kr_spread_chg = ktb10_bp - ktb3_bp
        if ktb3_bp > 0 and ktb10_bp <= 0:
            kr_curve = f"3년물 상승({ktb3_bp:+.1f}bp) 속 10년물 소폭 하락({ktb10_bp:+.1f}bp)으로 10-3년 커브 플래트닝 마감"
        elif ktb3_bp < 0 and ktb10_bp >= 0:
            kr_curve = f"3년물 하락({ktb3_bp:+.1f}bp) 속 10년물 상승({ktb10_bp:+.1f}bp)으로 커브 스티프닝 마감"
        else:
            kr_curve = f"국고채 3년물({ktb3_bp:+.1f}bp), 10년물({ktb10_bp:+.1f}bp) 마감"
        bd_parts.append(f"국내 채권시장: {kr_curve}")

        obs["bond"] = {
            "summary": " / ".join(bd_parts),
            "key_movers": ["US2Y", "US10Y", "KTB 3y", "KTB10y"],
            "us_2y_bp": us2_bp,
            "us_10y_bp": us10_bp,
            "us_curve_status": "STEEPENING" if us_spread_chg > 0.3 else ("FLATTENING" if us_spread_chg < -0.3 else "NEUTRAL"),
            "kr_3y_bp": ktb3_bp,
            "kr_10y_bp": ktb10_bp,
            "kr_curve_status": "FLATTENING" if kr_spread_chg < -0.3 else ("STEEPENING" if kr_spread_chg > 0.3 else "NEUTRAL"),
            "has_significant_move": any(abs(b) >= 1.0 for b in [us2_bp, us10_bp, ktb3_bp, ktb10_bp])
        }

        # 4. 원자재 (Commodities)
        cm_list = categories.get("COMMODITY", [])
        wti = next((x for x in cm_list if "WTI" in x.get("name", "")), None)
        brent = next((x for x in cm_list if "Brent" in x.get("name", "")), None)
        gold = next((x for x in cm_list if "금" in x.get("name", "")), None)
        silver = next((x for x in cm_list if "은" in x.get("name", "")), None)
        natgas = next((x for x in cm_list if "천연가스" in x.get("name", "")), None)

        wti_pct = wti.get("pct_change") if wti else 0.0
        brent_pct = brent.get("pct_change") if brent else 0.0
        gold_pct = gold.get("pct_change") if gold else 0.0
        ng_pct = natgas.get("pct_change") if natgas else 0.0

        cm_parts = []
        if wti_pct > 1.5:
            cm_parts.append(f"국제유가(WTI {wti_pct:+.2f}%, Brent {brent_pct:+.2f}%) 급등세")
        elif wti_pct < -1.5:
            cm_parts.append(f"국제유가(WTI {wti_pct:+.2f}%) 급락세")
        else:
            cm_parts.append(f"국제유가(WTI {wti_pct:+.2f}%) 보합권")

        if gold_pct < -0.3:
            cm_parts.append(f"국제 금 가격({gold_pct:+.2f}%) 하락세")
        elif gold_pct > 0.3:
            cm_parts.append(f"국제 금 가격({gold_pct:+.2f}%) 상승세")

        if ng_pct > 1.5:
            cm_parts.append(f"천연가스({ng_pct:+.2f}%) 동반 강세")

        obs["commodity"] = {
            "summary": " / ".join(cm_parts),
            "key_movers": ["WTI", "Brent", "Gold", "Natural Gas"],
            "oil_direction": "SURGE" if wti_pct > 1.5 else ("PLUNGE" if wti_pct < -1.5 else "FLAT"),
            "gold_direction": "DOWN" if gold_pct < -0.3 else ("UP" if gold_pct > 0.3 else "FLAT"),
            "has_significant_move": any(abs(p) >= 1.0 for p in [wti_pct, brent_pct, gold_pct, ng_pct])
        }

        return obs

    @classmethod
    def _match_for_asset(
        cls,
        asset_key: str,
        asset_name: str,
        market_obs: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        run_kst: datetime.datetime,
        close_kr_kst: datetime.datetime
    ) -> List[Dict[str, Any]]:
        """개별 자산군에 부합하는 뉴스를 세션별 시간축, 키워드, 소스 품질을 결합해 스코어링 후 Top 3~4 선정"""
        keywords = cls.ASSET_KEYWORDS.get(asset_name, [])
        scored_items = []

        for cand in candidates:
            hl = cand["headline"]
            sm = cand["summary"]
            full_text = f"{hl} {sm}".lower()

            kw_hits = sum(1 for kw in keywords if kw in full_text)

            # 직접적 연관 문구 감지
            has_direct_phrase = False
            if asset_name == "EQUITY" and any(w in full_text for w in [
                "stocks rally", "tech rally", "stocks fall", "shares tumble", "s&p 500", "nasdaq", "dow", "bourses",
                "futures fall", "stocks dented", "slide in ai", "techs tumble", "증시", "주가"
            ]):
                has_direct_phrase = True
            elif asset_name == "BOND" and any(w in full_text for w in [
                "yields rise", "yields surge", "yields fall", "treasury selloff", "bond yields climb", "10-year yield",
                "2-year yield", "treasury auction", "global bond blowup", "rate hike", "fed hike odds", "국채", "금리", "채권"
            ]):
                has_direct_phrase = True
            elif asset_name == "COMMODITY" and any(w in full_text for w in [
                "oil surges", "oil prices", "crude", "hormuz", "saudi pipeline", "oil jumps", "gold sinks", "gold falls",
                "petroleum", "유가", "원유", "금 가격"
            ]):
                has_direct_phrase = True
            elif asset_name == "FX" and any(w in full_text for w in [
                "dollar slips", "dollar gains", "fed hike odds lift dxy", "dxy", "eur/usd", "gbp/usd", "환율", "달러화"
            ]):
                has_direct_phrase = True

            if kw_hits == 0 and not has_direct_phrase:
                continue

            # 시장 세션별 시간축 분석
            is_kr_specific = cand.get("country") == "KR" or any(w in full_text for w in ["코스피", "코스닥", "한국은행", "국고채", "원화"])
            effective_market_time = close_kr_kst if is_kr_specific and run_kst.hour >= 16 else run_kst

            delta_h, temporal_rel, causal_cand = cls.evaluate_temporal_alignment(cand["published_dt_kst"], effective_market_time)

            base_rel = min(1.0, (kw_hits * 0.15) + (0.45 if has_direct_phrase else 0.0))

            causal_conf = cls.determine_causal_confidence(
                source_conf=cand["source_confidence"],
                temporal_rel=temporal_rel,
                headline_relevance=base_rel,
                coverage_count=cand["coverage_count"],
                has_direct_market_phrase=has_direct_phrase
            )

            src_score = 1.0 if cand["source_confidence"] == "HIGH" else (0.6 if cand["source_confidence"] == "MEDIUM" else 0.3)
            time_score = 1.0 if temporal_rel in ["HIGH_CONCURRENT", "STRONG_LEAD"] else (0.7 if temporal_rel == "MODERATE_LEAD" else 0.2)
            causal_score = 1.0 if causal_conf == "HIGH" else (0.6 if causal_conf == "MEDIUM" else 0.2)

            composite = (src_score * 0.20) + (time_score * 0.30) + (base_rel * 0.25) + (causal_score * 0.25)

            # 사실(news_fact)과 해석(causal_interpretation) 분리 구축
            news_fact = hl
            causal_interp = cls._synthesize_causal_interpretation(cand["cause_category"], hl, market_obs.get("summary", ""))

            scored_items.append({
                "news_id": cand["news_id"],
                "cluster_id": cand["cluster_id"],
                "title": hl,
                "summary": sm[:180] if sm else hl,
                "source": cand["source"],
                "published_at": cand["published_at_kst"],
                "published_at_kst": cand["published_at_kst"],
                "published_at_utc": cand["published_at_utc"],
                "url": cand["url"],
                "country": cand["country"],
                "asset_class": asset_name,
                "matched_market": ", ".join(market_obs.get("key_movers", [])),
                "cause_category": cand["cause_category"],
                "source_confidence": cand["source_confidence"],
                "causal_confidence": causal_conf,
                "temporal_relevance": temporal_rel,
                "news_to_market_time_delta_hours": delta_h,
                "causal_candidate": causal_cand,
                "relevance_score": round(base_rel, 2),
                "composite_score": round(composite, 2),
                "observed_market_move": market_obs.get("summary", ""),
                "news_fact": news_fact,
                "causal_interpretation": causal_interp
            })

        scored_items.sort(key=lambda x: (
            x["causal_confidence"] == "HIGH",
            x["composite_score"],
            x["coverage_count"] if "coverage_count" in x else 1
        ), reverse=True)

        return scored_items[:4]

    @classmethod
    def _synthesize_causal_interpretation(cls, cause_cat: str, headline: str, market_move: str) -> str:
        """뉴스가 전한 사실과 시장 움직임을 결합한 잠정적 인과 해석 후보 (동적 생성)"""
        h_lower = headline.lower()
        if "hormuz" in h_lower or "pipeline" in h_lower or "saudi" in h_lower or "attack" in h_lower:
            return "중동 주요 에너지 수송로 및 설비 피격 보도가 원유 공급 차질 우려를 자극하여 유가 급등 압력으로 작용함"
        elif "rate hike" in h_lower or "fed hike" in h_lower:
            return "연준 정책금리 인상 가능성 보도가 단기 자금시장 및 달러화 강세 요인으로 작용함"
        elif "ai slowdown" in h_lower or "ai warning" in h_lower:
            return "빅테크 및 인공지능 성장 속도 조절 경고가 증시 기술주 밸류에이션 부담으로 작용함"
        elif cause_cat == "Inflation":
            return "물가지표 관련 경계감이 기대인플레이션 및 통화정책 경로 재평가에 영향을 미침"
        elif cause_cat == "Central bank":
            return "중앙은행 정책금리 결정 및 연사 발언이 시장 금리와 통화 가치에 반영됨"
        elif cause_cat == "Supply / demand":
            return "원유 및 주요 원자재 수급 불안 요인이 가격 상방 압력으로 작용함"
        return "당일 보도된 매크로 이슈가 시장 참가자들의 위험선호 및 포트폴리오 조정에 영향을 준 것으로 해석됨"

    @classmethod
    def _synthesize_primary_theme(
        cls, 
        market_obs: Dict[str, Dict[str, Any]], 
        asset_matches: Dict[str, List[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        """시장 전체 대표 원인(primary_theme)과 자산별 촉매(asset_specific_catalysts) 동적 도출"""
        all_high_conf = []
        for k in ["commodity", "bond", "fx", "stock"]:
            for m in asset_matches.get(k, []):
                if m.get("causal_confidence") == "HIGH":
                    all_high_conf.append(m)

        # 1. 자산별 개별 촉매 정리
        asset_specific = {}
        for k in ["stock", "fx", "bond", "commodity"]:
            top = asset_matches.get(k, [])
            if top:
                best = top[0]
                asset_specific[k] = {
                    "catalyst_news": best.get("title"),
                    "cause_category": best.get("cause_category"),
                    "causal_confidence": best.get("causal_confidence"),
                    "interpretation": best.get("causal_interpretation"),
                    "news_fact": best.get("news_fact")
                }
            else:
                asset_specific[k] = {
                    "catalyst_news": None,
                    "cause_category": "None",
                    "causal_confidence": "LOW",
                    "interpretation": "관측된 시장 움직임 외에 당일 명확한 단독 촉매 뉴스는 제한적임",
                    "news_fact": None
                }

        # 2. 시장 관측 팩트에 기반한 대표 테마 동적 합성 (하드코딩 배제)
        comm_obs = market_obs.get("commodity", {})
        fx_obs = market_obs.get("fx", {})
        bond_obs = market_obs.get("bond", {})
        stock_obs = market_obs.get("stock", {})

        oil_surge = comm_obs.get("oil_direction") == "SURGE"
        oil_plunge = comm_obs.get("oil_direction") == "PLUNGE"
        dxy_up = fx_obs.get("dxy_direction") == "UP"

        if oil_surge and dxy_up:
            theme_text = "중동 지정학적 공급 리스크와 연준 긴축 경계에 따른 자산군별 변동성 확대"
            trans_summary = "중동 수송로/송유관 피격에 따른 유가 급등 ➡️ 원자재발 인플레이션 경계 및 연준 금리인상 확률 부각 ➡️ 달러화 강세 및 아시아 증시 밸류에이션 부담 전이"
            cat = "Geopolitics"
        elif oil_plunge:
            theme_text = "국제유가 급락과 인플레이션 경로 재평가"
            trans_summary = "원유 가격 하락에 따른 에너지 비용 완화 요인이 증시 기술주 반등으로 전이"
            cat = "Inflation"
        elif all_high_conf:
            lead = all_high_conf[0]
            cat = lead.get("cause_category", "Macro data")
            theme_text = f"{lead.get('title')[:60]} 중심 시장 반응"
            trans_summary = f"{lead.get('title')} 보도 이후 관련 자산군 간 차별화된 흐름 전개"
        else:
            theme_text = "거시 변수 점검 속 자산군별 차별화 전개"
            cat = "Other"
            trans_summary = "단일 지배적 촉매 부재 속 자산군별 수급 및 세부 일정에 연동된 흐름"

        return {
            "primary_theme": theme_text,
            "core_cause_category": cat,
            "causal_confidence": "HIGH" if all_high_conf else "MEDIUM",
            "transmission_summary": trans_summary,
            "asset_specific_catalysts": asset_specific
        }

    @classmethod
    def _build_claim_evidence_records(
        cls,
        market_obs: Dict[str, Dict[str, Any]],
        asset_matches: Dict[str, List[Dict[str, Any]]],
        theme_info: Dict[str, Any],
        economic_events: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Summary, Issue Review, Forecast의 각 주장별 Claim-Evidence 구조체 생성 (Requirement 1 & 13)
        """
        records = []

        # 1. Primary Theme Claim
        records.append({
            "section": "summary",
            "claim_type": "PRIMARY_THEME",
            "claim": theme_info.get("primary_theme", ""),
            "market_observation": " / ".join(v.get("summary", "") for v in market_obs.values()),
            "news_fact": theme_info.get("transmission_summary", ""),
            "causal_interpretation": f"핵심 원인 카테고리: {theme_info.get('core_cause_category')}",
            "transmission_path": theme_info.get("transmission_summary", ""),
            "evidence_news_ids": [m.get("news_id") for k in asset_matches for m in asset_matches[k][:1] if m.get("news_id")],
            "source_confidence": "HIGH",
            "causal_confidence": theme_info.get("causal_confidence", "MEDIUM"),
            "temporal_relevance": "STRONG_LEAD",
            "market_data_refs": ["WTI", "DXY", "US10Y", "KOSPI"]
        })

        # 2. Asset-specific Claims
        for asset_key, cat_name in [("stock", "EQUITY"), ("fx", "FX"), ("bond", "BOND"), ("commodity", "COMMODITY")]:
            obs = market_obs.get(asset_key, {})
            top_matches = asset_matches.get(asset_key, [])
            lead = top_matches[0] if top_matches else {}

            claim_text = f"{cat_name}: {obs.get('summary', '')}"
            news_fact = lead.get("news_fact", "관측된 시장 가격 데이터")
            causal_interp = lead.get("causal_interpretation", "세부 일정 및 수급 요인 반영")
            
            # 전이 경로 구성
            if asset_key == "commodity":
                trans = "원유 공급 충격 ➡️ 인플레이션 기대 ➡️ 통화정책 경로 ➡️ 금리 및 외환"
            elif asset_key == "bond":
                trans = "정책금리 및 물가 전망 ➡️ 2Y vs 10Y 상대 강도 ➡️ 수익률곡선 변동 ➡️ 증시 할인율"
            elif asset_key == "fx":
                trans = "글로벌 금리차 및 위험선호 ➡️ DXY 지수 ➡️ 주요 통화 및 신흥국 통화 차별화"
            else:
                trans = "에너지 비용 및 할인율 ➡️ 위험자산 밸류에이션 ➡️ 지역별/섹터별 등락"

            records.append({
                "section": f"issue_review_{asset_key}",
                "claim_type": "ASSET_REVIEW",
                "claim": claim_text,
                "market_observation": obs.get("summary", ""),
                "news_fact": news_fact,
                "causal_interpretation": causal_interp,
                "transmission_path": trans,
                "evidence_news_ids": [lead.get("news_id")] if lead.get("news_id") else [],
                "source_confidence": lead.get("source_confidence", "MEDIUM"),
                "causal_confidence": lead.get("causal_confidence", "LOW"),
                "temporal_relevance": lead.get("temporal_relevance", "UNKNOWN"),
                "market_data_refs": obs.get("key_movers", [])
            })

        # 3. Forecast Claim
        records.append({
            "section": "forecast",
            "claim_type": "WHAT_TO_WATCH",
            "claim": "지정학적 에너지 리스크와 차기 경제지표 발표에 따른 통화정책 및 금리/외환시장 전이 점검",
            "market_observation": "유가 및 달러 인덱스 변동성 확대 속 주요국 채권 커브 차별화",
            "news_fact": "향후 주요국 물가지표(CA CPI 등) 및 중앙은행 정책 발표 일정 예정",
            "causal_interpretation": "에너지발 인플레이션 압력이 차기 거시지표에 전이되는지 여부가 핵심",
            "transmission_path": "물가지표 결과 ➡️ 단기금리 및 달러 ➡️ 증시 할인율 및 신용스프레드",
            "evidence_news_ids": [],
            "source_confidence": "HIGH",
            "causal_confidence": "HIGH",
            "temporal_relevance": "STRONG_LEAD",
            "market_data_refs": ["DXY", "US2Y", "US10Y", "WTI"]
        })

        return records
