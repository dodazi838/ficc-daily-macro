"""
====================================================================
[FICC Daily Macro] 통합 엔드투엔드 파이프라인 (main.py)
====================================================================
- 1~2단계: 4대 자산군 28개 지표 + 핵심 스프레드 수집 및 정합성 검증
- 3단계: 공식 RSS/API 기반 매크로 뉴스 + 3-Way 경제 캘린더 수집/가공
- 4단계: Gemini 3.7 Flash (Thinking: Medium) AI 시황 생성 & FactValidator 엄격 게이트키핑 (오류 시 자동 1회 재시도)
- 5단계: 검증 통과(PASS) 시에만 네이버 블로그 Rich HTML(blog_post.html) 및 TXT(blog_post.txt) 렌더링
"""

import os
import sys
import argparse
import datetime
from tabulate import tabulate
from dotenv import load_dotenv

load_dotenv()

from collectors.equity import EquityCollector
from collectors.fx import FxCollector
from collectors.bond import BondCollector
from collectors.commodity import CommodityCollector
from collectors.news_fetcher import MacroNewsCollector
from collectors.economic_calendar import EconomicCalendarCollector
from processors.calculator import MacroCalculator, format_change
from processors.news_processor import MacroNewsProcessor
from processors.event_processor import MacroEventProcessor
from generators.report_generator import FiccReportGenerator
from storage.saver import DataSaver
from config.settings import TARGET_DAILY_TIME_STR

# Windows 콘솔 UTF-8 출력 호환성 보장
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

COLOR_CYAN = "\033[96m"
COLOR_GREEN = "\033[92m"
COLOR_RED = "\033[91m"
COLOR_YELLOW = "\033[93m"
COLOR_BOLD = "\033[1m"
COLOR_RESET = "\033[0m"

def print_header(now_kst: datetime.datetime, cutoff_kst: datetime.datetime, is_post_1630: bool):
    report_date = now_kst.strftime("%Y-%m-%d")
    print("=" * 115)
    print(f"{COLOR_BOLD}{COLOR_CYAN} [FICC Daily Macro] 통합 파이프라인 (Single Source of Truth & FactValidator Gatekeeper){COLOR_RESET}")
    print(f" • 보고서 기준일자 (report_date)   : {COLOR_BOLD}{report_date}{COLOR_RESET}")
    print(f" • 공식 데이터 기준시각 (cutoff_kst) : {COLOR_BOLD}{COLOR_GREEN}{cutoff_kst.strftime('%Y-%m-%d %H:%M:%S')} KST (16:30 고정 기준){COLOR_RESET}")
    print(f" • 실제 프로그램 실행시각 (run_time): {COLOR_BOLD}{now_kst.strftime('%Y-%m-%d %H:%M:%S')} KST{COLOR_RESET}")

    if is_post_1630:
        print(f" • 실행 모드 : {COLOR_GREEN}{COLOR_BOLD}[16:30 KST 정규 마감 확정치 (CONFIRMED)]{COLOR_RESET}")
    else:
        print(f" • 실행 모드 : {COLOR_YELLOW}{COLOR_BOLD}⚠️ [장중 실시간 집계 (16:30 이전 테스트)]{COLOR_RESET}")
        print(f"   {COLOR_YELLOW}※ 주의: 현재 시각({now_kst.strftime('%H:%M')} KST)은 정규 마감 기준시각(16:30 KST) 이전입니다.")
    print("=" * 115)

