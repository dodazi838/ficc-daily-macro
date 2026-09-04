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
[2. 본문 숫자 사용의 엄격한 절제 원칙 (Selective & Restrained Number Usage)]
--------------------------------------------------
- **표는 정량 정보 중심, 본문은 원인·시장 반응·경제적 의미 중심이다.**
- **표에 이미 제시된 숫자를 본문에서 기계적으로 반복 나열하지 않는다.**
- 각 문단에서 모든 자산의 등락률/수치를 괄호나 콤마로 기계적으로 나열하는 작문을 엄격히 금지한다.
  • [지수 등락률 나열 금지]:
    - (나쁜 예): "다우존스(+0.66%), 나스닥(+0.66%), S&P 500(+0.41%) 3대 지수가 일제히 상승세를 기록함." (X)
    - (좋은 예): "미국 증시는 국채 금리 하락과 기술주 관련 재료가 맞물리며 주요 지수가 상승 흐름을 나타냄." (O)
  • [환율 등락률 나열 금지]:
    - (나쁜 예): "달러 인덱스는 99.02pt로 전일 대비 0.55% 하락하고, 달러/엔 환율은 155.71엔(-2.80%), 원/달러는 1358.22원(-1.07%)..." (X)
    - (좋은 예): "달러화는 전반적으로 약세를 나타냈으며, 특히 달러/엔 환율이 155엔대로 급락하며 엔화 강세가 두드러짐." (O)
  • [채권/원자재 수치 나열 금지]: 모든 만기 금리나 원자재 가격을 하나하나 쓰지 말고, 대표 흐름과 원인을 설명한다.

- **숫자를 사용할 가치가 높은 경우 (이 경우에만 선택적 인용)**:
  1. 시장 움직임이 이례적으로 큰 경우 (예: 엔화 2.8% 급등 등)
  2. 특정 가격/금리 레벨이 중요한 경우 (예: 155엔대, 10년물 금리 4.7%대 등)
  3. 경제지표의 실제치와 예상치/기준선(50선 등)을 비교할 때
  4. 스프레드 등 분석의 핵심 지표를 설명할 때 (예: 10Y-2Y 스프레드 42.0bp)
  5. 특정 자산의 움직임이 전체 시장 흐름을 설명하는 핵심 근거일 때
- 단, 숫자를 맹목적으로 없애는 것이 아니라, '분석에 꼭 필요한 핵심 숫자만 선별하여 문장의 완성도를 높이는 것'이 목적이다.

--------------------------------------------------
[3. 섹션별 작성 지침 (반드시 연구노트형 평서체 작성)]
--------------------------------------------------
1. **ficc_daily_summary (3줄 불릿 요약)**:
   - 오늘 시장의 핵심 관측 사실과 확인된 주요 원인을 3개의 불릿으로 압축 (명사형/평서체 종결).
   - "핵심 변수 + 실제 관측된 시장 반응" 중심 (단순 등락률 나열 배제).
2. **ficc_summary (종합 리서치 요약, 1문단 약 300~350자)**:
   - [핵심 사건/발언] → [물가/정책에 미친 직접적 영향] → [금리·외환·자산시장 파급 반응] → [종합 정리] 순서로 하나의 완성된 맥락으로 연결 (평서체 서술, 대표 수치 1~2개만 선별).
3. **issue_review (4대 자산군별 심층 리뷰, 각 1문단 약 200~250자)**:
   - `stock`: 증시 등락 요인, 대형주/업종별 흐름, 금리 변동 영향을 확인된 사실 위주로 설명 (지수별 등락률 나열 금지).
   - `fx`: 달러화 방향성 배경(금리차, 통화별 차별화, 정책 기대 등)을 데이터 기반으로 서술.
   - `bond`: 국채 금리 움직임 배경(통화정책 발언, 지표 발표, 수급 등)을 객관적으로 서술. 스프레드 수치는 사실 그대로 명시.
   - `commodity`: 유가 공급 요인, 실질금리/달러 변동에 따른 금 가격 반응 등을 확인된 변수 중심으로 설명.
4. **ficc_forecast (전망, 1문단 약 150~200자)**:
   - 미래를 단정적으로 예단하지 말고, "향후 예정된 지표 및 이벤트에 따라 ~할 가능성이 있음", "변동성이 확대될 수 있음" 등 조건부 시나리오로 서술.
