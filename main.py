"""
====================================================================
[FICC Daily Macro] 통합 데이터 수집 & 일자별 저장 파이프라인 (main.py)
====================================================================
- 4대 자산군 총 28개 핵심 지표 종합 수집
- 타겟 기준 시각: 매일 16:30 KST
- 매크로/채권 스프레드 자동 산출
- 다중 실행 이력 보존:
    • data/raw/YYYY-MM-DD_HHMMSS_TEST.json 또는 _CONFIRMED.json (타임스탬프 영구 보존)
    • data/processed/YYYY-MM-DD.json (AI/블로그 생성용 최신 가공본 갱신)
"""

import sys
import argparse
import datetime
from tabulate import tabulate

from collectors.equity import EquityCollector
from collectors.fx import FxCollector
from collectors.bond import BondCollector
from collectors.commodity import CommodityCollector
from processors.calculator import MacroCalculator, format_change
from storage.saver import DataSaver
from config.settings import TARGET_DAILY_TIME_STR

# Windows 콘솔 UTF-8 출력 호환성 보장
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# 콘솔 색상 코드
COLOR_CYAN = "\033[96m"
COLOR_GREEN = "\033[92m"
COLOR_RED = "\033[91m"
COLOR_YELLOW = "\033[93m"
COLOR_BOLD = "\033[1m"
COLOR_RESET = "\033[0m"

def print_header(now_kst: datetime.datetime, is_post_1630: bool):
    report_date = now_kst.strftime("%Y-%m-%d")
    print("=" * 115)
    print(f"{COLOR_BOLD}{COLOR_CYAN} [FICC Daily Macro] 시장 28개 핵심 지표 종합 파이프라인{COLOR_RESET}")
    print(f" • 리포트 목표일자 (report_date) : {COLOR_BOLD}{report_date}{COLOR_RESET}")
    print(f" • 목표 벤치마크 시각 (target_time): {COLOR_BOLD}{TARGET_DAILY_TIME_STR}{COLOR_RESET}")
    print(f" • 실제 프로그램 실행시각 (run_time): {COLOR_BOLD}{now_kst.strftime('%Y-%m-%d %H:%M:%S')} KST{COLOR_RESET}")

    if is_post_1630:
        print(f" • 실행 모드 : {COLOR_GREEN}{COLOR_BOLD}[DAILY 16:30 OFFICIAL RUN - 정규 데일리 확정 실행 (CONFIRMED)]{COLOR_RESET}")
    else:
        print(f" • 실행 모드 : {COLOR_YELLOW}{COLOR_BOLD}⚠️ [PRE-16:30 TEST MODE - 장중/사전 테스트 실행 (TEST)]{COLOR_RESET}")
        print(f"   {COLOR_YELLOW}※ 주의: 현재 시각({now_kst.strftime('%H:%M')} KST)은 목표 기준시각(16:30 KST) 이전입니다.")
        print(f"   ※ 16:30 이전의 장중 데이터나 직전 마감 데이터를 '16:30 확정치'로 오인하지 않도록 명확히 분리 표시합니다.{COLOR_RESET}")
    print("=" * 115)

