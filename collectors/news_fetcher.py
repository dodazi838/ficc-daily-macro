"""
[FICC Daily Macro] 공식 RSS 및 금융 API 기반 매크로 뉴스 수집기 (news_fetcher.py)
- 지원 소스:
    1. Federal Reserve 공식 Press Releases RSS
    2. ECB (유럽중앙은행) 공식 Press Releases RSS
    3. MarketWatch Top Stories & Bulletins RSS
    4. Yahoo Finance News API (자산군 티커 연계)
- 특징:
    • 각 소스는 독립적인 Fetcher 클래스로 모듈화 (플러그형 구조)
    • 원문 description/summary가 존재할 경우 보존, 임의의 AI 요약 생성 배제
    • 소스별 수집 상태(SUCCESS/PARTIAL/ERROR) 및 건수 추적
    • Timezone-aware datetime 완벽 보장
"""

import datetime
import dateutil.parser
import pytz
import requests
import xml.etree.ElementTree as ET
import yfinance as yf
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

KST_TZ = pytz.timezone('Asia/Seoul')
UTC_TZ = pytz.utc
HTTP_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def ensure_kst_aware(dt: datetime.datetime) -> datetime.datetime:
    """datetime 객체를 Asia/Seoul 타임존 인식 객체로 보장"""
    if dt is None:
        return datetime.datetime.now(KST_TZ)
    if dt.tzinfo is None:
        return KST_TZ.localize(dt)
    return dt.astimezone(KST_TZ)

class BaseNewsFetcher(ABC):
    """뉴스 수집기 어댑터 기본 클래스"""
    def __init__(self, source_name: str, tier: int = 1):
        self.source_name = source_name
        self.tier = tier  # 1: 중앙은행/공식통신사, 2: 주요 금융미디어

    @abstractmethod
    def fetch(self, run_time_kst: datetime.datetime, lookback_hours: int = 36) -> Dict[str, Any]:
        pass

    @staticmethod
    def parse_datetime_to_kst(dt_raw: Any) -> Optional[datetime.datetime]:
        """다양한 형식의 날짜 문자열/타임스탬프를 KST timezone-aware datetime 객체로 변환"""
        if not dt_raw:
            return None
        try:
            if isinstance(dt_raw, (int, float)):
                # Unix timestamp
                dt = datetime.datetime.fromtimestamp(dt_raw, tz=pytz.utc)
                return dt.astimezone(KST_TZ)
            elif isinstance(dt_raw, str):
                dt = dateutil.parser.parse(dt_raw)
                if dt.tzinfo is None:
                    dt = pytz.utc.localize(dt)
                return dt.astimezone(KST_TZ)
        except Exception:
            return None
        return None

class FedNewsFetcher(BaseNewsFetcher):
    """미국 연방준비제도(Federal Reserve) 공식 보도자료 RSS 수집기"""
    def __init__(self):
        super().__init__(source_name="Federal Reserve", tier=1)
        self.url = "https://www.federalreserve.gov/feeds/press_all.xml"

    def fetch(self, run_time_kst: datetime.datetime, lookback_hours: int = 36) -> Dict[str, Any]:
        articles = []
        status = "SUCCESS"
        error_msg = None
        run_kst = ensure_kst_aware(run_time_kst)
        cutoff_kst = run_kst - datetime.timedelta(hours=lookback_hours)

        try:
            resp = requests.get(self.url, headers=HTTP_HEADERS, timeout=4)
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                items = root.findall(".//item")
                for item in items:
                    title_elem = item.find("title")
                    link_elem = item.find("link")
                    pub_elem = item.find("pubDate")
                    desc_elem = item.find("description")

                    headline = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
                    link = link_elem.text.strip() if link_elem is not None and link_elem.text else ""
                    pub_raw = pub_elem.text.strip() if pub_elem is not None and pub_elem.text else ""
                    summary = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else None

                    pub_kst = self.parse_datetime_to_kst(pub_raw)
                    if not headline or not link or not pub_kst:
                        continue

                    if pub_kst >= cutoff_kst:
                        articles.append({
                            "headline": headline,
                            "source": self.source_name,
                            "source_tier": self.tier,
                            "url": link,
                            "published_at": pub_raw,
                            "published_at_kst": pub_kst.strftime("%Y-%m-%d %H:%M:%S KST"),
                            "published_dt_kst": pub_kst,
                            "country": "US",
                            "category_hint": "MONETARY",
                            "summary": summary
                        })
            else:
                status = "ERROR"
                error_msg = f"HTTP {resp.status_code}"
        except Exception as e:
            status = "ERROR"
            error_msg = str(e)

        return {
            "source": self.source_name,
            "status": status,
            "count": len(articles),
            "error_message": error_msg,
            "articles": articles
        }