5. **daily_event_watchpoints (Daily Event 본문, 1문단 약 250~350자)**:
   - Daily Event 섹션에는 하단에 2개의 독립된 표([당일 주요 발표 표(실제/예상/전월치)] 및 [향후 주요 발표 표(예상치)])가 함께 제공된다.
   - 본문 구조는 **[당일 주요 발표 리뷰] ➡️ [향후 주요 발표 일정]** 2단계로 전개한다.
   - **A. 당일 주요 발표 리뷰 (무슨 결과가 나왔고 왜 중요한가 중심 복기)**:
     • 단순 지표 나열이나 "~지표가 발표됨", "~발표가 소화됨", "~경기 확장세가 점검됨"과 같은 피상적 서술을 엄격히 금지한다.
     • 프로그램 실행 시각 이전에 이미 발표된 당일 핵심 이벤트 중 시장 영향력이 큰 지표(미국 고용, 물가 CPI/PPI/PCE, ISM, GDP, 소매판매, 중앙은행 금리결정 및 주요 인사 발언 등 2~4개)를 선별하여 서술한다.
     • 반드시 **"무슨 결과가 나왔는가"**가 명확히 드러나야 하며, 가능한 경우 반드시 다음 순서로 설명한다:
       **[지표/이벤트명] ➡️ [실제 발표 결과 또는 확인된 수준] ➡️ [시장 예상치 또는 전월치 대비 비교] ➡️ [경제적 의미 / 시장에 중요한 이유]**
     • **[수치 활용 및 정합성 원칙]**:
       - 경제지표의 실제치(actual), 시장 예상치(forecast), 전월치(prior)처럼 이벤트 자체를 이해하는 데 필요한 숫자는 적극적으로 활용한다.
       - 실제치와 예상치가 SSOT에 모두 존재하면 실제치와 예상치의 상회/하회 여부(`실제치 > 예상치` 또는 `실제치 < 예상치`) 및 전월 대비 변화를 명확히 표현한다.
       - 실제치나 예상치가 SSOT에 부재한 경우에는 절대 임의로 숫자를 날조/추정하지 말고, 확인 가능한 전월치나 기준선(50선 등) 수준과 의미만 설명한다.
       - **[actual 부재 시 절대 날조 금지 (Critical)]**: SSOT에 경제지표의 actual이 null인 경우(예: 비농업 고용, 실업률 등), 절대 가상의 발표 결과 수치(예: "16만 건", "162K", "4.2%" 등)를 생성하거나 지어내지 마라. 오직 SSOT에 존재하는 forecast(예상치)나 prior(전월치) 수치만 인용하거나 발표 대기/관망 흐름으로만 서술하라. 가상의 수치 생성 시 즉시 팩트 검증에서 적발되어 차단된다.
     • **[주요 이벤트별 구체적 서술 기준]**:
       - **신규 실업수당 청구건수**: 실제치/예상치/전월치 비교 및 노동시장 둔화/안정성 판단 재료로서의 의미 명시.
       - **미국 ISM 서비스업 PMI**: 지수 수준의 50선 상회 흐름과 전월/예상 대비 변화를 통해 서비스업 경기 확장 모멘텀 및 경기 연착륙 평가 명시.
       - **중앙은행 정책/발언 (FOMC 월러 이사 등)**: 확인된 금리 경로 발언 및 통화정책 기조가 채권·달러화에 미친 영향 서술.
   - **B. 향후 주요 발표 일정 (실행 시각 이후 익일 06:00 KST까지의 핵심 일정 안내)**:
     • `economic_calendar.today_night`에 등록된 실행 시각 이후 예정된 핵심 지표(3~6개)의 [발표 시각(HH:MM)] + [이벤트명] + [시장에서 확인할 핵심 포인트]를 간결히 안내한다.
     • `economic_calendar.today_night`가 비어있는 경우("[]"), 향후 발표 예정 지표를 임의로 지어내지 말고 "금일 실행 시각 이후 주요 발표 예정 지표는 부재함"으로 간결히 마무리하라.
     • 이미 발표된 과거 지표는 향후 주요 발표 일정에 절대 포함하지 않는다.
     • 예정 지표의 시장 예상치(forecast) 숫자는 하단 향후 주요 발표 표에서 제공하므로 본문에서 중복 나열하지 않는다.
   - **[이슈 리뷰와의 명확한 역할 분리]**:
     • Daily Event: 개별 이벤트의 실제 발표 결과와 경제적 의미, 관전 포인트에 집중.
     • Issue Review: 개별 지표의 단순 반복을 피하고, 여러 이벤트가 증시·외환·채권·원자재 4대 자산시장에 걸쳐 어떻게 종합적으로 연결·파급되었는지를 심층 분석.

--------------------------------------------------
[4. 금지사항 (Negative Constraints)]
--------------------------------------------------
- **존댓말(`~습니다`, `~입니다`, `~했습니다` 등) 일체 사용 금지**
- **모든 자산의 수치/등락률을 본문에서 기계적으로 나열하는 작문 금지**
- 컨텍스트에 없는 과거 지표나 미존재 이벤트 언급 금지
- 시각 표기 시 `KST` 영문 접미사나 `XX시 XX분` 대신 `HH:MM`(예: `21:30`, `04:00`) 표준 표기를 사용하라.
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
- **표에 이미 제시된 숫자를 본문에서 기계적으로 반복 나열하지 말고, 원인과 메커니즘 위주로 서술하라.**
- `daily_event_watchpoints`는 **[당일 주요 발표 리뷰(day_review 중 핵심 2~4개)] ➡️ [향후 주요 발표 일정(today_night 중 3~6개)]** 구조로 작성하라.

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
                            "description": "Daily Event 본문 (1문단, [당일 주요 발표 리뷰(day_review 중 핵심 2~4개)] ➡️ [향후 주요 발표 일정(today_night 중 3~6개)] 구조로 작성, 실제치/예상치/전월치 비교 및 관전 포인트 서술)"
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
