"""
[FICC Daily Macro] LLM Provider 어댑터 모듈 (llm_adapter.py)
- Google GenAI 공식 SDK (from google import genai) 기반 구현
- Gemini 3.7 Flash + Thinking (thinking_level="medium")
- Structured Output (JSON Schema)
- response.parsed 우선 사용 및 정확한 토큰/비용 계산
"""

import os
import json
from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple, Optional
from dotenv import load_dotenv

load_dotenv()

# 공식 단가 테이블 (단위: 1,000,000 토큰당 USD)
# Gemini 3.7 Flash Standard: Input $0.75 / 1M, Output $3.75 / 1M (Output에 thinking tokens 포함)
MODEL_PRICING_TABLE = {
    "gemini-3.7-flash": {
        "input_per_million": 0.75,
        "output_per_million": 3.75
    },
    "gemini-2.5-flash": {
        "input_per_million": 0.075,
        "output_per_million": 0.30
    },
    "gemini-1.5-pro": {
        "input_per_million": 1.25,
        "output_per_million": 5.00
    },
    "gpt-4o": {
        "input_per_million": 2.50,
        "output_per_million": 10.00
    },
    "default": {
        "input_per_million": 0.75,
        "output_per_million": 3.75
    }
}

class BaseLLMAdapter(ABC):
    """LLM Provider 어댑터 기본 추상 클래스"""
    def __init__(self, provider_name: str, model_name: str):
        self.provider_name = provider_name
        self.model_name = model_name

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str, response_schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """구조화된 리포트 생성 실행"""
        pass

    @abstractmethod
    def estimate_token_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """토큰 기반 예상 비용(USD) 계산"""
        pass

class GeminiAdapter(BaseLLMAdapter):
    """Google Gemini API 어댑터 (google-genai 공식 SDK 기반)"""
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise ValueError(
                "GEMINI_API_KEY가 설정되지 않았습니다. .env 파일에 GEMINI_API_KEY=your_key 를 설정해주세요."
            )
        
        # 모델명은 .env의 LLM_MODEL 또는 전달받은 파라미터 우선 (기본 fallback: gemini-3.7-flash)
        model = model_name or os.getenv("LLM_MODEL") or "gemini-3.7-flash"
        super().__init__(provider_name="gemini", model_name=model)
        
        from google import genai
        self.client = genai.Client(api_key=key)

    def generate(self, system_prompt: str, user_prompt: str, response_schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Gemini 3.7 Flash Structured Output API 호출 (thinking_level='medium')"""
        from google.genai import types

        # Thinking 및 JSON Schema 설정
        config_args = {
            "system_instruction": system_prompt,
            "response_mime_type": "application/json",
            "thinking_config": types.ThinkingConfig(thinking_level="medium")
        }
        
        if response_schema:
            config_args["response_schema"] = response_schema

        config = types.GenerateContentConfig(**config_args)

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=user_prompt,
                config=config
            )
        except Exception as e:
            raise RuntimeError(f"[{self.provider_name}/{self.model_name}] API 호출 실패: {e}") from e

        # 토큰 사용량 추출 (SDK usage_metadata 실제 제공 필드 기준)
        usage_meta = getattr(response, "usage_metadata", None)
        prompt_tokens = getattr(usage_meta, "prompt_token_count", 0) if usage_meta else 0
        completion_tokens = getattr(usage_meta, "candidates_token_count", 0) if usage_meta else 0
        total_tokens = getattr(usage_meta, "total_token_count", prompt_tokens + completion_tokens) if usage_meta else 0
        thoughts_tokens = getattr(usage_meta, "thoughts_token_count", None) if usage_meta else None

        # 1. response.parsed 우선 활용
        parsed_json = None
        if hasattr(response, "parsed") and response.parsed is not None:
            if isinstance(response.parsed, dict):
                parsed_json = response.parsed
            elif hasattr(response.parsed, "model_dump"): # pydantic instance
                parsed_json = response.parsed.model_dump()

        # 2. parsed가 없을 경우 response.text -> json.loads fallback
        raw_text = response.text or ""
        if parsed_json is None:
            try:
                parsed_json = json.loads(raw_text)
            except json.JSONDecodeError:
                clean_text = raw_text.strip()
                if clean_text.startswith("```json"):
                    clean_text = clean_text[7:]
                if clean_text.endswith("```"):
                    clean_text = clean_text[:-3]
                try:
                    parsed_json = json.loads(clean_text.strip())
                except Exception as e:
                    raise ValueError(f"Gemini 응답 JSON 파싱 실패: {e}\n원본 텍스트: {raw_text[:200]}...") from e

        estimated_cost = self.estimate_token_cost(prompt_tokens, completion_tokens)

        return {
            "parsed_content": parsed_json,
            "raw_text": raw_text,
            "usage": {
                "provider": "gemini",
                "model": self.model_name,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "thinking_tokens": thoughts_tokens,
                "total_tokens": total_tokens,
                "estimated_cost_usd": round(estimated_cost, 6)
            }
        }

    def estimate_token_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """모델별 공식 단가 기준 비용 추정 (output 가격에 thinking tokens 포함)"""
        pricing = MODEL_PRICING_TABLE.get(self.model_name, MODEL_PRICING_TABLE["default"])
        input_cost = (prompt_tokens / 1_000_000) * pricing["input_per_million"]
        output_cost = (completion_tokens / 1_000_000) * pricing["output_per_million"]
        return input_cost + output_cost

class OpenAIAdapter(BaseLLMAdapter):
    """OpenAI API 어댑터 인터페이스 (확장용 스텁)"""
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        key = api_key or os.getenv("OPENAI_API_KEY")
        model = model_name or os.getenv("LLM_MODEL") or "gpt-4o"
        super().__init__(provider_name="openai", model_name=model)
        self.api_key = key

    def generate(self, system_prompt: str, user_prompt: str, response_schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")
        raise NotImplementedError("OpenAI Adapter는 향후 확장을 위한 인터페이스로 준비되었습니다.")

    def estimate_token_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        pricing = MODEL_PRICING_TABLE.get("gpt-4o", MODEL_PRICING_TABLE["default"])
        return ((prompt_tokens / 1_000_000) * pricing["input_per_million"]) + ((completion_tokens / 1_000_000) * pricing["output_per_million"])

def get_llm_adapter() -> BaseLLMAdapter:
    """환경변수(LLM_PROVIDER)에 따른 어댑터 팩토리 함수"""
    provider = os.getenv("LLM_PROVIDER", "gemini").lower().strip()
    if provider == "gemini":
        return GeminiAdapter()
    elif provider == "openai":
        return OpenAIAdapter()
    else:
        return GeminiAdapter()
