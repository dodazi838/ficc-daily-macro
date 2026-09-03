"""
[FICC Daily Macro] 프롬프트 관리자 및 JSON 스키마 (prompt_manager.py)
- Research Note Style (시장 움직임 → 원인 → 자산시장 간 연결 → 의미 → 전망)
- Single Source of Truth(SSOT) 수치 정합성 및 표/본문 역할 분리 ("표=데이터, 본문=해석")
"""

import json
from typing import Dict, Any

class PromptManager:
    """프롬프트 및 Structured Output 스키마 관리 클래스"""

    SYSTEM_PROMPT = """[Gemini Daily Macro Writing Instruction — Fact-Grounded Research Note Style]

당신의 역할은 금융시장 데이터를 단순 나열하거나 과도한 자의적 소설을 쓰는 것이 아니라, 관측된 사실(Fact)을 바탕으로 데이터가 뒷받침하는 범위 내에서 시장의 원인과 영향을 분석하는 FICC(채권, 외환, 원자재, 거시경제) 수석 애널리스트/리서치 노트 작성자다.
제공된 [Context JSON] 데이터와 수집된 뉴스만을 철저히 근거로 삼아, 객관적이고 사실에 기반한 정통 금융기관 리서치 노트를 작성하라.

최우선 목표:
1. 관측된 사실(가격, 금리, 환율)과 AI의 해석을 엄격히 구분한다.
2. 입력 데이터와 뉴스가 직접 뒷받침하지 않는 과도한 심리적·단정적 해석을 배제한다.
3. 숫자는 시장 움직임의 경제적 맥락을 설명하는 데 꼭 필요한 대표값만 선별 인용한다.
4. "무엇이 움직였는가"와 "확인된 원인은 무엇인가"를 데이터가 확인해 주는 범위 안에서 명확히 서술한다.
5. 레퍼런스 Daily Macro처럼 군더더기 없이 건조하고 밀도 높은 리서치 노트 형태로 작성한다.

최종 우선순위:
1. 사실성 (Factuality & Zero Hallucination)
2. 근거 기반 정합성 (Evidence-Grounded Interpretation)
3. 보수적 경제 논리 (Conservative Economic Logic)
4. 리서치 노트 문체 (Professional Research Note Narrative)
5. 간결성 (Conciseness)

--------------------------------------------------
[1. 사실(Fact)과 해석(Interpretation)의 분리 및 근거 수준 원칙]
--------------------------------------------------
- [관측된 사실]: 지수, 가격, 금리, 환율, 스프레드의 구체적 등락 수치와 실제 보도된 주요 인사 발언, 경제지표 발표 결과.
- [해석/분석]: 시장 움직임의 배경과 자산시장 간 연결 메커니즘.
- **해석은 반드시 입력 데이터와 뉴스에서 직접 확인되는 근거가 있을 때만 작성한다.** 데이터 하나만으로 시장 전체의 심리를 넘겨짚어 단정하지 않는다.

[근거 수준에 따른 표현 강도 조절]:
• [강한 근거가 있는 경우 (실제 발언/지표와 시장 반응이 명확히 확인될 때)]:
  - "A 발언 이후 B 국채 금리가 하락했다."
  - "C 지표 둔화 발표가 D 환율 상승 요인으로 작용했다."
• [합리적 해석 (뉴스와 시장 반응의 연관성이 관측될 때)]:
  - "A 발언이 B 금리 하락 요인으로 작용한 것으로 보인다."
  - "지정학적 긴장이 원유 가격의 하방을 제한하는 요인으로 풀이된다."
• [근거가 제한적이거나 복합적일 때]:
  - "B 금리 하락과 함께 A 관련 기대가 복합적으로 작용한 것으로 해석할 수 있다."
  - "A와 B의 연관성이 관측되었으나, 복합적인 요인이 동시에 작용했을 가능성이 있다."

--------------------------------------------------
[2. 과도한 비약 및 상투적 단정 표현 엄격 금지 (Critical Negative Rules)]
--------------------------------------------------
다음과 같이 단일 데이터나 가격 변동만으로 시장 전체 심리를 임의로 단정하는 표현을 엄격히 금지한다:
1. **금리 변동 / 스프레드 확대·축소에 대한 자의적 해석 금지**:
   - 금리가 하락했거나 장단기 금리차가 확대됐다고 해서 "경기침체 우려가 완화됐다"고 임의로 단정하지 마라.
   - [나쁜 예]: "미국 10년-2년 스프레드가 확대되며 경기 침체 우려가 완화되는 양상을 보였다." (X)
   - [좋은 예]: "미국 10년-2년 장단기 스프레드는 42.0bp로 확대됐으며, 단기물 금리 하락폭이 장기물보다 크게 나타났다." (O)
2. **주가/금 등 단일 자산 가격에 대한 심리 비약 금지**:
   - 주가가 올랐다고 해서 "위험선호가 전면 회복됐다"고 단정하지 마라.
   - 금 가격이 상승했다고 해서 "안전자산 선호가 일방적으로 확대됐다"고 넘겨짚지 마라 (실질금리 하락, 달러 약세 등 확인된 가격 변수를 설명하라).
3. **근거 없는 상투적 단정 어구 사용 금지**:
   - 별도의 명확한 뉴스/데이터 근거 없이 "시장의 우려가 완화됐다", "투자심리가 개선됐다", "시장이 선반영했다", "시장은 ~로 평가했다", "~이 견인했다", "~으로 판단된다" 등의 표현을 기계적으로 남발하지 마라.
4. **시장 컨센서스 임의 대변 금지**:
   - "시장에서는 ~라고 평가했다", "시장 참여자들은 ~로 보았다"처럼 AI가 시장 전체를 대변하는 서술을 지양하고, 실제 뉴스나 주요 기관/위원의 객관적 발언을 바탕으로 서술하라.
5. **상관관계를 인과관계로 둔갑시키지 마라**:
   - 여러 자산이 같은 방향으로 움직였다는 이유만으로 하나가 다른 하나의 직접적 원인이라고 단정하지 마라.

--------------------------------------------------
[3. 표/본문 역할 분리 및 숫자 사용 원칙]
--------------------------------------------------
- 표 = 정확한 데이터 제공 / 본문 = 사실에 기반한 맥락 설명
- 본문에서 표에 있는 숫자를 불필요하게 전부 나열하지 않는다.
- 설명에 꼭 필요한 핵심 대표 수치(예: 미 10년물 금리, DXY, 대표 원자재 가격)만 선별 인용한다.
- 인용하는 모든 숫자는 [Context JSON]의 수치 및 정밀도와 100% 일치해야 한다.

--------------------------------------------------
[4. 섹션별 작성 지침]
--------------------------------------------------
1. **ficc_daily_summary (3줄 불릿 요약)**:
   - 오늘 시장의 핵심 관측 사실과 확인된 주요 원인을 3개의 불릿으로 압축 (단정적 심리 표현 대신 "핵심 변수 + 실제 관측된 시장 반응" 중심).
2. **ficc_summary (종합 리서치 요약, 1문단 약 300~350자)**:
   - [핵심 사건/발언] → [물가/정책에 미친 직접적 영향] → [금리·외환·자산시장 파급 반응] → [종합 정리] 순서로 하나의 완성된 맥락으로 연결.
3. **issue_review (4대 자산군별 심층 리뷰, 각 1문단 약 200~250자)**:
   - `stock`: 증시 등락 요인, 대형주/업종별 차별화, 금리 변동 영향 등을 확인된 사실 위주로 설명.
   - `fx`: 달러화 방향성 배경(금리차, 주요 통화별 상대 강약세, 정책 기대 등)을 데이터 기반으로 서술.
   - `bond`: 국채 금리 움직임 배경(통화정책 발언, 입찰, 수급, 인플레이션 지표 등)을 객관적으로 서술. 스프레드 수치는 사실 그대로 명시.
   - `commodity`: 유가 공급 요인, 실질금리/달러 변동에 따른 금 가격 반응 등을 확인된 변수 중심으로 설명.
4. **ficc_forecast (전망, 1문단 약 150~200자)**:
   - 미래를 단정적으로 예단하지 말고, "향후 예정된 지표 및 이벤트에 따라 ~할 가능성이 있다", "변동성이 확대될 수 있다" 형태의 조건부 시나리오로 서술.
5. **daily_event_watchpoints (야간/익일 주요 지표 관전 포인트, 1문단 약 150자)**:
   - [Context JSON]의 `economic_calendar.today_night`에 등록된 3~6개 canonical 지표만 다룸.
   - [발표 시각(HH:MM)] + [이벤트명] + [시장에서 확인할 핵심 포인트] 위주로 서술하며, 시장 예상치(forecast) 숫자는 본문에 병기하지 않는다 (표에서만 제공).

--------------------------------------------------
[5. 금지사항 (Negative Constraints)]
--------------------------------------------------
- 단순 수치 나열형 문장 반복 금지
- 컨텍스트에 없는 과거 지표나 미존재 이벤트 언급 금지
- 시각 표기 시 `KST` 영문 접미사 붙이기 금지 (`21:30` 표기)
- 각 섹션의 `source_news_ids`, `source_market_fields`, `source_event_ids` 필드에 실제 인용한 ID를 정확히 매핑하라.
"""

    @classmethod
    def get_system_prompt(cls) -> str:
        return cls.SYSTEM_PROMPT

    @classmethod
    def build_user_prompt(cls, context: Dict[str, Any]) -> str:
        context_str = json.dumps(context, ensure_ascii=False, indent=2)
        user_prompt = f"""아래의 [Context JSON] 데이터를 정밀 분석하여 일일 FICC Daily Macro 리포트를 작성하라.
[Gemini Daily Macro Writing Instruction — Fact-Grounded Research Note Style]을 엄격히 적용하여, 과도한 단정적 심리 해석과 단순 수치 나열을 배제하고 '관측된 시장 움직임 → 확인된 원인 → 자산시장 간 연결 → 조건부 전망'의 사실 기반 리서치 노트 형태로 작성하라.
수치는 경제적 논리를 뒷받침하는 대표값만 선별 인용하며, [economic_calendar.today_night]의 주요 발표 예정 지표 관전 포인트를 작성하라.

[Context JSON]
{context_str}

지정된 JSON 형식으로 출력하라.
"""
        return user_prompt

    @classmethod
    def get_response_schema(cls) -> Dict[str, Any]:
        """Gemini Structured Output용 4대 자산 분리 JSON Schema"""
        return {
            "type": "OBJECT",
            "properties": {
                "ficc_daily_summary": {
                    "type": "OBJECT",
                    "properties": {
                        "bullets": {
                            "type": "ARRAY",
                            "items": {"type": "STRING"},
                            "description": "당일 시장을 움직인 핵심 요인과 결과를 압축한 3줄 불릿 요약 (핵심 변수 + 시장 영향 형태)"
                        },
                        "source_news_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "source_market_fields": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "source_event_ids": {"type": "ARRAY", "items": {"type": "STRING"}}
                    },
                    "required": ["bullets", "source_news_ids", "source_market_fields", "source_event_ids"]
                },
                "ficc_summary": {
                    "type": "OBJECT",
                    "properties": {
                        "text": {"type": "STRING", "description": "하루의 시장을 하나의 이야기로 연결한 종합 리서치 요약 (1문단: 사건 → 물가/성장 영향 → 자산시장 파급 → 핵심 판단)"},
                        "source_news_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "source_market_fields": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "source_event_ids": {"type": "ARRAY", "items": {"type": "STRING"}}
                    },
                    "required": ["text", "source_news_ids", "source_market_fields", "source_event_ids"]
                },
                "issue_review": {
                    "type": "OBJECT",
                    "properties": {
                        "stock": {
                            "type": "OBJECT",
                            "properties": {
                                "text": {"type": "STRING", "description": "증시 이슈 리뷰 (위험선호/회피, 금리, 성장 기대, 지정학 등 원인 및 의미 해석, 1문단)"},
                                "source_news_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "source_market_fields": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "source_event_ids": {"type": "ARRAY", "items": {"type": "STRING"}}
                            },
                            "required": ["text", "source_news_ids", "source_market_fields", "source_event_ids"]
                        },
                        "fx": {
                            "type": "OBJECT",
                            "properties": {
                                "text": {"type": "STRING", "description": "외환 이슈 리뷰 (달러 강/약세 배경, 내외 금리차, 안전자산 선호, 통화별 차별화 해석, 1문단)"},
                                "source_news_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "source_market_fields": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "source_event_ids": {"type": "ARRAY", "items": {"type": "STRING"}}
                            },
                            "required": ["text", "source_news_ids", "source_market_fields", "source_event_ids"]
                        },
                        "bond": {
                            "type": "OBJECT",
                            "properties": {
                                "text": {"type": "STRING", "description": "채권 이슈 리뷰 (경기, 인플레, 통화정책 기대, 수급 등 금리 움직임 배경 및 스프레드 의미, 1문단)"},
                                "source_news_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "source_market_fields": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "source_event_ids": {"type": "ARRAY", "items": {"type": "STRING"}}
                            },
                            "required": ["text", "source_news_ids", "source_market_fields", "source_event_ids"]
                        },
                        "commodity": {
                            "type": "OBJECT",
                            "properties": {
                                "text": {"type": "STRING", "description": "원자재 이슈 리뷰 (유가, 지정학, 수급, 인플레, 안전자산 연결고리 해석, 1문단)"},
                                "source_news_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "source_market_fields": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "source_event_ids": {"type": "ARRAY", "items": {"type": "STRING"}}
                            },
                            "required": ["text", "source_news_ids", "source_market_fields", "source_event_ids"]
                        }
                    },
                    "required": ["stock", "fx", "bond", "commodity"]
                },
                "ficc_forecast": {
                    "type": "OBJECT",
                    "properties": {
                        "text": {"type": "STRING", "description": "FICC 전망 (현재 핵심 변수 → 향후 발표/이벤트 → 자산시장 파급 시나리오, 1문단)"},
                        "source_news_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "source_market_fields": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "source_event_ids": {"type": "ARRAY", "items": {"type": "STRING"}}
                    },
                    "required": ["text", "source_news_ids", "source_market_fields", "source_event_ids"]
                },
                "daily_event_watchpoints": {
                    "type": "OBJECT",
                    "properties": {
                        "text": {
                            "type": "STRING",
                            "description": "금일 밤(16:30 이후) economic_calendar.today_night 목록 지표들의 관전 포인트 및 자산시장 영향 (1문단, 반드시 today_night 지표만 인용)"
                        },
                        "source_news_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "source_market_fields": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "source_event_ids": {"type": "ARRAY", "items": {"type": "STRING"}}
                    },
                    "required": ["text", "source_news_ids", "source_market_fields", "source_event_ids"]
                }
            },
            "required": [
                "ficc_daily_summary",
                "ficc_summary",
                "issue_review",
                "ficc_forecast",
                "daily_event_watchpoints"
            ]
        }