def print_market_tables(market_data: dict):
    categories = market_data.get("categories", {})
    spreads = market_data.get("spreads", [])

    # 1. 증시 (10개)
    print(f"\n{COLOR_BOLD}1. 글로벌 및 아시아 주요 증시 (Equities — 10개 지표){COLOR_RESET}")
    eq_rows = []
    for r in categories.get("EQUITY", []):
        c_str = f"{r['current']:,.2f}" if r['current'] is not None else "N/A"
        chg_str = format_change(r['change'], is_pct=False)
        pct_str = format_change(r['pct_change'], is_pct=True)
        eq_rows.append([r['name'], r['symbol'], c_str, chg_str, pct_str, r['price_type'], r['actual_as_of_kst']])
    print(tabulate(eq_rows, headers=["지수명", "심볼", "종가/현재가", "전일대비", "등락률(%)", "가격기준", "수집기준시각(KST)"], tablefmt="rounded_grid"))

    # 2. 외환 (6개)
    print(f"\n{COLOR_BOLD}2. 주요 외환 및 달러 인덱스 (Foreign Exchange — 6개 지표){COLOR_RESET}")
    fx_rows = []
    for r in categories.get("FX", []):
        c_str = f"{r['current']:.4f}" if (r['current'] is not None and r['unit'] == "$") else (f"{r['current']:,.2f}" if r['current'] is not None else "N/A")
        chg_str = format_change(r['change'], is_pct=False)
        pct_str = format_change(r['pct_change'], is_pct=True)
        fx_rows.append([r['name'], r['symbol'], c_str, chg_str, pct_str, r['price_type'], r['actual_as_of_kst']])
    print(tabulate(fx_rows, headers=["지표", "심볼", "현재환율", "전일대비", "등락률(%)", "가격기준", "수집기준시각(KST)"], tablefmt="rounded_grid"))

    # 3. 국채 (6개)
    print(f"\n{COLOR_BOLD}3. 주요국 국채 수익률 (Government Bond Yields — 6개 만기){COLOR_RESET}")
    bond_rows = []
    for r in categories.get("BOND", []):
        c_str = f"{r['current']:.2f}%" if r['current'] is not None else "N/A"
        bp_str = format_change(r['bp_change'], is_bp=True)
        pct_str = format_change(r['pct_change'], is_pct=True)
        bond_rows.append([r['name'], r['symbol'], c_str, bp_str, pct_str, r['data_source'], r['actual_as_of_kst']])
    print(tabulate(bond_rows, headers=["채권종류", "심볼", "수익률(%)", "전일대비(bp)", "등락률(%)", "출처", "수집기준시각(KST)"], tablefmt="rounded_grid"))

    # 4. 원자재 (6개)
    print(f"\n{COLOR_BOLD}4. 주요 원자재 (Commodities — 6개 지표){COLOR_RESET}")
    comm_rows = []
    for r in categories.get("COMMODITY", []):
        c_str = f"${r['current']:,.2f}" if r['current'] is not None else "N/A"
        chg_str = format_change(r['change'], is_pct=False)
        pct_str = format_change(r['pct_change'], is_pct=True)
        comm_rows.append([r['name'], r['symbol'], c_str, chg_str, pct_str, r['price_type'], r['actual_as_of_kst']])
    print(tabulate(comm_rows, headers=["품목명", "심볼", "가격", "전일대비", "등락률(%)", "가격기준", "수집기준시각(KST)"], tablefmt="rounded_grid"))

    # 5. 핵심 스프레드
    print(f"\n{COLOR_BOLD}5. FICC 핵심 장단기 & 국가간 금리 스프레드 (Calculated Spreads){COLOR_RESET}")
    sp_rows = []
    for sp in spreads:
        c_bp = f"{sp['current_bp']:+.1f} bp" if sp['current_bp'] is not None else "N/A"
        chg_bp = format_change(sp['change_bp'], is_bp=True)
        sp_rows.append([sp['name'], sp['type'], c_bp, chg_bp, sp['description']])
    print(tabulate(sp_rows, headers=["스프레드 명칭", "구분", "현재 스프레드", "전일대비(bp)", "매크로 해석"], tablefmt="rounded_grid"))

