# 📊 FICC Daily Macro 자동화 프로그램

한국 FICC (Fixed Income, Currencies, Commodities) 스터디용 일일 매크로 시황 자동 생성기입니다.

---

## 🗺️ 전체 개발 로드맵 (5단계)

| 단계 | 목표 | 세부 내용 | 상태 |
| :--- | :--- | :--- | :---: |
| **1단계** | **시장 핵심 데이터 수집 & 정합성 검증** | 4대 자산 28개 지표 데이터 수집, 동적 거래일 해결, %, bp 변동폭 및 스프레드 계산 | **✅ 완료 (100% 정상 수집 검증)** |
| **2단계** | **데이터 수집 모듈화 & 일자별 영구 저장** | 수집기 모듈화 (`collectors/`), 설정 분리 (`config/`), 스프레드 산출 (`processors/`), 일자별 JSON 자동 저장 (`data/`) | **✅ 완료 (`python main.py`)** |
| **3단계** | **공식 RSS/API 기반 매크로 뉴스 및 경제 이벤트 수집** | Fed/ECB/MarketWatch/Yahoo 공식 뉴스 수집, 대표기사+연계기사 클러스터링, 다차원 중요도 판정, ForexFactory 3-Way 타임 윈도우 캘린더 분기 | **✅ 완료** |
| **4단계** | **AI 기반 시황 리포트 작성 & 팩트 검증** | Gemini Structured Output(JSON Schema) 연동, `DailyFicc_26.03.07.pdf` 스타일 내재화, 다차원 팩트체커 및 결정론적 Confidence 산출 | **✅ 모듈 구현 완료 (API Key 연동 대기)** |
| **5단계** | **네이버 블로그 포맷 생성 & 스케줄러** | 복사-붙여넣기 전용 블로그 템플릿(HTML/표) 생성 및 16:30 자동 실행 등록 | 다음 단계 |

---

## 🏗️ 프로젝트 아키텍처 (4단계 완료 기준)

```
ficc-daily-macro/
├── config/
│   └── settings.py              # 28개 지표 메타데이터 및 기준 시간(16:30 KST) 설정
├── collectors/
│   ├── base.py                  # BaseCollector 추상 클래스
│   ├── equity.py                # 글로벌 증시 10개 지표 수집기
│   ├── fx.py                    # 글로벌 외환 6개 지표 수집기
│   ├── bond.py                  # 국고채(KOFIA) + 글로벌 벤치마크(CNBC) 채권 수집기
│   ├── commodity.py             # 주요 원자재 6개 지표 수집기
│   ├── news_fetcher.py          # Fed / ECB / MarketWatch / Yahoo 공식 RSS & API 뉴스 수집기
│   └── economic_calendar.py     # ForexFactory CSV/XML & BOK ECOS 어댑터 경제 캘린더 수집기
├── processors/
│   ├── calculator.py            # FICC 핵심 스프레드(한미/독미, 장단기 10Y-2Y/3Y) 산출
│   ├── news_processor.py        # URL 정규화, 헤드라인 유사도 클러스터링, 다차원 중요도 판정
│   ├── event_processor.py       # 16:30 KST 기준 3-Way 타임 윈도우 (DAY_REVIEW/TODAY_NIGHT/UPCOMING_WEEK) 분기
│   └── fact_validator.py        # 숫자, 단위, 부호, 자산 다차원 팩트체커 & 결정론적 Confidence 산출
├── generators/
│   ├── llm_adapter.py           # Gemini Structured Output 및 OpenAI 교체형 어댑터
│   ├── context_builder.py       # 레퍼런스 PDF 순서 정렬 및 LOW 노이즈 배제 컨텍스트 빌더
│   ├── prompt_manager.py        # KUFRI Daily Macro 스타일 프롬프트 및 JSON 스키마
│   └── report_generator.py      # 리포트 생성 총괄 관리자 및 토큰/비용 로거
├── storage/
│   └── saver.py                 # 일자별 독립 스냅샷(market, news, calendar) 및 최종 가공본 영구 저장
├── data/
│   ├── raw/                     # 일자별 원천 스냅샷 (*_market.json, *_news.json, *_calendar.json)
│   └── processed/               # 가공 통합본 (YYYY-MM-DD.json) 및 AI 리포트 (report_YYYY-MM-DD.json)
├── reference/
│   └── DailyFicc_26.03.07.pdf   # KUFRI Daily Macro 공식 레퍼런스 템플릿 PDF
├── .env.example                 # 환경변수 설정 템플릿
├── main.py                      # 전체 파이프라인 단일 실행 엔트리포인트
└── requirements.txt
```

---

## 🔑 환경변수 설정 (.env)

프로젝트 루트 디렉토리에 `.env` 파일을 생성하고 아래와 같이 설정합니다:

```bash
# 1. LLM Provider 및 모델 설정
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.5-flash

# 2. Gemini API Key 설정
GEMINI_API_KEY=AIzaSy...
```

---

## 🚀 파이프라인 실행 방법

```powershell
# 프로젝트 디렉토리 이동
cd C:\Users\duddn\.gemini\antigravity-ide\scratch\ficc-daily-macro

# 전체 파이프라인 실행 (시장 데이터 + 뉴스 + 캘린더 + AI 리포트 생성)
python main.py
```
