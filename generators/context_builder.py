"""
[FICC Daily Macro] AI 컨텍스트 빌더 (context_builder.py)
- 레퍼런스 PDF 순서(외환 -> 채권 -> 원자재 -> 증시) 정렬
- as_of 및 basis 메타데이터 명확화 (국내/아시아 당일 종가 vs 미국/유럽/원자재 직전 거래일 종가)
- LOW 노이즈 뉴스 배제, HIGH 및 핵심 MEDIUM 뉴스만 선별 주입
- 3-Way 경제 캘린더 핵심 이벤트 정제
"""

import json
from typing import Dict, Any, List

class AIContextBuilder:
    """1~3단계 가공 데이터에서 AI 시황 작성용 핵심 컨텍스트를 추출/정제하는 빌더"""

    @classmethod
    def build_context(cls, processed_data: Dict[str, Any]) -> Dict[str, Any]:
        report_date = processed_data.get("report_date", "")
        market_data = processed_data.get("market_data", {})
        news_events = processed_data.get("news_events", {})
        economic_events = processed_data.get("economic_events", {})

        # 1. 레퍼런스 PDF 순서대로 시장 데이터 정제 (FX -> Bond -> Commodity -> Equity)
        categories = market_data.get("categories", {})
        
        # 외환 (FX)
        fx_items = []
        for it in categories.get("FX", []):
            fx_items.append({
                "field_id": f"FX.{it.get('symbol')}",
                "name": it.get("name"),
                "current": it.get("current"),
                "change_pct": round(it.get("pct_change", 0.0), 2) if it.get("pct_change") is not None else None,
                "unit": it.get("unit"),
                "as_of": it.get("actual_as_of_kst", "16:30 KST 기준"),
                "basis": "KST_16:30_기준"
            })

        # 채권 (Bonds) & 핵심 스프레드
        bond_items = []
        for it in categories.get("BOND", []):
            is_kr = "한국" in it.get("name", "") or "KTB" in it.get("name", "")
            bond_items.append({
                "field_id": f"BOND.{it.get('symbol')}",
                "name": it.get("name"),
                "current": it.get("current"),
                "change_bp": round(it.get("bp_change", 0.0), 1) if it.get("bp_change") is not None else None,
                "unit": it.get("unit"),
                "as_of": it.get("actual_as_of_kst", "16:30 KST 기준" if is_kr else "직전 거래일 종가"),
                "basis": "KST_16:30_기준" if is_kr else "previous_trading_day_close (직전 현지 거래일 종가)"
            })

        spreads = []
        for sp in market_data.get("spreads", []):
            spreads.append({
                "name": sp.get("name"),
                "current_bp": round(sp.get("current_bp", 0.0), 1) if sp.get("current_bp") is not None else None,
                "change_bp": round(sp.get("change_bp", 0.0), 1) if sp.get("change_bp") is not None else None,
                "description": sp.get("description")
            })

        # 원자재 (Commodity)
        commodity_items = []
        for it in categories.get("COMMODITY", []):
            commodity_items.append({
                "field_id": f"COMMODITY.{it.get('symbol')}",
                "name": it.get("name"),
                "current": it.get("current"),
                "change_pct": round(it.get("pct_change", 0.0), 2) if it.get("pct_change") is not None else None,
                "unit": it.get("unit"),
                "as_of": it.get("actual_as_of_kst", "직전 거래일 종가"),
                "basis": "previous_trading_day_close (직전 거래일 종가)"
            })

        # 증시 (Equity)
        equity_items = []
        for it in categories.get("EQUITY", []):
            sym = it.get("symbol", "")
            is_asian = sym in ["^KS11", "^KQ11", "000001.SS", "^HSI", "^N225"]
            equity_items.append({
                "field_id": f"EQUITY.{it.get('symbol')}",
                "name": it.get("name"),
                "current": it.get("current"),
                "change_pct": round(it.get("pct_change", 0.0), 2) if it.get("pct_change") is not None else None,
                "unit": it.get("unit"),
                "as_of": it.get("actual_as_of_kst", "당일 현지 종가" if is_asian else "직전 거래일 종가"),
                "basis": "local_market_close (당일 현지 종가)" if is_asian else "previous_trading_day_close (직전 현지 거래일 종가)"
            })

        # 2. 뉴스 필터링: LOW 노이즈 제외, HIGH 전체 + 상위 MEDIUM 선별
        all_clusters = news_events.get("event_clusters", [])
        filtered_news = []
        for c in all_clusters:
            imp = c.get("importance", "LOW")
            if imp in ["HIGH", "MEDIUM"]:
                rep = c.get("representative_article", {})
                filtered_news.append({
                    "news_id": rep.get("id"),
                    "headline": rep.get("headline"),
                    "category": rep.get("category"),
                    "country": rep.get("country"),
                    "importance": imp,
                    "related_assets": rep.get("related_assets", []),
                    "summary": rep.get("summary")
                })

        # 3. 경제 캘린더 정제 (DAY_REVIEW + TODAY_NIGHT)
        # ※ 16:30 KST 이후 야간 발표 예정 이벤트는 단일 원천 데이터(SSOT)로 관리
        from generators.blog_formatter import NaverBlogFormatter
        
        calendar = {
            "day_review": [
                {
                    "event_id": ev.get("event_id"),
                    "country": ev.get("country"),
                    "event_name": ev.get("event_name"),
                    "event_name_kor": NaverBlogFormatter.translate_event_name(ev.get("event_name", ""), ev.get("country", "")),
                    "scheduled_at": ev.get("scheduled_at_kst"),
                    "importance": ev.get("importance"),
                    "actual": ev.get("actual"),
                    "forecast": ev.get("forecast"),
                    "previous": ev.get("previous"),
                    "impact_category": ev.get("impact_category")
                }
                for ev in economic_events.get("day_review_events", [])
            ],
            "today_night": [
                {
                    "event_id": ev.get("event_id"),
                    "country": ev.get("country"),
                    "event_name": ev.get("event_name"),
                    "event_name_kor": NaverBlogFormatter.translate_event_name(ev.get("event_name", ""), ev.get("country", "")),
                    "scheduled_at": ev.get("scheduled_at_kst"),
                    "scheduled_time_kst": ev.get("scheduled_at_kst", "")[11:16] if len(ev.get("scheduled_at_kst", "")) >= 16 else "",
                    "importance": ev.get("importance"),
                    "forecast": ev.get("forecast"),
                    "previous": ev.get("previous"),
                    "impact_category": ev.get("impact_category")
                }
                for ev in economic_events.get("today_night_events", [])
            ]
        }

        run_time_kst = processed_data.get("run_time_kst", "")
        as_of = processed_data.get("as_of", "") or (run_time_kst[11:16] + " 기준" if len(run_time_kst) >= 16 else "실시간 기준")

        return {
            "report_date": report_date,
            "run_time_kst": run_time_kst,
            "as_of": as_of,
            "market_data": {
                "fx": fx_items,
                "bonds": bond_items,
                "spreads": spreads,
                "commodities": commodity_items,
                "equities": equity_items
            },
            "verified_macro_news": filtered_news,
            "economic_calendar": calendar
        }
