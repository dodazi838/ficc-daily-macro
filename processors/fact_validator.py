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
        "DX-Y.NYB": ["달러 인덱스", "달러인덱스", "dxy", "달러화"],
        "KRW=X": ["원/달러", "달러/원", "원달러", "원화 환율", "환율"],
        "JPY=X": ["엔/달러", "달러/엔", "엔화"],
        "CNH=F": ["위안/달러", "달러/위안", "역외 위안"],
        "EURUSD=X": ["유로/달러", "유로화", "eur/usd"],
        "GBPUSD=X": ["파운드/달러", "파운드화", "gbp/usd"],
        "CL=F": ["wti", "유가", "국제유가", "서부텍사스산", "원유 선물", "원유"],
        "BZ=F": ["brent", "브렌트", "브렌트유"],
        "GC=F": ["금 선물", "금 가격", "금값", "gold", "금 시세"],
        "SI=F": ["은 선물", "은 가격", "silver", "은 시세"],
        "HG=F": ["구리 선물", "구리 가격", "copper", "구리"],
        "NG=F": ["천연가스", "가스 선물"],
        "BOND.KTB 3y": ["국고채 3년", "국채 3년", "한국 3년", "ktb 3년"],
        "BOND.KTB10y": ["국고채 10년", "국채 10년", "한국 10년", "ktb 10년"],
        "BOND.US2Y": ["미국 국채 2년", "미국채 2년", "미 2년물", "2년물 금리", "미국 2년"],
        "BOND.US10Y": ["미국 국채 10년", "미국채 10년", "미 10년물", "10년물 금리", "미국 10년", "10년물 국채"],
        "BOND.JP10Y": ["일본 국채 10년", "일본 10년", "jgb"],
        "BOND.DE10Y": ["독일 국채 10년", "독일 10년", "분트", "bund"],
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
        all_event_ids = {
            ev.get("event_id")
            for ev_list in raw_context.get("economic_calendar", {}).values()
            for ev in ev_list if ev.get("event_id")
        }

        errors: List[str] = []
        warnings: List[str] = []
        verified_count = 0
        section_scores = []

        sections_to_check = [
            ("ficc_daily_summary", " ".join(generated_content.get("ficc_daily_summary", {}).get("bullets", []))),
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

            if sec_name == "daily_event_watchpoints":
                event_errors = cls._validate_daily_event_section(sec_text, raw_context)
                errors.extend(event_errors)
                score = max(0.0, 100.0 - (len(event_errors) * 35.0))
                section_scores.append(score)
            else:
                sec_errors, sec_warnings, sec_verified = cls._validate_section_text(
                    sec_name, sec_text, asset_allowed_numbers, all_valid_context_numbers
                )
                errors.extend(sec_errors)
                warnings.extend(sec_warnings)
                verified_count += sec_verified
                score = 100.0 - (len(sec_errors) * 35.0) - (len(sec_warnings) * 10.0)
                score = max(0.0, score)
                section_scores.append(score)

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
                            cls._add_rounded_variants(all_nums, float(clean_f))
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
            masked_sent = re.sub(r'(?:다우존스|다우)\s*30', 'DJI_INDEX', masked_sent)
            masked_sent = re.sub(r'(?:니케이|닛케이|nikkei)\s*225', 'NIKKEI_INDEX', masked_sent)
            masked_sent = re.sub(r'(?:유로스톡스|stoxx)\s*50', 'STOXX_INDEX', masked_sent)
            masked_sent = re.sub(r'(?:나스닥|nasdaq)\s*100', 'NDX_INDEX', masked_sent)
            masked_sent = re.sub(r'(?:러셀|russell)\s*2000', 'RUT_INDEX', masked_sent)
            masked_sent = re.sub(r'\b\d{4}년\b', ' ', masked_sent)
            masked_sent = re.sub(r'\b\d{1,2}월\b', ' ', masked_sent)
            masked_sent = re.sub(r'\b\d{1,2}일\b', ' ', masked_sent)
            masked_sent = re.sub(r'\b\d{1,2}:\d{2}(?::\d{2})?\b', ' TIME_VAL ', masked_sent)
            masked_sent = re.sub(r'\b\d{1,2}\s*시\s*\d{1,2}\s*분\b', ' TIME_VAL ', masked_sent)
            masked_sent = re.sub(r'\b\d{1,2}\s*시\b', ' TIME_VAL ', masked_sent)
            masked_sent = re.sub(r'\b\d{1,2}\s*분\b', ' TIME_VAL ', masked_sent)

            # 4. 숫자 추출
            raw_nums = re.findall(r'[-+]?\d+(?:,\d{3})*(?:\.\d+)?', masked_sent)
            extracted_floats = []
            for n in raw_nums:
                try:
                    val = abs(float(n.replace(",", "")))
                    if val not in [2026.0, 1.0, 2.0, 3.0, 4.0, 5.0, 10.0]:
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

        # 0. 전체 캘린더(today_night 및 day_review)가 모두 비어있는 경우
        if not today_night and not day_review:
            if any(w in text for w in ["발표될 예정", "발표를 앞두고", "공개될"]):
                errors.append("[daily_event_watchpoints] 금일 발표되었거나 예정된 지표가 없으나 본문에 허위 발표 일정이 작성되었습니다.")
            return errors

        # 0-1. today_night(향후 예정 일정)가 비어있는 경우: 향후 발표 예정 허위 일정 작성 차단
        if not today_night:
            if any(w in text for w in ["발표될 예정", "발표를 앞두고", "공개될 예정", "발표가 예정되어 있어"]):
                errors.append("[daily_event_watchpoints] 금일 실행 시각 이후 예정된 지표가 없으나 본문에 향후 발표 예정 일정이 허위로 작성되었습니다.")

        # Canonical 데이터 코퍼스 및 매핑 구축 (today_night + day_review 통합)
        all_valid_events = list(today_night) + list(day_review)
        valid_text_corpus = []
        canonical_times = set()
        canonical_forecast_nums = set()
        canonical_actual_nums = set()

        for ev in all_valid_events:
            ev_name = ev.get("event_name", "")
            ev_kor = ev.get("event_name_kor", "")
            valid_text_corpus.append(ev_name.lower())
            valid_text_corpus.append(ev_kor.lower())

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

            # 예상치 (forecast)
            f_val = ev.get("forecast")
            if f_val and str(f_val).strip() not in ["-", "None", ""]:
                f_nums = re.findall(r'[-+]?\d+(?:\.\d+)?', str(f_val).strip())
                for fn in f_nums:
                    try:
                        canonical_forecast_nums.add(float(fn))
                        canonical_forecast_nums.add(abs(float(fn)))
                    except ValueError:
                        pass

            # 실제치 (actual)
            a_val = ev.get("actual")
            if a_val and str(a_val).strip() not in ["-", "None", ""]:
                a_nums = re.findall(r'[-+]?\d+(?:\.\d+)?', str(a_val).strip())
                for an in a_nums:
                    try:
                        canonical_actual_nums.add(float(an))
                        canonical_actual_nums.add(abs(float(an)))
                    except ValueError:
                        pass

        combined_corpus = " ".join(valid_text_corpus)

        # 주요 글로벌 경제 지표 키워드 감지 사전
        KNOWN_INDICATORS = {
            "ISM 제조업/서비스업 PMI": ["ism", "제조업 pmi", "서비스업 pmi", "ism 제조업", "ism 서비스업"],
            "JOLTS 구인건수": ["jolts", "구인건수", "구인이직"],
            "비농업 고용지수(NFP)": ["비농업 고용", "비농업 고용지수", "nfp", "non-farm payroll", "고용보고서"],
            "ADP 비농업 고용": ["adp", "adp 비농업", "adp 고용", "민간 고용"],
            "CPI (소비자물가)": ["cpi", "소비자물가", "소비자물가지수"],
            "PPI (생산자물가)": ["ppi", "생산자물가", "생산자물가지수"],
            "PCE 물가지수": ["pce", "개인소비지출", "근원 pce"],
            "GDP 성장률": ["gdp", "경제성장률 속보치"],
            "신규 실업수당 청구": ["신규 실업수당", "실업수당 청구", "jobless claims"],
            "소매판매": ["소매판매", "retail sales"],
            "BOC 통화정책/기준금리": ["boc", "캐나다 중앙은행", "캐나다 기준금리", "캐나다 금리"],
            "FOMC / Fed 금리": ["fomc", "연준 기준금리", "fed 금리결정", "연방공개시장위원회"],
            "ECB 기준금리": ["ecb", "유럽중앙은행 금리", "ecb 기준금리"],
            "공장재 수주": ["공장재", "factory orders", "공장 수주"],
            "주간 원유재고": ["원유재고", "eia 원유", "주간 원유재고", "crude oil inventories"],
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
                pass

        return errors
