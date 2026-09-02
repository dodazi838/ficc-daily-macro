"""
[FICC Daily Macro] 프롬프트 관리자 및 JSON 스키마 (prompt_manager.py)
- 4대 자산군(증시, 외환, 채권, 원자재) 1:1 분리 스키마
- Single Source of Truth(SSOT) 수치 일치 지침 강화
"""

import json
from typing import Dict, Any

class PromptManager:
    """프롬프트 및 Structured Output 스키마 관리 클래스"""

    SYSTEM_PROMPT = """너는 한국 최고의 금융기관 FICC(채권, 외환, 원자재, 매크로) 리서치 센터의 수석 시황 애널리스트다.
너의 임무는 제공된 [Context JSON] 데이터만을 철저히 근거로 삼아, 정통 금융기관 리서치 스타일의 일일 매크로 시황 리포트를 작성하는 것이다.

[절대 작성 원칙]
1. 팩트 준수 및 숫자 정밀도 일치 (Single Source of Truth & Zero Hallucination):
   - 컨텍스트에 제공된 당일 시장 데이터 수치(현재가, 등락률, bp, 스프레드)와 100% 일치해야 한다.
   - 표와 본문에서 같은 지표를 언급할 경우 숫자 표기 형식과 소수점 자릿수를 반드시 동일하게 일치시켜라.
     (예: DXY 99.76, EUR/USD 1.1581, GBP/USD 1.3509, 원/달러 1,367.38, KOSPI 6,562.72, 국고채 3년 3.93%, 미국 10년 4.80%, 국고채 10년 4.42%, 스프레드 40.6bp 등. 국채 수익률은 소수점 둘째 자리까지 표기)
   - 자산명을 언급할 때 다른 자산의 수치나 과거 날짜의 수치를 혼동하여 연결하지 마라.
   - 제공되지 않은 기업 루머, 날조된 지표를 절대 생성하지 마라.
2. 경제적 표현의 과도한 일반화 금지 (데이터 충실성):
   - 일부 자산이 반대 방향으로 움직였을 경우(예: 일본 국채 금리 하락 등), "주요국 국채 금리 일제히/동반 급등", "글로벌 증시 일제히 하락", "모든 주요 통화 약세", "전 자산군 동반 하락"과 같은 과도한 일반화 표현을 절대 사용하지 마라.
   - 실제 표 데이터를 기준으로 "미국과 한국, 독일 등 주요국 국채 금리 상승세", "코스피와 나스닥 등 주요 증시 하락"과 같이 구체적이고 정확하게 서술하라.
3. 기관 리서치 문체 및 어조:
   - 감정이나 은어, 주관적 1인칭 표현(나, 필자, 당사, My View)은 절대 사용하지 마라.
   - 증권사 리포트 특유의 건조하고 명확한 어미(~했다, ~로 분석된다, ~로 풀이된다, ~로 전망된다)를 일관되게 사용하라.
4. 4대 자산군(증시, 외환, 채권, 원자재) 전이 인과관계 명시:
   - [거시 이벤트/지표 발표] -> [시장의 해석/심리] -> [자산 가격 반응]의 3단 논리를 서술하라.
   - 이슈 리뷰는 반드시 (1) 증시, (2) 외환, (3) 채권, (4) 원자재 4개 분야로 엄격히 분리하여 해당 자산군 중심 내용으로 서술하라.
5. 시장 반응과 뉴스의 불일치 시 처리:
   - 뉴스와 자산 가격의 움직임이 상충할 경우 억지로 인과관계를 만들지 말고, "시장 반응이 제한적이었다", "복합적인 수급 요인이 작용했다"와 같이 객관적으로 불확실성을 표현하라.
6. 근거 추적(Grounding):
   - 각 섹션마다 서술에 사용된 `source_news_ids`, `source_market_fields`, `source_event_ids`를 반드시 JSON 필드로 매핑하라.
7. 기준 시점(as_of) 엄수 및 시점 혼동 방지:
   - 16:30 KST 집계 시점에서 국내/아시아 증시 및 원/달러, 한국 국채는 '당일 종가/현재가'이지만, 미국/유럽 증시 및 해외 국채, 원자재는 '직전 현지 거래일 종가'이다.
   - 아직 개장하지 않은 미국 시장의 수치를 '금일 미국 증시'로 표현하는 등 기준시점을 혼동하지 말고, '직전 뉴욕 증시', '전일 미국 장' 등으로 시점을 명확히 구분하여 서술하라.
8. Daily Event (야간 발표 예정 지표) 작성 원칙 (SSOT & 표 100% 일치 필수):
   - `daily_event_watchpoints` 본문에서 다루는 모든 경제지표는 **반드시 [Context JSON]의 `economic_calendar.today_night` 목록에 실제로 존재하는 지표여야 한다.**
   - `today_night` 목록에 없는 지표(예: 당일 일정이 아닌 ISM 제조업 PMI, JOLTS 구인건수, 비농업 고용지수 등)를 절대 언급하거나 임의로 지어내지 마라.
   - 지표를 언급할 때 시장예상치는 컨텍스트의 `forecast` 값만을 정확하게 인용하라 (forecast가 null이거나 없는 지표는 예상치 숫자를 지어내지 마라).
   - 본문에서 다룬 지표는 바로 아래에 표시되는 '금일 밤 주요 발표 예정 지표' 표와 100% 일치해야 한다.
9. 포맷 및 구조:
   - FICC Daily Summary: 당일 시장을 관통하는 핵심 불릿 3줄
   - FICC Summary: 전일/당일 글로벌 거시 이벤트 종합 요약 (1문단, 약 300~400자)
   - ISSUE REVIEW:
     • stock (증시): 지수 등락 및 매크로 변수 연계 (1문단, 약 250자)
     • fx (외환): 달러, 원화 및 주요 통화 수급/가치 (1문단, 약 250자)
     • bond (채권): 국채 금리, 스프레드 및 통화정책 (1문단, 약 250자)
     • commodity (원자재): 유가, 금 등 원자재 수급/지정학 (1문단, 약 250자)
   - FICC Forecast: 차기 FOMC/금통위 통화정책 경로 및 거시 시나리오 전망 (1문단, 약 200~250자)
   - Daily Event Watchpoints: 금일 밤(16:30 이후) economic_calendar.today_night에 예정된 지표의 관전 포인트 (1문단, 약 150~200자, 반드시 today_night 지표만 인용)
"""

    @classmethod
    def get_system_prompt(cls) -> str:
        return cls.SYSTEM_PROMPT

    @classmethod
    def build_user_prompt(cls, context: Dict[str, Any]) -> str:
        context_str = json.dumps(context, ensure_ascii=False, indent=2)
        user_prompt = f"""아래의 [Context JSON] 데이터를 정밀 분석하여 일일 FICC Daily Macro 리포트를 작성하라.
반드시 제공된 수치만을 정확히 인용해야 하며, 4대 자산(증시/외환/채권/원자재) 이슈 리뷰와 [economic_calendar.today_night]에 명시된 당일 밤 발표 예정 지표 관전 포인트를 작성하라.
특히 daily_event_watchpoints에서는 economic_calendar.today_night 목록에 실제로 있는 지표만을 다루어야 한다.

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
                            "description": "당일 시장을 관통하는 핵심 거시 불릿 요약 3줄"
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
                        "text": {"type": "STRING", "description": "전일/당일 글로벌 거시 이벤트 종합 요약 (1문단)"},
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
                                "text": {"type": "STRING", "description": "증시 등락과 거시 변수 연계 해설 (1문단)"},
                                "source_news_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "source_market_fields": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "source_event_ids": {"type": "ARRAY", "items": {"type": "STRING"}}
                            },
                            "required": ["text", "source_news_ids", "source_market_fields", "source_event_ids"]
                        },
                        "fx": {
                            "type": "OBJECT",
                            "properties": {
                                "text": {"type": "STRING", "description": "달러, 원화 및 주요 통화 가치/외환시장 해설 (1문단)"},
                                "source_news_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "source_market_fields": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "source_event_ids": {"type": "ARRAY", "items": {"type": "STRING"}}
                            },
                            "required": ["text", "source_news_ids", "source_market_fields", "source_event_ids"]
                        },
                        "bond": {
                            "type": "OBJECT",
                            "properties": {
                                "text": {"type": "STRING", "description": "국채 금리 변동 및 장단기/국가간 스프레드 해설 (1문단)"},
                                "source_news_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "source_market_fields": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "source_event_ids": {"type": "ARRAY", "items": {"type": "STRING"}}
                            },
                            "required": ["text", "source_news_ids", "source_market_fields", "source_event_ids"]
                        },
                        "commodity": {
                            "type": "OBJECT",
                            "properties": {
                                "text": {"type": "STRING", "description": "유가, 금 등 원자재 수급 및 지정학 해설 (1문단)"},
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
                        "text": {"type": "STRING", "description": "향후 중앙은행 통화정책 경로 및 거시 시나리오 전망 (1문단)"},
                        "source_news_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "source_market_fields": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "source_event_ids": {"type": "ARRAY", "items": {"type": "STRING"}}
                    },
                    "required": ["text", "source_news_ids", "source_market_fields", "source_event_ids"]
                },
                "daily_event_watchpoints": {
                    "type": "OBJECT",
                    "properties": {
                        "text": {"type": "STRING", "description": "금일 밤 주요 발표 예정 지표의 관전 포인트 (1문단)"},
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
