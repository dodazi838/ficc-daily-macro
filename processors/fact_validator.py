"""
[FICC Daily Macro] 다차원 팩트 검증기 및 엄격 게이트키퍼 (fact_validator.py)
- Single Source of Truth (data/processed/YYYY-MM-DD.json) 기반 정합성 검증
- 지수 고유명사(S&P 500, 다우 30, 니케이 225, 유로스톡스 50) 및 날짜(월/일/년) 사전 마스킹을 통한 오탐 방지
- passed / errors / warnings 명확 분리 및 ERROR 1건이라도 발생 시 게이트키퍼 게시 차단
"""

import re
from typing import Dict, Any, List, Tuple, Set

class FactValidator:
    """AI 생성 시황 리포트의 수치 및 인과관계 다차원 검증기"""

    ASSET_ALIASES = {
        "KOSPI": ["코스피", "kospi", "^ks11"],
        "KOSDAQ": ["코스닥", "kosdaq", "^kq11"],
        "VIX": ["vix", "변동성 지수", "변동성지수"],
        "^GSPC": ["s&p 500", "s&p500", "s&p", "에스앤피", "sp_index"],
        "^DJI": ["다우", "다우존스", "dji", "dji_index"],
        "^IXIC": ["나스닥", "nasdaq", "ndx_index"],
        "000001.SS": ["상해종합", "상하이"],
        "^HSI": ["항셍", "항셍지수", "hsi"],
        "^N225": ["니케이", "nikkei", "닛케이", "nikkei_index"],
        "^STOXX50E": ["유로스톡스", "euro stoxx", "stoxx 50", "stoxx_index"],
        "DX-Y.NYB": ["달러 인덱스", "달러인덱스", "dxy", "달러화 지수"],
        "KRW=X": ["원/달러", "달러/원", "원달러", "원화 환율", "원화", "달러 대비 원화"],
        "JPY=X": ["엔/달러", "달러/엔", "엔화", "엔/달러 환율", "달러 대비 엔화"],
        "CNH=F": ["위안/달러", "달러/위안", "역외 위안", "위안화"],
        "EURUSD=X": ["유로/달러", "유로화", "eur/usd"],
        "GBPUSD=X": ["파운드/달러", "파운드화", "gbp/usd"],
        "CL=F": ["wti", "유가", "국제유가", "서부텍사스산", "원유 선물", "원유"],
        "BZ=F": ["brent", "브렌트", "브렌트유"],
        "GC=F": ["금 선물", "금 가격", "금값", "gold", "금 시세", "금과 구리", "금과"],
        "SI=F": ["은 선물", "은 가격", "silver", "은 시세"],
        "HG=F": ["구리 선물", "구리 가격", "copper", "구리"],
        "NG=F": ["천연가스", "가스 선물"],
        "BOND.KTB 3y": ["국고채 3년", "한국 국채 3년", "한국 3년", "ktb 3년"],
        "BOND.KTB10y": ["국고채 10년", "한국 국채 10년", "한국 10년", "ktb 10년", "국내 국고채", "국고채 금리", "국고채", "국고채 10년물"],
        "BOND.US2Y": ["미국 국채 2년", "미국채 2년", "미 2년물", "2년물 금리", "미국 2년", "미국 2년물", "미 국채 2년"],
        "BOND.US10Y": ["미국 국채 10년", "미국채 10년", "미 10년물", "10년물 금리", "미국 10년", "10년물 국채", "미국 10년물", "미국 국채 금리", "미국채 금리", "미국 국채", "국채 10년물", "미 국채 10년", "미 국채 10년물"],
        "BOND.JP10Y": ["일본 국채 10년", "일본 10년", "jgb", "일본 10년물", "일본 국채 금리", "일본 국채"],
        "BOND.DE10Y": ["독일 국채 10년", "독일 10년", "분트", "bund", "독일 10년물", "독일 국채 금리", "독일 국채"],
        "SPREAD": ["장단기 스프레드", "10y-2y", "10y - 2y", "10y-3y", "한-미 스프레드", "독-미 스프레드", "스프레드"]
    }

    @classmethod
    def validate_and_enrich(cls, generated_content: Dict[str, Any], raw_context: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        AI 생성 JSON의 각 섹션을 엄격히 검증하고,
        검증 실패 시 passed=False, errors 리스트를 반환합니다.
        """
        asset_allowed_numbers = cls._build_asset_allowed_numbers(raw_context)
        all_valid_context_numbers = cls._collect_all_context_numbers(raw_context)
        all_news_ids = {n.get("news_id") for n in raw_context.get("verified_macro_news", [])}
        all_event_ids = set()
        for ev_list in raw_context.get("economic_calendar", {}).values():
            if isinstance(ev_list, list):
                for ev in ev_list:
                    if ev.get("event_id"):
                        all_event_ids.add(ev.get("event_id"))
                    for comp in ev.get("components") or []:
                        if comp.get("event_id"):
                            all_event_ids.add(comp.get("event_id"))

        errors: List[str] = []
        warnings: List[str] = []
        verified_count = 0
        section_scores = []

        sections_to_check = [
            ("ficc_daily_summary", "\n".join(generated_content.get("ficc_daily_summary", {}).get("bullets", []))),
            ("ficc_summary", generated_content.get("ficc_summary", {}).get("text", "")),
            ("issue_review_stock", generated_content.get("issue_review", {}).get("stock", {}).get("text", "")),
            ("issue_review_fx", generated_content.get("issue_review", {}).get("fx", {}).get("text", "")),
            ("issue_review_bond", generated_content.get("issue_review", {}).get("bond", {}).get("text", "")),
            ("issue_review_commodity", generated_content.get("issue_review", {}).get("commodity", {}).get("text", "")),
            ("ficc_forecast", generated_content.get("ficc_forecast", {}).get("text", "")),
            ("daily_event_watchpoints", generated_content.get("daily_event_watchpoints", {}).get("text", ""))
        ]

        for sec_name, sec_text in sections_to_check:
            if not sec_text:
                continue

            session_errors = cls._validate_market_session_representation(sec_name, sec_text, raw_context)
            errors.extend(session_errors)

            causality_errors = cls._validate_unsupported_causality(sec_name, sec_text, raw_context)
            errors.extend(causality_errors)

            sector_errors = cls._validate_unsupported_sector_and_stock_claims(sec_name, sec_text, raw_context)
            errors.extend(sector_errors)

            alignment_errors = cls._validate_data_to_sentence_alignment(sec_name, sec_text, raw_context)
            errors.extend(alignment_errors)

            total_extra_errs = len(session_errors) + len(causality_errors) + len(sector_errors) + len(alignment_errors)

            if sec_name == "daily_event_watchpoints":
                event_errors = cls._validate_daily_event_section(sec_text, raw_context)
                errors.extend(event_errors)
                score = max(0.0, 100.0 - ((len(event_errors) + total_extra_errs) * 35.0))
                section_scores.append(score)
            else:
                sec_errors, sec_warnings, sec_verified = cls._validate_section_text(
                    sec_name, sec_text, asset_allowed_numbers, all_valid_context_numbers
                )
                errors.extend(sec_errors)
                warnings.extend(sec_warnings)
                verified_count += sec_verified
                score = 100.0 - ((len(sec_errors) + total_extra_errs) * 35.0) - (len(sec_warnings) * 10.0)
                score = max(0.0, score)
                section_scores.append(score)

        # SSOT 및 컨텍스트 데이터 정합성 검증 (참조기간, 릴리스 일자, revised prior 연속성 등)
        context_data_errors = cls._validate_event_data_consistency(raw_context)
        errors.extend(context_data_errors)

        # Actual 미확인 이벤트 결과 분석 금지 검증 (No Actual = No Result Analysis)
        unverified_actual_errors = cls._validate_unverified_actual_analysis(generated_content, raw_context)
        errors.extend(unverified_actual_errors)

        # Source ID 검증
        today_night_eids = {
            ev.get("event_id")
            for ev in raw_context.get("economic_calendar", {}).get("today_night", [])
            if ev.get("event_id")
        }
        for sec_obj in [
            generated_content.get("ficc_daily_summary", {}),
            generated_content.get("ficc_summary", {}),
            generated_content.get("issue_review", {}).get("stock", {}),
            generated_content.get("issue_review", {}).get("fx", {}),
            generated_content.get("issue_review", {}).get("bond", {}),
            generated_content.get("issue_review", {}).get("commodity", {}),
            generated_content.get("ficc_forecast", {}),
            generated_content.get("daily_event_watchpoints", {})
        ]:
            if not sec_obj:
                continue
            for nid in sec_obj.get("source_news_ids", []):
                if nid and nid not in all_news_ids:
                    errors.append(f"존재하지 않는 news_id 인용: {nid}")
            for eid in sec_obj.get("source_event_ids", []):
                if eid and eid not in all_event_ids:
                    errors.append(f"존재하지 않는 event_id 인용: {eid}")

        # daily_event_watchpoints의 source_event_ids는 캘린더 전체(today_night 및 day_review)에 존재해야 함
        dev_obj = generated_content.get("daily_event_watchpoints", {})
        if dev_obj:
            for eid in dev_obj.get("source_event_ids", []):
                if eid and eid not in all_event_ids:
                    errors.append(f"[daily_event_watchpoints] 금일 캘린더에 존재하지 않는 event_id 인용: {eid}")

        is_passed = (len(errors) == 0)
        avg_score = sum(section_scores) / len(section_scores) if section_scores else 100.0

        if is_passed and avg_score >= 85.0:
            overall_conf = "HIGH"
        elif is_passed and avg_score >= 65.0:
            overall_conf = "MEDIUM"
        else:
            overall_conf = "LOW"

        cls._assign_section_confidences(generated_content, overall_conf if is_passed else "LOW")

        validation_summary = {
            "passed": is_passed,
            "is_passed": is_passed,
            "errors": errors,
            "warnings": warnings,
            "overall_confidence": overall_conf,
            "average_confidence_score": round(avg_score, 1),
            "fact_check_details": {
                "verified_numbers_count": verified_count,
                "errors_count": len(errors),
                "warnings_count": len(warnings),
                "mismatches": errors,
                "errors": errors,
                "warnings": warnings
            }
        }

        # Claim-Evidence 추적 데이터 보존 및 인리치먼트
        if "claims" not in generated_content or not generated_content.get("claims"):
            context_claims = raw_context.get("market_narrative_context", {}).get("claim_evidence", [])
            if context_claims:
                formatted_claims = []
                for c in context_claims:
                    formatted_claims.append({
                        "claim": c.get("claim"),
                        "evidence_news_ids": c.get("evidence_news_ids", []),
                        "market_data_refs": c.get("market_data_refs", []),
                        "source_confidence": c.get("source_confidence", "HIGH"),
                        "causal_confidence": c.get("causal_confidence", "HIGH"),
                        "temporal_relevance": c.get("temporal_relevance", "STRONG_LEAD")
                    })
                generated_content["claims"] = formatted_claims

        return generated_content, validation_summary

    @classmethod
    def _build_asset_allowed_numbers(cls, raw_context: Dict[str, Any]) -> Dict[str, Set[float]]:
        """각 자산별로 당일 데이터에서 계산/도출 가능한 모든 수치 Set 구성"""
        asset_numbers: Dict[str, Set[float]] = {}
        market_ordered = raw_context.get("market_data_ordered") or raw_context.get("market_data", {})

        for cat_name, cat_list in market_ordered.items():
            if not isinstance(cat_list, list):
                continue
            for item in cat_list:
                field_id = item.get("field_id", "")
                sym = field_id.split(".")[-1] if "." in field_id else item.get("name", "")
                name = item.get("name", "")
                
                allowed = set()
                curr = item.get("current")
                if curr is not None and isinstance(curr, (int, float)):
                    cls._add_rounded_variants(allowed, float(curr))

                pct = item.get("change_pct")
                if pct is not None and isinstance(pct, (int, float)):
                    cls._add_rounded_variants(allowed, float(pct))

                chg_bp = item.get("change_bp")
                if chg_bp is not None and isinstance(chg_bp, (int, float)):
                    cls._add_rounded_variants(allowed, float(chg_bp))

                curr_bp = item.get("current_bp")
                if curr_bp is not None and isinstance(curr_bp, (int, float)):
                    cls._add_rounded_variants(allowed, float(curr_bp))

                asset_numbers[field_id] = allowed
                asset_numbers[sym] = allowed
                asset_numbers[name] = allowed
                if cat_name in ["key_spreads", "spreads"]:
                    if "SPREAD" not in asset_numbers:
                        asset_numbers["SPREAD"] = set()
                    asset_numbers["SPREAD"].update(allowed)

        return asset_numbers

    @classmethod
    def _add_rounded_variants(cls, target_set: Set[float], val: float):
        """정밀도별 반올림 변형 추가"""
        abs_val = abs(val)
        target_set.add(round(abs_val, 4))
        target_set.add(round(abs_val, 3))
        target_set.add(round(abs_val, 2))
        target_set.add(round(abs_val, 1))
        target_set.add(round(abs_val, 0))

    @classmethod
    def _collect_all_context_numbers(cls, raw_context: Dict[str, Any]) -> Set[float]:
        """컨텍스트 전체(시장 데이터 + 캘린더 지표)에서 유효한 모든 수치 집합"""
        all_nums = set()
        market_ordered = raw_context.get("market_data_ordered") or raw_context.get("market_data", {})
        for cat_list in market_ordered.values():
            if isinstance(cat_list, list):
                for item in cat_list:
                    for k in ["current", "change_pct", "change_bp", "current_bp"]:
                        v = item.get(k)
                        if v is not None and isinstance(v, (int, float)):
                            cls._add_rounded_variants(all_nums, float(v))

        cal = raw_context.get("economic_calendar", {})
        for ev_list in cal.values():
            for ev in ev_list:
                for k in ["prior", "forecast", "actual"]:
                    val_str = str(ev.get(k) or "")
                    found = re.findall(r'[-+]?\d+(?:,\d{3})*(?:\.\d+)?', val_str)
                    for f in found:
                        try:
                            clean_f = f.replace(",", "")
                            val_float = float(clean_f)
                            cls._add_rounded_variants(all_nums, val_float)
                            if "k" in val_str.lower():
                                # K단위 (1,000)를 한국어 만(10,000) 단위로 표기할 때 (예: 22K -> 2.2만, 165K -> 16.5만)
                                cls._add_rounded_variants(all_nums, val_float / 10.0)
                        except ValueError:
                            pass
        return all_nums

    @classmethod
    def _validate_section_text(cls, sec_name: str, text: str, asset_allowed_numbers: Dict[str, Set[float]], all_valid_numbers: Set[float]) -> Tuple[List[str], List[str], int]:
        """문장 단위로 자산명과 인접 수치 간의 바인딩 검증 및 지수명/날짜 마스킹"""
        errors = []
        warnings = []
        verified_count = 0

        sentences = re.split(r'(?<=[가-힣a-zA-Z\)])\.\s+|\n+', text)
        for sent in sentences:
            sent_clean = sent.strip()
            if not sent_clean:
                continue

            # 1. 미제공 이동평균선(예: 50일 이평선, 20일선 등) 패턴 검출 -> ERROR
            if re.search(r'\b\d+\s*일\s*(?:이동평균선|이평선|선)', sent_clean):
                errors.append(f"[{sec_name}] 미제공 기술적 지표 인용: '{sent_clean}' 내 이동평균선 수치는 당일 데이터셋에 존재하지 않습니다.")

            # 2. 미제공 확률(예: 확률 68%, 70% 반영 등) 패턴 검출 -> ERROR
            prob_matches = re.findall(r'확률\s*(\d+)\s*%', sent_clean)
            for pm in prob_matches:
                p_val = float(pm)
                if p_val not in all_valid_numbers:
                    errors.append(f"[{sec_name}] 미제공 확률/전망치 인용: '{sent_clean}' 내 확률 {p_val}%는 당일 검증된 데이터셋에 존재하지 않습니다.")

            # 3. 고유명사 지수명, 날짜 및 시간 마스킹 (숫자 오탐 방지)
            masked_sent = sent_clean
            masked_sent = re.sub(r'(?i)(?:s&p|sp|에스앤피)\s*500', 'SP_INDEX', masked_sent)
            masked_sent = re.sub(r'(?i)(?:다우존스|다우|dow)\s*30', 'DJI_INDEX', masked_sent)
            masked_sent = re.sub(r'(?i)(?:니케이|닛케이|nikkei)\s*225', 'NIKKEI_INDEX', masked_sent)
            masked_sent = re.sub(r'(?i)(?:유로스톡스|euro\s*stoxx|stoxx)\s*50', 'STOXX_INDEX', masked_sent)
            masked_sent = re.sub(r'(?i)(?:나스닥|nasdaq)\s*100', 'NDX_INDEX', masked_sent)
            masked_sent = re.sub(r'(?i)(?:러셀|russell)\s*2000', 'RUT_INDEX', masked_sent)
            masked_sent = re.sub(r'\b\d{4}년\b', ' ', masked_sent)
            masked_sent = re.sub(r'\b\d{1,2}월\b', ' ', masked_sent)
            masked_sent = re.sub(r'\b\d{1,2}일\b', ' ', masked_sent)
            masked_sent = re.sub(r'\b\d{1,2}:\d{2}(?::\d{2})?\b', ' TIME_VAL ', masked_sent)
            masked_sent = re.sub(r'\b\d{1,2}\s*시\s*\d{1,2}\s*분\b', ' TIME_VAL ', masked_sent)
            masked_sent = re.sub(r'\b\d{1,2}\s*시\b', ' TIME_VAL ', masked_sent)
            masked_sent = re.sub(r'\b\d{1,2}\s*분\b', ' TIME_VAL ', masked_sent)
            masked_sent = re.sub(r'\b\d+(?:\.\d+)?\s*만(?:\s*[\d,]+)?(?:\s*천)?(?:\s*(?:명|건|개|달러|원))?\b', ' COUNT_VAL ', masked_sent)
            masked_sent = re.sub(r'\b\d+(?:\.\d+)?\s*천\s*(?:명|건|개|달러|원)\b', ' COUNT_VAL ', masked_sent)
            masked_sent = re.sub(r'\b\d+(?:,\d{3})*\s*(?:명|건|개)\b', ' COUNT_VAL ', masked_sent)
            masked_sent = re.sub(r'\b\d+(?:\.\d+)?\s*(?:명|건|개)\b', ' COUNT_VAL ', masked_sent)

            # 4. 숫자 추출
            raw_nums = re.findall(r'[-+]?\d+(?:,\d{3})*(?:\.\d+)?', masked_sent)
            extracted_floats = []
            for n in raw_nums:
                try:
                    val = abs(float(n.replace(",", "")))
                    if val not in [2026.0, 1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 30.0, 50.0, 100.0]:
                        extracted_floats.append(val)
                except ValueError:
                    pass

            if not extracted_floats:
                continue

            # 문장에 언급된 자산 식별
            mentioned_keys = []
            sent_lower = masked_sent.lower()
            for asset_key, aliases in cls.ASSET_ALIASES.items():
                if any(alias in sent_lower for alias in aliases):
                    mentioned_keys.append(asset_key)

            allowed_for_sentence = set()
            for k in mentioned_keys:
                allowed_for_sentence.update(asset_allowed_numbers.get(k, set()))

            for num in extracted_floats:
                num_round3 = round(num, 3)
                num_round2 = round(num, 2)
                num_round1 = round(num, 1)
                num_round0 = round(num, 0)

                if mentioned_keys:
                    is_level_match = any(
                        (num >= 10 and int(num) == int(a)) or 
                        (num >= 50 and int(num) == int(a // 10 * 10)) or
                        (num >= 500 and int(num) == int(a // 100 * 100))
                        for a in allowed_for_sentence
                    )
                    is_matched = (
                        (num_round3 in allowed_for_sentence) or 
                        (num_round2 in allowed_for_sentence) or 
                        (num_round1 in allowed_for_sentence) or 
                        (num_round0 in allowed_for_sentence) or 
                        any(abs(num - a) <= 0.05 for a in allowed_for_sentence) or
                        is_level_match
                    )
                    if is_matched:
                        verified_count += 1
                    else:
                        in_context_level = any(
                            (num >= 10 and int(num) == int(a)) or 
                            (num >= 50 and int(num) == int(a // 10 * 10)) or
                            (num >= 500 and int(num) == int(a // 100 * 100))
                            for a in all_valid_numbers
                        )
                        in_context = (
                            (num_round3 in all_valid_numbers) or 
                            (num_round2 in all_valid_numbers) or 
                            (num_round1 in all_valid_numbers) or 
                            any(abs(num - a) <= 0.05 for a in all_valid_numbers) or
                            in_context_level
                        )
                        if in_context:
                            verified_count += 1
                        else:
                            errors.append(f"[{sec_name}] 허위/과거 수치 적발: '{sent_clean}' 내 수치 {num}는 당일 검증된 시장 데이터셋에 존재하지 않습니다.")
                else:
                    is_valid_level = any(
                        (num >= 10 and int(num) == int(a)) or 
                        (num >= 50 and int(num) == int(a // 10 * 10)) or
                        (num >= 500 and int(num) == int(a // 100 * 100))
                        for a in all_valid_numbers
                    )
                    is_valid = (
                        (num_round3 in all_valid_numbers) or 
                        (num_round2 in all_valid_numbers) or 
                        (num_round1 in all_valid_numbers) or 
                        any(abs(num - a) <= 0.05 for a in all_valid_numbers) or
                        is_valid_level
                    )
                    if is_valid:
                        verified_count += 1
                    else:
                        errors.append(f"[{sec_name}] 검증되지 않은 수치 인용: '{sent_clean}' 내 수치 {num}는 당일 시장 데이터셋과 불일치합니다.")

        return errors, warnings, verified_count

    @classmethod
    def _assign_section_confidences(cls, content: Dict[str, Any], conf: str):
        """모든 섹션 객체에 confidence 등급 주입"""
        if "ficc_daily_summary" in content:
            content["ficc_daily_summary"]["confidence"] = conf
        if "ficc_summary" in content:
            content["ficc_summary"]["confidence"] = conf
        if "issue_review" in content:
            for k in ["stock", "fx", "bond", "commodity"]:
                if k in content["issue_review"]:
                    content["issue_review"][k]["confidence"] = conf
        if "ficc_forecast" in content:
            content["ficc_forecast"]["confidence"] = conf
        if "daily_event_watchpoints" in content:
            content["daily_event_watchpoints"]["confidence"] = conf

    @classmethod
    def _validate_daily_event_section(cls, text: str, raw_context: Dict[str, Any]) -> List[str]:
        """
        Daily Event 전용 검증 게이트키퍼:
        1. [Canonical 지표 검증] 본문에 언급된 경제지표가 오늘 16:30 이후 발표 예정 목록(today_night)에 실제로 존재하는지 확인
        2. [과거 지표 차단] 16:30 이전 이미 발표된 과거 지표(day_review)나 미예정 지표 인용 시 즉시 ERROR
        3. [발표 시각 일치 검증] 본문에 언급된 시각(HH:MM)이 canonical today_night 이벤트의 실제 발표시각과 일치하는지 확인
        4. [시장 예상치(forecast) 정합성 검증] 본문에 언급된 예상치가 canonical forecast와 100% 일치하는지, 원천에 없는 예상치를 날조했는지 확인
        5. [빈 목록 안전성] today_night가 비어있을 때 허위 지표 생성을 차단
        """
        errors = []
        if not text:
            return errors

        economic_cal = raw_context.get("economic_calendar", {})
        today_night = economic_cal.get("today_night", [])
        day_review = economic_cal.get("day_review", [])
        next_trading_day = economic_cal.get("next_trading_day", [])

        # 0. 전체 캘린더(today_night, day_review, next_trading_day)가 모두 비어있는 경우
        if not today_night and not day_review and not next_trading_day:
            dev_sentences = re.split(r'(?<=[가-힣a-zA-Z\)])\.\s+|\n+', text)
            for d_sent in dev_sentences:
                if any(w in d_sent for w in ["부재", "없음", "없다", "없습니다"]):
                    continue
                if re.search(r'(?:발표될\s*예정|발표를\s*앞두고|공개될\s*예정|발표가\s*예정|발표\s*대기|공개\s*대기|대기\s*흐름|앞으로\s*발표될|발표\s*예정)', d_sent):
                    errors.append("[daily_event_watchpoints] 금일 발표되었거나 예정된 지표가 없으나 본문에 발표 대기/예정 일정이 허위로 작성되었습니다.")
                    break
            return errors

        # 0-1. 향후 예정 일정(today_night 및 next_trading_day)이 모두 비어있는 경우: 향후 발표 예정 허위 일정 작성 차단
        if not today_night and not next_trading_day:
            dev_sentences = re.split(r'(?<=[가-힣a-zA-Z\)])\.\s+|\n+', text)
            for d_sent in dev_sentences:
                if any(w in d_sent for w in ["부재", "없음", "없다", "없습니다"]):
                    continue
                if any(w in d_sent for w in ["발표될 예정", "발표를 앞두고", "공개될 예정", "발표가 예정되어 있어"]):
                    errors.append("[daily_event_watchpoints] 금일 실행 시각 이후 예정된 지표가 없으나 본문에 향후 발표 예정 일정이 허위로 작성되었습니다.")
                    break

        # Canonical 데이터 코퍼스 및 매핑 구축 (today_night + day_review + next_trading_day 통합)
        all_valid_events = list(today_night) + list(day_review) + list(next_trading_day)
        valid_text_corpus = []
        canonical_times = set()
        canonical_forecast_nums = set()
        canonical_actual_nums = set()
        canonical_prior_nums = set()

        for ev in all_valid_events:
            ev_name = ev.get("event_name", "")
            ev_kor = ev.get("event_name_kor", "")
            rep_ev = ev.get("representative_event", "")
            valid_text_corpus.append(ev_name.lower())
            valid_text_corpus.append(ev_kor.lower())
            if rep_ev:
                valid_text_corpus.append(rep_ev.lower())

            # 시각 (HH:MM)
            sched_time = ev.get("scheduled_time_kst") or (ev.get("scheduled_at", "")[11:16] if len(ev.get("scheduled_at", "")) >= 16 else "")
            if sched_time:
                canonical_times.add(sched_time)
                # "19시 45분", "19시", "01시 15분", "1시 15분" 형태 변형 허용
                if ":" in sched_time:
                    try:
                        h_str, m_str = sched_time.split(":")[:2]
                        h_int = int(h_str)
                        m_int = int(m_str)
                        canonical_times.add(f"{h_int}:{m_str}")
                        canonical_times.add(f"{h_int}시 {m_int}분" if m_int > 0 else f"{h_int}시")
                        canonical_times.add(f"{h_str}시 {m_str}분" if m_int > 0 else f"{h_str}시")
                    except Exception:
                        pass

            # 컴포넌트(세부 일정)도 canonical에 반영
            for comp in ev.get("components") or []:
                c_name = comp.get("event_name", "")
                c_kor = comp.get("event_name_kor", "")
                valid_text_corpus.append(c_name.lower())
                valid_text_corpus.append(c_kor.lower())
                c_time = comp.get("scheduled_time_kst", "")
                if c_time:
                    canonical_times.add(c_time)
                    if ":" in c_time:
                        try:
                            h_str, m_str = c_time.split(":")[:2]
                            h_int = int(h_str)
                            m_int = int(m_str)
                            canonical_times.add(f"{h_int}:{m_str}")
                            canonical_times.add(f"{h_int}시 {m_int}분" if m_int > 0 else f"{h_int}시")
                            canonical_times.add(f"{h_str}시 {m_str}분" if m_int > 0 else f"{h_str}시")
                        except Exception:
                            pass
                cf_val = comp.get("forecast")
                if cf_val and str(cf_val).strip() not in ["-", "None", ""]:
                    f_nums = re.findall(r'[-+]?\d+(?:\.\d+)?', str(cf_val).strip())
                    for fn in f_nums:
                        try:
                            fv = float(fn)
                            canonical_forecast_nums.add(fv)
                            canonical_forecast_nums.add(abs(fv))
                        except ValueError:
                            pass

            # 예상치 (forecast)
            f_val = ev.get("forecast")
            if f_val and str(f_val).strip() not in ["-", "None", ""]:
                f_nums = re.findall(r'[-+]?\d+(?:\.\d+)?', str(f_val).strip())
                for fn in f_nums:
                    try:
                        fv = float(fn)
                        canonical_forecast_nums.add(fv)
                        canonical_forecast_nums.add(abs(fv))
                        if "k" in str(f_val).lower():
                            canonical_forecast_nums.add(fv / 10.0)
                            canonical_forecast_nums.add(abs(fv / 10.0))
                    except ValueError:
                        pass

            # 실제치 (actual)
            a_val = ev.get("actual")
            if a_val and str(a_val).strip() not in ["-", "None", ""]:
                a_nums = re.findall(r'[-+]?\d+(?:\.\d+)?', str(a_val).strip())
                for an in a_nums:
                    try:
                        av = float(an)
                        canonical_actual_nums.add(av)
                        canonical_actual_nums.add(abs(av))
                        if "k" in str(a_val).lower():
                            canonical_actual_nums.add(av / 10.0)
                            canonical_actual_nums.add(abs(av / 10.0))
                    except ValueError:
                        pass

            # 전월치 (prior)
            p_val = ev.get("prior") or ev.get("previous")
            if p_val and str(p_val).strip() not in ["-", "None", ""]:
                p_nums = re.findall(r'[-+]?\d+(?:\.\d+)?', str(p_val).strip())
                for pn in p_nums:
                    try:
                        pv = float(pn)
                        canonical_prior_nums.add(pv)
                        canonical_prior_nums.add(abs(pv))
                        if "k" in str(p_val).lower():
                            canonical_prior_nums.add(pv / 10.0)
                            canonical_prior_nums.add(abs(pv / 10.0))
                    except ValueError:
                        pass

        combined_corpus = " ".join(valid_text_corpus)

        # 주요 글로벌 경제 지표 키워드 감지 사전
        KNOWN_INDICATORS = {
            "ISM 제조업/서비스업 PMI": ["ism", "제조업 pmi", "서비스업 pmi", "ism 제조업", "ism 서비스업"],
            "JOLTS 구인건수": ["jolts", "구인건수", "구인이직"],
            "비농업 고용지수(NFP)": ["비농업 고용", "비농업 고용지수", "비농업 부문", "nfp", "non-farm payroll", "고용보고서"],
            "실업률": ["실업률", "unemployment rate"],
            "ADP 비농업 고용": ["adp", "adp 비농업", "adp 고용", "민간 고용", "adp 주간", "주간 고용변화"],
            "CPI (소비자물가)": ["cpi", "소비자물가", "소비자물가지수"],
            "PPI (생산자물가)": ["ppi", "생산자물가", "생산자물가지수"],
            "PCE 물가지수": ["pce", "개인소비지출", "근원 pce"],
            "GDP 성장률": ["gdp", "경제성장률 속보치"],
            "신규 실업수당 청구": ["신규 실업수당", "실업수당 청구", "jobless claims"],
            "소매판매": ["소매판매", "retail sales"],
            "BOC 통화정책/기준금리": ["boc", "캐나다 중앙은행", "캐나다 기준금리", "캐나다 금리"],
            "FOMC / Fed 금리": ["fomc", "연준 기준금리", "fed 금리결정", "연방공개시장위원회"],
            "ECB 기준금리": ["ecb", "유럽중앙은행 금리", "ecb 기준금리", "ecb 통화정책"],
            "공장재 수주": ["공장재", "factory orders", "공장 수주"],
            "주간 원유재고": ["원유재고", "eia 원유", "주간 원유재고", "crude oil inventories"],
            "소비자신용": ["소비자신용", "consumer credit"],
            "국채 입찰": ["국채 입찰", "국채입찰", "채권 입찰", "bond auction"],
            "정부 재정수지": ["재정수지", "budget balance"],
            "실업자수 변동": ["실업자수", "unemployment change"]
        }

        text_lower = text.lower()

        # 1. 본문에 언급된 지표가 오늘 캘린더 목록(day_review 또는 today_night)에 존재하는지 전수 대조
        for ind_name, keywords in KNOWN_INDICATORS.items():
            if any(kw in text_lower for kw in keywords):
                if not any(kw in combined_corpus for kw in keywords):
                    errors.append(
                        f"[daily_event_watchpoints] 금일 캘린더 목록에 없는 지표 인용 오류: "
                        f"'{ind_name}' 관련 지표는 오늘 발표되었거나 예정된 지표 목록에 존재하지 않습니다."
                    )

        # 2. 본문에 언급된 시각(HH:MM 또는 X시 Y분) 정합성 검사
        as_of_val = raw_context.get("as_of", "")
        run_time_val = raw_context.get("run_time_kst", "")
        as_of_hhmm = run_time_val[11:16] if len(run_time_val) >= 16 else ""

        time_matches = re.findall(r'(?<!\d)([0-2]?\d:[0-5]\d)(?!\d)', text)
        for tm in time_matches:
            # 보고서 기준시각(예: 16:30, 23:25 등) 및 윈도우 마감시각(06:00)은 본문에서 언급될 수 있으므로 예외
            if tm in ["16:30", "16:30:00", "06:00", as_of_hhmm] or (as_of_val and tm in as_of_val):
                continue
            # "01:15" vs "1:15" 정규화
            tm_norm = tm if len(tm) == 5 else f"0{tm}"
            if tm not in canonical_times and tm_norm not in canonical_times:
                errors.append(
                    f"[daily_event_watchpoints] canonical 일정과 불일치하는 발표 시각 인용: "
                    f"'{tm}'은 당일 발표/예정 목록의 공식 발표시각과 불일치합니다."
                )

        # 3. 시장 예상치(forecast) 날조 및 불일치 검증
        forecast_mentions = re.findall(r'(?:예상치?|전망치?|컨센서스)\s*(?:는|가|로|:)?\s*([-+]?\d+(?:\.\d+)?)\s*(?:k|m|b|%|pt|만|억)?', text, re.IGNORECASE)
        for fm in forecast_mentions:
            try:
                fm_float = float(fm)
                if fm_float not in canonical_forecast_nums and abs(fm_float) not in canonical_forecast_nums:
                    errors.append(
                        f"[daily_event_watchpoints] 원천 데이터에 없는 시장 예상치(forecast) 인용/날조 오류: "
                        f"수치 '{fm}'은 당일 캘린더의 공식 예상치 목록에 존재하지 않습니다."
                    )
            except ValueError:
                pass

        # 4. 시제 왜곡(tense mismatch) 검증: 이미 발표 완료/경과된 당일 이벤트를 '발표 예정', '발표 대기', '대기 흐름'으로 서술하는 오류 검출
        pending_pat_str = r'(?:발표될\s*예정|발표를\s*앞두고|공개될\s*예정|발표가\s*예정|발표\s*대기|공개\s*대기|대기\s*흐름|앞으로\s*발표될|발표\s*예정|발표\s*일정을\s*앞두고|발표를\s*대기)'

        # 4-1. today_night 및 next_trading_day가 모두 비어있는 경우 본문에 발표 대기/예정 표현이 있으면 즉시 오류 (단, '부재함', '없음' 등 부재 안내 문장 제외)
        if not today_night and not next_trading_day:
            dev_sentences = re.split(r'(?<=[가-힣a-zA-Z\)])\.\s+|\n+', text)
            for d_sent in dev_sentences:
                if any(w in d_sent for w in ["부재", "없음", "없다", "없습니다"]):
                    continue
                if re.search(pending_pat_str, d_sent):
                    err_msg = (
                        f"[daily_event_watchpoints] 잔여 예정 지표 부재 중 시제 왜곡 오류: "
                        f"향후 예정된 지표가 없으나 문장 '{d_sent.strip()}'에 발표 대기/예정 표현이 사용되었습니다. "
                        f"과거 지표는 '공식 수치 미확인' 또는 '실제치 확인 필요'로 서술하십시오."
                    )
                    if err_msg not in errors:
                        errors.append(err_msg)

        # 4-2. day_review 과거 발표 이벤트별 시제 왜곡 정밀 검출
        GENERIC_EVENT_WORDS = {
            "전년비", "전월비", "전기비", "전분기비", "변동", "지수", "수정치", "예비치", "확정치",
            "발표", "지표", "미국", "일본", "독일", "유로존", "영국", "중국", "캐나다", "한국", "m/m", "y/y", "q/q",
            "월간", "연간", "연간치", "월간치", "잠정치"
        }

        dev_sentences = re.split(r'(?<=[가-힣a-zA-Z\)])\.\s+|\n+', text)
        for ev in day_review:
            ev_kor = ev.get('event_name_kor', '')
            ev_name = ev.get('event_name', '')
            country = ev.get('country', '')
            kw_list = [k for k in [ev_kor, ev_name] if k and k != '-']

            # 한글 및 영문 명칭 토큰 확장 (일반 수식어/통계주기/국가명 토큰 제외)
            if ev_kor and ev_kor != '-':
                for tok in re.split(r'[\s\(\)/]+', ev_kor):
                    if len(tok) >= 2 and tok.lower() not in GENERIC_EVENT_WORDS:
                        kw_list.append(tok)
            if ev_name and ev_name != '-':
                for tok in re.split(r'[\s\(\)/]+', ev_name):
                    if len(tok) >= 3 and tok.lower() not in GENERIC_EVENT_WORDS:
                        kw_list.append(tok)

            # 세부 지표별 동의어 및 주요 키워드 확장 (국가명 단독 키워드 배제, 복합 지표명 사용)
            name_combined = (ev_name + " " + ev_kor).lower()
            if 'leading' in name_combined or '선행' in name_combined:
                kw_list.extend(['선행지수', '선행 지수', '일본 선행'])
            if 'industrial' in name_combined or '산업생산' in name_combined:
                kw_list.extend(['산업생산', '산업 생산', '독일 산업생산'])
            if 'employment' in name_combined or '취업자' in name_combined or '고용' in name_combined:
                kw_list.extend(['취업자수', '취업자 수', '취업자수 변동', '고용 변동'])
            if 'gdp' in name_combined:
                kw_list.extend(['gdp 수정치', '국내총생산'])
            if 'cpi' in name_combined or '물가' in name_combined:
                kw_list.extend(['소비자물가', 'cpi'])
            if 'unemployment' in name_combined or '실업률' in name_combined:
                kw_list.extend(['실업률'])
            if 'nfp' in name_combined or 'non-farm' in name_combined or '비농업' in name_combined:
                kw_list.extend(['비농업 고용', '비농업고용', 'nfp'])

            for kw in kw_list:
                clean_kw = re.sub(r'[\(\)]', '', kw).strip()
                if not clean_kw or len(clean_kw) < 2 or clean_kw.lower() in GENERIC_EVENT_WORDS:
                    continue
                found_err = False
                for d_sent in dev_sentences:
                    # 향후 발표 예정 이벤트(today_night 및 next_trading_day)의 대상 문장이면 과거 지표 시제 왜곡에서 제외
                    is_upcoming_sentence = False
                    upcoming_events = list(today_night) + list(next_trading_day)
                    for fut_ev in upcoming_events:
                        f_name = (fut_ev.get('event_name_kor', '') + " " + fut_ev.get('event_name', '')).lower()
                        for comp in fut_ev.get('components') or []:
                            f_name += " " + (comp.get('event_name_kor', '') + " " + comp.get('event_name', '')).lower()
                        for f_tok in re.split(r'[\s\(\)/]+', f_name):
                            if len(f_tok) >= 3 and f_tok.lower() not in GENERIC_EVENT_WORDS and f_tok.lower() in d_sent.lower():
                                is_upcoming_sentence = True
                                break
                        if is_upcoming_sentence:
                            break

                    if not is_upcoming_sentence and any(w in d_sent for w in ["다음 거래일", "익일", "내일", "다음날", "향후 발표", "주요 발표 예정"]):
                        is_upcoming_sentence = True

                    if is_upcoming_sentence:
                        continue

                    # 만약 과거 이벤트 ev가 특정 국가(예: 중국, 독일)인데, 대상 문장 d_sent가 다른 국가(예: 미국)의 일정을 기술하고 있다면 과거 이벤트 시제 왜곡 아님
                    if country and country.upper() in ["CN", "DE", "JP", "KR", "GB", "CA", "AU"]:
                        if any(c_name in d_sent for c_name in ["미국", "미 ", "US", "U.S."]) and not any(c_name in d_sent for c_name in ["중국", "독일", "일본", "한국", "영국"]):
                            continue

                    if clean_kw.lower() in d_sent.lower() and re.search(pending_pat_str, d_sent, re.IGNORECASE):
                        if any(w in d_sent for w in ["부재", "없음", "없다", "없습니다", "미확인", "확인 필요", "확인이 필요", "확인되지 않아", "예정이었던"]):
                            continue
                        err_msg = (
                            f"[daily_event_watchpoints] 발표 완료 이벤트 시제 왜곡(tense mismatch) 오류: "
                            f"'{clean_kw}'은(는) 발표 시각이 지난 과거 이벤트이나 '{d_sent.strip()}'에서 '발표 대기', '대기 흐름' 또는 '발표 예정'으로 서술되었습니다. "
                            f"actual이 없는 경우 '공식 수치 미확인', '실제치 확인 필요' 등으로 서술하십시오 (가상 수치 생성 금지)."
                        )
                        if err_msg not in errors:
                            errors.append(err_msg)
                        found_err = True
                        break
                if found_err:
                    break

        # 5. actual 부재 지표의 가상 발표치 날조 검증
        for ev in day_review:
            a_val = ev.get("actual")
            if a_val is None or str(a_val).strip() in ["-", "None", ""]:
                ev_kor = ev.get("event_name_kor", "")
                ev_name = ev.get("event_name", "")
                clean_kw = re.sub(r'[\(\)]', '', ev_kor or ev_name).strip()
                if not clean_kw:
                    continue
                # actual이 없는데 본문에서 "실제치는 XX로 발표됨"처럼 작성한 경우 검출
                pat = rf"{re.escape(clean_kw)}[^\.\n]*(?:실제치|발표치|결과(?:는|가)?)\s*(?:는|가|로|:)?\s*([-+]?\d+(?:\.\d+)?)"
                fake_match = re.search(pat, text, re.IGNORECASE)
                if fake_match:
                    errors.append(
                        f"[daily_event_watchpoints] SSOT에 없는 가상 actual 날조 오류: "
                        f"'{clean_kw}'의 actual은 데이터셋에 존재하지 않으나 '{fake_match.group(0)}'으로 작성되었습니다."
                    )

        # 6. 미래 예정 이벤트에 실제치(actual) 날조 검증
        for ev in (today_night + next_trading_day):
            ev_kor = ev.get("event_name_kor", "")
            ev_name = ev.get("event_name", "")
            clean_kw = re.sub(r'[\(\)]', '', ev_kor or ev_name).strip()
            if not clean_kw:
                continue
            pat = rf"{re.escape(clean_kw)}[^\.\n]*(?:실제치(?:는|가|로)?|발표치(?:는|가|로)?|결과(?:는|가)?)\s*([-+]?\d+(?:\.\d+)?)"
            fake_future_match = re.search(pat, text, re.IGNORECASE)
            if fake_future_match:
                errors.append(
                    f"[daily_event_watchpoints] 미래 예정 이벤트 실제치(actual) 날조 오류: "
                    f"'{clean_kw}'은(는) 발표 예정 지표이나 실제치 '{fake_future_match.group(0)}'이(가) 서술되었습니다."
                )

        # 7. 발표 완료 이벤트 실제치 존재 시 forecast만 단독 사용 검증
        for ev in day_review:
            a_val = ev.get("actual")
            f_val = ev.get("forecast")
            if a_val and f_val and str(a_val).strip() not in ["-", "None", ""]:
                ev_kor = ev.get("event_name_kor", "")
                ev_name = ev.get("event_name", "")
                clean_kw = re.sub(r'[\(\)]', '', ev_kor or ev_name).strip()
                if clean_kw and clean_kw in text:
                    pat_only_fc = rf"{re.escape(clean_kw)}[^\.\n]*(?:예상치|전망치)[^\.\n]*(?:기대됨|예정|전망됨)"
                    if re.search(pat_only_fc, text) and not any(w in text for w in ["실제", "발표", "기록", "상회", "하회"]):
                        errors.append(
                            f"[daily_event_watchpoints] 발표 완료 이벤트({clean_kw})의 실제치(actual) 누락 및 forecast만 단독 사용 오류"
                        )

        return errors

    @classmethod
    def _validate_market_session_representation(cls, sec_name: str, text: str, raw_context: Dict[str, Any]) -> List[str]:
        """장중 진행 중인 자산(미국 증시, USD/KRW 야간 환율, 원자재 선물)을 '종가'나 '마감'으로 왜곡 서술했는지, 또는 휴장 상태인 자산을 '장중/당일 거래'로 왜곡했는지 검증"""
        errors = []
        if not text:
            return errors

        # 1. USD/KRW 장외/글로벌 현재환율 세션 오표기 검증
        fx_items = raw_context.get("market_data", {}).get("fx", [])
        usd_krw = next((x for x in fx_items if "KRW" in x.get("field_id", "") or "원/달러" in x.get("name", "")), None)
        if usd_krw and (usd_krw.get("market_status") == "INTRADAY" or "장외" in str(usd_krw.get("price_type", ""))):
            if re.search(r'(?:원/달러|달러/원|원화\s*환율)(?:(?!\.\s)[^\n]){1,30}?(?:하락\s*마감|상승\s*마감|종가를\s*기록|종가로\s*마감)', text):
                errors.append(f"[{sec_name}] USD/KRW 장외 현재환율 세션 왜곡 오류: 야간 장외 환율을 '하락 마감' 등 서울 종가로 단정 서술할 수 없습니다.")

        # 2. 미국 장중 지수 세션 오표기 검증 (정규장 거래 시 '마감' 서술 금지)
        eq_items = raw_context.get("market_data", {}).get("equities", [])
        us_eq_intraday = [x for x in eq_items if x.get("market_status") == "INTRADAY" and not x.get("is_holiday")]
        if us_eq_intraday:
            us_m = re.search(r'(?:미국\s*증시|뉴욕\s*증시|다우(?:\s*지수)?|나스닥(?:\s*종합)?|s&p\s*500)(?:(?!\.\s)[^\n]){1,45}?(?:상승\s*마감|하락\s*마감|종가를\s*기록|종가로\s*마감)', text, re.IGNORECASE)
            if us_m:
                matched_str = us_m.group(0)
                has_other_subject_or_contrast = bool(
                    re.search(r'(?:반면|한편|그러나|하지만|다만)', matched_str) or
                    re.search(r'(?:아시아|국내|한국|중화권|유럽|코스피|코스닥|니케이|상해|항셍|stoxx)\s*(?:증시|지수)?\s*(?:는|은|가|이|도)?\s*(?:[^\n]{0,20})?(?:상승\s*마감|하락\s*마감)', matched_str, re.IGNORECASE)
                )
                if not has_other_subject_or_contrast:
                    errors.append(f"[{sec_name}] 미국 장중 지수 세션 왜곡 오류: 정규장 진행 중인 현재가를 '마감'으로 서술할 수 없습니다.")

        # 3. 미국 증시 휴장 상태 세션 왜곡 검증 (휴장 시 '장중 약세/상승' 등 당일 거래 서술 금지)
        us_eq_holiday = [
            x for x in eq_items 
            if x.get("is_holiday") 
            or ("US" in x.get("field_id", "") and x.get("price_type") == "PREVIOUS_CLOSE" and x.get("market_status") in ["CLOSED", "MARKET_CLOSED"])
            or x.get("return_basis") == "PREVIOUS_TRADING_DAY"
        ]
        has_us_equity_holiday = bool(us_eq_holiday) or any("미국" in str(h) or "S&P" in str(h) for h in raw_context.get("market_holidays", []))
        if has_us_equity_holiday:
            if re.search(r'(?:미국\s*(?:주요\s*)?지수|미국\s*증시|뉴욕\s*증시|다우|나스닥|s&p\s*500)(?:(?!\.\s)[^\n]){1,30}?(?:장중\s*약세|장중\s*하락|장중\s*상승|장중\s*흐름|장중에|현재\s*약세|현재\s*상승|현재\s*하락|장중\s*거래)', text, re.IGNORECASE):
                errors.append(f"[{sec_name}] 미국 증시 휴장 세션 왜곡 오류: 미국 증시가 공식 휴장 상태이나 '장중 약세/하락/상승' 등 당일 거래를 전제로 서술되었습니다. '휴장' 또는 '직전 거래일 종가 유지'로 서술하십시오.")

        # 4. 미국 국채시장 휴장 상태 세션 왜곡 검증 (휴장 시 '당일 금리 상승/오름세 유지' 등 당일 거래 서술 금지)
        bond_items = raw_context.get("market_data", {}).get("bonds", [])
        us_bond_holiday = [
            x for x in bond_items 
            if ("US" in x.get("field_id", "") or "미국" in x.get("name", "")) 
            and (x.get("is_holiday") or x.get("market_status") in ["CLOSED", "MARKET_CLOSED"] or x.get("return_basis") == "PREVIOUS_TRADING_DAY")
        ]
        has_us_bond_holiday = bool(us_bond_holiday) or any("국채" in str(h) for h in raw_context.get("market_holidays", []))
        if has_us_bond_holiday:
            if re.search(r'(?:미국\s*국채(?:\s*금리)?|미국채(?:\s*금리)?|미국\s*및\s*국내\s*국채\s*금리)(?:(?!\.\s)[^\n]){1,30}?(?:당일\s*상승|오름세를\s*유지|상승세를\s*유지|당일\s*상승\s*압력|상승\s*압력을\s*받음)', text):
                errors.append(f"[{sec_name}] 미국 국채시장 휴장 세션 왜곡 오류: 미국 국채시장이 공식 휴장 상태이나 '당일 상승/오름세 유지' 등 당일 거래를 전제로 서술되었습니다. '휴장으로 직전 거래일 수준 유지'로 서술하십시오.")

        # 5. 원자재 장중 가격 세션 오표기 검증
        comm_items = raw_context.get("market_data", {}).get("commodities", [])
        intraday_comm = [x for x in comm_items if x.get("market_status") == "INTRADAY"]
        if intraday_comm:
            # 원자재 자체가 주어로서 마감으로 서술된 경우만 탐지 ('유가 상승 부담 속에 [미국 증시] 하락 마감' 등 타 주어 수식은 제외)
            comm_match = re.search(r'(?:wti|국제유가|유가|원유|금\s*선물)(?:(?!\.\s)[^\n]){1,45}?(?:상승\s*마감|하락\s*마감|종가를\s*기록|종가로\s*마감)', text, re.IGNORECASE)
            if comm_match:
                matched_str = comm_match.group(0)
                is_causal_or_other_subject = bool(
                    re.search(r'(?:에\s*따른|으로\s*인한|로\s*인한|에\s*기인한|부담\s*속에|영향\s*속에|부담으로|우려로|영향으로|압력으로)', matched_str) or
                    re.search(r'(?:증시|지수|다우|나스닥|s&p|코스피|코스닥)\s*(?:가|는|이|도|들이)\s*(?:[^\n]{0,20})?(?:상승\s*마감|하락\s*마감)', matched_str, re.IGNORECASE) or
                    re.search(r'(?:상승|급등|하락|급락)\s*(?:부담|영향|우려|여파|압력|속에|따라|대책)', matched_str)
                )
                if not is_causal_or_other_subject:
                    errors.append(f"[{sec_name}] 원자재 장중 선물 세션 왜곡 오류: 장중 현재가를 '마감'으로 서술할 수 없습니다.")

        # 6. 원자재 change_status == UNAVAILABLE 시 '0% 변동' / '보합 마감/유지' 왜곡 서술 검증
        unavail_comm = [x for x in comm_items if x.get("change_status") == "UNAVAILABLE"]
        if unavail_comm:
            if re.search(r'(?:wti|brent|브렌트|천연가스|국제유가)(?:(?!\.\s)[^\n])*?(?:0%|0\.00%|보합세(?:를\s*기록|를\s*유지|를\s*보임|으로)|변동\s*없이\s*마감|변동\s*없음)', text, re.IGNORECASE):
                errors.append(f"[{sec_name}] 원자재 정산가 미발표 왜곡 오류: 해당 원자재(WTI/Brent 등)는 미국 휴장/정산가 미제공으로 변동률이 미확인(UNAVAILABLE) 상태이나 '0% 변동/보합세'로 왜곡 서술되었습니다. 가격 수준만 객관적으로 언급하십시오.")

        return errors

    @classmethod
    def _validate_unsupported_causality(cls, sec_name: str, text: str, raw_context: Dict[str, Any]) -> List[str]:
        """SSOT에 근거 없는 변수(실질금리 부담, 공급 부담), 직접 관측되지 않은 수급/심리(차익실현), 미근거 인과관계(연동되어) 및 역사적 비교(몇 개월 만의 최고치) 차단"""
        errors = []
        if not text:
            return errors

        PROHIBITED_CAUSALITY_PATTERNS = [
            (r'차익\s*실현(?:\s*매물)?(?:이\s*유입|로\s*연결|이\s*출회)?', "차익실현 매물 유입"),
            (r'실질\s*금리\s*부담', "실질금리 부담"),
            (r'안전자산\s*수요와\s*인플레이션\s*헤지\s*심리', "안전자산 수요와 인플레이션 헤지 심리"),
            (r'인플레이션\s*헤지\s*심리', "인플레이션 헤지 심리 유입"),
            (r'공급\s*부담이\s*금리\s*상승\s*압력', "공급 부담이 금리 상승 압력 작용"),
            (r'채권\s*공급\s*부담', "채권 공급 부담"),
            (r'국채\s*발행\s*공급\s*부담', "국채 발행 공급 부담"),
            (r'(?:에\s*연동되어|과\s*연동되어|와\s*연동되어|에\s*연동돼|과\s*연동돼|와\s*연동돼)', "동시 발생 자산 간 미근거 연동 인과관계 단정"),
            (r'시장에서는\s*[^.\n]+(?:평가했다|평가함|보고\s*있다|해석했다|해석함)', "확인되지 않은 시장 평가/심리 단정"),
            (r'(?:에\s*따른|에\s*따라)\s*[^.\n]+(?:판단된다|판단함|풀이된다|풀이함)', "미근거 인과관계 판단 단정"),
            (r'(?:최근\s*)?(?:\d+\s*개월|\d+\s*년|\d+\s*주)\s*만의\s*(?:최고|최저|최대|수준)', "SSOT 미근거 과거 기간 비교(몇 개월/년 만의 최고치 등)"),
            (r'(?:올해\s*들어|연중|사상|역대)\s*(?:가장\s*높은|가장\s*낮은|최고|최저|최대)', "SSOT 미근거 연중/사상/역대 최고·최저 비교"),
            (r'사상\s*최고(?:치)?', "사상 최고치 표현"),
            (r'역대\s*최고(?:치)?', "역대 최고치 표현"),
            (r'휴장(?:으로|함에\s*따라|에\s*따라)[^.\n]*(?:지표\s*발표|발표가\s*제한|일정이\s*제한)', "금융시장 휴장과 경제지표 발표 인과관계 왜곡"),
            (r'가격\s*재산정\s*과정', "가격 재산정 과정 클리셰"),
            (r'위험\s*회피\s*심리가\s*(?:강화|확대|고조|부각|지속|작용)', "위험회피 심리 강화 클리셰"),
            (r'안전\s*자산\s*선호(?:가|는)?\s*(?:강화|확대|고조|부각|지속|작용)', "안전자산 선호 강화 클리셰"),
            (r'차익\s*실현\s*매물이\s*출회', "차익실현 매물 출회 클리셰"),
            (r'불확실성이\s*(?:상존|지속|확대|부각|고조)', "불확실성이 상존/지속/확대 클리셰"),
            (r'흐름이\s*지속될\s*전망', "흐름이 지속될 전망 클리셰"),
            (r'때문에', "근거 없는 인과관계(~때문에)"),
            (r'에\s*따른\s*결과', "근거 없는 인과관계(~에 따른 결과)"),
        ]

        for pat, desc in PROHIBITED_CAUSALITY_PATTERNS:
            match = re.search(pat, text)
            if match:
                errors.append(
                    f"[{sec_name}] SSOT 미근거 변수/수급/인과관계/역사적비교/클리셰 오류: "
                    f"'{match.group(0)}'과(와) 같이 SSOT에 존재하지 않는 인과관계, 평가, 또는 과거 기간 최고/최저 표현 및 상투적 클리셰는 금지됩니다. "
                    f"관측된 당일 사실 중심으로 단순화하십시오."
                )

        return errors

    @classmethod
    def _validate_unsupported_sector_and_stock_claims(cls, sec_name: str, text: str, raw_context: Dict[str, Any]) -> List[str]:
        """
        SSOT 뉴스에 명시적인 근거가 없는 개별 종목/업종의 움직임이나 사건 날조 차단.
        뉴스에 실제로 존재할 때만 해당 내용의 범위 안에서 서술 허용.
        """
        errors = []
        if not text:
            return errors

        # SSOT 뉴스 코퍼스 구축 (제목, 요약, 카테고리 등)
        news_items = raw_context.get("verified_macro_news", []) or raw_context.get("news", [])
        news_corpus_parts = []
        for n in news_items:
            news_corpus_parts.append(str(n.get("headline", "")))
            news_corpus_parts.append(str(n.get("summary", "")))
            news_corpus_parts.append(str(n.get("category", "")))
        news_corpus = " ".join(news_corpus_parts).lower()

        # 요주의 업종/종목/사건 키워드 목록
        SECTOR_KEYWORDS = [
            (r'ai\s*하드웨어(?:\s*인프라)?', "AI 하드웨어 인프라"),
            (r'반도체(?:주|업종|기업)?', "반도체주/업종"),
            (r'바이오(?:주|업종|기업)?', "바이오주/업종"),
            (r'제약\s*(?:주|업종|기업|바이오|섹터)', "제약주/업종"),
            (r'금융주', "금융주"),
            (r'임상\s*(?:실패|결과|진행|성공)', "임상 실패/결과"),
            (r'개별\s*(?:종목|업종)의\s*(?:실적|임상|상대강도)', "개별 종목/업종 실적/상대강도"),
        ]

        for pat, desc in SECTOR_KEYWORDS:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                matched_term = match.group(0)
                # 핵심 단어가 뉴스 코퍼스에 존재하는지 확인
                core_words = re.findall(r'[가-힣a-zA-Z]{2,}', matched_term)
                has_news_ground = any(cw.lower() in news_corpus for cw in core_words if len(cw) >= 2)
                if not has_news_ground:
                    errors.append(
                        f"[{sec_name}] SSOT 뉴스 미근거 개별 업종/종목 서술 오류: "
                        f"'{matched_term}'은(는) 당일 SSOT 뉴스 기사에 근거가 존재하지 않는 개별 업종/종목 내용입니다. "
                        f"지수 데이터만 있는 경우 개별 종목군이나 업종의 세부 움직임을 임의 추론하여 작성할 수 없습니다."
                    )
        return errors

    @classmethod
    def _validate_data_to_sentence_alignment(cls, sec_name: str, text: str, raw_context: Dict[str, Any]) -> List[str]:
        """
        데이터-문장 변환 정합성 검증 (자산-문장/절 단위 바인딩):
        1. 각 문장을 접속사/쉼표 기준 절(clause) 단위로 분할하여 해당 절에 언급된 자산 식별
        2. 식별된 자산의 SSOT 수치(change_pct, bp_change, price_type, change_status, is_holiday)와 해당 절의 서술 대조
        3. 자산명-등락방향 불일치, 등락폭 과장 수식어(<1%에 가파른/큰폭), price_type 오표기(마감 자산에 장중), 원자재 미산출 왜곡 검출
        """
        errors = []
        if not text:
            return errors

        # 1. SSOT 자산 정보 맵 빌드
        FIELD_ID_TO_ALIAS_KEY = {
            "EQUITY.^KS11": "KOSPI", "^KS11": "KOSPI",
            "EQUITY.^KQ11": "KOSDAQ", "^KQ11": "KOSDAQ",
            "EQUITY.^VIX": "VIX", "^VIX": "VIX",
            "EQUITY.^GSPC": "^GSPC",
            "EQUITY.^DJI": "^DJI",
            "EQUITY.^IXIC": "^IXIC",
            "EQUITY.000001.SS": "000001.SS", "000001.SS": "000001.SS",
            "EQUITY.^HSI": "^HSI",
            "EQUITY.^N225": "^N225",
            "EQUITY.^STOXX50E": "^STOXX50E",
            "FX.DX-Y.NYB": "DX-Y.NYB",
            "FX.KRW=X": "KRW=X",
            "FX.JPY=X": "JPY=X",
            "FX.CNH=F": "CNH=F",
            "FX.EURUSD=X": "EURUSD=X",
            "FX.GBPUSD=X": "GBPUSD=X",
            "BOND.KTB 3y": "BOND.KTB 3y", "KTB 3y": "BOND.KTB 3y",
            "BOND.KTB10y": "BOND.KTB10y", "KTB10y": "BOND.KTB10y",
            "BOND.US2Y": "BOND.US2Y", "US2Y": "BOND.US2Y",
            "BOND.US10Y": "BOND.US10Y", "US10Y": "BOND.US10Y",
            "BOND.JP10Y-JP": "BOND.JP10Y", "JP10Y-JP": "BOND.JP10Y", "BOND.JP10Y": "BOND.JP10Y",
            "BOND.DE10Y-DE": "BOND.DE10Y", "DE10Y-DE": "BOND.DE10Y", "BOND.DE10Y": "BOND.DE10Y",
            "COMMODITY.CL=F": "CL=F",
            "COMMODITY.BZ=F": "BZ=F",
            "COMMODITY.GC=F": "GC=F",
            "COMMODITY.SI=F": "SI=F",
            "COMMODITY.HG=F": "HG=F",
            "COMMODITY.NG=F": "NG=F"
        }

        asset_map: Dict[str, Dict[str, Any]] = {}
        market_ordered = raw_context.get("market_data_ordered") or raw_context.get("market_data", {})
        for cat_name, cat_list in market_ordered.items():
            if not isinstance(cat_list, list) or cat_name in ["spreads", "key_spreads"]:
                continue
            for item in cat_list:
                sym = item.get("symbol", "")
                field_id = item.get("field_id", "")
                name = item.get("name", "")
                asset_info = {
                    "field_id": field_id,
                    "name": name,
                    "symbol": sym,
                    "change_pct": item.get("change_pct") if item.get("change_pct") is not None else item.get("pct_change"),
                    "bp_change": item.get("change_bp") if item.get("change_bp") is not None else item.get("bp_change"),
                    "price_type": item.get("price_type", ""),
                    "market_status": item.get("market_status", ""),
                    "return_basis": item.get("return_basis", ""),
                    "change_status": item.get("change_status", "CONFIRMED"),
                    "is_holiday": bool(item.get("is_holiday") or item.get("market_status") == "MARKET_CLOSED")
                }
                alias_k = FIELD_ID_TO_ALIAS_KEY.get(field_id) or FIELD_ID_TO_ALIAS_KEY.get(sym)
                if alias_k:
                    asset_map[alias_k] = asset_info
                if sym:
                    asset_map[sym] = asset_info
                if field_id:
                    asset_map[field_id] = asset_info
                if name:
                    asset_map[name] = asset_info

        # 문장 단위 분할
        sentences = re.split(r'(?<=[가-힣a-zA-Z\)])\.\s+|\n+', text)
        for sent in sentences:
            sent_clean = sent.strip()
            if not sent_clean:
                continue

            sent_lower = sent_clean.lower()
            # 문장 내 모든 자산 언급 위치(span) 식별
            occurrences: List[Tuple[int, int, str, Dict[str, Any]]] = []
            for asset_key, aliases in cls.ASSET_ALIASES.items():
                if asset_key == "SPREAD":
                    continue
                info = asset_map.get(asset_key)
                if not info:
                    continue
                for alias in aliases:
                    pos = 0
                    while True:
                        idx = sent_lower.find(alias.lower(), pos)
                        if idx == -1:
                            break
                        occurrences.append((idx, idx + len(alias), asset_key, info))
                        pos = idx + len(alias)

            if not occurrences:
                continue

            # 위치 순으로 정렬하고 겹치는 매칭(예: '엔/달러' vs '엔/달러 환율')은 더 긴 쪽 선택
            occurrences.sort(key=lambda x: (x[0], -(x[1] - x[0])))
            filtered_occs: List[Tuple[int, int, str, Dict[str, Any]]] = []
            for o in occurrences:
                if not filtered_occs or o[0] >= filtered_occs[-1][1]:
                    filtered_occs.append(o)

            for i, (st, end, asset_key, info) in enumerate(filtered_occs):
                next_st = filtered_occs[i+1][0] if i < len(filtered_occs) - 1 else len(sent_clean)
                scope_raw = sent_clean[st:next_st].strip()

                # 절(Clause) 단위 경계 식별: 자산명 이후의 첫 접속사/연결어미에서 자산 범위 분리 (단순 쉼표 제외)
                rel_end = end - st
                after_asset = scope_raw[rel_end:]
                delim_m = re.search(r'[,;]\s*(?:반면|한편|그러나|하지만|다만)\b|\b(?:반면|가운데|한편)\b|(?<=[가-힣])(?:하여|하며|하고|했으나|하였으나|되었으나|마감하여|마감하며|마감하고|마감했으나|았으나|었으나|으나|받았으나|지만|바\s*있어|했으며|하였으며|마감했으며)', after_asset)
                if delim_m:
                    scope_text = (scope_raw[:rel_end] + after_asset[:delim_m.end()]).strip()
                else:
                    scope_text = scope_raw

                # Disambiguation between Korean and US bonds
                prefix_context = sent_clean[max(0, st - 30):st]
                if asset_key == "BOND.KTB10y":
                    if any(w in scope_text for w in ["미국", "미 ", "미국채", "미 10년", "장중"]) or ("국고채" not in scope_text and "한국" not in scope_text and "국내" not in scope_text and "장중" in scope_text):
                        us10_info = asset_map.get("BOND.US10Y") or asset_map.get("US10Y")
                        if us10_info:
                            asset_key = "BOND.US10Y"
                            info = us10_info
                elif asset_key == "BOND.US10Y":
                    if any(w in scope_text or w in prefix_context for w in ["국고채", "한국", "국내"]):
                        ktb10_info = asset_map.get("BOND.KTB10y") or asset_map.get("KTB10y")
                        if ktb10_info:
                            asset_key = "BOND.KTB10y"
                            info = ktb10_info
                elif asset_key == "BOND.KTB 3y":
                    if any(w in scope_text for w in ["미국", "미 ", "미국채", "미 2년"]):
                        us2_info = asset_map.get("BOND.US2Y") or asset_map.get("US2Y")
                        if us2_info:
                            asset_key = "BOND.US2Y"
                            info = us2_info
                elif asset_key == "BOND.US2Y":
                    if any(w in scope_text or w in prefix_context for w in ["국고채", "한국", "국내"]):
                        ktb3_info = asset_map.get("BOND.KTB 3y") or asset_map.get("KTB 3y")
                        if ktb3_info:
                            asset_key = "BOND.KTB 3y"
                            info = ktb3_info

                asset_name = info.get("name") or asset_key
                chg_pct = info.get("change_pct")
                bp_chg = info.get("bp_change")
                pt = str(info.get("price_type", ""))
                ms = str(info.get("market_status", ""))
                chg_st = str(info.get("change_status", "CONFIRMED"))
                is_hol = info.get("is_holiday", False)

                # A. 수식어 과장 검출 (절대값 < 1.0% 또는 채권 < 5.0 bp)
                is_small_change = False
                if chg_pct is not None and abs(chg_pct) < 1.0:
                    is_small_change = True
                elif bp_chg is not None and abs(bp_chg) < 5.0:
                    is_small_change = True

                if is_small_change:
                    if re.search(r'(?:가파른|급격한|큰\s*폭의|이례적인)', scope_text):
                        chg_display = f"{chg_pct}%" if chg_pct is not None else f"{bp_chg}bp"
                        errors.append(
                            f"[{sec_name}] 등락폭 과장 수식어 오류: '{asset_name}'(변동폭: {chg_display})의 변동은 ±1.0%(또는 5bp) 미만이나 '{scope_text}'에서 '가파른', '큰 폭의' 등 과장된 수식어가 사용되었습니다."
                        )

                # B. 방향성 일치 검증
                # 외환 (FX) 통화쌍 특별 처리
                if asset_key == "KRW=X" or "KRW" in asset_key:
                    if chg_pct is not None:
                        if chg_pct < -0.05: # 환율 하락 = 원화 강세
                            if re.search(r'(?:원화\s*약세|환율\s*상승|원화\s*절하)', scope_text):
                                errors.append(f"[{sec_name}] 환율 방향 왜곡 오류: USD/KRW 환율 하락({chg_pct}%)은 원화 강세이나 '{scope_text}'에서 원화 약세/환율 상승으로 서술되었습니다.")
                        elif chg_pct > 0.05: # 환율 상승 = 원화 약세
                            if re.search(r'(?:원화\s*강세|환율\s*하락|원화\s*절상)', scope_text):
                                errors.append(f"[{sec_name}] 환율 방향 왜곡 오류: USD/KRW 환율 상승(+{chg_pct}%)은 원화 약세이나 '{scope_text}'에서 원화 강세/환율 하락으로 서술되었습니다.")
                elif asset_key == "JPY=X" or "JPY" in asset_key:
                    if chg_pct is not None:
                        if chg_pct < -0.05: # 환율 하락 = 엔화 강세
                            if re.search(r'(?:엔화\s*약세|환율\s*상승|엔화\s*절하)', scope_text):
                                errors.append(f"[{sec_name}] 환율 방향 왜곡 오류: USD/JPY 환율 하락({chg_pct}%)은 엔화 강세이나 '{scope_text}'에서 엔화 약세/환율 상승으로 서술되었습니다.")
                        elif chg_pct > 0.05: # 환율 상승 = 엔화 약세
                            if re.search(r'(?:엔화\s*강세|환율\s*하락|엔화\s*절상)', scope_text):
                                errors.append(f"[{sec_name}] 환율 방향 왜곡 오류: USD/JPY 환율 상승(+{chg_pct}%)은 엔화 약세이나 '{scope_text}'에서 엔화 강세/환율 하락으로 서술되었습니다.")
                elif asset_key == "CNH=F" or "CNH" in asset_key:
                    if chg_pct is not None:
                        if chg_pct < -0.05: # 환율 하락 = 위안화 강세
                            if re.search(r'(?:위안화\s*약세|환율\s*상승|위안화\s*절하)', scope_text):
                                errors.append(f"[{sec_name}] 환율 방향 왜곡 오류: USD/CNH 환율 하락({chg_pct}%)은 위안화 강세이나 '{scope_text}'에서 위안화 약세/환율 상승으로 서술되었습니다.")
                        elif chg_pct > 0.05: # 환율 상승 = 위안화 약세
                            if re.search(r'(?:위안화\s*강세|환율\s*하락|위안화\s*절상)', scope_text):
                                errors.append(f"[{sec_name}] 환율 방향 왜곡 오류: USD/CNH 환율 상승(+{chg_pct}%)은 위안화 약세이나 '{scope_text}'에서 위안화 강세/환율 하락으로 서술되었습니다.")
                else:
                    # 일반 자산 (주식, 원자재, 채권, DXY, EUR/USD, GBP/USD)
                    if chg_pct is not None:
                        # '달러화 약세/강세' 등 달러 배경 수식어는 다른 자산의 자체 등락 표현이 아니므로 마스킹
                        dir_scope_text = scope_text
                        if asset_key != "DX-Y.NYB":
                            dir_scope_text = re.sub(r'달러(?:화)?\s*(?:약세|강세)', 'USD_BIAS', dir_scope_text)

                        if chg_pct > 0.1: # 상승 자산
                            target_dir_text = dir_scope_text
                            if re.search(r'(?:증시|주가|지수|주식시장)\s*(?:[^\n]{0,15})?(?:약세|하락|하락세|내림세|조정|반락)', target_dir_text):
                                target_dir_text = re.sub(r'(?:증시|주가|지수|주식시장)\s*(?:[^\n]{0,15})?(?:약세|하락|하락세|내림세|조정|반락)', 'EQUITY_WEAKNESS', target_dir_text)

                            if re.search(r'(?:하락\s*마감|하락세|내림세|약세|하락함|하락했다|내렸다|하회|급락|하향|조정|반락|되돌림)', target_dir_text) and not re.search(r'(?:상승|오름세|강세|올랐다|상회|급등|반등|상향)', target_dir_text):
                                errors.append(f"[{sec_name}] 자산 등락 방향 왜곡 오류: '{asset_name}'(등락률: +{chg_pct}%)은 상승하였으나 '{scope_text}'에서 하락/약세로 서술되었습니다.")
                        elif chg_pct < -0.1: # 하락 자산
                            if re.search(r'(?:상승\s*마감|상승세|오름세|강세|상승함|상승했다|올랐다|상회|급등|반등|상향)', dir_scope_text) and not re.search(r'(?:하락|내림세|약세|내렸다|하회|급락|하향|조정|조정을\s*받|반락|되돌림)', dir_scope_text):
                                errors.append(f"[{sec_name}] 자산 등락 방향 왜곡 오류: '{asset_name}'(등락률: {chg_pct}%)은 하락하였으나 '{scope_text}'에서 상승/강세로 서술되었습니다.")
                    elif bp_chg is not None:
                        # 채권 금리 bp 단위 방향성 일치 검증
                        if bp_chg > 0.2: # 금리 상승
                            if re.search(r'(?:하락\s*마감|하락세|내림세|약세|하락함|하락했다|내렸다|하회|급락)', scope_text) and not re.search(r'(?:상승|오름세|강세|올랐다|상회|급등|반등|상향)', scope_text):
                                errors.append(f"[{sec_name}] 채권 금리 방향 왜곡 오류: '{asset_name}'(변동폭: +{bp_chg}bp)은 상승하였으나 '{scope_text}'에서 하락/내림세로 서술되었습니다.")
                        elif bp_chg < -0.2: # 금리 하락
                            if re.search(r'(?:상승\s*마감|상승세|오름세|강세|상승함|상승했다|올랐다|상회|급등|반등|상향)', scope_text) and not re.search(r'(?:하락|내림세|약세|내렸다|하회|급락|하향|조정)', scope_text):
                                errors.append(f"[{sec_name}] 채권 금리 방향 왜곡 오류: '{asset_name}'(변동폭: {bp_chg}bp)은 하락하였으나 '{scope_text}'에서 상승/오름세로 서술되었습니다.")

                # C. price_type 및 세션 일치 검증
                if is_hol or pt == "PREVIOUS_CLOSE" or ms == "MARKET_CLOSED":
                    if re.search(r'(?:장중\s*(?:약세|상승|하락|거래|흐름)?|장중에|당일\s*상승|당일\s*하락|오름세를\s*유지|당일\s*마감)', scope_text):
                        errors.append(
                            f"[{sec_name}] 휴장 자산 당일 거래 왜곡 오류: '{asset_name}'은 휴장(직전 종가 기준) 자산이나 '{scope_text}'에서 장중 거래 또는 당일 변동으로 서술되었습니다. '직전 거래일 종가 유지'로 서술하십시오."
                        )
                elif ms == "CLOSED" or pt in ["종가", "확정종가"]:
                    # 명시적으로 '마감'이 기술되어 있다면 장중 오표기가 아님
                    if re.search(r'마감(?:함|했다|하며|하여|한|하고|했으나|으로)', scope_text):
                        pass
                    elif re.search(r'(?:장중\s*(?:약세|상승|하락|거래|흐름)?|장중에)', scope_text):
                        errors.append(
                            f"[{sec_name}] 마감 자산 세션 오표기 오류: '{asset_name}'은 당일 마감된 자산(price_type={pt})이나 '{scope_text}'에서 '장중'으로 왜곡 서술되었습니다. '상승/하락 마감'으로 서술하십시오."
                        )
                elif ms == "INTRADAY" or pt in ["현재가", "INTRADAY"]:
                    if re.search(r'(?:상승\s*마감|하락\s*마감|종가를\s*기록|종가로\s*마감)', scope_text):
                        is_causal_or_other_subject = bool(
                            re.search(r'(?:에\s*따른|으로\s*인한|로\s*인한|에\s*기인한|부담\s*속에|영향\s*속에|부담으로|우려로|영향으로|압력으로)', scope_text) or
                            re.search(r'(?:증시|지수|다우|나스닥|s&p|코스피|코스닥)\s*(?:가|는|이|도|들이)\s*(?:[^\n]{0,20})?(?:상승\s*마감|하락\s*마감)', scope_text, re.IGNORECASE) or
                            re.search(r'(?:상승|급등|하락|급락)\s*(?:부담|영향|우려|여파|압력|속에|따라|대책)', scope_text)
                        )
                        if not is_causal_or_other_subject:
                            errors.append(
                                f"[{sec_name}] 장중 자산 세션 오표기 오류: '{asset_name}'은 실시간 장중 거래 자산(price_type={pt})이나 '{scope_text}'에서 '마감'으로 왜곡 서술되었습니다. '장중 거래/상승/하락'으로 서술하십시오."
                            )


                # D. change_status == UNAVAILABLE (원자재 정산가 미산출 등)
                if chg_st == "UNAVAILABLE":
                    if re.search(r'(?:상승|하락|오름세|내림세|강세|약세|0%|0\.00%|보합|변동\s*없이)', scope_text):
                        errors.append(
                            f"[{sec_name}] 원자재 미산출 데이터 왜곡 오류: '{asset_name}'은 등락률 확인 불가(UNAVAILABLE) 상태이나 '{scope_text}'에서 방향성이나 0%/보합으로 왜곡 서술되었습니다."
                        )

        # E. 채권 커브(Steepening / Flattening) 및 만기 상반 방향 검증
        us10_info = asset_map.get("BOND.US10Y") or asset_map.get("US10Y")
        us2_info = asset_map.get("BOND.US2Y") or asset_map.get("US2Y")
        if us10_info and us2_info:
            u10_bp = us10_info.get("bp_change") or 0.0
            u2_bp = us2_info.get("bp_change") or 0.0
            u_curve_diff = u10_bp - u2_bp
            if u_curve_diff > 0.3: # 스티프닝 (장단기 스프레드 확대)
                if re.search(r'(?:미국|미\s*국채|미\s*10년|10-2년)[^\.\n]{0,25}?(?:수익률곡선|커브|스프레드|금리차)?[^\.\n]{0,15}?(?:플래트닝|평탄화)', text):
                    errors.append(f"[{sec_name}] 미국 국채 커브 왜곡 오류: 미국 10Y-2Y 스프레드가 확대(+{u_curve_diff:.1f}bp)되어 스티프닝이나 '플래트닝'으로 왜곡 서술되었습니다.")
            elif u_curve_diff < -0.3: # 플래트닝 (장단기 스프레드 축소)
                if re.search(r'(?:미국|미\s*국채|미\s*10년|10-2년)[^\.\n]{0,25}?(?:수익률곡선|커브|스프레드|금리차)?[^\.\n]{0,15}?(?:스티프닝|가팔라)', text):
                    errors.append(f"[{sec_name}] 미국 국채 커브 왜곡 오류: 미국 10Y-2Y 스프레드가 축소({u_curve_diff:.1f}bp)되어 플래트닝이나 '스티프닝'으로 왜곡 서술되었습니다.")

            # 미국 2년물과 10년물 방향이 다른 경우 단일 방향 서술 차단 ("미국 금리 상승" 단정 차단)
            if u2_bp < -0.2 and u10_bp > 0.2:
                if re.search(r'미국\s*(?:국채\s*)?금리(?:가|는)?\s*(?:전반적으로\s*)?(?:상승|오름세|급등)', text) and not re.search(r'(?:혼조|차별화|2년물은\s*하락|엇갈|스티프닝|만기별)', text):
                    errors.append(f"[{sec_name}] 채권 만기별 방향 왜곡: 미국 2년물({u2_bp:+.1f}bp)과 10년물({u10_bp:+.1f}bp)의 방향이 상이하나 '미국 국채금리 상승'으로 단일 방향 요약됨. '만기별 차별화' 또는 '혼조세'로 서술하십시오.")

        # 한국 국고채 커브 검증
        ktb10_info = asset_map.get("BOND.KTB10y") or asset_map.get("KTB10y")
        ktb3_info = asset_map.get("BOND.KTB 3y") or asset_map.get("KTB 3y")
        if ktb10_info and ktb3_info:
            k10_bp = ktb10_info.get("bp_change") or 0.0
            k3_bp = ktb3_info.get("bp_change") or 0.0
            k_curve_diff = k10_bp - k3_bp
            if k_curve_diff < -0.3: # 플래트닝
                if re.search(r'(?:국내|한국|국고채|10-3y|10-3년)[^\.\n]{0,25}?(?:수익률곡선|커브|스프레드|금리차)?[^\.\n]{0,15}?(?:스티프닝|가팔라)', text):
                    errors.append(f"[{sec_name}] 국내 국고채 커브 왜곡 오류: 국고채 10-3y 스프레드가 축소({k_curve_diff:.1f}bp)되어 플래트닝이나 '스티프닝'으로 왜곡 서술되었습니다.")
            elif k_curve_diff > 0.3: # 스티프닝
                if re.search(r'(?:국내|한국|국고채|10-3y|10-3년)[^\.\n]{0,25}?(?:수익률곡선|커브|스프레드|금리차)?[^\.\n]{0,15}?(?:플래트닝|평탄화)', text):
                    errors.append(f"[{sec_name}] 국내 국고채 커브 왜곡 오류: 국고채 10-3y 스프레드가 확대(+{k_curve_diff:.1f}bp)되어 스티프닝이나 '플래트닝'으로 왜곡 서술되었습니다.")

        return errors

    @classmethod
    def _validate_event_data_consistency(cls, raw_context: Dict[str, Any]) -> List[str]:
        """SSOT/컨텍스트 자체의 데이터 정합성 검증 (참조기간 vs 관측기간, 릴리스 정합성, revised prior 연속성)"""
        errors = []
        cal = raw_context.get("economic_calendar", {})
        day_review = cal.get("day_review", [])

        for ev in day_review:
            ref_p = ev.get("reference_period") or ev.get("target_period")
            act_src = ev.get("actual_source")
            # reference period와 BLS observation period 불일치
            if ref_p and act_src and "BLS" in str(act_src):
                src_period_match = re.search(r'(\d{4}-M\d{2})', str(act_src))
                if src_period_match:
                    src_p = src_period_match.group(1)
                    if src_p != ref_p:
                        errors.append(f"이벤트 대상월({ref_p})과 BLS 관측기간({src_p}) 불일치 오류")

            # revised prior가 비연속월이면 오류
            if ev.get("is_revised_prior"):
                rev_p = ev.get("revised_prior_period")
                if ref_p and rev_p:
                    try:
                        y_t, m_t = int(ref_p.split("-")[0]), int(ref_p.split("-M")[1])
                        y_r, m_r = int(rev_p.split("-")[0]), int(rev_p.split("-M")[1])
                        expected_y, expected_m = (y_t - 1, 12) if m_t == 1 else (y_t, m_t - 1)
                        if (y_r, m_r) != (expected_y, expected_m):
                            errors.append(f"revised prior 비연속월 오류: 대상월 {ref_p}의 직전 연속월은 {expected_y}-M{expected_m:02d}이나 {rev_p}로 지정됨")
                    except Exception:
                        pass

        return errors

    @classmethod
    def _validate_unverified_actual_analysis(cls, generated_content: Dict[str, Any], raw_context: Dict[str, Any]) -> List[str]:
        """
        [핵심 거버넌스 규칙] Actual 미확인 이벤트 결과 분석 차단 검증:
        actual_status == 'NOT_FOUND' 또는 actual in [None, '-', '', 'null'] 인 과거 발표 이벤트(day_review)에 대해,
        본문에서 '상승', '하락', '상회', '하회', '악화', '개선', '호조', '부진' 등 결과나 방향성을 단정하여 분석하는 작문을 엄격히 차단한다.
        """
        errors = []
        cal = raw_context.get("economic_calendar", {})
        day_review = cal.get("day_review", [])
        if not day_review:
            day_review = raw_context.get("economic_events", {}).get("day_review_events", [])

        unverified_indicators = []
        for ev in day_review:
            act_val = ev.get("actual")
            has_act = (act_val is not None and str(act_val).strip() not in ["", "-", "None", "null", "N/A"])
            if not has_act:
                ev_name = ev.get("event_name", "")
                ev_kor = ev.get("event_name_kor", "")
                combined = (ev_name + " " + ev_kor).lower()

                STOPWORDS = {
                    "미국", "한국", "일본", "중국", "유럽", "영국", "독일", "유로존", "글로벌",
                    "주간", "월간", "연간", "지수", "지표", "발표", "동향", "속보", "잠정", "확정", "수정",
                    "전월", "전년", "대비", "보고서", "변동", "추이", "현황", "기준", "조사", "집계",
                    "분기", "전기", "전월비", "전년비", "원유", "국채", "채권"
                }

                keywords = []
                if "ppi" in combined or "생산자물가" in combined:
                    keywords.extend(["ppi", "생산자물가", "생산자물가지수", "도매물가"])
                    label = "생산자물가지수(PPI)"
                elif "cpi" in combined or "소비자물가" in combined:
                    keywords.extend(["cpi", "소비자물가", "소비자물가지수"])
                    label = "소비자물가지수(CPI)"
                elif "unemployment claims" in combined or "실업수당" in combined:
                    keywords.extend(["실업수당", "청구건수", "신규 실업수당", "신규실업수당", "jobless claims"])
                    label = "실업수당 청구건수"
                elif "non-farm" in combined or "비농업" in combined:
                    keywords.extend(["비농업 고용", "비농업고용", "nfp"])
                    label = "비농업 고용"
                elif "gdp" in combined:
                    keywords.extend(["gdp", "국내총생산"])
                    label = "GDP"
                elif "crude" in combined or "원유재고" in combined or "oil inventories" in combined:
                    keywords.extend(["원유재고", "원유 재고", "주간 원유재고", "eia 원유재고", "crude oil inventories"])
                    label = "주간 원유재고"
                elif "auction" in combined or "입찰" in combined:
                    keywords.extend(["국채 입찰", "국채입찰", "채권 입찰", "bond auction"])
                    label = "국채 입찰"
                else:
                    clean_tokens = [tok for tok in re.split(r'[\s\(\)/]+', ev_kor) if len(tok) >= 2 and tok.lower() not in STOPWORDS]
                    keywords.extend(clean_tokens)
                    label = ev_kor or ev_name

                if keywords:
                    unverified_indicators.append({
                        "label": label,
                        "keywords": list(set(keywords)),
                        "event": ev
                    })

        if not unverified_indicators:
            return errors

        # 전체 생성 텍스트 문장 수집
        all_sections_text = []
        daily_summary = generated_content.get("ficc_daily_summary", {})
        if isinstance(daily_summary, dict) and "bullets" in daily_summary:
            all_sections_text.extend(daily_summary["bullets"])
        if isinstance(generated_content.get("ficc_summary"), dict):
            all_sections_text.append(generated_content["ficc_summary"].get("text", ""))
        issue_rev = generated_content.get("issue_review", {})
        if isinstance(issue_rev, dict):
            for sub in ["stock", "fx", "bond", "commodity"]:
                if isinstance(issue_rev.get(sub), dict):
                    all_sections_text.append(issue_rev[sub].get("text", ""))
        if isinstance(generated_content.get("ficc_forecast"), dict):
            all_sections_text.append(generated_content["ficc_forecast"].get("text", ""))
        if isinstance(generated_content.get("daily_event_watchpoints"), dict):
            all_sections_text.append(generated_content["daily_event_watchpoints"].get("text", ""))

        all_sentences = []
        for sec_t in all_sections_text:
            if sec_t:
                sents = re.split(r'(?<=[가-힣a-zA-Z\)])\.\s+|\n+', sec_t)
                all_sentences.extend([s.strip() for s in sents if s.strip()])

        # 결과 단정 분석 단어
        RESULT_ASSERT_WORDS = [
            "상승", "하락", "올랐", "내렸", "반등", "둔화", "상회", "하회",
            "높았", "낮았", "웃돌", "밑돌", "악화", "개선", "호조", "부진",
            "급등", "급락", "견조", "늘었", "줄었", "증가", "감소", "오름세", "내림세"
        ]
        # 허용된 상태/미확인 서술 표현
        ABSENCE_MARKERS = [
            "미확인", "확인 필요", "확인이 필요", "확인되지 않", "집계되지 않",
            "발표되지 않", "발표 시각이 지났으나", "발표 시각이 경과했으나", "수치 확인이",
            "결과 확인", "확인 전"
        ]

        for u_ind in unverified_indicators:
            lbl = u_ind["label"]
            kws = u_ind["keywords"]
            for sent in all_sentences:
                sent_lower = sent.lower()
                if any(kw.lower() in sent_lower for kw in kws):
                    # 미래 일정(익일 발표될 CPI, 향후 전망 등)은 과거 지표 분석 위반에서 제외
                    if any(w in sent for w in ["익일", "다음 거래일", "예정된", "발표될", "앞두고", "예상치", "전망"]):
                        if not any(w in sent for w in ["발표된", "확인된", "나타난", "발표 이후", "반등하고", "상승하고"]):
                            continue

                    # 허용된 상태 표현이 포함되어 있는지 확인
                    if any(ab in sent for ab in ABSENCE_MARKERS):
                        continue

                    # 결과 단정 단어가 포함되어 있다면 오류
                    for raw in RESULT_ASSERT_WORDS:
                        if raw in sent:
                            errors.append(
                                f"[FactValidator] Actual 미확인 이벤트 결과 분석 금지 위반: '{lbl}'의 실제치가 확인되지 않은 상태(Actual='-')에서 본문에서 결과 단정('{raw}') 분석이 사용되었습니다: '{sent}'"
                            )
                            break
        return errors
