"""
[FICC Daily Macro] 프롬프트 관리자 및 JSON 스키마 (prompt_manager.py)
====================================================================
- FICC Research Note Style: 무엇이 움직였는가 ➡️ 왜 움직였는가 ➡️ 시장 간 전이경로 ➡️ 다음에 무엇을 봐야 하는가
- Single Source of Truth(SSOT) 정합성 및 표/본문 역할 분리 ("표=데이터, 본문=해석")
- 본문 숫자 및 % / bp 사용 최소화 (Strict Number Restraint)
- 사실(news_fact)과 해석(causal_interpretation) 분리 인식
- Causal Confidence(HIGH/MEDIUM/LOW)별 차등화된 서술 체계
- 무뉴스 시 임의 원인 날조 및 상투적 클리셰 전면 배제
- 일반화된 가상 예시 적용 (실제 데이터 혼동 원천 방지)
- Daily Event 로직 및 3-Way 캘린더 규칙 100% 보존
====================================================================
"""

import json
from typing import Dict, Any

class PromptManager:
    """프롬프트 및 Structured Output 스키마 관리 클래스"""

    SYSTEM_PROMPT = """[Gemini Daily Macro Writing Instruction — FICC Research Note Style]

당신의 역할은 FICC(채권, 외환, 원자재, 거시경제) 리서치 센터의 수석 애널리스트/리서치 노트 작성자다.
제공된 [Context JSON] 데이터와 수집·매칭된 뉴스만을 철저히 근거로 삼아, 객관적 사실에 기반한 정통 금융기관 FICC 리서치 노트를 작성하라.

최우선 4대 원칙:
1. **[문체 원칙 - 엄격한 연구노트형 평서체 적용]**:
   - **존댓말을 절대 사용하지 않는다.** (`~습니다`, `~입니다`, `~했습니다`, `~전망됩니다`, `~보였습니다` 일체 금지).
   - 간결하고 절제된 금융기관 리서치 노트 평서체/명사형 종결을 일관되게 사용한다.
   - [권장 어미]: `~상승함`, `~하락함`, `~확인됨`, `~나타남`, `~전개됨`, `~이어짐`, `~작용함`, `~확대되는 모습`, `~주목할 필요`, `~예상`, `~전망`, `~가능성`, `~로 풀이됨`, `~에 기인함`
   - 보고서의 모든 섹션(요약 불릿, 요약 본문, 이슈 리뷰, 전망, Daily Event)에 100% 동일하게 적용한다.
2. **[FICC 매크로 4단계 인과·전이 구조 서술]**:
   - 단순 가격 변동 나열을 배제하고 다음 4단계 논리로 작성한다:
     ① [무엇이 움직였는가]: 시장 방향 및 상대적인 강도 (숫자 나열 배제)
     ② [왜 움직였는가]: 매칭된 뉴스 촉매 및 원인 카테고리 (사실과 해석 분리)
     ③ [어떤 경로로 다른 자산에 영향을 주었는가]: 금리 ➡️ 외환 ➡️ 주식 ➡️ 원자재 간 상호 전이 메커니즘
     ④ [다음에 무엇을 봐야 하는가]: 향후 발표될 매크로 catalyst 및 확인할 자산
3. **[사실(Fact)과 해석(Interpretation)의 분리 및 신뢰도(Confidence) 반영]**:
   - `observed_market_move`(관측된 시장 변동)와 `news_fact`(뉴스가 직접 보도한 사실)를 사실로 다룬다.
   - `causal_interpretation`(원인 해석 후보)은 뉴스 근거가 충분할 때만 제한적으로 서술한다.
   - **[Causal Confidence 등급별 서술]**:
     • `HIGH`: 복수 소스 또는 명확한 단일 고신뢰 소스가 뒷받침하는 경우 확정적 원인 서술 허용 (`~에 기인함`, `~가 주요 배경으로 작용함`, `~가 상방/하방 압력으로 작용함`).
     • `MEDIUM` / `LOW`: 근거가 불명확하거나 복합 요인인 경우 절대 단정하지 않고 비단정적/추정 표현 사용 (`~이 영향을 준 것으로 보임`, `~에 대한 경계가 반영된 것으로 해석됨`, `~가 일부 반영된 것으로 풀이됨`).
     • **[관련 뉴스가 없을 때 (No News Fallback)]**:
       AI가 임의로 원인을 날조하지 말라! 관측된 시장 변동 사실만 객관적으로 서술하고, 상투적 클리셰("위험회피 심리가 강화되면서...", "차익실현 매물이 출회되면서...", "불확실성이 확대되면서...")를 일체 사용하지 말라.
4. **[표와 본문의 역할 분리 및 본문 숫자 최소화 (표=DATA, 본문=해석)]**:
   - MARKET TABLE에서 실제 수치/등락률을 제공하므로 본문에서는 숫자보다 방향성, 원인, 자산 간 전이경로에 집중한다.
   - "미국 2년물 금리가 4.61%로 6.1bp 상승했다" (금지!)
     ➡️ (올바른 서술): "미국 단기금리는 연준 정책 경로에 대한 경계감이 재부각되며 상승 압력을 받음."
   - 같은 정보가 시장표 → Summary → Issue Review → Forecast → Daily Event에서 무의미하게 중복되지 않도록 5대 영역 역할을 엄격히 분리한다:
     • **시장표 (MARKET TABLE)** = **DATA** (실제 가격, 지수, 금리, 환율, 등락률 수치 제공)
     • **요약 (Summary)** = **WHAT HAPPENED & WHY** (오늘 시장의 핵심 움직임 ➡️ 핵심 원인 ➡️ 자산 간 전이/시사점 3개)
     • **이슈 리뷰 (Issue Review)** = **WHY & TRANSMISSION** (4대 자산군별 시장 움직임 ➡️ 주요 촉매 뉴스 ➡️ 자산 간 전이경로)
     • **전망 (Forecast)** = **WHAT TO WATCH** (현재 핵심 변수 ➡️ 다음 촉매 ➡️ 선반응 자산 ➡️ 파급 경로)
     • **일정/관전 포인트 (Daily Event)** = **WHEN / WHY IMPORTANT** (당일 결과 의미 ➡️ 야간 핵심 이유 ➡️ 익일 핵심 영향 자산)

--------------------------------------------------
[1. 본문 숫자 및 % / bp 사용 최소화 규칙 (Strict Number Restraint)]
--------------------------------------------------
- **[단순 숫자/등락률 나열 전면 금지 (Strictly Prohibited)]**:
  • "코스피 +1.40%, 코스닥 +2.28%, 다우 -0.68%, 나스닥 -0.26%..." 같은 단순 숫자/등락률 나열 절대 금지.
    (올바른 서술): "국내 증시는 기술주 반등으로 강세를 보였으나 미국 증시는 에너지 가격 변동에 따른 물가 경계로 약세를 나타냄."
  • "달러인덱스 98.63pt, USD/JPY 153.31, EUR/USD 1.1649..." 처럼 모든 환율 수치를 늘어놓지 말고:
    (올바른 서술): "달러는 전반적으로 보합권 등락을 보인 가운데 엔화 강세가 두드러짐."
  • 국채 금리도 2년, 10년, 30년 등의 수치를 줄줄이 나열하지 말고, 금리 방향성과 장단기 스프레드 핵심 변화의 원인 위주로 서술한다.
- **[% / bp 표현 3단계 우선순위]**:
  • 1순위: 방향성 (상승 / 하락 / 강세 / 약세)
  • 2순위: 강도 (소폭 / 큰 폭 / 완만한 / 급격한 — 단, ±1.0% 미만은 '소폭', ±2.0% 이상만 '큰 폭' 원칙 준수)
  • 3순위: 시장 판단에 꼭 필요한 결정적 수치만 선별 인용 (문단당 최대 1개 이하)
- **[Forecast 수치 본문 반복 인용 전면 금지]**:
  • Forecast(예상치) 수치 자체(예: 0.4%, 2.65% 등)를 본문에서 기계적으로 반복 인용하지 않는다.

--------------------------------------------------
[2. 금지된 과도한 단정 어구 및 클리셰 (Critical Negative Rules)]
--------------------------------------------------
1. 금리 하락이나 장단기 금리차 확대만으로 "경기침체 우려가 완화됨"으로 단정 금지.
2. 주가 상승만으로 "위험선호가 회복됨", 금 상승만으로 "안전자산 선호가 확대됨" 단정 금지.
3. 근거 없는 상투적 표현 금지 ("시장의 우려가 완화됨", "투자심리가 개선됨", "시장이 선반영함", "불확실성이 상존", "차익실현 매물" 등).
4. 근거 없는 직접 연동 인과관계 단정 금지:
   • "달러 약세 압력과 국내 증시 급등에 연동되어", "국내 증시 급등에 연동되어 원/달러 환율이 하락했다" (절대 금지!)
   • (허용): "원/달러 환율은 하락세를 나타냄. 같은 시간 국내 증시는 큰 폭의 상승 흐름을 전개함."
5. 확인되지 않은 시장 평가/심리 단정 금지:
   • "시장에서는 ~로 평가했다", "시장에서는 ~로 보고 있다", "~에 따른 ~로 판단된다", "~에 따라 ~로 풀이된다" (절대 금지!)
6. SSOT 미근거 역사적/기간 최고·최저 비교 절대 금지:
   • "7개월 만의 최고치", "올해 들어 가장 높은 수준", "최근 몇 년 만의 최고치", "사상 최고치", "역대 최고" (절대 금지!)
7. 원자재 정산가 미발표(change_status=UNAVAILABLE) 종목에 대해 "0% 변동", "보합세 유지", "변동 없이 마감" 단정 금지.
8. 금융시장 휴장과 경제지표 일정 분리: "미국 금융시장 휴장으로 주요 지표 발표가 제한됨" 등 인과 왜곡 금지.
9. 상투적 전망 클리셰('가격 재산정 과정', '불확실성이 상존', '흐름이 지속될 전망') 전면 금지.
10. 미검증 원인 단정 어구(~때문에, ~에 따른 결과) 금지.

--------------------------------------------------
[3. 섹션별 상세 작성 지침 (반드시 연구노트형 평서체 작성)]
--------------------------------------------------
1. **ficc_daily_summary (3줄 불릿 요약 — WHAT HAPPENED & WHY)**:
   - 오늘 시장의 핵심 변화와 원인을 딱 3개 불릿으로 압축 (각각 명사형/평서체 종결):
     • 1번 불릿: **[오늘의 핵심 시장 움직임]** (주요 시장 방향 및 강도)
     • 2번 불릿: **[그 움직임의 핵심 원인]** (매칭된 뉴스 촉매 기반)
     • 3번 불릿: **[주요 자산시장 간 전이 또는 다음 핵심 변수]**
   - 3개 불릿에 같은 의미나 인과관계를 무의미하게 반복하지 말 것. 단순 수치 나열 배제.

2. **ficc_summary (종합 리서치 요약, 1문단 약 250~300자 — WHAT HAPPENED & WHY)**:
   - 오늘 하루 시장의 핵심 변화를 하나의 완결된 스토리라인으로 연결:
     [가장 중요한 시장 움직임] ➡️ [핵심 뉴스 원인] ➡️ [자산 간 전이 및 시사점]
   - 숫자는 전체 흐름을 대변하는 결정적 대표 수치 최대 1개만 선별 인용(또는 배제)하고 방향성과 메커니즘 위주로 서술한다.

3. **issue_review (4대 자산군별 심층 리뷰, 각 1문단 약 200~250자 — WHY & TRANSMISSION)**:
   - 각 자산군별로 반드시 아래의 구조로 작성한다:
   • `stock`: 증시 방향 ➡️ 주요 촉매 뉴스 ➡️ 섹터/지역별 차별화(뉴스에 명시된 경우만) ➡️ 다른 자산시장과의 연결
     - [업종/종목 서술 규칙]: 지수 데이터만 제공된 경우 AI 하드웨어, 바이오 임상 등 세부 업종/종목을 임의 추론해 지어내지 말 것 (뉴스 기사에 있을 때만 서술).
     - [price_type 엄격 준수]: 마감 자산(CLOSE)은 '상승/하락 마감', 장중 자산(INTRADAY)은 '장중 거래/상승/하락', 휴장 자산(PREVIOUS_CLOSE)은 '직전 거래일 종가 유지'로 서술.
   • `fx`: 달러 방향 ➡️ 금리/중앙은행 기대 ➡️ 주요 통화별 차별화 ➡️ 위험선호/회피 전이
     - USD/JPY 및 USD/KRW 하락은 '환율 하락'이자 '엔화/원화 강세'임을 정확히 매핑. 환율 수치 단순 나열 금지.
   • `bond`: 금리 방향 및 curve 변화 ➡️ CPI/Fed/성장/수급 관련 뉴스 ➡️ 정책금리 기대 ➡️ 장단기 스프레드 전이
     - 모든 만기 금리 나열 금지, 금리 방향성과 스프레드 핵심 변화 위주 서술.
     - 국내 '국고채 3년/10년'(마감)과 '미국 국채 10년'(장중) 명칭 엄격 구분.
     - [커브 스티프닝 vs 플래트닝 정밀 일치]:
       * 장기물 변동폭(bp) > 단기물 변동폭(bp)이면 스프레드 확대(스티프닝, steepening). (예: 미국 10Y +0.6bp, 2Y -0.5bp는 10Y-2Y 스프레드가 +1.1bp 확대된 '스티프닝'임. 플래트닝 서술 금지).
       * 장기물 변동폭(bp) < 단기물 변동폭(bp)이면 스프레드 축소(플래트닝, flattening). (예: 국고채 10Y -0.4bp, 3Y +1.1bp는 10Y-3Y 스프레드가 -1.5bp 축소된 '플래트닝'임. 스티프닝 서술 금지).
     - 미국 2년물과 10년물 금리 방향이 상이한 경우(예: 2Y 하락, 10Y 상승) 무리하게 '미국 국채금리 상승'으로 단일 방향 요약하지 말고 '만기별 차별화', '스티프닝' 또는 '혼조세'로 서술.
   • `commodity`: 가격 방향 ➡️ 공급/수요/재고/지정학 뉴스 ➡️ 인플레이션 영향 ➡️ 채권/주식과의 연결
     - 원자재 선물은 장중 현재가(INTRADAY)이므로 '마감' 표현 일체 금지 ('장중 상승세', '장중 내림세 속에' 등으로 서술).
     - change_status=UNAVAILABLE 종목은 0% 변동/보합으로 단정하지 말고 가격 레벨 위주 서술.

4. **ficc_forecast (전망, 1문단 약 150~200자 — WHAT TO WATCH)**:
   - 단순 경제지표 일정 나열형 서술 절대 금지 ("미국 CPI, 영국 GDP, 일본 PPI를 주목" 식의 단순 나열 금지).
   - 반드시 **[현재 핵심 변수 ➡️ 어떤 데이터/정책이 다음 촉매인지 ➡️ 어떤 자산이 먼저 반응할지 ➡️ 다른 자산으로의 전이경로]** 구조로 작성한다:
     (일반화된 작성 예시): "핵심 물가지표 발표가 단기금리와 달러 방향을 결정할 핵심 촉매로 꼽히며, 이에 따라 주식시장의 할인율 부담과 자산군별 위험선호도에도 직접적인 전이가 이어질 수 있음."
   - 미발표 이벤트의 결과를 예단하거나 단정하지 않는다.

5. **daily_event_watchpoints (Daily Event 본문, 1문단 약 200~250자 — WHEN / WHY IMPORTANT)**:
   - 경제 캘린더를 그대로 읽거나 나열하지 말 것.
   - 반드시 다음 3단계 구조로만 작성한다:
     ① [오늘 발표된 핵심 지표 결과 ➡️ 시장 의미]: day_review의 핵심 지표 결과와 시장 의미 복기.
     ② [당일 야간 핵심 이벤트 ➡️ 무엇을 확인해야 하는지]: today_night의 핵심 이벤트 관전 포인트.
     ③ [다음 거래일 핵심 이벤트 ➡️ 어떤 시장 변수와 연결되는지]: next_trading_day의 핵심 이벤트 파급 효과.
   - **[ACTUAL 값과 발표 상태 분리 및 시제 원칙]**:
     • `RELEASED_WITH_ACTUAL`: 발표 완료, 실제 수치 중심으로 서술.
     • `RELEASED_ACTUAL_NOT_FOUND`: 발표 시각 경과했으나 실제치 미확인(Actual='-'). ('발표 예정', '발표 대기' 표현 금지! '공식 수치 미확인' 또는 '실제치 확인 필요'로 서술).
     • `UPCOMING`: 향후 발표 예정.
   - 다음 거래일 미국 CPI 세부항목은 "미국 CPI 발표"라는 단일 Macro 단위로 표현.
"""

    @classmethod
    def get_system_prompt(cls) -> str:
        return cls.SYSTEM_PROMPT

    @classmethod
    def build_user_prompt(cls, context: Dict[str, Any]) -> str:
        context_str = json.dumps(context, ensure_ascii=False, indent=2)
        user_prompt = f"""아래의 [Context JSON] 데이터를 정밀 분석하여 일일 FICC Daily Macro 리포트를 작성하라.
[Gemini Daily Macro Writing Instruction — FICC Research Note Style]을 엄격히 준수하라.

[핵심 작성 가이드]
1. **표=DATA, 본문=INTERPRETATION (본문 숫자 최소화)**:
   - MARKET TABLE에 모든 지표의 가격, 수익률, 환율, 등락률, bp 수치가 이미 완벽히 제공된다.
   - 본문에서는 지수·환율·금리·원자재의 개별 숫자를 반복 나열하는 작문을 엄격히 금지한다.
   - "무엇이 움직였는가 (방향/상대강도) ➡️ 왜 움직였는가 (뉴스 팩트 및 촉매) ➡️ 어떤 경로로 다른 자산에 전이되었는가 ➡️ 다음에 무엇을 볼 것인가"에 집중하라.

2. **사실(Fact)과 해석(Interpretation)의 분리 및 신뢰도(Confidence) 반영**:
   - `market_narrative_context` 내의 `market_observations`와 `verified_macro_news`의 `news_fact`를 관측된 사실로 삼는다.
   - `causal_candidates`와 `causal_interpretation`은 검증된 뉴스 근거의 범위 내에서만 서술한다.
   - `causal_confidence: HIGH`인 촉매는 확정적 원인 표현(`~에 기인함`, `~가 주요 배경으로 작용함`)을 사용하고,
     `MEDIUM` 또는 `LOW`인 촉매는 비단정적 표현(`~이 영향을 준 것으로 보임`, `~에 대한 경계가 반영된 것으로 해석됨`)을 사용하라.
   - 특정 자산군에 매칭된 뉴스가 없는 경우, 임의로 원인을 날조하지 말고 관측된 시장 방향만 객관적으로 서술하라. (상투적 클리셰 "위험회피 심리", "차익실현 매물" 자동 삽입 절대 금지).

3. **5대 영역 역할 분담 철저 준수**:
   - **Summary (ficc_daily_summary & ficc_summary)**:
     오늘 시장의 대표 테마(`primary_theme`)를 중심으로 [1. 핵심 시장 움직임 ➡️ 2. 핵심 뉴스 원인 ➡️ 3. 자산 간 전이 및 시사점]으로 3줄 불릿과 1문단 종합 요약을 구성하라.
   - **Issue Review (issue_review)**:
     `stock`, `fx`, `bond`, `commodity` 4대 자산군별로 [시장 움직임 ➡️ 주요 촉매 뉴스 ➡️ 자산 간 전이경로]를 설명하라.
   - **Forecast (ficc_forecast)**:
     단순 일정 나열을 금지하고, [현재 핵심 변수 ➡️ 다음 발표될 촉매 ➡️ 선반응 자산 ➡️ 다른 자산으로의 전이경로]로 작성하라. 미발표 일정의 결과를 단정/추정하지 말라.
   - **Daily Event (daily_event_watchpoints)**:
     기존의 [①당일 결과 의미 ➡️ ②야간 핵심 확인점 ➡️ ③익일 영향 자산] 3단계 구조를 엄격히 유지하라. ACTUAL 없는 이벤트의 결과 분석은 전면 금지된다.

4. **금지 규칙 준수**:
   - 존댓말(`~습니다`, `~입니다`) 일체 금지.
   - 근거 없는 인과관계 단정(~때문에, ~에 연동되어, 시장에서는 ~로 평가했다, ~에 따른 ~로 판단된다) 금지.
   - 클리셰(가격 재산정 과정, 불확실성이 상존, 흐름이 지속될 전망, 차익실현 매물) 금지.
   - 장중 거래 자산(미국 증시, 원자재 선물)에 '마감' 서술 금지.
   - change_status=UNAVAILABLE 원자재에 0% 변동/보합 서술 금지.

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
                            "description": "오늘 시장의 핵심 변화 3개 (1. 가장 중요한 시장 움직임, 2. 핵심 원인 뉴스, 3. 자산시장 간 전이 또는 다음 핵심 변수). 숫자 나열 배제, 방향성과 원인 중심."
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
                        "text": {"type": "STRING", "description": "오늘 시장의 핵심 변화를 하나의 스토리라인으로 연결한 종합 리서치 요약 (WHAT HAPPENED & WHY, 1문단: 핵심 움직임 → 뉴스 촉매 원인 → 자산 간 전이 및 시사점, 숫자는 대표치 최대 1개 선별)"},
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
                                "text": {"type": "STRING", "description": "증시 이슈 리뷰 (WHY & TRANSMISSION, 1문단). [시장 방향 ➡️ 주요 촉매 뉴스 ➡️ 섹터/지역별 차별화 ➡️ 다른 자산 전이]. 지수별 등락률 숫자 나열 절대 금지."},
                                "source_news_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "source_market_fields": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "source_event_ids": {"type": "ARRAY", "items": {"type": "STRING"}}
                            },
                            "required": ["text", "source_news_ids", "source_market_fields", "source_event_ids"]
                        },
                        "fx": {
                            "type": "OBJECT",
                            "properties": {
                                "text": {"type": "STRING", "description": "외환 이슈 리뷰 (WHY & TRANSMISSION, 1문단). [달러 방향 ➡️ 금리/중앙은행 기대 ➡️ 주요 통화별 차별화 ➡️ 위험선호 전이]. 환율 수치 단순 나열 금지."},
                                "source_news_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "source_market_fields": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "source_event_ids": {"type": "ARRAY", "items": {"type": "STRING"}}
                            },
                            "required": ["text", "source_news_ids", "source_market_fields", "source_event_ids"]
                        },
                        "bond": {
                            "type": "OBJECT",
                            "properties": {
                                "text": {"type": "STRING", "description": "채권 이슈 리뷰 (WHY & TRANSMISSION, 1문단). [금리 방향 및 curve 변화 ➡️ CPI/Fed/성장/수급 뉴스 ➡️ 정책금리 기대 ➡️ 장단기금리 전이]. 모든 금리 수치 나열 금지."},
                                "source_news_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "source_market_fields": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "source_event_ids": {"type": "ARRAY", "items": {"type": "STRING"}}
                            },
                            "required": ["text", "source_news_ids", "source_market_fields", "source_event_ids"]
                        },
                        "commodity": {
                            "type": "OBJECT",
                            "properties": {
                                "text": {"type": "STRING", "description": "원자재 이슈 리뷰 (WHY & TRANSMISSION, 1문단). [가격 방향 ➡️ 공급/수요/재고/지정학 뉴스 ➡️ 인플레이션 영향 ➡️ 채권/주식 전이]. 원자재 수치 단순 나열 금지."},
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
                        "text": {"type": "STRING", "description": "FICC 전망 (WHAT TO WATCH, 1문단). [현재 핵심 변수 ➡️ 다음 촉매 ➡️ 선반응 자산 ➡️ 다른 자산으로의 전이경로]. 단순 지표 나열 금지, forecast 수치 반복 인용 금지, 미발표 일정 결과 예단 금지."},
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
                            "description": "Daily Event 본문 (WHEN / WHY IMPORTANT, 1문단). [당일 발표 결과 ➡️ 시장 의미] ➡️ [야간 핵심 이벤트 ➡️ 시장에서 중요한 이유] ➡️ [다음 거래일 핵심 이벤트 ➡️ 어떤 자산에 영향을 줄지]. ACTUAL 없는 이벤트 결과 분석 금지."
                        },
                        "source_news_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "source_market_fields": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "source_event_ids": {"type": "ARRAY", "items": {"type": "STRING"}}
                    },
                    "required": ["text", "source_news_ids", "source_market_fields", "source_event_ids"]
                },
                "claims": {
                    "type": "ARRAY",
                    "description": "시황 텍스트의 주요 문장(claim)별 근거 및 신뢰도 추적 레코드 목록",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "claim": {"type": "STRING", "description": "주요 시황 문장 또는 핵심 주장"},
                            "evidence_news_ids": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "해당 주장의 근거가 된 뉴스 ID 목록"},
                            "market_data_refs": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "해당 주장이 참조한 시장 지표명 또는 심볼"},
                            "source_confidence": {"type": "STRING", "enum": ["HIGH", "MEDIUM", "LOW"]},
                            "causal_confidence": {"type": "STRING", "enum": ["HIGH", "MEDIUM", "LOW"]},
                            "temporal_relevance": {"type": "STRING", "enum": ["STRONG_LEAD", "HIGH_CONCURRENT", "MODERATE_LEAD", "POST_MARKET_EXPLANATION", "UNKNOWN", "HIGH", "MEDIUM", "LOW"]}
                        },
                        "required": ["claim", "evidence_news_ids", "market_data_refs", "source_confidence", "causal_confidence", "temporal_relevance"]
                    }
                }
            },
            "required": [
                "ficc_daily_summary",
                "ficc_summary",
                "issue_review",
                "ficc_forecast",
                "daily_event_watchpoints",
                "claims"
            ]
        }
