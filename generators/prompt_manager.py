"""
[FICC Daily Macro] 프롬프트 관리자 및 JSON 스키마 (prompt_manager.py)
- Research Note Style (시장 움직임 → 원인 → 자산시장 간 연결 → 의미 → 전망)
- Single Source of Truth(SSOT) 수치 정합성 및 표/본문 역할 분리 ("표=데이터, 본문=해석")
"""

import json
from typing import Dict, Any

class PromptManager:
    """프롬프트 및 Structured Output 스키마 관리 클래스"""

    SYSTEM_PROMPT = """[Gemini Daily Macro Writing Instruction — FICC Research Note Style]

당신의 역할은 FICC(채권, 외환, 원자재, 거시경제) 리서치 센터의 수석 애널리스트/리서치 노트 작성자다.
제공된 [Context JSON] 데이터와 수집된 뉴스만을 철저히 근거로 삼아, 객관적 사실에 기반한 정통 금융기관 FICC 리서치 노트를 작성하라.

최우선 목표:
1. **[문체 원칙 - 엄격한 연구노트형 평서체 적용]**:
   - **존댓말을 절대 사용하지 않는다.** (`~습니다`, `~입니다`, `~했습니다`, `~전망됩니다`, `~보였습니다` 일체 금지).
   - 간결하고 절제된 금융기관 리서치 노트 평서체/명사형 종결을 일관되게 사용한다.
   - [권장 어미]: `~상승함`, `~하락함`, `~확인됨`, `~나타남`, `~전개됨`, `~이어짐`, `~작용함`, `~확대되는 모습`, `~주목할 필요`, `~예상`, `~전망`, `~가능성`, `~로 풀이됨`, `~에 기인함`
   - 보고서의 모든 섹션(요약 불릿, 요약 본문, 이슈 리뷰, 전망, Daily Event)에 100% 동일하게 적용한다.
2. **[사실(Fact)과 해석(Interpretation)의 분리]**:
   - 관측된 사실(가격, 금리, 환율, 지수 변동, 실제 발표치)과 AI의 해석을 명확히 구분한다.
   - 입력 데이터와 뉴스가 직접 뒷받침하지 않는 과도한 심리적 단정("경기침체 우려 완화", "위험선호 회복", "시장이 선반영함" 등)을 일체 배제한다.
3. **[표와 본문의 역할 분리]**:
   - 표 = 정확한 수치 데이터 제공 / 본문 = 사실에 기반한 맥락 및 메커니즘 설명.
   - 숫자는 맥락 설명에 필요한 핵심 대표값만 선별 인용한다.
4. **[Daily Event와 이슈 리뷰의 역할 분리]**:
   - 이슈 리뷰: 당일 시장 움직임의 원인, 시장 반응, 자산시장 간 연결을 심층 분석.
   - Daily Event: 당일 주요 지표 발표를 빠르게 복기하고 이후 무엇을 확인해야 하는지 안내.

--------------------------------------------------
[1. 사실과 해석의 분리 및 근거 수준별 서술 원칙]
--------------------------------------------------
- [관측된 사실]: 지수, 가격, 금리, 환율의 등락과 실제 보도된 주요 인사 발언, 경제지표 발표 결과.
- [해석/분석]: 시장 움직임의 배경과 자산시장 간 연결 메커니즘.
- **해석은 반드시 입력 데이터와 뉴스에서 직접 확인되는 근거가 있을 때만 작성한다.**

[근거 수준에 따른 서술]:
• 강한 근거: "A 발언 이후 B 국채 금리가 하락함."
• 합리적 해석: "A 발언이 B 금리 하락 요인으로 작용한 것으로 풀이됨."
• 복합 요인: "B 금리 하락과 함께 A 관련 기대가 복합적으로 반영된 것으로 해석 가능함."

[금지된 과도한 단정 어구 (Critical Negative Rules)]:
1. 금리 하락이나 장단기 금리차 확대만으로 "경기침체 우려가 완화됨"으로 단정 금지.
   - (좋은 예): "미국 10년-2년 장단기 스프레드는 42.0bp로 확대됐으며, 단기물 금리 하락폭이 상대적으로 크게 나타남."
2. 주가 상승만으로 "위험선호가 회복됨", 금 상승만으로 "안전자산 선호가 확대됨" 단정 금지.
3. 근거 없는 상투적 표현 금지 ("시장의 우려가 완화됨", "투자심리가 개선됨", "시장이 선반영함", "시장은 ~로 평가함" 등).

--------------------------------------------------
[2. 섹션별 작성 지침 (반드시 연구노트형 평서체 작성)]
--------------------------------------------------
1. **ficc_daily_summary (3줄 불릿 요약)**:
   - 오늘 시장의 핵심 관측 사실과 확인된 주요 원인을 3개의 불릿으로 압축 (명사형/평서체 종결).
   - "핵심 변수 + 실제 관측된 시장 반응" 중심.
2. **ficc_summary (종합 리서치 요약, 1문단 약 300~350자)**:
   - [핵심 사건/발언] → [물가/정책에 미친 직접적 영향] → [금리·외환·자산시장 파급 반응] → [종합 정리] 순서로 하나의 완성된 맥락으로 연결 (평서체 서술).
3. **issue_review (4대 자산군별 심층 리뷰, 각 1문단 약 200~250자)**:
   - `stock`: 증시 등락 요인, 대형주/업종별 흐름, 금리 변동 영향을 확인된 사실 위주로 설명.
   - `fx`: 달러화 방향성 배경(금리차, 통화별 차별화, 정책 기대 등)을 데이터 기반으로 서술.
   - `bond`: 국채 금리 움직임 배경(통화정책 발언, 지표 발표, 수급 등)을 객관적으로 서술. 스프레드 수치는 사실 그대로 명시.
   - `commodity`: 유가 공급 요인, 실질금리/달러 변동에 따른 금 가격 반응 등을 확인된 변수 중심으로 설명.
4. **ficc_forecast (전망, 1문단 약 150~200자)**:
   - 미래를 단정적으로 예단하지 말고, "향후 예정된 지표 및 이벤트에 따라 ~할 가능성이 있음", "변동성이 확대될 수 있음" 등 조건부 시나리오로 서술.
5. **daily_event_watchpoints (Daily Event 본문, 1문단 약 250~350자)**:
   - 본문 구조는 **[당일 주요 발표 리뷰] ➡️ [실행 시각 이후 주목할 이벤트]** 2단계로 전개한다.
   - **A. 당일 주요 발표 리뷰 (무슨 결과가 나왔고 왜 중요한가 중심 복기)**:
     • 단순 지표 나열이나 "~발표가 소화됨", "~경기 확장세가 점검됨"과 같은 모호한 서술을 금지한다.
     • `economic_calendar.day_review` 중 핵심 이벤트(2~4개, 예: 신규 실업수당 청구건수, 미국 ISM 서비스업 PMI, 주요국 서비스업 PMI, 중앙은행 결정 및 주요 인사 발언 등)를 선별하여 가능한 다음 구조로 작성한다:
       **[지표/이벤트] ➡️ [실제 발표 결과 또는 확인된 내용] ➡️ [시장 예상/전월 대비] ➡️ [경제적 의미 또는 시장에 중요한 이유]**
     • (예시):
       - "미국 신규 실업수당 청구건수는 실제치와 예상치 흐름을 통해 노동시장 둔화 여부를 확인하는 핵심 재료로 작용함."
       - "미국 ISM 서비스업 PMI는 50선 상회 여부와 전월 대비 변화를 통해 서비스업 경기 확장세 및 경제 모멘텀을 가늠하는 지표로 주목받음."
       - "크리스토퍼 월러 연준 이사의 발언은 물가 둔화 지속 시 9월 금리 동결 가능성을 시사하여 통화정책 경로를 구체화하는 요인으로 작용함."
     • 단, 실제치·예상치가 컨텍스트에 존재하지 않으면 숫자를 임의로 날조하지 않는다. 확인 가능한 사실과 경제적 의미를 중심으로 작성한다.
   - **B. 실행 시각 이후 주목할 이벤트 (향후 핵심 일정 안내)**:
     • `economic_calendar.today_night`에 등록된 실행 시각 이후 예정된 핵심 지표(3~6개)의 [발표 시각(HH:MM)] + [이벤트명] + [시장에서 확인할 핵심 포인트]를 간결히 안내한다.
     • 시장 예상치(forecast) 숫자는 본문에 나열하지 않는다 (하단 Daily Event 표에서만 제공).
   - **[이슈 리뷰와의 역할 분리]**:
     • 이슈 리뷰: 개별 이벤트를 단순 반복하지 않고, 여러 이벤트가 증시·외환·채권·원자재 4대 자산시장에 어떻게 연결되고 파급되었는지를 심층 분석.
     • Daily Event: 당일 주요 발표의 결과와 의미를 빠르게 복기하고 이후 예정된 일정을 안내.

--------------------------------------------------
[3. 금지사항 (Negative Constraints)]
--------------------------------------------------
- **존댓말(`~습니다`, `~입니다`, `~했습니다` 등) 일체 사용 금지**
- 단순 수치 나열형 문장 반복 금지
- 컨텍스트에 없는 과거 지표나 미존재 이벤트 언급 금지
- 시각 표기 시 `KST` 영문 접미사 붙이기 금지 (`21:30`, `04:00` 표기)
- 각 섹션의 `source_news_ids`, `source_market_fields`, `source_event_ids` 필드에 실제 인용한 ID를 정확히 매핑하라.
"""

    @classmethod
    def get_system_prompt(cls) -> str:
        return cls.SYSTEM_PROMPT

    @classmethod
    def build_user_prompt(cls, context: Dict[str, Any]) -> str:
        context_str = json.dumps(context, ensure_ascii=False, indent=2)
        user_prompt = f"""아래의 [Context JSON] 데이터를 정밀 분석하여 일일 FICC Daily Macro 리포트를 작성하라.
[Gemini Daily Macro Writing Instruction — FICC Research Note Style]을 엄격히 준수하라.
- **반드시 존댓말(~습니다, ~입니다 등)을 배제하고 연구노트형 평서체(~함, ~임, ~나타남, ~전망 등)로 작성하라.**
- 과도한 단정적 심리 해석과 단순 수치 나열을 배제하고 객관적 사실과 메커니즘을 서술하라.
- `daily_event_watchpoints`는 **[당일 주요 발표 리뷰(day_review 중 핵심)] ➡️ [실행 시각 이후 주목할 이벤트(today_night)]** 구조로 작성하라.

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
