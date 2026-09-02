"""
[FICC Daily Macro] 네이버 블로그 포맷터 (blog_formatter.py)
- 사용자 맞춤형 디자인 설정:
    1. 최상단 헤더 구성:
       - 제목: '[FICC Daily] 글로벌 매크로 시황' (22px Bold)
       - 부제: 'YYYY-MM-DD | 16:30 기준' (14px Normal)
       - 헤더 하단 구분선(선) 없음
    2. 시황정리 4대 시장 표 밑 개별 기준 문구 배제 (상단 16:30 기준 단일화)
    3. 원자재 표:
       - 열 제목: '가격'
       - 표기: '$90.15', '$94.97', '$4,373.90' (상세 단위 제거 및 $ 접두어 적용)
    4. 스마트에디터 ONE 복사·붙여넣기 테이블 열 너비 고정:
       - table-layout: fixed 및 colgroup / th / td 인라인 width 명시
       - Daily Event 표: 국가(10%, center), 예정시각(17%, center), 중요도(12%, center), 지표명(43%, left, keep-all), 시장예상치(18%, right)
       - 3열 시장 표: 품목/지수명(46%, left), 가격/환율/수익률(30%, right), 등락률/변동(24%, right)
    5. 네이버 블로그 스마트에디터 실측 픽셀(px) 규격:
       - 주요 섹션 제목: 19px Bold (#000000)
       - 본문 텍스트: 16px Normal (줄간격 1.85, #000000)
       - 요약 불릿: 16px Bold (#000000)
       - 이슈 리뷰 소제목: 16px Bold (#000000)
       - 일반 시장 표 및 지표 표: 15px (#000000)
    6. 글자 색상 검정(#000000) 통일 (등락률 빨강/파랑 및 중요도 별표 주황색 제외)
    7. 스마트에디터 완벽 호환 (h1~h3 태그 배제, p+span 인라인 font-weight 명시로 볼드 전파 원천 차단)
    8. 면책조항(Disclaimer) 없음
"""

import os
import re
from typing import Dict, Any, List

