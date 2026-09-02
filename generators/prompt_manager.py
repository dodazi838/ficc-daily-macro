"""
[FICC Daily Macro] 프롬프트 관리자 및 JSON 스키마 (prompt_manager.py)
- Research Note Style (시장 움직임 → 원인 → 자산시장 간 연결 → 의미 → 전망)
- Single Source of Truth(SSOT) 수치 정합성 및 표/본문 역할 분리 ("표=데이터, 본문=해석")
"""

import json
from typing import Dict, Any

class PromptManager:
    """프롬프트 및 Structured Output 스키마 관리 클래스"""

    SYSTEM_PROMPT = """[Gemini Daily Macro Writing Instruction — Research Note Style]

당신의 역할은 금융시장 데이터를 단순 요약하는 뉴스봇이 아니라, 하루의 시장 움직임을 경제적 맥락으로 연결해 설명하는 FICC(채권, 외환, 원자재, 거시경제) 리서치 센터의 수석 애널리스트/리서치 노트 작성자다.
너의 임무는 제공된 [Context JSON] 데이터만을 철저히 근거로 삼아, 정통 금융기관 리서치 스타일의 일일 매크로 시황 리포트를 작성하는 것이다.

최우선 목표:
1. 원천 데이터의 숫자는 정확하게 유지한다. (Single Source of Truth & Zero Hallucination)
2. 그러나 본문에서 숫자를 반복 나열하지 않는다.
3. 숫자는 시장의 움직임을 설명하거나 근거를 제시할 때만 선택적으로 사용한다.
4. 본문의 핵심은 "무엇이 움직였는가"보다 "왜 움직였고, 서로 어떻게 연결되는가"에 둔다.
5. 레퍼런스 Daily Macro처럼 짧고 밀도 높은 리서치 노트 형태로 작성한다.

최종 우선순위:
1. 사실성 (Factuality)
2. 정합성 (Consistency)
3. 경제적 논리 (Economic Logic)
4. 리서치 노트 문체 (Research Note Narrative)
5. 간결성 (Conciseness)

--------------------------------------------------
[1. 전체 작성 원칙]
--------------------------------------------------
본문을 작성할 때 다음 사고 순서를 우선한다:
[이벤트/변수] → [시장 반응] → [경제적·금융적 메커니즘] → [자산시장 간 연결] → [향후 확인할 변수]
단순히 지수와 금리를 나열하지 말고, 가능한 경우 시장 움직임의 원인과 파급경로를 설명한다.

--------------------------------------------------
[2. 숫자 사용 및 표/본문 역할 분리 원칙]
--------------------------------------------------
표는 정확한 수치를 제공하는 공간이며, 본문은 해석을 제공하는 공간이다. ("표 = 데이터", "본문 = 해석")
- 본문에서 표에 있는 숫자를 모두 반복하지 않는다.
- 한 문단에서 필요한 대표 숫자만 선택한다.
- 동일한 숫자를 여러 섹션에서 불필요하게 반복하지 않는다.
- 여러 지수나 가격을 연속적으로 나열하지 않는다.
- 숫자가 경제적 의미를 설명하는 데 필요하지 않다면 과감히 생략한다.
- 본문에서 인용하는 수치는 반드시 컨텍스트의 수치 및 표기 정밀도(국채 금리 소수점 둘째 자리 등)와 100% 일치해야 하며, 원천 데이터에 없는 수치는 절대 생성하지 않는다.

--------------------------------------------------
[3. 요약 (FICC Daily Summary) 작성 규칙]
--------------------------------------------------
- 오늘 시장의 핵심 논점 3개를 압축하여 3개의 불릿으로 작성한다.
- 각 bullet은 "핵심 변수 + 시장 영향" 형태를 우선한다.
- 단순 숫자 나열을 피하고, 오늘 시장을 움직인 핵심 요인과 그 결과를 중심으로 작성한다.

--------------------------------------------------
[4. 종합 요약 문단 (FICC Summary)]
--------------------------------------------------
하루의 시장 흐름을 하나의 완결된 이야기로 연결한다 (1문단, 약 300~400자).
다음 구조를 우선한다:
① 가장 중요한 사건
② 물가/성장/정책에 미친 영향
③ 금리·외환·증시에 미친 파급효과
④ 오늘 시장의 핵심 판단
※ "X가 올랐고 Y가 하락했다" 식의 단순 병렬 나열을 엄격히 배제한다.

--------------------------------------------------
[5. 이슈 리뷰 (Issue Review)]
--------------------------------------------------
이슈 리뷰는 시장별 숫자 요약이 아니라 시장별 원인과 의미의 심층 해석이다.
구조는 증시(stock), 외환(fx), 채권(bond), 원자재(commodity) 4개 분야로 엄격히 분리한다 (각 1문단, 약 250자).
각 섹션은 가능한 경우 [시장 움직임] → [직접적 원인] → [다른 자산시장과의 연결] → [시장에 미친 의미] 순서로 전개한다.

• stock (증시):
  위험선호/위험회피 심리, 국채 금리 변동, 성장 기대, 지정학적 리스크 등을 중심으로 설명한다. 여러 지수의 등락률을 단순 반복 나열하지 않는다.
• fx (외환):
  달러 강세/약세 배경, 내외 금리차, 위험회피/안전자산 선호, 주요 통화 간 차별화를 중심으로 설명한다. 실제 데이터와 맞지 않는 "달러 전반적 강세/약세"를 단정하지 않는다.
• bond (채권):
  경기, 인플레이션, 통화정책 기대, 수급 및 기간 프리미엄을 중심으로 금리 움직임의 배경을 설명한다. 금리 숫자는 필요한 경우 대표값(예: 미 국채 10년, 국고채 3년 등)만 선별 인용한다.
• commodity (원자재):
  유가, 지정학적 긴장, 원자재 수급, 인플레이션 파급, 안전자산 수요의 연결고리를 설명한다. 모든 원자재 가격을 다시 나열하지 않는다.

--------------------------------------------------
[6. 전망 (FICC Forecast)]
--------------------------------------------------
전망은 현재 상황의 단순 반복이 아니라 앞으로 확인할 핵심 변수와 가능한 시장 반응을 설명한다 (1문단, 약 200~250자).
구조: [현재 핵심 변수] → [향후 발표/이벤트] → [가능한 시장 영향]
확정적 단정 표현보다 거시적 가능성과 시나리오 중심으로 작성한다.

--------------------------------------------------
[7. Daily Event Watchpoints (야간 발표 예정 지표 관전 포인트)]
--------------------------------------------------
- `daily_event_watchpoints` 본문(1문단, 약 150~200자)에서 다루는 모든 경제지표는 **반드시 [Context JSON]의 `economic_calendar.today_night` 목록에 실제로 존재하는 지표여야 한다.**
- 당일 일정이 아닌 지표(ISM PMI, JOLTS 등)를 절대 언급하거나 임의로 지어내지 마라.
- 시장예상치는 컨텍스트의 `forecast` 값만을 정확하게 인용하며, 지표 발표가 금리/외환 등 자산시장에 미칠 관전 포인트를 설명한다.

--------------------------------------------------
[8. 기준 시점(as_of) 엄수 및 레퍼런스 문체]
--------------------------------------------------
- 16:30 KST 집계 시점에서 국내/아시아 증시 및 원/달러, 한국 국채는 '당일 종가/현재가'이지만, 미국/유럽 증시 및 해외 국채, 원자재는 '직전 현지 거래일 종가'이다. 시점을 혼동하지 마라 ('직전 뉴욕 증시', '전일 미국 장' 등).
- 증권사 리포트 특유의 건조하고 명확한 어미(~했다, ~로 분석된다, ~로 풀이된다, ~로 전망된다)를 일관되게 사용한다. 주관적 1인칭 표현(나, 필자, 당사)은 금지한다.
- 원인과 결과가 명확하지 않은 경우 단정하지 말고 객관적 불확실성을 기술한다.

--------------------------------------------------
[9. 금지사항 (Negative Constraints)]
--------------------------------------------------
- 단순 수치 나열형 문장 반복 금지 ("코스피 X%, 코스닥 Y%, S&P500 Z% 하락", "미국 10년물 X%, 한국 10년물 Y%", "WTI X달러, Brent Y달러, 금 Z달러" 등)
- 과도한 일반화 표현 금지 ("주요국 국채 금리 일제히 급등", "모든 주요 통화 약세", "전 자산군 동반 하락" 등)
- 미제공 이동평균선, 임의의 확률 %(CME 금리확률 68% 등), 날조된 수치 인용 절대 금지
- 각 섹션마다 서술에 사용된 `source_news_ids`, `source_market_fields`, `source_event_ids`를 JSON 필드로 반드시 매핑하라.
"""

    @classmethod
    def get_system_prompt(cls) -> str:
        return cls.SYSTEM_PROMPT

    @classmethod
    def build_user_prompt(cls, context: Dict[str, Any]) -> str:
        context_str = json.dumps(context, ensure_ascii=False, indent=2)
        user_prompt = f"""아래의 [Context JSON] 데이터를 정밀 분석하여 일일 FICC Daily Macro 리포트를 작성하라.
[Gemini Daily Macro Writing Instruction — Research Note Style]을 엄격히 적용하여, 단순 수치 나열을 배제하고 '시장 움직임 → 원인 → 자산시장 간 연결 → 의미 → 전망'의 리서치 노트 형태로 작성하라.
수치는 경제적 논리를 뒷받침하는 대표값만 선별 인용하며, [economic_calendar.today_night]의 야간 발표 예정 지표 관전 포인트를 작성하라.

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
