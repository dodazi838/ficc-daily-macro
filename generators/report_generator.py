"""
[FICC Daily Macro] AI 시황 리포트 및 블로그 원고 생성 총괄 관리자 (report_generator.py)
====================================================================
- data/generated/YYYY-MM-DD/
    • gemini_draft.json     (최초 Gemini 생성 결과 및 메타데이터)
    • corrected_draft.json  (검증 실패 시 자동 수정된 2차 생성 결과)
    • validation.json       (1~2차 FactValidator 검증 이력 및 최종 판정)
    • history/              (동일 날짜 재실행 시 이전 생성/검증 파일 아카이빙)
- data/output/YYYY-MM-DD/
    • blog_post.html        (검증 통과 시 네이버 블로그 복사용 Rich HTML)
    • blog_post.txt         (검증 통과 시 블로그 검수용 순수 텍스트 원고)
====================================================================
"""

import os
import sys
import json
import shutil
import re
import datetime
from typing import Dict, Any, Optional, List, Set
from dotenv import load_dotenv

load_dotenv()

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from generators.context_builder import AIContextBuilder
from generators.prompt_manager import PromptManager
from generators.llm_adapter import get_llm_adapter, BaseLLMAdapter
from generators.blog_formatter import NaverBlogFormatter
from processors.fact_validator import FactValidator