class EcbNewsFetcher(BaseNewsFetcher):
    """유럽중앙은행(ECB) 공식 보도자료 RSS 수집기"""
    def __init__(self):
        super().__init__(source_name="ECB", tier=1)
        self.url = "https://www.ecb.europa.eu/rss/press.html"

    def fetch(self, run_time_kst: datetime.datetime, lookback_hours: int = 36) -> Dict[str, Any]:
        articles = []
        status = "SUCCESS"
        error_msg = None
        run_kst = ensure_kst_aware(run_time_kst)
        cutoff_kst = run_kst - datetime.timedelta(hours=lookback_hours)

        try:
            resp = requests.get(self.url, headers=HTTP_HEADERS, timeout=4)
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                items = root.findall(".//item")
                for item in items:
                    title_elem = item.find("title") or item.find("{http://purl.org/rss/1.0/}title")
                    link_elem = item.find("link") or item.find("{http://purl.org/rss/1.0/}link")
                    pub_elem = item.find("pubDate") or item.find("{http://purl.org/dc/elements/1.1/}date")
                    desc_elem = item.find("description") or item.find("{http://purl.org/rss/1.0/}description")

                    headline = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
                    link = link_elem.text.strip() if link_elem is not None and link_elem.text else ""
                    pub_raw = pub_elem.text.strip() if pub_elem is not None and pub_elem.text else ""
                    summary = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else None

                    pub_kst = self.parse_datetime_to_kst(pub_raw)
                    if not headline or not link or not pub_kst:
                        continue

                    if pub_kst >= cutoff_kst:
                        articles.append({
                            "headline": headline,
                            "source": self.source_name,
                            "source_tier": self.tier,
                            "url": link,
                            "published_at": pub_raw,
                            "published_at_kst": pub_kst.strftime("%Y-%m-%d %H:%M:%S KST"),
                            "published_dt_kst": pub_kst,
                            "country": "EU",
                            "category_hint": "MONETARY",
                            "summary": summary
                        })
            else:
                status = "ERROR"
                error_msg = f"HTTP {resp.status_code}"
        except Exception as e:
            status = "ERROR"
            error_msg = str(e)

        return {
            "source": self.source_name,
            "status": status,
            "count": len(articles),
            "error_message": error_msg,
            "articles": articles
        }

class MarketWatchNewsFetcher(BaseNewsFetcher):
    """MarketWatch 거시 및 시장 주요 뉴스 RSS 수집기"""
    def __init__(self):
        super().__init__(source_name="MarketWatch", tier=2)
        self.urls = [
            "https://feeds.content.marketwatch.com/marketwatch/topstories/",
            "https://feeds.content.marketwatch.com/marketwatch/bulletins"
        ]

    def fetch(self, run_time_kst: datetime.datetime, lookback_hours: int = 36) -> Dict[str, Any]:
        articles = []
        status = "SUCCESS"
        errors = []
        run_kst = ensure_kst_aware(run_time_kst)
        cutoff_kst = run_kst - datetime.timedelta(hours=lookback_hours)

        for u in self.urls:
            try:
                resp = requests.get(u, headers=HTTP_HEADERS, timeout=4)
                if resp.status_code == 200:
                    root = ET.fromstring(resp.content)
                    items = root.findall(".//item")
                    for item in items:
                        title_elem = item.find("title")
                        link_elem = item.find("link")
                        pub_elem = item.find("pubDate")
                        desc_elem = item.find("description")

                        headline = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
                        link = link_elem.text.strip() if link_elem is not None and link_elem.text else ""
                        pub_raw = pub_elem.text.strip() if pub_elem is not None and pub_elem.text else ""
                        summary = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else None

                        pub_kst = self.parse_datetime_to_kst(pub_raw)
                        if not headline or not link or not pub_kst:
                            continue

                        if pub_kst >= cutoff_kst:
                            articles.append({
                                "headline": headline,
                                "source": self.source_name,
                                "source_tier": self.tier,
                                "url": link,
                                "published_at": pub_raw,
                                "published_at_kst": pub_kst.strftime("%Y-%m-%d %H:%M:%S KST"),
                                "published_dt_kst": pub_kst,
                                "country": "US",
                                "category_hint": "MARKET",
                                "summary": summary
                            })
                else:
                    errors.append(f"{u} (HTTP {resp.status_code})")
            except Exception as e:
                errors.append(f"{u} ({e})")

        if errors and len(articles) == 0:
            status = "ERROR"
        elif errors and len(articles) > 0:
            status = "PARTIAL"

        return {
            "source": self.source_name,
            "status": status,
            "count": len(articles),
            "error_message": "; ".join(errors) if errors else None,
            "articles": articles
        }

