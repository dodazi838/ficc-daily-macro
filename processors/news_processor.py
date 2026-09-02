"""
[FICC Daily Macro] 뉴스 데이터 정규화, 중복 제거, 이벤트 클러스터링 및 중요도 판정기 (news_processor.py)
"""

import re
import hashlib
import datetime
import pytz
from urllib.parse import urlparse, urlunparse
from typing import List, Dict, Any, Tuple, Optional

KST_TZ = pytz.timezone('Asia/Seoul')

def ensure_kst_aware(dt: datetime.datetime) -> datetime.datetime:
    """datetime 객체를 Asia/Seoul 타임존 인식 객체로 보장"""
    if dt is None:
        return datetime.datetime.now(KST_TZ)
    if dt.tzinfo is None:
        return KST_TZ.localize(dt)
    return dt.astimezone(KST_TZ)

class MacroNewsProcessor:
    """원천 뉴스 목록을 가공하여 대표 기사 + 관련 기사 보존형 클러스터 및 정형 데이터셋 생성"""

    @classmethod
    def process_news(cls, raw_articles: List[Dict[str, Any]], run_time_kst: datetime.datetime) -> Dict[str, Any]:
        if not raw_articles:
            return {
                "total_raw": 0,
                "total_unique": 0,
                "total_clusters": 0,
                "event_clusters": [],
                "all_processed_articles": []
            }

        run_kst = ensure_kst_aware(run_time_kst)

        # 1. URL 정규화 및 1차 완전 중복 제거
        unique_by_url = cls._deduplicate_by_url(raw_articles)

        # 2. 메타데이터 태깅 (카테고리, 국가, 중요도, 관련 자산군, 타임 윈도우)
        tagged_articles = []
        for idx, art in enumerate(unique_by_url):
            tagged = cls._enrich_article_metadata(art, idx + 1, run_kst)
            tagged_articles.append(tagged)

        # 3. 헤드라인 유사도 및 시간 근접 기반 클러스터링 (대표 기사 + 관련 기사 보존)
        event_clusters = cls._cluster_events(tagged_articles)

        return {
            "total_raw": len(raw_articles),
            "total_unique": len(tagged_articles),
            "total_clusters": len(event_clusters),
            "event_clusters": event_clusters,
            "all_processed_articles": tagged_articles
        }

    @staticmethod
    def normalize_url(url: str) -> str:
        """URL에서 불필요한 트래킹 파라미터(utm, ref 등) 제거 후 정규화"""
        if not url:
            return ""
        try:
            parsed = urlparse(url)
            clean_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
            return clean_url.rstrip("/")
        except Exception:
            return url.strip()

    @classmethod
    def _deduplicate_by_url(cls, raw_articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """정규화된 URL 기준으로 1차 중복 제거"""
        seen_urls = set()
        unique = []
        for art in raw_articles:
            raw_url = art.get("url", "")
            norm_url = cls.normalize_url(raw_url)
            if norm_url and norm_url not in seen_urls:
                seen_urls.add(norm_url)
                art["normalized_url"] = norm_url
                unique.append(art)
        return unique

    @staticmethod
    def normalize_headline(headline: str) -> str:
        """헤드라인 텍스트 정규화 (특수문자 제거, 소문자화)"""
        if not headline:
            return ""
        text = re.sub(r'[^a-zA-Z0-9가-힣\s]', ' ', headline)
        tokens = [t.lower() for t in text.split() if len(t) > 1]
        return " ".join(tokens)

    @classmethod
    def calculate_headline_similarity(cls, h1: str, h2: str) -> float:
        """두 헤드라인 간의 Jaccard 토큰 유사도 계산"""
        tokens1 = set(cls.normalize_headline(h1).split())
        tokens2 = set(cls.normalize_headline(h2).split())
        if not tokens1 or not tokens2:
            return 0.0
        intersection = len(tokens1.intersection(tokens2))
        union = len(tokens1.union(tokens2))
        return intersection / union if union > 0 else 0.0

    @classmethod
    def _enrich_article_metadata(cls, art: Dict[str, Any], seq: int, run_kst: datetime.datetime) -> Dict[str, Any]:
        """기사 텍스트 기반 다차원 메타데이터 추출 및 태깅"""
        headline = art.get("headline", "")
        summary = art.get("summary") or ""
        combined_text = f"{headline} {summary}".lower()
        pub_dt = art.get("published_dt_kst")
        if pub_dt:
            pub_dt = ensure_kst_aware(pub_dt)

        # 1. 국가 (Country) 판정
        country = art.get("country", "GLOBAL")
        if any(w in combined_text for w in ["fed", "federal reserve", "powell", "treasury", "wall street", "us ", "u.s.", "cpi", "nfp"]):
            country = "US"
        elif any(w in combined_text for w in ["bok", "bank of korea", "한국은행", "금통위", "국고채", "원/달러", "코스피"]):
            country = "KR"
        elif any(w in combined_text for w in ["ecb", "lagarde", "eurozone", "germany", "bund"]):
            country = "EU"
        elif any(w in combined_text for w in ["boj", "ueda", "yen", "japan", "jgb"]):
            country = "JP"
        elif any(w in combined_text for w in ["pboc", "china", "beijing", "yuan", "cnh"]):
            country = "CN"

        # 2. 카테고리 (Category) 판정
        category = "MARKET"
        if any(w in combined_text for w in ["rate", "fed", "fomc", "ecb", "bok", "boj", "monetary", "interest rate", "cut", "hike", "금리", "통화정책"]):
            category = "MONETARY"
        elif any(w in combined_text for w in ["cpi", "ppi", "inflation", "pce", "jobs", "payrolls", "unemployment", "gdp", "pmi", "물가", "고용"]):
            category = "INDICATOR"
        elif any(w in combined_text for w in ["oil", "wti", "brent", "opec", "crude", "gold", "gas", "copper", "원유", "금", "원자재"]):
            category = "COMMODITY"
        elif any(w in combined_text for w in ["war", "sanction", "tariff", "israel", "iran", "russia", "taiwan", "관세", "지정학"]):
            category = "GEOPOLITICS"

        # 3. 관련 자산군 (Related Assets) 매핑
        related_assets = []
        if category == "MONETARY" or "treasury" in combined_text or "yield" in combined_text or "국채" in combined_text:
            related_assets.extend(["US10Y", "US2Y", "KTB 3y", "KTB10y", "DXY"])
        if "dollar" in combined_text or "환율" in combined_text or "fx" in combined_text or "currency" in combined_text:
            related_assets.extend(["USD/KRW", "USD/JPY", "EUR/USD", "DXY"])
        if category == "COMMODITY" or "oil" in combined_text or "유가" in combined_text:
            related_assets.extend(["WTI", "Brent", "Gold"])
        if "stock" in combined_text or "equity" in combined_text or "nasdaq" in combined_text or "s&p" in combined_text or "증시" in combined_text:
            related_assets.extend(["S&P 500", "NASDAQ", "KOSPI", "VIX"])
        if not related_assets:
            related_assets = ["S&P 500", "US10Y", "DXY"]
        related_assets = list(dict.fromkeys(related_assets))

        # 4. 다차원 중요도 (Importance) 산출
        importance_score = 0
        if category in ["MONETARY", "INDICATOR"]:
            importance_score += 3
        elif category in ["GEOPOLITICS", "COMMODITY"]:
            importance_score += 2
        else:
            importance_score += 1

        if country in ["US", "KR"]:
            importance_score += 2
        elif country in ["EU", "CN", "JP"]:
            importance_score += 1

        if art.get("source_tier", 2) == 1:
            importance_score += 2

        if any(w in combined_text for w in ["emergency", "surprise", "sharp", "plunge", "surge", "shock", "급등", "급락", "쇼크"]):
            importance_score += 2

        if importance_score >= 6:
            importance = "HIGH"
        elif importance_score >= 4:
            importance = "MEDIUM"
        else:
            importance = "LOW"

        # 5. 16:30 KST 기준 타임 윈도우 판정
        time_window = "DAY_REVIEW"
        if pub_dt:
            today_1630 = run_kst.replace(hour=16, minute=30, second=0, microsecond=0)
            yesterday_1630 = today_1630 - datetime.timedelta(days=1)
            
            if pub_dt < yesterday_1630:
                time_window = "PAST"
            elif pub_dt <= today_1630:
                time_window = "DAY_REVIEW"
            else:
                time_window = "TODAY_NIGHT"

        date_str = run_kst.strftime("%Y%m%d")
        item_id = f"NEWS_{date_str}_{country}_{seq:03d}"

        return {
            "id": item_id,
            "headline": headline,
            "source": art.get("source", "UNKNOWN"),
            "url": art.get("url", ""),
            "published_at": art.get("published_at", ""),
            "published_at_kst": art.get("published_at_kst", ""),
            "published_dt_kst": pub_dt,
            "country": country,
            "category": category,
            "importance": importance,
            "related_assets": related_assets,
            "time_window": time_window,
            "summary": summary if summary else None,
            "source_tier": art.get("source_tier", 2),
            "event_id": None
        }

    @classmethod
    def _cluster_events(cls, tagged_articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """유사 헤드라인 및 시간 근접 기사를 동일 이벤트 클러스터로 묶고 대표 기사 선정"""
        clusters = []
        assigned = set()

        for i, art in enumerate(tagged_articles):
            if i in assigned:
                continue

            cluster_members = [art]
            assigned.add(i)

            h1 = art["headline"]
            dt1 = art.get("published_dt_kst")

            for j in range(i + 1, len(tagged_articles)):
                if j in assigned:
                    continue
                cand = tagged_articles[j]
                h2 = cand["headline"]
                dt2 = cand.get("published_dt_kst")

                time_diff_hours = abs((dt1 - dt2).total_seconds()) / 3600.0 if (dt1 and dt2) else 0.0
                sim = cls.calculate_headline_similarity(h1, h2)

                if (sim >= 0.40 and time_diff_hours <= 6.0) or (art["category"] == cand["category"] and art["country"] == cand["country"] and sim >= 0.30 and time_diff_hours <= 2.0):
                    cluster_members.append(cand)
                    assigned.add(j)

            cluster_members.sort(key=lambda x: (
                x.get("source_tier", 2) == 1,
                len(x.get("summary") or ""),
                x.get("published_at_kst", "")
            ), reverse=True)

            rep_art = cluster_members[0]
            cluster_id = f"EVT_{rep_art['id']}"

            for m in cluster_members:
                m["event_id"] = cluster_id

            related_list = []
            for m in cluster_members[1:]:
                related_list.append({
                    "id": m["id"],
                    "headline": m["headline"],
                    "source": m["source"],
                    "url": m["url"],
                    "published_at_kst": m["published_at_kst"]
                })

            clusters.append({
                "event_id": cluster_id,
                "event_cluster_name": rep_art["headline"],
                "country": rep_art["country"],
                "category": rep_art["category"],
                "importance": rep_art["importance"],
                "time_window": rep_art["time_window"],
                "representative_article": rep_art,
                "related_articles": related_list,
                "total_coverage_count": len(cluster_members),
                "related_assets": rep_art["related_assets"]
            })

        return clusters