class FiccReportGenerator:
    """FICC Daily Macro AI 리포트 및 블로그 원고 생성 총괄 관리자"""

    def __init__(self, llm_adapter: Optional[BaseLLMAdapter] = None):
        self.llm_adapter = llm_adapter or get_llm_adapter()

    def _archive_previous_runs(self, gen_dir: str):
        """동일 날짜 재실행 시 기존 생성/검증 파일을 history 디렉토리에 보존"""
        existing_files = [f for f in ["gemini_draft.json", "corrected_draft.json", "validation.json"] if os.path.exists(os.path.join(gen_dir, f))]
        if existing_files:
            try:
                # 첫 번째 파일의 수정 시각을 기준으로 타임스탬프 폴더 생성
                first_file = os.path.join(gen_dir, existing_files[0])
                mtime = os.path.getmtime(first_file)
                mtime_str = datetime.datetime.fromtimestamp(mtime).strftime("%H%M%S")
                history_dir = os.path.join(gen_dir, "history", f"run_{mtime_str}")
                os.makedirs(history_dir, exist_ok=True)
                for f_name in existing_files:
                    src = os.path.join(gen_dir, f_name)
                    dst = os.path.join(history_dir, f_name)
                    shutil.move(src, dst)
            except Exception:
                pass

    @classmethod
    def _identify_failed_sections(cls, errors: List[str], raw_content: Dict[str, Any]) -> Set[str]:
        """FactValidator 에러 목록을 분석하여 재작성이 필요한 섹션 식별"""
        failed: Set[str] = set()
        for err in errors:
            err_lower = err.lower()
            if "[ficc_daily_summary]" in err_lower:
                failed.add("ficc_daily_summary")
            elif "[ficc_summary]" in err_lower:
                failed.add("ficc_summary")
            elif any(f"[issue_review_{k}]" in err_lower for k in ["stock", "fx", "bond", "commodity"]) or "[issue_review]" in err_lower:
                failed.add("issue_review")
            elif "[ficc_forecast]" in err_lower:
                failed.add("ficc_forecast")
            elif "[daily_event_watchpoints]" in err_lower:
                failed.add("daily_event_watchpoints")
            else:
                matched = False
                quotes = re.findall(r"'([^']+)'", err)
                for q in quotes:
                    if len(q) < 5:
                        continue
                    if "ficc_daily_summary" in raw_content:
                        bullets_text = " ".join(raw_content.get("ficc_daily_summary", {}).get("bullets", []))
                        if q in bullets_text:
                            failed.add("ficc_daily_summary")
                            matched = True
                    if "ficc_summary" in raw_content:
                        if q in raw_content.get("ficc_summary", {}).get("text", ""):
                            failed.add("ficc_summary")
                            matched = True
                    if "issue_review" in raw_content:
                        for sub in ["stock", "fx", "bond", "commodity"]:
                            if q in raw_content.get("issue_review", {}).get(sub, {}).get("text", ""):
                                failed.add("issue_review")
                                matched = True
                    if "ficc_forecast" in raw_content:
                        if q in raw_content.get("ficc_forecast", {}).get("text", ""):
                            failed.add("ficc_forecast")
                            matched = True
                    if "daily_event_watchpoints" in raw_content:
                        if q in raw_content.get("daily_event_watchpoints", {}).get("text", ""):
                            failed.add("daily_event_watchpoints")
                            matched = True
                
                if not matched:
                    if "daily_event" in err_lower or "캘린더" in err_lower or "today_night" in err_lower or "day_review" in err_lower:
                        failed.add("daily_event_watchpoints")
                    elif "forecast" in err_lower or "전망" in err_lower or "catalyst" in err_lower:
                        failed.add("ficc_forecast")
                    elif "summary" in err_lower:
                        failed.add("ficc_summary")
                    elif any(k in err_lower for k in ["증시", "주식", "환율", "외환", "국채", "채권", "원자재", "유가", "금리"]):
                        failed.add("issue_review")

        if not failed:
            return {"ficc_daily_summary", "ficc_summary", "issue_review", "ficc_forecast", "daily_event_watchpoints"}
        return failed

    def generate_report_from_file(self, 
                                 processed_json_path: str, 
                                 base_data_dir: str = "data", 
                                 is_post_1630: bool = False) -> Dict[str, Any]:
        """
        가공 데이터 파일(data/processed/YYYY-MM-DD.json)을 읽어
        1) AI Structured Report 생성 (Gemini 3.7 Flash) -> gemini_draft.json
        2) Fact Validator 엄격 검증 -> validation.json
        3) 실패 시 오류 피드백을 반영한 자동 1회 재시도 (Self-Correction) -> corrected_draft.json
        4) 검증 통과(PASS) 시에만 data/output/YYYY-MM-DD/blog_post.html / blog_post.txt 생성
        5) 검증 최종 실패 시 output 파일 생성을 원천 차단
        """
        if not os.path.exists(processed_json_path):
            raise FileNotFoundError(f"가공 데이터 파일을 찾을 수 없습니다: {processed_json_path}")

        with open(processed_json_path, "r", encoding="utf-8") as f:
            processed_data = json.load(f)

        report_date = processed_data.get("report_date", datetime.datetime.now().strftime("%Y-%m-%d"))
        run_timestamp = datetime.datetime.now().strftime("%H%M%S")
        run_id = f"RUN_{report_date}_{run_timestamp}"

        # 디렉토리 설정
        gen_date_dir = os.path.join(base_data_dir, "generated", report_date)
        out_date_dir = os.path.join(base_data_dir, "output", report_date)
        os.makedirs(gen_date_dir, exist_ok=True)
        os.makedirs(out_date_dir, exist_ok=True)

        # 동일 날짜 기존 파일이 있다면 안전하게 history 폴더로 아카이빙
        self._archive_previous_runs(gen_date_dir)

        # 1. AI 컨텍스트 빌드 (SSOT)
        context = AIContextBuilder.build_context(processed_data)
        system_prompt = PromptManager.get_system_prompt()
        schema = PromptManager.get_response_schema()

        validation_history: List[Dict[str, Any]] = []
        gemini_draft_path = os.path.join(gen_date_dir, "gemini_draft.json")
        corrected_draft_path = os.path.join(gen_date_dir, "corrected_draft.json")
        validation_json_path = os.path.join(gen_date_dir, "validation.json")
        blog_html_path = os.path.join(out_date_dir, "blog_post.html")
        blog_text_path = os.path.join(out_date_dir, "blog_post.txt")

        # ==========================================
        # [시도 1] Gemini 1차 생성 (Draft 1)
        # ==========================================
        attempts = 1
        print(f" • [AI 생성 시도 1/2] Gemini 3.7 Flash 호출 중...")
        user_prompt_1 = PromptManager.build_user_prompt(context)
        llm_result_1 = self.llm_adapter.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt_1,
            response_schema=schema
        )

        raw_content_1 = llm_result_1.get("parsed_content", {})
        usage_meta_1 = llm_result_1.get("usage", {})

        # FactValidator 1차 검증
        enriched_content_1, val_summary_1 = FactValidator.validate_and_enrich(raw_content_1, context)
        validation_history.append({
            "attempt": 1,
            "validated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S KST"),
            "is_passed": val_summary_1.get("passed", False),
            "errors": val_summary_1.get("errors", []),
            "warnings": val_summary_1.get("warnings", []),
            "overall_confidence": val_summary_1.get("overall_confidence", "LOW"),
            "average_confidence_score": val_summary_1.get("average_confidence_score", 0.0),
            "verified_numbers_count": val_summary_1.get("fact_check_details", {}).get("verified_numbers_count", 0)
        })

        # 1차 초안 저장 (data/generated/YYYY-MM-DD/gemini_draft.json)
        gemini_draft_payload = {
            "report_date": report_date,
            "run_id": run_id,
            "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S KST"),
            "attempt": 1,
            "model": usage_meta_1.get("model", "gemini-3.7-flash"),
            "prompt_version": "v1.2-structured-ficc",
            "token_usage": usage_meta_1,
            "estimated_cost_usd": usage_meta_1.get("estimated_cost_usd", 0.0),
            "source_processed_file": processed_json_path,
            "validation_status": "PASS" if val_summary_1.get("passed") else "FAIL",
            "validation_errors_count": len(val_summary_1.get("errors", [])),
            "validation_errors": val_summary_1.get("errors", []),
            "content": raw_content_1
        }
        with open(gemini_draft_path, "w", encoding="utf-8") as f:
            json.dump(gemini_draft_payload, f, ensure_ascii=False, indent=2)

        final_content = enriched_content_1
        last_val_summary = val_summary_1
        last_usage_meta = usage_meta_1

        # ==========================================
        # [시도 2] 검증 실패 시 자동 보정 (Self-Correction)
        # ==========================================
        if val_summary_1.get("passed", False):
            print(f" • [AI 생성 시도 1/2] FactValidator 검증 통과 (PASS)!")
        else:
            errors_1 = val_summary_1.get("errors", [])
            print(f" • [AI 생성 시도 1/2] FactValidator 검증 실패 ({len(errors_1)}건 에러 발견)")
            for err in errors_1[:3]:
                print(f"   - {err}")

            attempts = 2
            failed_sections = self._identify_failed_sections(errors_1, raw_content_1)
            is_partial = len(failed_sections) < 5
            failed_names = ", ".join(sorted(failed_sections))
            print(f" • [AI 생성 시도 2/2] 오류 피드백 기반 {'부분 재작성(Targeted: ' + failed_names + ')' if is_partial else '전체 재작성'} Gemini 호출 중...")
            error_feedback_text = "\n".join([f"- {e}" for e in errors_1])

            if is_partial:
                partial_props = {k: schema["properties"][k] for k in failed_sections if k in schema.get("properties", {})}
                active_schema = {
                    "type": "OBJECT",
                    "properties": partial_props,
                    "required": list(partial_props.keys())
                }
                user_prompt_2 = f"""[긴급 팩트 검증 오류 수정 요청 - 부분 재작성]
이전에 작성된 리포트 중 다음 섹션에서만 사실/수치 불일치 오류가 적발되었습니다:
수정 대상 섹션: [{failed_names}]

적발된 오류 내역:
{error_feedback_text}

[절대 수정 지침]
1. 오류가 적발된 섹션({failed_names})만 수정하여 JSON으로 반환하라. (나머지 정상 섹션은 응답에서 제외할 것).
2. 위에서 적발된 허위/미제공 수치(예: SSOT에 없는 임의의 지표 발표 수치, 25bp/50bp 등 임의의 금리 변동폭, 이동평균선, 임의의 % 등)를 본문에서 즉시 완전히 삭제하거나, 반드시 아래 [Context JSON]에 제공된 정확한 수치로만 대체하라.
3. [단순 숫자 나열 및 Forecast 수치 반복 전면 금지]: 지수·환율·금리·원자재의 단순 등락률 나열을 일체 배제하고, Forecast 수치 자체를 본문에서 반복 인용하지 마라.
4. [상투적 클리셰 및 미근거 인과관계 전면 금지]:
   - '불확실성이 상존', '불확실성이 지속', '불확실성 확대', '가격 재산정 과정', '흐름이 지속될 전망' 등 상투적 클리셰를 절대 쓰지 마라!
   - '에 연동되어', '과 연동되어', '시장에서는 ~로 평가했다', '~때문에', '~에 따른 결과' 등 미근거 인과관계를 절대 쓰지 마라! 동시 발생 사건은 'A가 상승한 가운데 B도 하락했다'처럼 병렬 서술하라.
5. 특히 경제지표의 실제치(actual)가 null인 경우, 절대 가상의 발표 수치를 지어내지 마라.
6. daily_event_watchpoints는 [Context JSON]의 economic_calendar(day_review, today_night, next_trading_day)에 실제로 존재하는 지표만을 다루어라.
7. 반드시 존댓말 없이 연구노트형 평서체(~함, ~임, ~나타남, ~확인됨, ~작용함)를 일관되게 유지하라.
8. 과거 발표 시각이 경과한 지표(day_review 등)에 대해 '발표 예정', '발표 대기', '대기 흐름'을 절대 쓰지 마라! 실제 수치 미확인 시 '공식 수치 미확인' 또는 '실제치 확인 필요'로만 서술하라.
9. 지정된 JSON 포맷({failed_names})을 완벽히 준수하여 다시 작성하라.

[Context JSON]
{json.dumps(context, ensure_ascii=False, indent=2)}
"""
            else:
                active_schema = schema
                user_prompt_2 = f"""[긴급 팩트 검증 오류 수정 요청]
이전에 작성된 리포트에서 다음과 같은 치명적인 사실/수치 불일치 오류가 적발되었습니다:
{error_feedback_text}

[절대 수정 지침]
1. 위에서 적발된 허위/미제공 수치(예: SSOT에 없는 임의의 지표 발표 수치, 25bp/50bp 등 임의의 금리 변동폭, 이동평균선, 임의의 % 등)를 본문에서 즉시 완전히 삭제하거나, 반드시 아래 [Context JSON]에 제공된 정확한 수치로만 대체하라.
2. [단순 숫자 나열 및 Forecast 수치 반복 전면 금지]: 지수·환율·금리·원자재의 단순 등락률 나열을 일체 배제하고, Forecast 수치 자체를 본문에서 반복 인용하지 마라.
3. [상투적 클리셰 및 미근거 인과관계 전면 금지]:
   - '불확실성이 상존', '불확실성이 지속', '불확실성 확대', '가격 재산정 과정', '흐름이 지속될 전망' 등 상투적 클리셰를 절대 쓰지 마라!
   - '에 연동되어', '과 연동되어', '시장에서는 ~로 평가했다', '~때문에', '~에 따른 결과' 등 미근거 인과관계를 절대 쓰지 마라! 동시 발생 사건은 'A가 상승한 가운데 B도 하락했다'처럼 병렬 서술하라.
4. 특히 경제지표의 실제치(actual)가 null인 경우, 절대 가상의 발표 수치를 지어내지 마라.
5. daily_event_watchpoints는 [Context JSON]의 economic_calendar(day_review, today_night, next_trading_day)에 실제로 존재하는 지표만을 다루어라.
6. 반드시 존댓말 없이 연구노트형 평서체(~함, ~임, ~나타남, ~확인됨, ~작용함)를 일관되게 유지하라.
7. 과거 발표 시각이 경과한 지표(day_review 등)에 대해 '발표 예정', '발표 대기', '대기 흐름'을 절대 쓰지 마라! 실제 수치 미확인 시 '공식 수치 미확인' 또는 '실제치 확인 필요'로만 서술하라.
8. 지정된 JSON 포맷을 완벽히 준수하여 다시 작성하라.

[Context JSON]
{json.dumps(context, ensure_ascii=False, indent=2)}
"""

            llm_result_2 = self.llm_adapter.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt_2,
                response_schema=active_schema
            )

            raw_content_2 = llm_result_2.get("parsed_content", {})
            usage_meta_2 = llm_result_2.get("usage", {})

            # 부분 재작성 시 기존 통과 섹션과 결합하여 완전한 report JSON 구성
            import copy
            if is_partial:
                eval_content_2 = copy.deepcopy(raw_content_1)
                for k in failed_sections:
                    if k in raw_content_2:
                        if k == "issue_review" and isinstance(eval_content_2.get(k), dict) and isinstance(raw_content_2.get(k), dict):
                            merged_issue = dict(eval_content_2[k])
                            has_specific_sub_error = any(f"issue_review_{sub_k}" in e.lower() for e in errors_1 for sub_k in ["stock", "fx", "bond", "commodity"])
                            for sub_k, sub_val in raw_content_2[k].items():
                                if not has_specific_sub_error or any(f"issue_review_{sub_k}" in e.lower() for e in errors_1):
                                    merged_issue[sub_k] = sub_val
                            eval_content_2[k] = merged_issue
                        else:
                            eval_content_2[k] = raw_content_2[k]
            else:
                eval_content_2 = raw_content_2

            # FactValidator 2차 재검증
            enriched_content_2, val_summary_2 = FactValidator.validate_and_enrich(eval_content_2, context)
            validation_history.append({
                "attempt": 2,
                "validated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S KST"),
                "is_passed": val_summary_2.get("passed", False),
                "errors": val_summary_2.get("errors", []),
                "warnings": val_summary_2.get("warnings", []),
                "overall_confidence": val_summary_2.get("overall_confidence", "LOW"),
                "average_confidence_score": val_summary_2.get("average_confidence_score", 0.0),
                "verified_numbers_count": val_summary_2.get("fact_check_details", {}).get("verified_numbers_count", 0)
            })

            # 2차 수정본 저장 (data/generated/YYYY-MM-DD/corrected_draft.json)
            corrected_draft_payload = {
                "report_date": report_date,
                "run_id": run_id,
                "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S KST"),
                "attempt": 2,
                "model": usage_meta_2.get("model", "gemini-3.7-flash"),
                "prompt_version": "v1.2-structured-ficc-correction",
                "token_usage": usage_meta_2,
                "estimated_cost_usd": usage_meta_2.get("estimated_cost_usd", 0.0),
                "source_processed_file": processed_json_path,
                "feedback_errors_received": errors_1,
                "validation_status": "PASS" if val_summary_2.get("passed") else "FAIL",
                "validation_errors_count": len(val_summary_2.get("errors", [])),
                "validation_errors": val_summary_2.get("errors", []),
                "targeted_sections": list(failed_sections) if is_partial else "ALL",
                "content": eval_content_2
            }
            with open(corrected_draft_path, "w", encoding="utf-8") as f:
                json.dump(corrected_draft_payload, f, ensure_ascii=False, indent=2)

            final_content = enriched_content_2
            last_val_summary = val_summary_2
            last_usage_meta = usage_meta_2

            if val_summary_2.get("passed", False):
                print(f" • [AI 생성 시도 2/2] FactValidator 검증 통과 (PASS)!")
            else:
                errors_2 = val_summary_2.get("errors", [])
                print(f" • [AI 생성 시도 2/2] FactValidator 최종 검증 실패 ({len(errors_2)}건 에러)")
                for err in errors_2[:3]:
                    print(f"   - {err}")

        # ==========================================
        # [검증 결과 통합 저장] data/generated/YYYY-MM-DD/validation.json
        # ==========================================
        is_finally_passed = last_val_summary.get("passed", False)
        validation_payload = {
            "report_date": report_date,
            "run_id": run_id,
            "validated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S KST"),
            "final_passed": is_finally_passed,
            "total_attempts": attempts,
            "self_correction_executed": (attempts > 1),
            "source_processed_file": processed_json_path,
            "history": validation_history,
            "validation_summary": last_val_summary,
            "final_summary": last_val_summary,
            "content": final_content,
            "validated_content": final_content if is_finally_passed else None
        }
        with open(validation_json_path, "w", encoding="utf-8") as f:
            json.dump(validation_payload, f, ensure_ascii=False, indent=2)

        # ==========================================
        # [최종 Blog Output 렌더링] data/output/YYYY-MM-DD/
        # ==========================================
        if is_finally_passed:
            # FactValidator 최종 PASS인 경우에만 생성
            blog_html = NaverBlogFormatter.format_blog_html(
                report_data=validation_payload,
                processed_market_data=processed_data,
                is_post_1630=is_post_1630
            )
            with open(blog_html_path, "w", encoding="utf-8") as f:
                f.write(blog_html)

            blog_text = NaverBlogFormatter.format_blog_text(
                report_data=validation_payload,
                processed_market_data=processed_data,
                is_post_1630=is_post_1630
            )
            with open(blog_text_path, "w", encoding="utf-8") as f:
                f.write(blog_text)

            # 최신 canonical output 동기화 (report_date가 최신일 때만 preview 갱신)
            try:
                sync_latest_output(base_data_dir=base_data_dir, target_report_date=report_date)
            except Exception as e:
                print(f" [Warning] 최신 프리뷰 동기화 건너뜀: {e}")

            return {
                "success": True,
                "report_date": report_date,
                "run_id": run_id,
                "attempts": attempts,
                "gemini_draft_path": gemini_draft_path,
                "corrected_draft_path": corrected_draft_path if (attempts > 1) else None,
                "validation_json_path": validation_json_path,
                "blog_html_path": blog_html_path,
                "blog_text_path": blog_text_path,
                "validated_data": validation_payload,
                "blog_html": blog_html,
                "blog_text": blog_text,
                "usage": last_usage_meta,
                "validation_summary": last_val_summary
            }
        else:
            # FactValidator 최종 FAIL 시에는 output 파일 생성 차단 및 기존 파일 삭제
            if os.path.exists(blog_html_path):
                os.remove(blog_html_path)
            if os.path.exists(blog_text_path):
                os.remove(blog_text_path)

            return {
                "success": False,
                "report_date": report_date,
                "run_id": run_id,
                "attempts": attempts,
                "gemini_draft_path": gemini_draft_path,
                "corrected_draft_path": corrected_draft_path if (attempts > 1) else None,
                "validation_json_path": validation_json_path,
                "blog_html_path": None,
                "blog_text_path": None,
                "usage": last_usage_meta,
                "validation_summary": last_val_summary
            }


