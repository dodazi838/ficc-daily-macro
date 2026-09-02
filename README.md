# 📊 FICC Daily Macro 자동화 프로그램

한국 FICC (Fixed Income, Currencies, Commodities) 스터디용 일일 매크로 시황 자동 생성기입니다.

---

## 🗺️ 전체 개발 로드맵 (5단계)

| 단계 | 목표 | 세부 내용 | 상태 |
| :--- | :--- | :--- | :---: |
| **1단계** | **시장 핵심 데이터 수집 & 정합성 검증** | 4대 자산 28개 지표 데이터 수집, 동적 거래일 해결, %, bp 변동폭 및 스프레드 계산 | **✅ 완료 (100% 정상 수집 검증)** |
| **2단계** | **데이터 수집 모듈화 & 일자별 영구 저장** | 수집기 모듈화 (`collectors/`), 설정 분리 (`config/`), 스프레드 산출 (`processors/`), 일자별 JSON 자동 저장 (`data/`) | **✅ 완료 (`python main.py`)** |
| **3단계** | **당일 주요 매크로 뉴스 수집** | 네이버 금융/연합인포맥스/외신 등 거시경제 핵심 뉴스 헤드라인 크롤링 및 주요 이벤트 추출 | 다음 단계 |
| **4단계** | **AI 기반 시황 리포트 작성** | LLM(Gemini) 연동하여 Market Summary, Review, Outlook 자동 작성 | 예정 |
| **5단계** | **네이버 블로그 포맷 생성 & 스케줄러** | 복사-붙여넣기 전용 블로그 템플릿(HTML/표) 생성 및 16:30 자동 실행 등록 | 예정 |

---

## 🏗️ 프로젝트 아키텍처 (2단계 완료 기준)

```
ficc-daily-macro/
├── config/
│   └── settings.py          # 28개 지표 메타데이터 및 기준 시간(16:30 KST) 설정
├── collectors/
│   ├── base.py              # BaseCollector 추상 클래스
│   ├── equity.py            # 글로벌 증시 10개 지표 수집기
│   ├── fx.py                # 글로벌 외환 6개 지표 수집기
│   ├── bond.py              # 국고채(KOFIA) + 글로벌 벤치마크(CNBC) 채권 수집기
│   └── commodity.py         # 주요 원자재 6개 지표 수집기
├── processors/
│   └── calculator.py        # FICC 핵심 스프레드(한미/독미, 장단기 10Y-2Y/3Y) 산출
├── storage/
│   └── saver.py             # 일자별 JSON 영구 저장 (data/raw/, data/processed/)
├── data/
│   ├── raw/                 # 일자별 원천 수집 데이터 (YYYY-MM-DD.json)
│   └── processed/           # 가공 및 스프레드 계산 완료 정형 데이터
├── main.py                  # 일일 데이터 수집 및 저장 파이프라인 엔트리포인트
└── requirements.txt
```

---

## 📈 최종 확정 28개 지표 및 4대 스프레드

1. **증시 (10개)**: 코스피, 코스닥, VIX, S&P 500, 다우존스, 나스닥, 상해종합, 항셍지수, 니케이 225, EURO STOXX 50
2. **외환 (6개)**: 달러 인덱스 (DXY), USD/KRW, USD/JPY, USD/CNH, EUR/USD, GBP/USD
3. **채권 벤치마크 (6개)**: 한국 국고채 3Y, 한국 국고채 10Y, 미국 국채 2Y, 미국 국채 10Y, 일본 국채 10Y, 독일 국채 10Y
4. **원자재 (6개)**: WTI 원유, Brent 원유, 금(Gold), 은(Silver), 구리(Copper), 천연가스(Natural Gas)
5. **핵심 4대 스프레드**:
   - 미국 장단기 금리차 (`US 10Y - US 2Y`)
   - 한국 장단기 금리차 (`KR 10Y - KR 3Y`)
   - 한-미 10년물 스프레드 (`KR 10Y - US 10Y`)
   - 독-미 10년물 스프레드 (`DE 10Y - US 10Y`)

---

## 🚀 파이프라인 실행 방법

```powershell
# 프로젝트 디렉토리 이동
cd C:\Users\duddn\.gemini\antigravity-ide\scratch\ficc-daily-macro

# 전체 파이프라인 실행 및 일자별 JSON 저장
python main.py

# 저장 없이 콘솔 출력만 확인
python main.py --no-save
```
