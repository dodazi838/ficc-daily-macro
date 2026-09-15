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
        
        run_time_val = processed_data.get("run_time_kst", "")
        as_of_time = processed_data.get("as_of", "") or (run_time_val[11:16] + " 기준" if len(run_time_val) >= 16 else "실시간 기준")

        # 외환 (FX)
        fx_items = []
        for it in categories.get("FX", []):
            rec = {
                "field_id": f"FX.{it.get('symbol')}",
                "name": it.get("name"),
                "value": it.get("current"),
                "current": it.get("current"),
                "change_pct": round(it.get("pct_change", 0.0), 2) if it.get("pct_change") is not None else None,
                "unit": it.get("unit"),
                "as_of": it.get("actual_as_of_kst", as_of_time),
                "market_status": it.get("market_status", "INTRADAY"),
                "price_type": it.get("price_type", "장외/글로벌 현재환율"),
                "session_type": it.get("session_type", "")
            }
            if it.get("seoul_close") is not None:
                rec["seoul_close"] = it.get("seoul_close")
            fx_items.append(rec)

        # 채권 (Bonds) & 핵심 스프레드
        bond_items = []
        for it in categories.get("BOND", []):
            is_kr = "한국" in it.get("name", "") or "KTB" in it.get("name", "")
            is_closed = it.get("market_status") in ["CLOSED", "MARKET_CLOSED"] or is_kr or it.get("is_holiday", False)
            default_status = "CLOSED" if is_closed else "INTRADAY"
            default_pt = "최종호가수익률" if is_kr else ("PREVIOUS_CLOSE" if (it.get("is_holiday") or is_closed) else "Benchmark Cash Yield")
            is_hol = bool(it.get("is_holiday") or it.get("market_status") == "MARKET_CLOSED")
            ret_basis = it.get("return_basis") or ("PREVIOUS_TRADING_DAY" if is_hol or default_pt == "PREVIOUS_CLOSE" else "DAILY")
            b_rec = {
                "field_id": f"BOND.{it.get('symbol')}",
                "name": it.get("name"),
                "value": it.get("current"),
                "current": it.get("current"),
                "change_bp": round(it.get("bp_change", 0.0), 1) if it.get("bp_change") is not None else None,
                "unit": it.get("unit"),
                "as_of": it.get("actual_as_of_kst", as_of_time),
                "market_status": it.get("market_status", default_status),
                "price_type": it.get("price_type", default_pt),
                "return_basis": ret_basis,
                "session_type": it.get("session_type", "")
            }
            if is_hol:
                b_rec["is_holiday"] = True
                b_rec["holiday_name"] = it.get("holiday_name")
                b_rec["display_guide"] = f"해당 국채시장 휴장({it.get('holiday_name', '공휴일')})으로 가격 및 변동폭(bp) 모두 직전 거래일 마감 기준임(return_basis=PREVIOUS_TRADING_DAY). 당일 장중 거래/금리변동으로 서술 절대 금지."
            bond_items.append(b_rec)

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
            pct_val = it.get("pct_change")
            change_st = it.get("change_status") or ("CONFIRMED" if pct_val is not None else "UNAVAILABLE")
            c_rec = {
                "field_id": f"COMMODITY.{it.get('symbol')}",
                "name": it.get("name"),
                "value": it.get("current"),
                "current": it.get("current"),
                "change_pct": round(pct_val, 2) if pct_val is not None else None,
                "change_status": change_st,
                "unit": it.get("unit"),
                "as_of": it.get("actual_as_of_kst", as_of_time),
                "market_status": it.get("market_status", "INTRADAY"),
                "price_type": it.get("price_type", "현재가 (장중)"),
                "return_basis": it.get("return_basis", "INTRADAY"),
                "session_type": it.get("session_type", "")
            }
            if change_st == "UNAVAILABLE":
                c_rec["display_guide"] = "해당 원자재는 미국 휴장 또는 정산가 미발표로 변동률이 미확인 상태임(change_status=UNAVAILABLE, change_pct=null). 본문에서 '0% 변동', '보합세 지속', '변동 없음' 등으로 왜곡 서술 절대 금지. 가격 레벨만 객관적으로 서술할 것."
            commodity_items.append(c_rec)

        # 증시 (Equity)
        equity_items = []
        for it in categories.get("EQUITY", []):
            sym = it.get("symbol", "")
            is_hol = bool(it.get("is_holiday") or it.get("market_status") == "MARKET_CLOSED")
            ret_basis = it.get("return_basis") or ("PREVIOUS_TRADING_DAY" if is_hol or it.get("price_type") == "PREVIOUS_CLOSE" else "DAILY")
            eq_rec = {
                "field_id": f"EQUITY.{sym}",
                "name": it.get("name"),
                "value": it.get("current"),
                "current": it.get("current"),
                "change_pct": round(it.get("pct_change", 0.0), 2) if it.get("pct_change") is not None else None,
                "unit": it.get("unit"),
                "as_of": it.get("actual_as_of_kst", as_of_time),
                "market_status": it.get("market_status", "CLOSED"),
                "price_type": it.get("price_type", "종가"),
                "return_basis": ret_basis,
                "session_type": it.get("session_type", "")
            }
            if is_hol:
                eq_rec["is_holiday"] = True
                eq_rec["holiday_name"] = it.get("holiday_name")
                eq_rec["display_guide"] = f"해당 증시 휴장({it.get('holiday_name', '공휴일')})으로 가격 및 등락률 모두 직전 거래일 종가 기준임(return_basis=PREVIOUS_TRADING_DAY). 당일 장중 거래/등락으로 서술 절대 금지."
            elif eq_rec["market_status"] == "CLOSED" or eq_rec["price_type"] in ["종가", "확정종가"]:
                eq_rec["display_guide"] = "해당 증시는 당일 거래 마감 상태임(price_type=종가). '상승 마감/하락 마감'으로 서술하고 절대 '장중' 표현을 쓰지 말 것."
            elif eq_rec["market_status"] == "INTRADAY":
                eq_rec["display_guide"] = "해당 증시는 현재 장중 거래 진행 중임(price_type=현재가 (장중)). '장중 거래/장중 등락'으로 서술하고 정규장 마감으로 단정하지 말 것."
            equity_items.append(eq_rec)

        # 2. 시장-뉴스 매칭 및 다차원 인과관계 분석 (MarketNewsMatcher)
        from processors.market_news_matcher import MarketNewsMatcher, ensure_kst_aware
        run_kst = ensure_kst_aware(run_time_val)

        matched_macro = MarketNewsMatcher.match_market_news(
            market_data=market_data,
            news_events=news_events,
            economic_events=economic_events,
            run_time_kst=run_kst
        )
        curated_news_list = matched_macro.get("verified_macro_news", [])


        # 3. 경제 캘린더 정제 (DAY_REVIEW + TODAY_NIGHT + NEXT_TRADING_DAY)
        from generators.blog_formatter import NaverBlogFormatter
        from processors.event_processor import MacroEventProcessor, ensure_kst_aware

        raw_day_review = economic_events.get("day_review_events", [])
        run_kst = ensure_kst_aware(run_time_val)
        curated_day = MacroEventProcessor.curate_day_review_events(raw_day_review, run_kst)

        day_review_items = []
        seen_day_keys = set()
        for ev in curated_day:
            sched_dt = ev.get("scheduled_dt_kst") or ev.get("scheduled_at_kst")
            sched_dt_kst = ensure_kst_aware(sched_dt)
            
            # 동일 이벤트 중복 주입 방지
            ev_id = ev.get("event_id")
            ev_name = ev.get("event_name", "")
            dedup_key = ev_id or f"{ev.get('country')}_{ev_name}_{sched_dt_kst.strftime('%Y%m%d%H%M')}"
            if dedup_key in seen_day_keys:
                continue
            seen_day_keys.add(dedup_key)

            act_val = ev.get("actual")
            has_act = (act_val is not None and str(act_val).strip() not in ["", "-", "None"])

            time_status = "RELEASED" if sched_dt_kst <= run_kst else "UPCOMING"
            actual_status = "FOUND" if has_act else "NOT_FOUND"

            if time_status == "RELEASED":
                if actual_status == "FOUND":
                    freshness = "RELEASED_WITH_ACTUAL"
                    analysis_permission = "RESULT_BASED_ANALYSIS_ALLOWED (실제치 기반 결과/방향성 분석 허용)"
                    display_guide = f"발표 완료 (실제 수치: {act_val} 확인됨. 실제 수치와 예상치 간 관계 기반으로 결과 분석 작성 가능)"
                else:
                    freshness = "RELEASED_ACTUAL_NOT_FOUND"
                    analysis_permission = "RESULT_ANALYSIS_STRICTLY_PROHIBITED (실제치 미확인 상태이므로 '상승했다', '상회했다', '악화됐다' 등 결과 단정 절대 금지! 오직 '발표 시각이 지났으나 공식 수치 미확인 상태'로만 서술 허용)"
                    display_guide = "발표 완료되었으나 실제 수치 미확인 (Actual='-'). 본문에서 '상승/하락/호조/부진' 등 결과 단정 절대 금지! '발표 시각이 경과했으나 공식 수치가 확인되지 않아 결과 확인이 필요함'으로만 서술 가능."
            else:
                freshness = "UPCOMING"
                analysis_permission = "UPCOMING_SCHEDULE_ONLY (미래 일정이므로 결과 분석 불가, 일정 및 관전 포인트만 서술)"
                display_guide = "향후 발표 예정 지표 ('발표 예정', '발표를 앞두고' 표현 허용)"

            day_review_items.append({
                "event_id": ev_id,
                "country": ev.get("country"),
                "event_name": ev_name,
                "event_name_kor": NaverBlogFormatter.translate_event_name(ev_name, ev.get("country", "")),
                "scheduled_at": ev.get("scheduled_at_kst"),
                "scheduled_time_kst": ev.get("scheduled_time_kst", "") or (ev.get("scheduled_at_kst", "")[11:16] if len(ev.get("scheduled_at_kst", "")) >= 16 else ""),
                "target_period": ev.get("target_period") or ev.get("reference_period"),
                "reference_period": ev.get("reference_period") or ev.get("target_period"),
                "importance": ev.get("importance"),
                "macro_priority": ev.get("macro_priority") or MacroEventProcessor.get_macro_priority(ev),
                "star_rating": NaverBlogFormatter.get_event_star_rating(ev),
                "actual": ev.get("actual"),
                "forecast": ev.get("forecast"),
                "prior": ev.get("prior") or ev.get("previous"),
                "previous": ev.get("prior") or ev.get("previous"),
                "is_revised_prior": ev.get("is_revised_prior", False),
                "actual_source": ev.get("actual_source"),
                "time_status": time_status,
                "actual_status": actual_status,
                "freshness_status": freshness,
                "analysis_permission": analysis_permission,
                "display_guide": display_guide,
                "impact_category": ev.get("impact_category")
            })

        today_night_items = []
        seen_night_keys = set()
        for ev in economic_events.get("today_night_events", []):
            imp = ev.get("importance", "MEDIUM")
            is_cluster = (ev.get("cluster_type") in ["CENTRAL_BANK_POLICY", "CPI_CLUSTER", "MACRO_EVENT_CLUSTER"])
            # 최종 분석에 사용되지 않는 저중요도 비매크로 이벤트 제외
            if imp == "LOW" and not is_cluster:
                continue

            ev_id = ev.get("event_id")
            ev_name = ev.get("event_name", "")
            dedup_key = ev_id or f"{ev.get('country')}_{ev_name}"
            if dedup_key in seen_night_keys:
                continue
            seen_night_keys.add(dedup_key)

            comps = []
            if is_cluster:
                for c in ev.get("components", []):
                    comps.append({
                        "event_id": c.get("event_id"),
                        "event_name": c.get("event_name"),
                        "event_name_kor": NaverBlogFormatter.translate_event_name(c.get("event_name", ""), ev.get("country", "")),
                        "detail_type": c.get("detail_type"),
                        "scheduled_time_kst": c.get("scheduled_time_kst"),
                        "component_type": c.get("component_type"),
                        "forecast": c.get("forecast"),
                        "prior": c.get("prior")
                    })
            today_night_items.append({
                "event_id": ev_id,
                "cluster_type": ev.get("cluster_type"),
                "representative_name": ev.get("representative_event") or ev.get("event_name_kor"),
                "institution": ev.get("institution"),
                "country": ev.get("country"),
                "event_name": ev_name,
                "event_name_kor": NaverBlogFormatter.translate_event_name(ev_name, ev.get("country", "")),
                "scheduled_at": ev.get("scheduled_at_kst"),
                "scheduled_time_kst": ev.get("scheduled_time_kst", "") or (ev.get("scheduled_at_kst", "")[11:16] if len(ev.get("scheduled_at_kst", "")) >= 16 else ""),
                "target_period": ev.get("target_period") or ev.get("reference_period"),
                "reference_period": ev.get("reference_period") or ev.get("target_period"),
                "importance": ev.get("importance"),
                "macro_priority": ev.get("macro_priority") or MacroEventProcessor.get_macro_priority(ev),
                "star_rating": NaverBlogFormatter.get_event_star_rating(ev),
                "actual": None,
                "forecast": ev.get("forecast"),
                "prior": ev.get("prior") or ev.get("previous"),
                "previous": ev.get("prior") or ev.get("previous"),
                "is_revised_prior": False,
                "actual_source": None,
                "time_status": "UPCOMING",
                "actual_status": "NOT_FOUND",
                "freshness_status": "UPCOMING",
                "analysis_permission": "UPCOMING_SCHEDULE_ONLY (미래 일정이므로 결과 분석 불가, 일정 및 관전 포인트만 서술)",
                "display_guide": "향후 발표 예정 지표 ('발표 예정', '발표를 앞두고' 표현 허용)",
                "impact_category": ev.get("impact_category"),
                "components": comps if is_cluster else None
            })

        next_trading_day_items = []
        seen_next_keys = set()
        for ev in economic_events.get("next_trading_day_events", []):
            imp = ev.get("importance", "HIGH")
            is_cluster = (ev.get("cluster_type") in ["CENTRAL_BANK_POLICY", "CPI_CLUSTER", "MACRO_EVENT_CLUSTER"])
            if imp == "LOW" and not is_cluster:
                continue

            ev_id = ev.get("event_id")
            ev_name = ev.get("event_name", "")
            dedup_key = ev_id or f"{ev.get('country')}_{ev_name}"
            if dedup_key in seen_next_keys:
                continue
            seen_next_keys.add(dedup_key)

            comps = []
            if is_cluster:
                for c in ev.get("components", []):
                    comps.append({
                        "event_id": c.get("event_id"),
                        "event_name": c.get("event_name"),
                        "event_name_kor": NaverBlogFormatter.translate_event_name(c.get("event_name", ""), ev.get("country", "")),
                        "detail_type": c.get("detail_type"),
                        "scheduled_time_kst": c.get("scheduled_time_kst"),
                        "component_type": c.get("component_type"),
                        "forecast": c.get("forecast"),
                        "prior": c.get("prior")
                    })
            next_trading_day_items.append({
                "event_id": ev_id,
                "cluster_type": ev.get("cluster_type"),
                "representative_name": ev.get("representative_event") or ev.get("event_name_kor"),
                "institution": ev.get("institution"),
                "country": ev.get("country"),
                "event_name": ev_name,
                "event_name_kor": NaverBlogFormatter.translate_event_name(ev_name, ev.get("country", "")),
                "scheduled_at": ev.get("scheduled_at_kst"),
                "scheduled_time_kst": ev.get("scheduled_time_kst", "") or (ev.get("scheduled_at_kst", "")[11:16] if len(ev.get("scheduled_at_kst", "")) >= 16 else ""),
                "target_period": ev.get("target_period") or ev.get("reference_period"),
                "reference_period": ev.get("reference_period") or ev.get("target_period"),
                "importance": ev.get("importance", "HIGH"),
                "macro_priority": ev.get("macro_priority") or MacroEventProcessor.get_macro_priority(ev),
                "star_rating": NaverBlogFormatter.get_event_star_rating(ev),
                "actual": ev.get("actual"),
                "forecast": ev.get("forecast"),
                "prior": ev.get("prior") or ev.get("previous"),
                "previous": ev.get("prior") or ev.get("previous"),
                "is_revised_prior": False,
                "actual_source": None,
                "time_status": "UPCOMING",
                "actual_status": "NOT_FOUND",
                "freshness_status": "UPCOMING",
                "analysis_permission": "UPCOMING_SCHEDULE_ONLY (미래 일정이므로 결과 분석 불가, 일정 및 관전 포인트만 서술)",
                "display_guide": "다음 거래일 핵심 예정 지표 ('미국 CPI 발표' 등 단일 Macro 단위로 표현하며 세부항목 수치 나열은 지양하고 시장 파급 경로 중심으로 서술)",
                "impact_category": ev.get("impact_category", "MONETARY_POLICY" if is_cluster else "GENERAL"),
                "components": comps if is_cluster else None
            })

        calendar = {
            "day_review": day_review_items,
            "today_night": today_night_items,
            "next_trading_day": next_trading_day_items
        }

        run_time_kst = processed_data.get("run_time_kst", "")
        as_of = processed_data.get("as_of", "") or as_of_time

        # 시장 휴장 상태 요약
        market_holidays = []
        for it in categories.get("EQUITY", []) + categories.get("BOND", []):
            if it.get("is_holiday") and it.get("holiday_name"):
                h_desc = f"{it.get('name')}: {it.get('holiday_name')} 휴장"
                if h_desc not in market_holidays:
                    market_holidays.append(h_desc)

        return {
            "report_date": report_date,
            "run_time_kst": run_time_kst,
            "as_of": as_of,
            "market_holidays": market_holidays,
            "market_data": {
                "fx": fx_items,
                "bonds": bond_items,
                "spreads": spreads,
                "commodities": commodity_items,
                "equities": equity_items
            },
            "market_narrative_context": {
                "market_observations": matched_macro.get("market_observations", {}),
                "primary_theme": matched_macro.get("primary_theme"),
                "core_cause_category": matched_macro.get("core_cause_category"),
                "causal_confidence": matched_macro.get("causal_confidence"),
                "transmission_summary": matched_macro.get("transmission_summary"),
                "asset_specific_catalysts": matched_macro.get("asset_specific_catalysts", {}),
                "asset_matches": matched_macro.get("asset_matches", {}),
                "claim_evidence": matched_macro.get("claim_evidence", [])
            },
            "verified_macro_news": curated_news_list,
            "economic_calendar": calendar
        }
