"""
[FICC Daily Macro] 글로벌 주요 증시 10개 지표 수집기
"""

import pytz
import yfinance as yf
from datetime import datetime
from typing import List, Dict, Any
from collectors.base import BaseCollector
from config.settings import EQUITY_INDICATORS, KST_TZ

class EquityCollector(BaseCollector):
    """글로벌 주요 증시 및 변동성 지표(VIX) 수집기"""

    def __init__(self):
        super().__init__(name="EquityCollector")
        self.indicators = EQUITY_INDICATORS

    def collect(self, run_time_kst: datetime, is_post_1630: bool) -> List[Dict[str, Any]]:
        report_date = run_time_kst.strftime("%Y-%m-%d")
        results = []

        for item in self.indicators:
            record = self.create_empty_record(item, run_time_kst, data_source="Yahoo Finance")
            sym = item["symbol"]
            market_type = item["market_type"]
            native_tz = pytz.timezone(item.get("tz", "UTC"))

            try:
                t = yf.Ticker(sym)
                hist = t.history(period="10d", interval="1d")

                if len(hist) < 2:
                    record["validation_status"] = "DELAYED"
                    record["message"] = f"조회된 일봉 데이터 부족 ({len(hist)}일)"
                    results.append(record)
                    continue

                last_dt = hist.index[-1]
                prev_dt = hist.index[-2]
                curr_val = float(hist['Close'].iloc[-1])
                prev_val = float(hist['Close'].iloc[-2])

                # 장중 1분봉 틱/타임스탬프 확인
                intraday_ts_kst = None
                raw_intraday_ts = None
                try:
                    h_1m = t.history(period="1d", interval="1m")
                    if len(h_1m) > 0:
                        raw_intraday_ts = h_1m.index[-1]
                        intraday_ts_kst = raw_intraday_ts.astimezone(KST_TZ)
                        if market_type == "HK_EQUITY":
                            curr_val = float(h_1m['Close'].iloc[-1])
                except Exception:
                    pass

                # 시장별 세션 판정
                if market_type == "KR_EQUITY":
                    local_dt = last_dt.astimezone(native_tz) if last_dt.tzinfo else native_tz.localize(last_dt)
                    record["market_as_of_date"] = local_dt.strftime("%Y-%m-%d")
                    is_kr_closed = (run_time_kst.hour > 15 or (run_time_kst.hour == 15 and run_time_kst.minute >= 30))
                    if is_kr_closed:
                        record["actual_as_of_kst"] = f"{record['market_as_of_date']} 15:30:00 KST (장 마감)"
                        record["raw_source_timestamp"] = str(last_dt)
                        record["session_type"] = "당일 확정종가 (15:30 마감)"
                        record["validation_status"] = "DAILY_CONFIRMED" if is_post_1630 else "PRE_1630_TEST"
                    else:
                        tick_str = intraday_ts_kst.strftime('%H:%M:%S') if intraday_ts_kst else run_time_kst.strftime('%H:%M')
                        record["actual_as_of_kst"] = f"{record['market_as_of_date']} {tick_str} KST (장중)"
                        record["raw_source_timestamp"] = str(raw_intraday_ts) if raw_intraday_ts else str(last_dt)
                        record["session_type"] = f"당일 장중 실시간가 ({tick_str} 미확정)"
                        record["validation_status"] = "PRE_1630_TEST"

                elif market_type == "JP_EQUITY":
                    local_dt = last_dt.astimezone(native_tz) if last_dt.tzinfo else native_tz.localize(last_dt)
                    record["market_as_of_date"] = local_dt.strftime("%Y-%m-%d")
                    is_jp_closed = (run_time_kst.hour >= 15)
                    if is_jp_closed:
                        record["actual_as_of_kst"] = f"{record['market_as_of_date']} 15:00:00 KST (장 마감)"
                        record["raw_source_timestamp"] = str(last_dt)
                        record["session_type"] = "당일 확정종가 (15:00 마감)"
                        record["validation_status"] = "DAILY_CONFIRMED" if is_post_1630 else "PRE_1630_TEST"
                    else:
                        tick_str = intraday_ts_kst.strftime('%H:%M:%S') if intraday_ts_kst else run_time_kst.strftime('%H:%M')
                        record["actual_as_of_kst"] = f"{record['market_as_of_date']} {tick_str} KST (장중)"
                        record["raw_source_timestamp"] = str(raw_intraday_ts) if raw_intraday_ts else str(last_dt)
                        record["session_type"] = f"당일 장중 실시간가 ({tick_str} 미확정)"
                        record["validation_status"] = "PRE_1630_TEST"

                elif market_type == "CN_EQUITY":
                    local_dt = last_dt.astimezone(native_tz) if last_dt.tzinfo else native_tz.localize(last_dt)
                    record["market_as_of_date"] = local_dt.strftime("%Y-%m-%d")
                    is_cn_closed = (run_time_kst.hour >= 16)
                    if is_cn_closed:
                        record["actual_as_of_kst"] = f"{record['market_as_of_date']} 16:00:00 KST (장 마감)"
                        record["raw_source_timestamp"] = str(last_dt)
                        record["session_type"] = "당일 확정종가 (16:00 마감)"
                        record["validation_status"] = "DAILY_CONFIRMED" if is_post_1630 else "PRE_1630_TEST"
                    else:
                        tick_str = intraday_ts_kst.strftime('%H:%M:%S') if intraday_ts_kst else run_time_kst.strftime('%H:%M')
                        record["actual_as_of_kst"] = f"{record['market_as_of_date']} {tick_str} KST (장중)"
                        record["raw_source_timestamp"] = str(raw_intraday_ts) if raw_intraday_ts else str(last_dt)
                        record["session_type"] = f"당일 장중 실시간가 ({tick_str} 미확정)"
                        record["validation_status"] = "PRE_1630_TEST"

                elif market_type == "HK_EQUITY":
                    local_dt = last_dt.astimezone(native_tz) if last_dt.tzinfo else native_tz.localize(last_dt)
                    record["market_as_of_date"] = local_dt.strftime("%Y-%m-%d")
                    tick_str = intraday_ts_kst.strftime('%H:%M:%S KST') if intraday_ts_kst else f"{run_time_kst.strftime('%H:%M:%S')} KST (근사)"
                    record["actual_as_of_kst"] = tick_str
                    record["raw_source_timestamp"] = str(raw_intraday_ts) if raw_intraday_ts else str(last_dt)
                    if is_post_1630:
                        record["session_type"] = "16:30 기준 장중 스냅샷"
                        record["validation_status"] = "DAILY_CONFIRMED"
                    else:
                        record["session_type"] = f"장중 실시간 스냅샷 ({tick_str}, 16:30 이전)"
                        record["validation_status"] = "PRE_1630_TEST"

                elif market_type == "US_EQUITY":
                    local_dt = last_dt.astimezone(native_tz) if last_dt.tzinfo else native_tz.localize(last_dt)
                    record["market_as_of_date"] = local_dt.strftime("%Y-%m-%d")
                    kst_close_dt = local_dt.astimezone(KST_TZ)
                    record["actual_as_of_kst"] = f"{kst_close_dt.strftime('%Y-%m-%d')} 05:00 KST (미국 정규장 마감)"
                    record["raw_source_timestamp"] = str(last_dt)
                    record["session_type"] = f"직전 확정종가 ({record['market_as_of_date']} 미국 마감)"
                    record["validation_status"] = "DAILY_CONFIRMED" if is_post_1630 else "PRE_1630_TEST"

                elif market_type == "EU_EQUITY":
                    if last_dt.strftime("%Y-%m-%d") == report_date and len(hist) >= 3:
                        curr_val = float(hist['Close'].iloc[-2])
                        prev_val = float(hist['Close'].iloc[-3])
                        last_dt = hist.index[-2]
                    local_dt = last_dt.astimezone(native_tz) if last_dt.tzinfo else native_tz.localize(last_dt)
                    record["market_as_of_date"] = local_dt.strftime("%Y-%m-%d")
                    record["actual_as_of_kst"] = f"{local_dt.strftime('%Y-%m-%d')} 01:30 KST (유럽 정규장 마감)"
                    record["raw_source_timestamp"] = str(last_dt)
                    record["session_type"] = f"직전 확정종가 ({record['market_as_of_date']} 유럽 마감)"
                    record["validation_status"] = "DAILY_CONFIRMED" if is_post_1630 else "PRE_1630_TEST"

                chg = curr_val - prev_val
                pct_chg = (chg / prev_val) * 100.0 if prev_val != 0 else 0.0

                record["current"] = curr_val
                record["prev"] = prev_val
                record["change"] = chg
                record["pct_change"] = pct_chg
                record["message"] = "정상 수집"

            except Exception as e:
                record["validation_status"] = "ERROR"
                record["message"] = str(e)

            results.append(record)

        return results