class NaverBlogFormatter:
    """네이버 블로그 HTML / TXT 듀얼 포맷터"""

    EVENT_TRANSLATION_MAP = {
        "french gov budget balance": "프랑스 정부 재정수지",
        "spanish unemployment change": "스페인 실업자수 변동",
        "adp non-farm employment change": "미국 ADP 비농업 부문 고용 변화",
        "boc rate statement": "캐나다 중앙은행(BOC) 통화정책 성명서",
        "overnight rate": "캐나다 기준금리 결정",
        "factory orders m/m": "미국 공장재 수주 (전월비)",
        "factory orders": "미국 공장재 수주",
        "boc press conference": "캐나다 중앙은행(BOC) 기자회견",
        "crude oil inventories": "미국 EIA 주간 원유재고",
        "ism manufacturing pmi": "미국 ISM 제조업 구매관리자지수(PMI)",
        "ism services pmi": "미국 ISM 서비스업 구매관리자지수(PMI)",
        "ism manufacturing prices": "미국 ISM 제조업 지불가격지수",
        "jolts job openings": "미국 JOLTS 구인건수",
        "non-farm employment change": "미국 비농업 고용지수(NFP) 변동",
        "unemployment rate": "실업률",
        "unemployment claims": "미국 신규 실업수당 청구건수",
        "cpi m/m": "소비자물가지수(CPI, 전월비)",
        "cpi y/y": "소비자물가지수(CPI, 전년비)",
        "core cpi m/m": "근원 소비자물가지수(Core CPI, 전월비)",
        "core cpi y/y": "근원 소비자물가지수(Core CPI, 전년비)",
        "ppi m/m": "생산자물가지수(PPI, 전월비)",
        "ppi y/y": "생산자물가지수(PPI, 전년비)",
        "core pce price index m/m": "근원 개인소비지출(PCE) 물가지수 (전월비)",
        "core pce price index y/y": "근원 개인소비지출(PCE) 물가지수 (전월비)",
        "retail sales m/m": "소매판매 (전월비)",
        "prelim gdp q/q": "GDP 성장률 속보치 (전분기비)",
        "fed interest rate decision": "미 연준(Fed) 기준금리 결정",
        "fomc statement": "FOMC 성명서 발표",
        "fomc press conference": "FOMC 기자회견",
        "ecb main refinancing rate": "ECB 기준금리 결정",
        "monetary policy statement": "통화정책 성명서"
    }

    DISPLAY_NAME_MAP = {
        # 증시
        "코스피 (KOSPI)": "코스피",
        "코스닥 (KOSDAQ)": "코스닥",
        "VIX 변동성 지수": "VIX",
        "S&P 500": "S&P 500",
        "다우존스 30": "다우존스 30",
        "나스닥 종합 (NASDAQ)": "나스닥 종합",
        "상해종합 (SSE)": "상해종합",
        "항셍지수 (HSI)": "항셍지수",
        "니케이 225 (Nikkei)": "니케이 225",
        "EURO STOXX 50": "EURO STOXX 50",

        # 외환
        "달러 인덱스 (DXY)": "DXY",
        "원/달러 환율 (USD/KRW)": "USD/KRW",
        "엔/달러 환율 (USD/JPY)": "USD/JPY",
        "역외 위안/달러 (USD/CNH)": "USD/CNH",
        "유로/달러 환율 (EUR/USD)": "EUR/USD",
        "파운드/달러 환율 (GBP/USD)": "GBP/USD",

        # 원자재
        "WTI 원유": "WTI",
        "Brent 원유": "Brent",
        "금 (Gold)": "금",
        "은 (Silver)": "은",
        "구리 (Copper)": "구리",
        "천연가스 (Natural Gas)": "천연가스",
    }

    @classmethod
    def clean_display_name(cls, raw_name: str) -> str:
        if not raw_name:
            return ""
        return cls.DISPLAY_NAME_MAP.get(raw_name, raw_name)

    @classmethod
    def translate_event_name(cls, event_name: str, country: str = "") -> str:
        if not event_name:
            return "-"
        clean_name = event_name.strip()
        lower_name = clean_name.lower()

        if lower_name in cls.EVENT_TRANSLATION_MAP:
            return cls.EVENT_TRANSLATION_MAP[lower_name]

        for eng_pat, kor_trans in cls.EVENT_TRANSLATION_MAP.items():
            if eng_pat in lower_name:
                return kor_trans

        res = clean_name
        country_prefix = ""
        if country == "US" and not res.startswith("US"):
            country_prefix = "미국 "
        elif country == "EU":
            country_prefix = "유로존 "
        elif country == "CA":
            country_prefix = "캐나다 "
        elif country == "JP":
            country_prefix = "일본 "
        elif country == "CN":
            country_prefix = "중국 "
        elif country == "KR":
            country_prefix = "한국 "

        replacements = [
            ("Unemployment Change", "실업자수 변동"),
            ("Unemployment Claims", "실업수당 청구건수"),
            ("Unemployment Rate", "실업률"),
            ("Budget Balance", "재정수지"),
            ("Gov Budget", "정부 재정"),
            ("Crude Oil Inventories", "주간 원유재고"),
            ("Inventories", "재고"),
            ("Trade Balance", "무역수지"),
            ("Retail Sales", "소매판매"),
            ("Factory Orders", "공장재 수주"),
            ("Rate Statement", "통화정책 성명서"),
            ("Press Conference", "기자회견"),
            ("Interest Rate", "기준금리"),
            ("Overnight Rate", "기준금리 결정"),
            ("m/m", "(전월비)"),
            ("y/y", "(전년비)"),
            ("q/q", "(전분기비)"),
        ]
        for eng, kor in replacements:
            res = re.sub(re.escape(eng), kor, res, flags=re.IGNORECASE)

        return f"{country_prefix}{res}".strip()

    @classmethod
    def format_spreads_inline(cls, spreads: List[Dict[str, Any]]) -> str:
        if not spreads:
            return ""
        items = []
        for sp in spreads:
            name = sp.get("name", "")
            curr_bp = sp.get("current_bp")
            curr_str = f"{curr_bp:+.1f}bp" if curr_bp is not None else "-"
            
            if "미국 장단기" in name or "10Y - 2Y" in name:
                items.append(f"미국 10Y-2Y {curr_str}")
            elif "한국 장단기" in name or "10Y - 3Y" in name:
                items.append(f"한국 10Y-3Y {curr_str}")
            elif "한-미" in name:
                items.append(f"한-미 10Y {curr_str}")
            elif "독-미" in name:
                items.append(f"독-미 10Y {curr_str}")
            else:
                items.append(f"{name} {curr_str}")

        return " · ".join(items)

    @classmethod
    def get_session_title(cls, is_post_1630: bool) -> str:
        return "16:30 기준" if is_post_1630 else "장중 실시간 집계 (16:30 이전)"

    @classmethod
    def _validate_input_report(cls, report_data: Dict[str, Any]):
        val_sum = report_data.get("validation_summary") or report_data.get("final_summary", {})
        is_passed = val_sum.get("passed", False) or report_data.get("final_passed", False)
        if not is_passed:
            errors = val_sum.get("errors", [])
            raise ValueError(f"검증을 통과하지 못한 리포트는 블로그 원고로 렌더링할 수 없습니다. (적발된 오류: {len(errors)}건)")

    @classmethod
    def format_blog_text(cls, report_data: Dict[str, Any], processed_market_data: Dict[str, Any], is_post_1630: bool = False) -> str:
        """검수용 Plain Text 원고 생성"""
        cls._validate_input_report(report_data)

        report_date = report_data.get("report_date", "")
        content = report_data.get("content") or report_data.get("validated_content") or {}
        categories = processed_market_data.get("market_data", {}).get("categories", {})
        spreads = processed_market_data.get("market_data", {}).get("spreads", [])
        economic_events = processed_market_data.get("economic_events", {})

        session_str = cls.get_session_title(is_post_1630)
        lines = []

        # 헤더
        lines.append("[FICC Daily] 글로벌 매크로 시황")
        lines.append(f"{report_date} | {session_str}")
        lines.append("")

        # 1. 시황정리
        lines.append("시황정리")
        lines.append("=" * 65)

        # [증시 표]
        lines.append("1. 증시")
        lines.append(f"{'지수명':<16} | {'종가/현재가':>12} | {'등락률':>10}")
        lines.append("-" * 46)
        for it in categories.get("EQUITY", []):
            d_name = cls.clean_display_name(it['name'])
            curr_str = f"{it['current']:,.2f}" if it.get("current") is not None else "-"
            pct_val = it.get("pct_change")
            pct_str = f"{pct_val:+.2f}%" if pct_val is not None else "-"
            lines.append(f"{d_name:<16} | {curr_str:>12} | {pct_str:>10}")
        lines.append("")

        # [외환 표]
        lines.append("2. 외환")
        lines.append(f"{'지표':<16} | {'현재환율':>12} | {'등락률':>10}")
        lines.append("-" * 46)
        for it in categories.get("FX", []):
            d_name = cls.clean_display_name(it['name'])
            curr_str = f"{it['current']:,.4f}" if ("EUR" in it['name'] or "GBP" in it['name'] or "CNH" in it['name']) else f"{it['current']:,.2f}"
            pct_val = it.get("pct_change")
            pct_str = f"{pct_val:+.2f}%" if pct_val is not None else "-"
            lines.append(f"{d_name:<16} | {curr_str:>12} | {pct_str:>10}")
        lines.append("")

        # [국채 표]
        lines.append("3. 국채")
        lines.append(f"{'채권 만기':<16} | {'수익률(%)':>12} | {'변동(bp)':>10}")
        lines.append("-" * 46)
        for it in categories.get("BOND", []):
            d_name = cls.clean_display_name(it['name'])
            curr_str = f"{it['current']:.2f}%" if it.get("current") is not None else "-"
            bp_val = it.get("bp_change")
            bp_str = f"{bp_val:+.1f} bp" if bp_val is not None else "-"
            lines.append(f"{d_name:<16} | {curr_str:>12} | {bp_str:>10}")
        if spreads:
            spread_inline = cls.format_spreads_inline(spreads)
            lines.append(f"   주요 스프레드: {spread_inline}")
        lines.append("")

        # [원자재 표]
        lines.append("4. 원자재")
        lines.append(f"{'품목명':<16} | {'가격':>12} | {'등락률':>10}")
        lines.append("-" * 46)
        for it in categories.get("COMMODITY", []):
            d_name = cls.clean_display_name(it['name'])
            curr_str = f"${it['current']:,.2f}" if it.get("current") is not None else "-"
            pct_val = it.get("pct_change")
            pct_str = f"{pct_val:+.2f}%" if pct_val is not None else "-"
            lines.append(f"{d_name:<16} | {curr_str:>12} | {pct_str:>10}")
        lines.append("")

        # 2. 요약
        lines.append("요약")
        lines.append("=" * 65)
        daily_sum = content.get("ficc_daily_summary", {})
        for b in daily_sum.get("bullets", []):
            lines.append(f"• {b}")
        lines.append("")
        ficc_sum = content.get("ficc_summary", {})
        lines.append(ficc_sum.get("text", ""))
        lines.append("")

        # 3. 이슈 리뷰
        issue_rev = content.get("issue_review", {})
        lines.append("이슈 리뷰")
        lines.append("=" * 65)
        
        lines.append("· 증시")
        lines.append(issue_rev.get("stock", {}).get("text", ""))
        lines.append("")

        lines.append("· 외환")
        lines.append(issue_rev.get("fx", {}).get("text", ""))
        lines.append("")

        lines.append("· 채권")
        lines.append(issue_rev.get("bond", {}).get("text", ""))
        lines.append("")

        lines.append("· 원자재")
        lines.append(issue_rev.get("commodity", {}).get("text", ""))
        lines.append("")

        # 4. 전망
        lines.append("전망")
        lines.append("=" * 65)
        lines.append(content.get("ficc_forecast", {}).get("text", ""))
        lines.append("")

        # 5. Daily Event
        lines.append("Daily Event")
        lines.append("=" * 65)
        lines.append(content.get("daily_event_watchpoints", {}).get("text", ""))
        lines.append("")

        today_night = economic_events.get("today_night_events", [])
        if today_night:
            lines.append("금일 밤(16:30 이후) 주요 발표 예정 지표")
            lines.append(f"{'국가':<6} | {'발표예정(KST)':<16} | {'중요도':<6} | {'지표명 (한글)':<32} | {'예상치':>8}")
            lines.append("-" * 75)
            for ev in today_night[:8]:
                imp_star = "★★★" if ev.get("importance") == "HIGH" else ("★★" if ev.get("importance") == "MEDIUM" else "★")
                time_short = ev.get("scheduled_at_kst", "")[11:16]
                f_val = ev.get("forecast") or "-"
                kor_event_name = cls.translate_event_name(ev.get("event_name", ""), ev.get("country", ""))
                lines.append(f"{ev.get('country', ''):<6} | {time_short:<16} | {imp_star:<6} | {kor_event_name[:30]:<32} | {f_val:>8}")
            lines.append("")
        else:
            lines.append("※ 금일 16:30 이후 주요 발표 예정 지표 없음")
            lines.append("")

        lines.append("=" * 65)
        return "\n".join(lines)

    @classmethod
    def format_blog_html(cls, report_data: Dict[str, Any], processed_market_data: Dict[str, Any], is_post_1630: bool = False) -> str:
        """네이버 블로그 SmartEditor ONE 전용 Rich HTML"""
        cls._validate_input_report(report_data)

        report_date = report_data.get("report_date", "")
        content = report_data.get("content") or report_data.get("validated_content") or {}
        categories = processed_market_data.get("market_data", {}).get("categories", {})
        spreads = processed_market_data.get("market_data", {}).get("spreads", [])
        economic_events = processed_market_data.get("economic_events", {})

        session_str = cls.get_session_title(is_post_1630)

        FONT_FAMILY = "'NanumGothic', '나눔고딕', 'Malgun Gothic', '맑은 고딕', sans-serif"

        html = []
        html.append(f'<div style="font-family: {FONT_FAMILY}; line-height: 1.85; color: #000000; max-width: 820px; margin: 0 auto; padding: 10px;">')

        # -------------------------------------------------------------
        # 헤더 (하단 구분선 없음)
        # -------------------------------------------------------------
        html.append('<div style="margin-bottom: 25px;">')
        html.append(f'<p style="font-family: {FONT_FAMILY}; font-size: 22px; font-weight: bold; color: #000000; margin: 0 0 6px 0;"><span style="font-size: 22px; font-weight: bold; color: #000000;">[FICC Daily] 글로벌 매크로 시황</span></p>')
        html.append(f'<p style="font-family: {FONT_FAMILY}; font-size: 14px; font-weight: normal; color: #000000; margin: 0;"><span style="font-size: 14px; font-weight: normal; color: #000000;">{report_date} | {session_str}</span></p>')
        html.append('</div>')

        # -------------------------------------------------------------
        # 1. 시황정리 (주요 섹션 제목 = 19px Bold, 검정)
        # -------------------------------------------------------------
        html.append(f'<p style="font-family: {FONT_FAMILY}; font-size: 19px; font-weight: bold; color: #000000; border-left: 4px solid #000000; padding-left: 10px; margin: 30px 0 15px 0;"><span style="font-size: 19px; font-weight: bold; color: #000000;">시황정리</span></p>')

        market_3col_widths = ["46%", "30%", "24%"]
        market_3col_aligns = ["left", "right", "right"]

        # [1] 증시 표 (15px)
        html.append(cls._render_table_html(
            title="1. 증시",
            headers=["지수명", "종가/현재가", "등락률"],
            rows=[
                [
                    cls.clean_display_name(it['name']),
                    f"{it['current']:,.2f}" if it.get("current") is not None else "-",
                    cls._format_pct_html(it.get("pct_change"))
                ]
                for it in categories.get("EQUITY", [])
            ],
            font_family=FONT_FAMILY,
            col_widths=market_3col_widths,
            col_aligns=market_3col_aligns
        ))

        # [2] 외환 표 (15px)
        html.append(cls._render_table_html(
            title="2. 외환",
            headers=["지표", "현재환율", "등락률"],
            rows=[
                [
                    cls.clean_display_name(it['name']),
                    f"{it['current']:,.4f}" if ("EUR" in it['name'] or "GBP" in it['name'] or "CNH" in it['name']) else f"{it['current']:,.2f}",
                    cls._format_pct_html(it.get("pct_change"))
                ]
                for it in categories.get("FX", [])
            ],
            font_family=FONT_FAMILY,
            col_widths=market_3col_widths,
            col_aligns=market_3col_aligns
        ))

        # [3] 국채 표 & 간결한 스프레드 인라인 표기 (15px)
        bond_rows = [
            [
                cls.clean_display_name(it['name']),
                f"{it['current']:.2f}%" if it.get("current") is not None else "-",
                cls._format_bp_html(it.get("bp_change"))
            ]
            for it in categories.get("BOND", [])
        ]
        html.append(cls._render_table_html(
            title="3. 국채",
            headers=["채권 만기", "수익률(%)", "전일대비(bp)"],
            rows=bond_rows,
            font_family=FONT_FAMILY,
            col_widths=market_3col_widths,
            col_aligns=market_3col_aligns
        ))

        if spreads:
            spread_inline = cls.format_spreads_inline(spreads)
            html.append(f'<p style="font-family: {FONT_FAMILY}; font-size: 15px; font-weight: normal; color: #000000; margin-top: -10px; margin-bottom: 22px; padding: 4px 6px;"><span style="font-size: 15px; font-weight: normal; color: #000000;"><strong>주요 스프레드:</strong> {spread_inline}</span></p>')

        # [4] 원자재 표 (15px)
        html.append(cls._render_table_html(
            title="4. 원자재",
            headers=["품목명", "가격", "등락률"],
            rows=[
                [
                    cls.clean_display_name(it['name']),
                    f"${it['current']:,.2f}" if it.get("current") is not None else "-",
                    cls._format_pct_html(it.get("pct_change"))
                ]
                for it in categories.get("COMMODITY", [])
            ],
            font_family=FONT_FAMILY,
            col_widths=market_3col_widths,
            col_aligns=market_3col_aligns
        ))

        # -------------------------------------------------------------
        # 2. 요약 (주요 섹션 = 19px Bold, 불릿 박스 = 16px Bold, 본문 = 16px Normal)
        # -------------------------------------------------------------
        html.append(f'<p style="font-family: {FONT_FAMILY}; font-size: 19px; font-weight: bold; color: #000000; border-left: 4px solid #000000; padding-left: 10px; margin: 35px 0 15px 0;"><span style="font-size: 19px; font-weight: bold; color: #000000;">요약</span></p>')
        
        daily_sum = content.get("ficc_daily_summary", {})
        bullets = daily_sum.get("bullets", [])
        if bullets:
            html.append('<div style="border: 1px solid #ced4da; padding: 14px 18px; border-radius: 4px; margin-bottom: 18px; background-color: #ffffff;">')
            html.append(f'<ul style="margin: 0; padding-left: 18px; font-family: {FONT_FAMILY}; font-size: 16px; font-weight: bold; color: #000000;">')
            for b in bullets:
                html.append(f'<li style="margin-bottom: 6px; font-size: 16px; font-weight: bold; color: #000000;"><span style="font-size: 16px; font-weight: bold; color: #000000;">{b}</span></li>')
            html.append('</ul></div>')

        ficc_sum = content.get("ficc_summary", {})
        html.append(f'<p style="font-family: {FONT_FAMILY}; font-size: 16px; font-weight: normal; line-height: 1.85; color: #000000; margin: 0 0 25px 0; text-align: justify;"><span style="font-size: 16px; font-weight: normal; color: #000000;">{ficc_sum.get("text", "")}</span></p>')

        # -------------------------------------------------------------
        # 3. 이슈 리뷰 (주요 섹션 = 19px Bold, 소제목 = 16px Bold, 본문 = 16px Normal)
        # -------------------------------------------------------------
        html.append(f'<p style="font-family: {FONT_FAMILY}; font-size: 19px; font-weight: bold; color: #000000; border-left: 4px solid #000000; padding-left: 10px; margin: 35px 0 15px 0;"><span style="font-size: 19px; font-weight: bold; color: #000000;">이슈 리뷰</span></p>')
        issue_rev = content.get("issue_review", {})

        asset_reviews = [
            ("· 증시", issue_rev.get("stock", {}).get("text", "")),
            ("· 외환", issue_rev.get("fx", {}).get("text", "")),
            ("· 채권", issue_rev.get("bond", {}).get("text", "")),
            ("· 원자재", issue_rev.get("commodity", {}).get("text", ""))
        ]

        for title, text in asset_reviews:
            html.append(f'<p style="font-family: {FONT_FAMILY}; font-size: 16px; font-weight: bold; color: #000000; margin: 20px 0 8px 0;"><span style="font-size: 16px; font-weight: bold; color: #000000;">{title}</span></p>')
            html.append(f'<p style="font-family: {FONT_FAMILY}; font-size: 16px; font-weight: normal; line-height: 1.85; color: #000000; margin: 0 0 18px 0; text-align: justify;"><span style="font-size: 16px; font-weight: normal; color: #000000;">{text}</span></p>')

        # -------------------------------------------------------------
        # 4. 전망 (주요 섹션 = 19px Bold, 본문 = 16px Normal)
        # -------------------------------------------------------------
        html.append(f'<p style="font-family: {FONT_FAMILY}; font-size: 19px; font-weight: bold; color: #000000; border-left: 4px solid #000000; padding-left: 10px; margin: 35px 0 15px 0;"><span style="font-size: 19px; font-weight: bold; color: #000000;">전망</span></p>')
        forecast_text = content.get("ficc_forecast", {}).get("text", "")
        html.append(f'<p style="font-family: {FONT_FAMILY}; font-size: 16px; font-weight: normal; line-height: 1.85; color: #000000; margin: 0 0 25px 0; text-align: justify;"><span style="font-size: 16px; font-weight: normal; color: #000000;">{forecast_text}</span></p>')

        # -------------------------------------------------------------
        # 5. Daily Event (주요 섹션 = 19px Bold, 본문 = 16px Normal)
        # -------------------------------------------------------------
        html.append(f'<p style="font-family: {FONT_FAMILY}; font-size: 19px; font-weight: bold; color: #000000; border-left: 4px solid #000000; padding-left: 10px; margin: 35px 0 15px 0;"><span style="font-size: 19px; font-weight: bold; color: #000000;">Daily Event</span></p>')
        event_wp = content.get("daily_event_watchpoints", {}).get("text", "")
        if event_wp:
            html.append(f'<p style="font-family: {FONT_FAMILY}; font-size: 16px; font-weight: normal; line-height: 1.85; color: #000000; margin: 0 0 15px 0;"><span style="font-size: 16px; font-weight: normal; color: #000000;">{event_wp}</span></p>')

        today_night = economic_events.get("today_night_events", [])
        if today_night:
            event_rows = []
            for ev in today_night[:8]:
                imp_star = "★★★" if ev.get("importance") == "HIGH" else ("★★" if ev.get("importance") == "MEDIUM" else "★")
                time_short = ev.get("scheduled_at_kst", "")[11:16]
                kor_event_name = cls.translate_event_name(ev.get("event_name", ""), ev.get("country", ""))
                event_rows.append([
                    ev.get("country", ""),
                    time_short,
                    f'<span style="color: #e65100; font-weight: bold;">{imp_star}</span>',
                    kor_event_name,
                    ev.get("forecast") or "-"
                ])

            # 네이버 스마트에디터 복사·붙여넣기 시에도 열 너비가 균등 배분되지 않도록 전용 폭/정렬 지정
            html.append(cls._render_table_html(
                title="금일 밤(16:30 이후) 주요 발표 예정 지표",
                headers=["국가", "예정시각(KST)", "중요도", "지표명", "시장예상치"],
                rows=event_rows,
                font_family=FONT_FAMILY,
                col_widths=["10%", "17%", "12%", "43%", "18%"],
                col_aligns=["center", "center", "center", "left", "right"]
            ))
        else:
            html.append(f'<p style="font-family: {FONT_FAMILY}; font-size: 14px; font-weight: normal; color: #6c757d; margin: 10px 0 20px 0;"><span style="font-size: 14px; color: #6c757d;">※ 금일 16:30 이후 주요 발표 예정 지표 없음</span></p>')

        html.append('</div>')
        return "\n".join(html)

    @staticmethod
    def _format_pct_html(val) -> str:
        if val is None:
            return "-"
        if val > 0:
            return f'<span style="color: #d32f2f; font-weight: bold;">+{val:.2f}%</span>'
        elif val < 0:
            return f'<span style="color: #1976d2; font-weight: bold;">{val:.2f}%</span>'
        else:
            return f'<span style="color: #000000; font-weight: normal;">0.00%</span>'

    @staticmethod
    def _format_bp_html(val) -> str:
        if val is None:
            return "-"
        if val > 0:
            return f'<span style="color: #d32f2f; font-weight: bold;">+{val:.1f} bp</span>'
        elif val < 0:
            return f'<span style="color: #1976d2; font-weight: bold;">{val:.1f} bp</span>'
        else:
            return f'<span style="color: #000000; font-weight: normal;">0.0 bp</span>'

    @classmethod
    def _render_table_html(
        cls, 
        title: str, 
        headers: list, 
        rows: list, 
        font_family: str = "", 
        baseline_note: str = "",
        col_widths: list = None,
        col_aligns: list = None
    ) -> str:
        """표 렌더링 (15px, table-layout: fixed 및 colgroup / th / td 인라인 width 적용)"""
        html = [f'<div style="margin-bottom: 22px;">']
        html.append(f'<p style="font-family: {font_family}; font-size: 15px; font-weight: bold; color: #000000; margin: 0 0 7px 0;"><span style="font-size: 15px; font-weight: bold; color: #000000;">{title}</span></p>')
        if baseline_note:
            html.append(f'<p style="font-family: {font_family}; font-size: 13px; font-weight: normal; color: #6c757d; margin: 0 0 8px 0;"><span style="font-size: 13px; font-weight: normal; color: #6c757d;">{baseline_note}</span></p>')
        
        table_style = (
            f"width: 100%; table-layout: fixed; border-collapse: collapse; "
            f"font-family: {font_family}; font-size: 15px; font-weight: normal; "
            f"text-align: left; border: 1px solid #dee2e6;"
        )
        html.append(f'<table style="{table_style}">')
        
        # Colgroup 정의
        if col_widths and len(col_widths) == len(headers):
            html.append('<colgroup>')
            for w in col_widths:
                html.append(f'<col style="width: {w};">')
            html.append('</colgroup>')

        # 헤더 (15px Bold)
        html.append('<thead style="background-color: #f1f3f5; border-bottom: 2px solid #ced4da;"><tr>')
        for idx, h in enumerate(headers):
            align_val = col_aligns[idx] if col_aligns and idx < len(col_aligns) else ("right" if idx in [1, 2, 4] else "left")
            w_style = f"width: {col_widths[idx]}; " if col_widths and idx < len(col_widths) else ""
            th_style = (
                f"padding: 8px 6px; box-sizing: border-box; font-family: {font_family}; "
                f"font-size: 15px; font-weight: bold; color: #000000; text-align: {align_val}; {w_style}"
                f"word-break: keep-all; overflow-wrap: break-word;"
            )
            html.append(f'<th style="{th_style}"><span style="font-size: 15px; font-weight: bold; color: #000000;">{h}</span></th>')
        html.append('</tr></thead>')

        # 바디 (15px Normal)
        html.append('<tbody>')
        for r_idx, r in enumerate(rows):
            bg = '#ffffff' if r_idx % 2 == 0 else '#f8f9fa'
            html.append(f'<tr style="background-color: {bg}; border-bottom: 1px solid #e9ecef;">')
            for c_idx, cell in enumerate(r):
                align_val = col_aligns[c_idx] if col_aligns and c_idx < len(col_aligns) else ("right" if c_idx in [1, 2, 4] else "left")
                w_style = f"width: {col_widths[c_idx]}; " if col_widths and c_idx < len(col_widths) else ""
                td_style = (
                    f"padding: 8px 6px; box-sizing: border-box; font-family: {font_family}; "
                    f"font-size: 15px; font-weight: normal; color: #000000; text-align: {align_val}; {w_style}"
                    f"word-break: keep-all; overflow-wrap: break-word; line-height: 1.45;"
                )
                html.append(f'<td style="{td_style}"><span style="font-size: 15px; font-weight: normal; color: #000000;">{cell}</span></td>')
            html.append('</tr>')
        html.append('</tbody></table></div>')
        return "\n".join(html)