class YahooFinanceNewsFetcher(BaseNewsFetcher):
    """Yahoo Finance API 및 메이저 매크로 지표 티커 연계 뉴스 수집기"""
    def __init__(self):
        super().__init__(source_name="Yahoo Finance", tier=2)
        self.macro_tickers = ["^TNX", "DX-Y.NYB", "CL=F", "^GSPC", "GC=F"]

    def fetch(self, run_time_kst: datetime.datetime, lookback_hours: int = 36) -> Dict[str, Any]:
        articles = []
        status = "SUCCESS"
        errors = []
        run_kst = ensure_kst_aware(run_time_kst)
        cutoff_kst = run_kst - datetime.timedelta(hours=lookback_hours)

        for ticker in self.macro_tickers:
            try:
                t = yf.Ticker(ticker)
                raw_news = t.news
                if not raw_news:
                    continue

                for item in raw_news:
                    content = item.get("content", item)
                    headline = content.get("title", "")
                    publisher = content.get("provider", {}).get("displayName", item.get("publisher", "Yahoo Finance"))
                    
                    link = ""
                    canonical_url = content.get("canonicalUrl", {})
                    if isinstance(canonical_url, dict):
                        link = canonical_url.get("url", "")
                    elif isinstance(canonical_url, str):
                        link = canonical_url
                    if not link:
                        link = item.get("link", "")

                    pub_ts = item.get("providerPublishTime") or content.get("pubDate")
                    summary = content.get("summary", item.get("summary", None))

                    pub_kst = self.parse_datetime_to_kst(pub_ts)
                    if not headline or not link or not pub_kst:
                        continue

                    if pub_kst >= cutoff_kst:
                        articles.append({
                            "headline": headline,
                            "source": f"{self.source_name} ({publisher})",
                            "source_tier": self.tier,
                            "url": link,
                            "published_at": str(pub_ts),
                            "published_at_kst": pub_kst.strftime("%Y-%m-%d %H:%M:%S KST"),
                            "published_dt_kst": pub_kst,
                            "country": "US",
                            "category_hint": "TICKER_MACRO",
                            "summary": summary
                        })
            except Exception as e:
                errors.append(f"{ticker} ({e})")

        if errors and len(articles) == 0:
            status = "ERROR"
        elif errors and len(articles) > 0:
            status = "PARTIAL"

        return {
            "source": self.source_name,
            "status": status,
            "count": len(articles),
            "error_message": "; ".join(errors) if errors else None,
            "articles": articles
        }

class MacroNewsCollector:
    """모든 뉴스 Fetcher를 통합 실행하고 수집 통계를 집계하는 오케스트레이터"""
    def __init__(self):
        self.fetchers: List[BaseNewsFetcher] = [
            FedNewsFetcher(),
            EcbNewsFetcher(),
            MarketWatchNewsFetcher(),
            YahooFinanceNewsFetcher()
        ]

    def collect_all(self, run_time_kst: datetime.datetime, lookback_hours: int = 36) -> Dict[str, Any]:
        from concurrent.futures import ThreadPoolExecutor
        all_raw_articles = []
        source_reports = []

        with ThreadPoolExecutor(max_workers=4) as executor:
            reports = list(executor.map(lambda f: f.fetch(run_time_kst, lookback_hours=lookback_hours), self.fetchers))

        for report in reports:
            source_reports.append({
                "source": report["source"],
                "status": report["status"],
                "count": report["count"],
                "error_message": report["error_message"]
            })
            all_raw_articles.extend(report.get("articles", []))

        total_collected = len(all_raw_articles)
        overall_status = "SUCCESS"
        if any(r["status"] == "ERROR" for r in source_reports):
            overall_status = "PARTIAL" if total_collected > 0 else "ERROR"

        return {
            "collected_at_kst": ensure_kst_aware(run_time_kst).strftime("%Y-%m-%d %H:%M:%S KST"),
            "overall_status": overall_status,
            "total_raw_count": total_collected,
            "source_reports": source_reports,
            "raw_articles": all_raw_articles
        }
