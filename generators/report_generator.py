"""
[FICC Daily Macro] AI 시황 리포트 및 블로그 원고 생성 총괄 관리자 (report_generator.py)
- Single Source of Truth 기반 Context -> Gemini 3.7 Flash 호출 -> FactValidator 엄격 검증
- 검증 실패 시 자동 보정(Self-Correction) 재시도 (최대 2회)
- 검증 통과(passed == True) 시에만 blog_post.html / blog_post.txt 생성
- 2회 모두 실패 시 validation_failed.json 저장 및 게시물 생성 즉시 차단
"""

import os
import json
import datetime
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

from generators.context_builder import AIContextBuilder
from generators.prompt_manager import PromptManager
from generators.llm_adapter import get_llm_adapter, BaseLLMAdapter
from generators.blog_formatter import NaverBlogFormatter
from processors.fact_validator import FactValidator

class FiccReportGenerator:
    """FICC Daily Macro AI 리포트 및 블로그 원고 생성 총괄 관리자"""

    def __init__(self, llm_adapter: Optional[BaseLLMAdapter] = None):
        self.llm_adapter = llm_adapter or get_llm_adapter()

    def generate_report_from_file(self, processed_json_path: str, generated_dir: str = "data/generated", is_post_1630: bool = False) -> Dict[str, Any]:
        """
        가공 데이터 파일(data/processed/YYYY-MM-DD.json)을 읽어
        1) AI Structured Report 생성 (Gemini 3.7 Flash)
        2) Fact Validator 엄격 검증 (Strict Asset-Value Binding)
        3) 실패 시 오류 피드백을 반영한 자동 1회 재시도 (최대 2회)
        4) 검증 통과 시에만 blog_post.html / blog_post.txt 렌더링
        5) 최종 실패 시 validation_failed.json 저장 및 게시 차단
        """
        if not os.path.exists(processed_json_path):
            raise FileNotFoundError(f"가공 데이터 파일을 찾을 수 없습니다: {processed_json_path}")

        with open(processed_json_path, "r", encoding="utf-8") as f:
            processed_data = json.load(f)

        report_date = processed_data.get("report_date", datetime.datetime.now().strftime("%Y-%m-%d"))
        os.makedirs(generated_dir, exist_ok=True)

        # 1. AI 컨텍스트 빌드 (SSOT)
        context = AIContextBuilder.build_context(processed_data)
        system_prompt = PromptManager.get_system_prompt()
        schema = PromptManager.get_response_schema()

        attempts = 0
        max_attempts = 2
        current_user_prompt = PromptManager.build_user_prompt(context)
        last_raw_content = None
        last_usage_meta = {}
        last_val_summary = {}

        while attempts < max_attempts:
            attempts += 1
            print(f" • [AI 생성 시도 {attempts}/{max_attempts}] Gemini 3.7 Flash 호출 중...")

            # Gemini 호출
            llm_result = self.llm_adapter.generate(
                system_prompt=system_prompt,
                user_prompt=current_user_prompt,
                response_schema=schema
            )

            raw_content = llm_result.get("parsed_content", {})
            usage_meta = llm_result.get("usage", {})
            last_raw_content = raw_content
            last_usage_meta = usage_meta

            # FactValidator 엄격 검증
            enriched_content, val_summary = FactValidator.validate_and_enrich(raw_content, context)
            last_val_summary = val_summary

            if val_summary.get("passed", False):
                print(f" • [AI 생성 시도 {attempts}/{max_attempts}] FactValidator 검증 통과 (PASS)!")
                break
            else:
                errors = val_summary.get("errors", [])
                print(f" • [AI 생성 시도 {attempts}/{max_attempts}] FactValidator 검증 실패 ({len(errors)}건 에러 발견)")
                for err in errors[:3]:
                    print(f"   - {err}")

                if attempts < max_attempts:
                    # 보정 프롬프트 생성 (Self-Correction Prompt)
                    error_feedback_text = "\n".join([f"- {e}" for e in errors])
                    current_user_prompt = f"""[긴급 팩트 검증 오류 수정 요청]
이전에 작성된 리포트에서 다음과 같은 치명적인 사실/수치 불일치 오류가 적발되었습니다:
{error_feedback_text}

[절대 수정 지침]
1. 위에서 적발된 허위/미제공 수치(예: 미제공 이동평균선 '50일선', 임의의 확률 % '68%', 컨텍스트에 없는 수치)를 본문에서 즉시 완전히 삭제하거나, 반드시 아래 [Context JSON]에 제공된 정확한 당일 시장 데이터 수치로만 대체하라.
2. 당일 시장 데이터에 없는 숫자를 절대 새로 추정하거나 날조하지 마라.
3. 지정된 JSON 포맷을 완벽히 준수하여 다시 작성하라.

[Context JSON]
{json.dumps(context, ensure_ascii=False, indent=2)}
"""

        # 최종 판정 처리
        is_finally_passed = last_val_summary.get("passed", False)

        # 1. 1차 원본 저장 (data/generated/report.json)
        raw_report_payload = {
            "report_date": report_date,
            "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S KST"),
            "attempts": attempts,
            "llm_metadata": last_usage_meta,
            "content": last_raw_content
        }
        report_json_path = os.path.join(generated_dir, "report.json")
        with open(report_json_path, "w", encoding="utf-8") as f:
            json.dump(raw_report_payload, f, ensure_ascii=False, indent=2)

        # 2. 2차 검증본 저장 (data/generated/validated.json)
        validated_payload = {
            "report_date": report_date,
            "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S KST"),
            "attempts": attempts,
            "llm_metadata": last_usage_meta,
            "validation_summary": last_val_summary,
            "content": enriched_content
        }
        validated_json_path = os.path.join(generated_dir, "validated.json")
        with open(validated_json_path, "w", encoding="utf-8") as f:
            json.dump(validated_payload, f, ensure_ascii=False, indent=2)

        blog_html_path = os.path.join(generated_dir, "blog_post.html")
        blog_text_path = os.path.join(generated_dir, "blog_post.txt")
        val_failed_path = os.path.join(generated_dir, "validation_failed.json")

        if is_finally_passed:
            # 검증 통과: blog_post.html / blog_post.txt 생성
            blog_html = NaverBlogFormatter.format_blog_html(
                report_data=validated_payload,
                processed_market_data=processed_data,
                is_post_1630=is_post_1630
            )
            with open(blog_html_path, "w", encoding="utf-8") as f:
                f.write(blog_html)

            blog_text = NaverBlogFormatter.format_blog_text(
                report_data=validated_payload,
                processed_market_data=processed_data,
                is_post_1630=is_post_1630
            )
            with open(blog_text_path, "w", encoding="utf-8") as f:
                f.write(blog_text)

            # 이전에 실패 파일이 있었다면 정리
            if os.path.exists(val_failed_path):
                os.remove(val_failed_path)

            return {
                "success": True,
                "report_date": report_date,
                "attempts": attempts,
                "report_json_path": report_json_path,
                "validated_json_path": validated_json_path,
                "blog_html_path": blog_html_path,
                "blog_text_path": blog_text_path,
                "validated_data": validated_payload,
                "blog_html": blog_html,
                "blog_text": blog_text,
                "usage": last_usage_meta,
                "validation_summary": last_val_summary
            }
        else:
            # 검증 최종 실패: blog_post 파일 생성 차단 및 validation_failed.json 저장
            if os.path.exists(blog_html_path):
                os.remove(blog_html_path)
            if os.path.exists(blog_text_path):
                os.remove(blog_text_path)

            failed_payload = {
                "report_date": report_date,
                "failed_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S KST"),
                "attempts": attempts,
                "status": "VALIDATION_FAILED_POST_BLOCKED",
                "validation_summary": last_val_summary,
                "raw_content": last_raw_content
            }
            with open(val_failed_path, "w", encoding="utf-8") as f:
                json.dump(failed_payload, f, ensure_ascii=False, indent=2)

            return {
                "success": False,
                "report_date": report_date,
                "attempts": attempts,
                "status": "VALIDATION_FAILED_POST_BLOCKED",
                "validation_failed_path": val_failed_path,
                "report_json_path": report_json_path,
                "validated_json_path": validated_json_path,
                "blog_html_path": None,
                "blog_text_path": None,
                "validation_summary": last_val_summary,
                "usage": last_usage_meta
            }