def get_latest_canonical_date(base_data_dir: str = "data") -> Optional[str]:
    """
    data/output 디렉토리 및 processed, validation을 스캔하여
    모든 필수 파일이 온전히 존재하는 가장 최신의 유효한 canonical report_date를 반환합니다.
    """
    out_root = os.path.join(base_data_dir, "output")
    if not os.path.exists(out_root):
        return None

    valid_dates = []
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    for item in os.listdir(out_root):
        if not date_pattern.match(item):
            continue
        out_dir = os.path.join(out_root, item)
        if not os.path.isdir(out_dir):
            continue

        # 4대 필수 파일 존재 확인
        has_html = os.path.exists(os.path.join(out_dir, "blog_post.html"))
        has_txt = os.path.exists(os.path.join(out_dir, "blog_post.txt"))
        has_proc = os.path.exists(os.path.join(base_data_dir, "processed", f"{item}.json"))
        has_val = os.path.exists(os.path.join(base_data_dir, "generated", item, "validation.json"))

        if has_html and has_txt and has_proc and has_val:
            valid_dates.append(item)

    if not valid_dates:
        return None

    return max(valid_dates)


def sync_latest_output(base_data_dir: str = "data", target_report_date: Optional[str] = None) -> Dict[str, Any]:
    """
    최신(latest) canonical 산출물을 검증하고, 검증 조건을 통과했을 때만 preview 파일을 동기화합니다.

    조건:
    1. target_report_date가 지정된 경우, 해당 날짜가 저장소 내 최신(latest) 날짜 이상이어야 함.
       과거 날짜(target_report_date < latest_date)인 경우 preview 파일 수정을 엄격히 차단하고 거부.
    2. target_report_date 또는 자동 감지된 latest_date에 대해:
       - data/output/{date}/blog_post.html, blog_post.txt 존재 확인
       - data/processed/{date}.json 존재 확인 및 report_date 일치 확인
       - data/generated/{date}/validation.json 존재 확인 및 report_date 일치, final_passed 확인
       - 서로 다른 날짜의 processed/validation 조합 절대 불가
    3. 모든 검증을 통과한 경우에만:
       - data/generated/latest_preview.html
       - data/generated/latest_preview.txt
       - data/generated/blog_post.html (하위 호환)
       - data/generated/blog_post.txt (하위 호환)
       - data/generated/validated.json (하위 호환)
       - data/generated/latest_manifest.json
       을 최신 산출물로 원자적 갱신.
    """
    latest_date = get_latest_canonical_date(base_data_dir)

    if target_report_date:
        if latest_date and target_report_date < latest_date:
            msg = (
                f"[SyncRejected] 요청된 target_report_date('{target_report_date}')는 "
                f"현재 최신 canonical 날짜('{latest_date}')보다 과거 날짜입니다. "
                f"최신 preview를 과거 데이터로 덮어쓰는 것을 차단했습니다."
            )
            return {
                "success": False,
                "synced": False,
                "reason": msg,
                "canonical_latest_date": latest_date
            }
        date_to_sync = target_report_date
    else:
        date_to_sync = latest_date

    if not date_to_sync:
        return {
            "success": False,
            "synced": False,
            "reason": "동기화할 유효한 canonical report_date가 없습니다."
        }

    # 파일 존재 확인
    proc_file = os.path.join(base_data_dir, "processed", f"{date_to_sync}.json")
    val_file = os.path.join(base_data_dir, "generated", date_to_sync, "validation.json")
    out_html = os.path.join(base_data_dir, "output", date_to_sync, "blog_post.html")
    out_txt = os.path.join(base_data_dir, "output", date_to_sync, "blog_post.txt")

    for p in [proc_file, val_file, out_html, out_txt]:
        if not os.path.exists(p):
            return {
                "success": False,
                "synced": False,
                "reason": f"필수 파일이 존재하지 않습니다: {p}"
            }

    # 날짜 및 검증 상태 확인
    with open(proc_file, "r", encoding="utf-8") as f:
        proc_data = json.load(f)
    with open(val_file, "r", encoding="utf-8") as f:
        val_data = json.load(f)

    p_date = proc_data.get("report_date")
    v_date = val_data.get("report_date")

    if p_date != date_to_sync or v_date != date_to_sync:
        raise ValueError(f"[DateMismatchError] SSOT 날짜('{p_date}') 또는 Validation 날짜('{v_date}')가 대상 날짜('{date_to_sync}')와 일치하지 않습니다.")

    if p_date != v_date:
        raise ValueError(f"[DateMismatchError] processed 날짜('{p_date}')와 validation 날짜('{v_date}')가 서로 다릅니다.")

    val_sum = val_data.get("validation_summary") or val_data.get("final_summary", {})
    is_passed = val_sum.get("passed", False) or val_data.get("final_passed", False) or (val_data.get("validation_status") == "PASS")
    if not is_passed:
        return {
            "success": False,
            "synced": False,
            "reason": f"Validation이 PASS 상태가 아닙니다: {val_file}"
        }

    # 복사 실행
    with open(out_html, "r", encoding="utf-8") as f:
        html_content = f.read()
    with open(out_txt, "r", encoding="utf-8") as f:
        txt_content = f.read()

    gen_root = os.path.join(base_data_dir, "generated")
    os.makedirs(gen_root, exist_ok=True)

    # 1) 프리뷰 전용 파일
    with open(os.path.join(gen_root, "latest_preview.html"), "w", encoding="utf-8") as f:
        f.write(html_content)
    with open(os.path.join(gen_root, "latest_preview.txt"), "w", encoding="utf-8") as f:
        f.write(txt_content)

    # 2) 하위 호환 루트 파일
    with open(os.path.join(gen_root, "blog_post.html"), "w", encoding="utf-8") as f:
        f.write(html_content)
    with open(os.path.join(gen_root, "blog_post.txt"), "w", encoding="utf-8") as f:
        f.write(txt_content)
    with open(os.path.join(gen_root, "validated.json"), "w", encoding="utf-8") as f:
        json.dump(val_data, f, ensure_ascii=False, indent=2)

    # 3) 매니페스트 기록
    manifest = {
        "canonical_latest_date": date_to_sync,
        "synced_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S KST"),
        "source_output_dir": f"{base_data_dir}/output/{date_to_sync}",
        "source_processed_file": proc_file,
        "source_validation_file": val_file
    }
    with open(os.path.join(gen_root, "latest_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    return {
        "success": True,
        "synced": True,
        "canonical_latest_date": date_to_sync,
        "manifest": manifest
    }


def rerender_date_report(report_date: str, base_data_dir: str = "data", sync_if_latest: bool = True, is_post_1630: bool = False) -> Dict[str, Any]:
    """
    지정된 날짜(report_date)의 processed SSOT와 validation 결과만을 엄격 매칭하여
    해당 날짜의 data/output/{report_date}/blog_post.* 만 재렌더링합니다.
    과거 날짜를 재렌더링할 경우 최신 프리뷰 파일은 절대 덮어쓰지 않습니다.
    """
    proc_path = os.path.join(base_data_dir, "processed", f"{report_date}.json")
    val_path = os.path.join(base_data_dir, "generated", report_date, "validation.json")

    if not os.path.exists(proc_path):
        raise FileNotFoundError(f"Processed SSOT를 찾을 수 없습니다: {proc_path}")
    if not os.path.exists(val_path):
        raise FileNotFoundError(f"Validation 결과를 찾을 수 없습니다: {val_path}")

    with open(proc_path, "r", encoding="utf-8") as f:
        proc_data = json.load(f)
    with open(val_path, "r", encoding="utf-8") as f:
        val_data = json.load(f)

    # NaverBlogFormatter 내부에서 _validate_date_alignment를 통해 report_date 일치성 강제 검사
    html_content = NaverBlogFormatter.format_blog_html(val_data, proc_data, is_post_1630=is_post_1630)
    text_content = NaverBlogFormatter.format_blog_text(val_data, proc_data, is_post_1630=is_post_1630)

    out_dir = os.path.join(base_data_dir, "output", report_date)
    os.makedirs(out_dir, exist_ok=True)
    out_html = os.path.join(out_dir, "blog_post.html")
    out_txt = os.path.join(out_dir, "blog_post.txt")

    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html_content)
    with open(out_txt, "w", encoding="utf-8") as f:
        f.write(text_content)

    sync_res = None
    if sync_if_latest:
        # sync_latest_output will safely refuse if report_date is older than canonical latest
        sync_res = sync_latest_output(base_data_dir=base_data_dir, target_report_date=report_date)

    return {
        "success": True,
        "report_date": report_date,
        "html_path": out_html,
        "text_path": out_txt,
        "sync_result": sync_res
    }


# FiccReportGenerator 클래스 바인딩
FiccReportGenerator.get_latest_canonical_date = staticmethod(get_latest_canonical_date)
FiccReportGenerator.sync_latest_output = staticmethod(sync_latest_output)
FiccReportGenerator.rerender_date_report = staticmethod(rerender_date_report)

