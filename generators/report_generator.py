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
import datetime
from typing import Dict, Any, Optional, List
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
            print(f" • [AI 생성 시도 2/2] 오류 피드백 기반 자동 보정(Self-Correction) Gemini 호출 중...")
            error_feedback_text = "\n".join([f"- {e}" for e in errors_1])
            user_prompt_2 = f"""[긴급 팩트 검증 오류 수정 요청]
이전에 작성된 리포트에서 다음과 같은 치명적인 사실/수치 불일치 오류가 적발되었습니다:
{error_feedback_text}

[절대 수정 지침]
1. 위에서 적발된 허위/미제공 수치(예: 미제공 이동평균선 '50일선', 임의의 확률 % '68%', 컨텍스트에 없는 수치)를 본문에서 즉시 완전히 삭제하거나, 반드시 아래 [Context JSON]에 제공된 정확한 당일 시장 데이터 수치로만 대체하라.
2. daily_event_watchpoints 본문은 반드시 [Context JSON]의 economic_calendar.today_night 에 실제로 존재하는 지표(예: ADP 비농업 고용, BOC 기준금리, EIA 원유재고 등)와 제공된 forecast 예상치만을 다루어라. 목록에 없는 지표(ISM PMI, JOLTS 등)는 완전히 제거하라.
3. 당일 시장 데이터 및 캘린더에 없는 숫자를 절대 새로 추정하거나 날조하지 마라.
4. 지정된 JSON 포맷을 완벽히 준수하여 다시 작성하라.

[Context JSON]
{json.dumps(context, ensure_ascii=False, indent=2)}
"""
            llm_result_2 = self.llm_adapter.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt_2,
                response_schema=schema
            )

            raw_content_2 = llm_result_2.get("parsed_content", {})
            usage_meta_2 = llm_result_2.get("usage", {})

            # FactValidator 2차 재검증
            enriched_content_2, val_summary_2 = FactValidator.validate_and_enrich(raw_content_2, context)
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
                "content": raw_content_2
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

        # 하위 호환성을 위한 최상위 generated/validated.json 동시 유지
        legacy_val_path = os.path.join(base_data_dir, "generated", "validated.json")
        try:
            with open(legacy_val_path, "w", encoding="utf-8") as f:
                json.dump(validation_payload, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

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

            # 하위 호환 복사본
            try:
                legacy_html = os.path.join(base_data_dir, "generated", "blog_post.html")
                legacy_txt = os.path.join(base_data_dir, "generated", "blog_post.txt")
                with open(legacy_html, "w", encoding="utf-8") as f:
                    f.write(blog_html)
                with open(legacy_txt, "w", encoding="utf-8") as f:
                    f.write(blog_text)
            except Exception:
                pass

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