def run_pipeline(save_data: bool = True):
    now_kst = datetime.datetime.now()
    cutoff_time = now_kst.replace(hour=16, minute=30, second=0, microsecond=0)
    is_post_1630 = now_kst >= cutoff_time

    print_header(now_kst, cutoff_time, is_post_1630)

    # 1. 시장 데이터 수집 (28개)
    collectors = [EquityCollector(), FxCollector(), BondCollector(), CommodityCollector()]
    all_raw_market_records = []
    for c in collectors:
        records = c.collect(now_kst, is_post_1630)
        all_raw_market_records.extend(records)

    processed_market = MacroCalculator.process_all(all_raw_market_records)
    print_market_tables(processed_market)

    # 2. 뉴스 수집
    news_collector = MacroNewsCollector()
    raw_news_report = news_collector.collect_all(now_kst, lookback_hours=36)
    processed_news = MacroNewsProcessor.process_news(raw_news_report.get("raw_articles", []), now_kst)

    # 3. 경제 캘린더 수집
    calendar_collector = EconomicCalendarCollector()
    raw_cal_report = calendar_collector.collect_all(now_kst)
    processed_events = MacroEventProcessor.process_calendar_events(raw_cal_report.get("raw_events", []), now_kst)

    # 4. Single Source of Truth 저장 및 16:30 공식 SSOT 보호
    proc_path = None
    if save_data:
        saver = DataSaver(base_data_dir="data")
        raw_market_path = saver.save_raw_market(all_raw_market_records, now_kst, cutoff_time, is_post_1630)
        raw_news_path = saver.save_raw_news(raw_news_report, now_kst, cutoff_time, is_post_1630)
        raw_events_path = saver.save_raw_events(raw_cal_report, now_kst, cutoff_time, is_post_1630)

        raw_snapshots = {
            "market": raw_market_path,
            "news": raw_news_path,
            "events": raw_events_path
        }

        proc_path = saver.save_processed(
            market_data=processed_market,
            processed_news=processed_news,
            processed_events=processed_events,
            run_time_kst=now_kst,
            cutoff_kst=cutoff_time,
            is_post_1630=is_post_1630,
            raw_snapshots=raw_snapshots
        )

        date_str = now_kst.strftime("%Y-%m-%d")
        print("\n" + "=" * 115)
        print(f"{COLOR_GREEN}{COLOR_BOLD}💾 [1~3단계 원천 및 가공 데이터 영구 저장 완료 (SSOT)]{COLOR_RESET}")
        print(f" • 보고서 기준 시각 (Cutoff) : {COLOR_BOLD}{cutoff_time.strftime('%Y-%m-%d %H:%M:%S')} KST (16:30 고정){COLOR_RESET}")
        print(f" • 실제 실행 시각 (Run Time): {COLOR_CYAN}{now_kst.strftime('%Y-%m-%d %H:%M:%S')} KST{COLOR_RESET}")
        print(f" • 원천 데이터 (Raw)         : {COLOR_CYAN}data/raw/{date_str}/ (market.json, news.json, events.json){COLOR_RESET}")
        print(f" • 공식 통합본 (SSOT)        : {COLOR_GREEN}{COLOR_BOLD}{proc_path}{COLOR_RESET}")
        print("=" * 115)

    # 5. 4~5단계 리포트 및 블로그 원고(HTML / TXT) 생성
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if proc_path and gemini_key:
        print(f"\n{COLOR_BOLD}{COLOR_CYAN}🤖 [4~5단계] Gemini 3.7 Flash AI 시황 생성 & FactValidator 게이트키핑 시작...{COLOR_RESET}")
        try:
            report_gen = FiccReportGenerator()
            res = report_gen.generate_report_from_file(proc_path, is_post_1630=is_post_1630)
            
            usage = res.get("usage", {})
            val = res.get("validation_summary", {})
            
            if res.get("success"):
                print(f"\n{COLOR_GREEN}{COLOR_BOLD}✅ [성공] 팩트 검증 통과 (PASS) 및 네이버 블로그 원고 생성 완료! (시도: {res.get('attempts')}회){COLOR_RESET}")
                print(f" • 모델: {COLOR_CYAN}{usage.get('model')}{COLOR_RESET} | 총 토큰: {usage.get('total_tokens')} (입력: {usage.get('prompt_tokens')}, 출력: {usage.get('completion_tokens')}, Thinking: {usage.get('thinking_tokens')})")
                print(f" • 예상 비용: {COLOR_CYAN}${usage.get('estimated_cost_usd'):.6f}{COLOR_RESET}")
                print(f" • 팩트 검증: {COLOR_GREEN}PASS (신뢰도: {val.get('overall_confidence')}){COLOR_RESET} | 검증된 수치: {val.get('fact_check_details', {}).get('verified_numbers_count')}개")
                print(f"\n • 저장된 날짜별 산출물 구조:")
                print(f"   1) Gemini 1차 초안  : {COLOR_CYAN}{res.get('gemini_draft_path')}{COLOR_RESET}")
                if res.get('corrected_draft_path'):
                    print(f"   2) 자동 수정본(2차) : {COLOR_CYAN}{res.get('corrected_draft_path')}{COLOR_RESET}")
                print(f"   3) 팩트 검증 결과   : {COLOR_CYAN}{res.get('validation_json_path')}{COLOR_RESET}")
                print(f"   4) 블로그 게시용 HTML: {COLOR_GREEN}{COLOR_BOLD}{res.get('blog_html_path')}{COLOR_RESET}")
                print(f"   5) 블로그 검수용 TXT : {COLOR_CYAN}{res.get('blog_text_path')}{COLOR_RESET}")
            else:
                print(f"\n{COLOR_RED}{COLOR_BOLD}⛔ [게시 차단] FactValidator 검증 최종 실패 (FAIL: {len(val.get('errors', []))}건 에러, {res.get('attempts')}회 시도 후 중단){COLOR_RESET}")
                print(f" • 블로그 게시물(blog_post.html / blog_post.txt) 생성을 엄격히 차단했습니다.")
                print(f" • 검증 상세 내역 저장 경로: {COLOR_RED}{res.get('validation_json_path')}{COLOR_RESET}")
                print(f" • [적발된 오류 목록]:")
                for err in val.get("errors", []):
                    print(f"   ❌ {err}")

        except Exception as e:
            print(f"{COLOR_RED}❌ 리포트 생성 파이프라인 오류 발생: {e}{COLOR_RESET}")
    elif proc_path and not gemini_key:
        print(f"\n{COLOR_YELLOW}⚠️ [4~5단계 안내] GEMINI_API_KEY가 .env 파일에 아직 설정되지 않았습니다.{COLOR_RESET}")

    return {
        "market": processed_market,
        "news": processed_news,
        "calendar": processed_events
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FICC Daily Macro Pipeline Runner")
    parser.add_argument("--no-save", action="store_true", help="결과를 파일로 저장하지 않고 화면에만 출력")
    args = parser.parse_args()

    run_pipeline(save_data=not args.no_save)