def print_tables(processed_data: dict):
    categories = processed_data["categories"]
    spreads = processed_data["spreads"]

    # 1. 증시 (10개)
    print(f"\n{COLOR_BOLD}1. 국내외 증시 (Equity Markets — 10개 지표){COLOR_RESET}")
    eq_rows = []
    for r in categories.get("EQUITY", []):
        c_str = f"{r['current']:,.2f}" if r['current'] is not None else "N/A"
        chg_str = format_change(r['change'], is_pct=False)
        pct_str = format_change(r['pct_change'], is_pct=True)
        st_color = COLOR_GREEN if r['validation_status'] == "DAILY_CONFIRMED" else (COLOR_YELLOW if r['validation_status'] == "PRE_1630_TEST" else COLOR_RED)
        eq_rows.append([
            r['name'], r['symbol'], c_str, chg_str, pct_str,
            r['market_as_of_date'], r['actual_as_of_kst'], r['session_type'],
            f"{st_color}{r['validation_status']}{COLOR_RESET}"
        ])
    print(tabulate(eq_rows, headers=["지수명", "티커", "기준가/종가", "전일대비", "등락률(%)", "현지시장일자", "실제 데이터 시각(KST)", "세션 성격", "검증 상태"], tablefmt="rounded_grid"))

    # 2. 외환 (6개)
    print(f"\n{COLOR_BOLD}2. 외환 시장 (FX Rates — 6개 지표){COLOR_RESET}")
    fx_rows = []
    for r in categories.get("FX", []):
        is_4dec = ("EUR" in r['name'] or "GBP" in r['name'] or "CNH" in r['name'])
        c_str = f"{r['current']:.4f}" if (r['current'] is not None and is_4dec) else (f"{r['current']:,.2f}" if r['current'] is not None else "N/A")
        chg_str = format_change(r['change'], is_pct=False, decimals=4 if is_4dec else 2)
        pct_str = format_change(r['pct_change'], is_pct=True)
        st_color = COLOR_GREEN if r['validation_status'] == "DAILY_CONFIRMED" else (COLOR_YELLOW if r['validation_status'] == "PRE_1630_TEST" else COLOR_RED)
        fx_rows.append([
            r['name'], r['symbol'], c_str, chg_str, pct_str,
            r['market_as_of_date'], r['actual_as_of_kst'], r['session_type'],
            f"{st_color}{r['validation_status']}{COLOR_RESET}"
        ])
    print(tabulate(fx_rows, headers=["통화쌍/지표", "티커", "현재환율", "전일대비", "등락률(%)", "현지시장일자", "실제 데이터 시각(KST)", "세션 성격", "검증 상태"], tablefmt="rounded_grid"))

    # 3. 채권 벤치마크 (6개)
    print(f"\n{COLOR_BOLD}3. 채권 시장 벤치마크 금리 (Sovereign Benchmark Yields — 6개 지표){COLOR_RESET}")
    bond_rows = []
    for r in categories.get("BOND", []):
        c_str = f"{r['current']:.3f}%" if r['current'] is not None else "N/A"
        bp_str = format_change(r['bp_change'], is_bp=True)
        st_color = COLOR_GREEN if r['validation_status'] == "DAILY_CONFIRMED" else (COLOR_YELLOW if r['validation_status'] == "PRE_1630_TEST" else COLOR_RED)
        bond_rows.append([
            r['name'], r['symbol'], c_str, bp_str,
            r['market_as_of_date'], r['actual_as_of_kst'], r['data_source'], r['session_type'],
            f"{st_color}{r['validation_status']}{COLOR_RESET}"
        ])
    print(tabulate(bond_rows, headers=["국채 지표", "코드/심볼", "수익률(%)", "전일대비(bp)", "현지시장일자", "실제 데이터 시각(KST)", "제공처", "세션 성격", "검증 상태"], tablefmt="rounded_grid"))

    # 4. 채권 핵심 스프레드 분석
    print(f"\n{COLOR_BOLD}4. 주요 채권 매크로 스프레드 분석 (Macro Term & Cross-Country Spreads){COLOR_RESET}")
    spread_rows = []
    for s in spreads:
        c_bp_str = f"{s['current_bp']:+.1f} bp" if s['current_bp'] is not None else "N/A"
        chg_bp_str = format_change(s['change_bp'], is_bp=True)
        st_color = COLOR_GREEN if s['validation_status'] == "DAILY_CONFIRMED" else (COLOR_YELLOW if s['validation_status'] == "PRE_1630_TEST" else COLOR_RED)
        spread_rows.append([
            s['name'], c_bp_str, chg_bp_str, s['description'],
            f"{st_color}{s['validation_status']}{COLOR_RESET}"
        ])
    print(tabulate(spread_rows, headers=["스프레드 구분", "현재 스프레드(bp)", "전일대비 변동(bp)", "매크로 해석 의미", "검증 상태"], tablefmt="rounded_grid"))

    # 5. 원자재 (6개)
    print(f"\n{COLOR_BOLD}5. 주요 원자재 (Commodities — 6개 지표){COLOR_RESET}")
    comm_rows = []
    for r in categories.get("COMMODITY", []):
        c_str = f"{r['current']:,.2f} {r['unit']}" if r['current'] is not None else "N/A"
        chg_str = format_change(r['change'], is_pct=False)
        pct_str = format_change(r['pct_change'], is_pct=True)
        st_color = COLOR_GREEN if r['validation_status'] == "DAILY_CONFIRMED" else (COLOR_YELLOW if r['validation_status'] == "PRE_1630_TEST" else COLOR_RED)
        comm_rows.append([
            r['name'], r['symbol'], c_str, chg_str, pct_str,
            r['market_as_of_date'], r['actual_as_of_kst'], r['session_type'],
            f"{st_color}{r['validation_status']}{COLOR_RESET}"
        ])
    print(tabulate(comm_rows, headers=["원자재명", "선물 심볼", "현재가(단위)", "전일대비", "등락률(%)", "현지시장일자", "실제 데이터 시각(KST)", "세션 성격", "검증 상태"], tablefmt="rounded_grid"))

def run_pipeline(save_data: bool = True):
    now_kst = datetime.datetime.now()
    is_post_1630 = (now_kst.hour > 16 or (now_kst.hour == 16 and now_kst.minute >= 30))

    print_header(now_kst, is_post_1630)

    # 1. 수집기 실행
    collectors = [
        EquityCollector(),
        FxCollector(),
        BondCollector(),
        CommodityCollector()
    ]

    all_raw_records = []
    for col in collectors:
        records = col.collect(now_kst, is_post_1630)
        all_raw_records.extend(records)

    # 2. 데이터 가공 및 스프레드 산출
    processed_data = MacroCalculator.process_all(all_raw_records)

    # 3. 콘솔 표 출력
    print_tables(processed_data)

    # 4. 다중 실행 이력 스냅샷 및 최신 가공본 저장
    if save_data:
        saver = DataSaver(base_data_dir="data")
        # 1) 원천 스냅샷 저장 (타임스탬프 파일, 덮어쓰기 없음)
        raw_path = saver.save_raw(all_raw_records, now_kst, is_post_1630)
        # 2) 최신 가공본 저장 (AI/블로그 생성용 단일 진입점 파일)
        proc_path = saver.save_processed(processed_data, now_kst, is_post_1630, raw_snapshot_path=raw_path)

        print("\n" + "=" * 115)
        print(f"{COLOR_GREEN}{COLOR_BOLD}💾 [데이터 저장 완료]{COLOR_RESET}")
        print(f" • 원천 스냅샷 저장 완료 (타임스탬프 영구 보존): {COLOR_CYAN}{raw_path}{COLOR_RESET}")
        print(f" • 최신 가공본 저장 완료 (AI/블로그 파이프라인용) : {COLOR_CYAN}{proc_path}{COLOR_RESET}")
        print("=" * 115)

    stats = processed_data["summary_stats"]
    print(f"\n✨ 총 {stats['total_indicators']}개 지표 수집 완료 | 검증 상태: {stats['status_counts']}")
    return processed_data

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FICC Daily Macro Pipeline Runner")
    parser.add_argument("--no-save", action="store_true", help="결과를 파일로 저장하지 않고 화면에만 출력")
    args = parser.parse_args()

    run_pipeline(save_data=not args.no_save)
