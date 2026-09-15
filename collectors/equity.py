"""
[FICC Daily Macro] 글로벌 주요 증시 10개 지표 수집기
"""

import pytz
import yfinance as yf
from datetime import datetime
from typing import List, Dict, Any
from collectors.base import BaseCollector
from config.settings import EQUITY_INDICATORS, KST_TZ
from config.holidays import is_us_equity_holiday

class EquityCollector(BaseCollector):
    """글로벌 주요 증시 및 변동성 지표(VIX) 수집기"""

    def __init__(self):
        super().__init__(name="EquityCollector")
        self.indicators = EQUITY_INDICATORS

    def _collect_single(self, item: Dict[str, Any], run_time_kst: datetime, is_post_1630: bool) -> Dict[str, Any]:
        report_date = run_time_kst.strftime("%Y-%m-%d")
        record = self.create_empty_record(item, run_time_kst, data_source="Yahoo Finance")
        sym = item["symbol"]
        market_type = item["market_type"]
        native_tz = pytz.timezone(item.get("tz", "UTC"))

        try:
            t = yf.Ticker(sym)
            hist = t.history(period="10d", interval="1d")

            clean_hist = hist.dropna(subset=['Close'])
            if len(clean_hist) < 2:
                record["validation_status"] = "DELAYED"
                record["message"] = f"조회된 유효 일봉 데이터 부족 ({len(clean_hist)}일)"
                return record

            last_dt = clean_hist.index[-1]
            prev_dt = clean_hist.index[-2]
            curr_val = float(clean_hist['Close'].iloc[-1])
            prev_val = float(clean_hist['Close'].iloc[-2])

            # 장중 실시간 시장인지 판정 (마감 확정된 시장은 불필요한 1분봉 추가 조회 안 함)
            intraday_ts_kst = None
            raw_intraday_ts = None
            is_intraday_market = False
            if market_type == "HK_EQUITY":
                is_intraday_market = (10 <= run_time_kst.hour < 17)
            elif market_type == "KR_EQUITY":
                is_intraday_market = (9 <= run_time_kst.hour < 15) or (run_time_kst.hour == 15 and run_time_kst.minute < 30)
            elif market_type == "JP_EQUITY":
                is_intraday_market = (9 <= run_time_kst.hour < 15)
            elif market_type == "US_EQUITY":
                is_intraday_market = (run_time_kst.hour >= 22 or run_time_kst.hour < 6)

            if is_intraday_market:
                try:
                    h_1m = t.history(period="1d", interval="1m")
                    if len(h_1m) > 0:
                        raw_intraday_ts = h_1m.index[-1]
                        intraday_ts_kst = raw_intraday_ts.astimezone(KST_TZ)
                        if market_type == "HK_EQUITY":
                            curr_val = float(h_1m['Close'].iloc[-1])
                except Exception:
                    pass

            record["is_holiday"] = False
            record["holiday_name"] = None
            record["return_basis"] = "DAILY"

            # 시장별 세션 판정 및 price_type / market_status 설정
            if market_type == "KR_EQUITY":
                local_dt = last_dt.astimezone(native_tz) if last_dt.tzinfo else native_tz.localize(last_dt)
                record["market_as_of_date"] = local_dt.strftime("%Y-%m-%d")
                is_kr_open = (9 <= run_time_kst.hour < 15) or (run_time_kst.hour == 15 and run_time_kst.minute < 30)
                is_kr_closed = not is_kr_open
                if is_kr_closed:
                    record["actual_as_of_kst"] = f"{record['market_as_of_date']} 15:30:00 KST (장 마감)"
                    record["raw_source_timestamp"] = str(last_dt)
                    record["session_type"] = "당일 확정종가 (15:30 마감)"
                    record["price_type"] = "종가"
                    record["market_status"] = "CLOSED"
                    record["validation_status"] = "DAILY_CONFIRMED" if is_post_1630 else "PRE_1630_TEST"
                else:
                    tick_str = intraday_ts_kst.strftime('%H:%M:%S') if intraday_ts_kst else run_time_kst.strftime('%H:%M')
                    record["actual_as_of_kst"] = f"{record['market_as_of_date']} {tick_str} KST (장중)"
                    record["raw_source_timestamp"] = str(raw_intraday_ts) if raw_intraday_ts else str(last_dt)
                    record["session_type"] = f"당일 장중 실시간가 ({tick_str} 미확정)"
                    record["price_type"] = "현재가 (장중)"
                    record["market_status"] = "INTRADAY"
                    record["validation_status"] = "PRE_1630_TEST"

            elif market_type == "JP_EQUITY":
                local_dt = last_dt.astimezone(native_tz) if last_dt.tzinfo else native_tz.localize(last_dt)
                record["market_as_of_date"] = local_dt.strftime("%Y-%m-%d")
                is_jp_open = (9 <= run_time_kst.hour < 15)
                is_jp_closed = not is_jp_open
                if is_jp_closed:
                    record["actual_as_of_kst"] = f"{record['market_as_of_date']} 15:00:00 KST (장 마감)"
                    record["raw_source_timestamp"] = str(last_dt)
                    record["session_type"] = "당일 확정종가 (15:00 마감)"
                    record["price_type"] = "종가"
                    record["market_status"] = "CLOSED"
                    record["validation_status"] = "DAILY_CONFIRMED" if is_post_1630 else "PRE_1630_TEST"
                else:
                    tick_str = intraday_ts_kst.strftime('%H:%M:%S') if intraday_ts_kst else run_time_kst.strftime('%H:%M')
                    record["actual_as_of_kst"] = f"{record['market_as_of_date']} {tick_str} KST (장중)"
                    record["raw_source_timestamp"] = str(raw_intraday_ts) if raw_intraday_ts else str(last_dt)
                    record["session_type"] = f"당일 장중 실시간가 ({tick_str} 미확정)"
                    record["price_type"] = "현재가 (장중)"
                    record["market_status"] = "INTRADAY"
                    record["validation_status"] = "PRE_1630_TEST"

            elif market_type == "CN_EQUITY":
                local_dt = last_dt.astimezone(native_tz) if last_dt.tzinfo else native_tz.localize(last_dt)
                record["market_as_of_date"] = local_dt.strftime("%Y-%m-%d")
                is_cn_open = (10 <= run_time_kst.hour < 16)
                is_cn_closed = not is_cn_open
                if is_cn_closed:
                    record["actual_as_of_kst"] = f"{record['market_as_of_date']} 16:00:00 KST (장 마감)"
                    record["raw_source_timestamp"] = str(last_dt)
                    record["session_type"] = "당일 확정종가 (16:00 마감)"
                    record["price_type"] = "종가"
                    record["market_status"] = "CLOSED"
                    record["validation_status"] = "DAILY_CONFIRMED" if is_post_1630 else "PRE_1630_TEST"
                else:
                    tick_str = intraday_ts_kst.strftime('%H:%M:%S') if intraday_ts_kst else run_time_kst.strftime('%H:%M')
                    record["actual_as_of_kst"] = f"{record['market_as_of_date']} {tick_str} KST (장중)"
                    record["raw_source_timestamp"] = str(raw_intraday_ts) if raw_intraday_ts else str(last_dt)
                    record["session_type"] = f"당일 장중 실시간가 ({tick_str} 미확정)"
                    record["price_type"] = "현재가 (장중)"
                    record["market_status"] = "INTRADAY"
                    record["validation_status"] = "PRE_1630_TEST"

            elif market_type == "HK_EQUITY":
                local_dt = last_dt.astimezone(native_tz) if last_dt.tzinfo else native_tz.localize(last_dt)
                record["market_as_of_date"] = local_dt.strftime("%Y-%m-%d")
                is_hk_open = (10 <= run_time_kst.hour < 17)
                is_hk_closed = not is_hk_open
                if is_hk_closed:
                    record["actual_as_of_kst"] = f"{record['market_as_of_date']} 17:00:00 KST (장 마감)"
                    record["raw_source_timestamp"] = str(last_dt)
                    record["session_type"] = "당일 확정종가 (17:00 마감)"
                    record["price_type"] = "종가"
                    record["market_status"] = "CLOSED"
                    record["validation_status"] = "DAILY_CONFIRMED" if is_post_1630 else "PRE_1630_TEST"
                else:
                    tick_str = intraday_ts_kst.strftime('%H:%M:%S') if intraday_ts_kst else run_time_kst.strftime('%H:%M')
                    record["actual_as_of_kst"] = f"{record['market_as_of_date']} {tick_str} KST (장중)"
                    record["raw_source_timestamp"] = str(raw_intraday_ts) if raw_intraday_ts else str(last_dt)
                    record["session_type"] = f"당일 장중 실시간가 ({tick_str} 미확정)"
                    record["price_type"] = "현재가 (장중)"
                    record["market_status"] = "INTRADAY"
                    record["validation_status"] = "PRE_1630_TEST"

            elif market_type == "US_EQUITY":
                local_dt = last_dt.astimezone(native_tz) if last_dt.tzinfo else native_tz.localize(last_dt)
                record["market_as_of_date"] = local_dt.strftime("%Y-%m-%d")

                us_current_date = run_time_kst.astimezone(native_tz).date()
                is_holiday, holiday_name = is_us_equity_holiday(us_current_date)
                record["is_holiday"] = is_holiday
                record["holiday_name"] = holiday_name

                if is_holiday:
                    record["session_type"] = f"미국 증시 휴장 ({holiday_name}) 직전 확정종가"
                    record["price_type"] = "PREVIOUS_CLOSE"
                    record["market_status"] = "MARKET_CLOSED"
                    record["return_basis"] = "PREVIOUS_TRADING_DAY"
                    record["validation_status"] = "DAILY_CONFIRMED"
                    record["actual_as_of_kst"] = f"{record['market_as_of_date']} 05:00:00 KST (미국 마감)"
                    record["raw_source_timestamp"] = str(last_dt)
                else:
                    is_us_open = (run_time_kst.hour >= 22 or run_time_kst.hour < 6)
                    if is_us_open:
                        tick_str = intraday_ts_kst.strftime('%H:%M:%S') if intraday_ts_kst else run_time_kst.strftime('%H:%M')
                        record["actual_as_of_kst"] = f"{record['market_as_of_date']} {tick_str} KST (장중)"
                        record["raw_source_timestamp"] = str(raw_intraday_ts) if raw_intraday_ts else str(last_dt)
                        record["session_type"] = "미국 정규장 실시간가"
                        record["price_type"] = "현재가 (장중)"
                        record["market_status"] = "INTRADAY"
                        record["return_basis"] = "INTRADAY"
                        record["validation_status"] = "DAILY_CONFIRMED"
                    else:
                        record["actual_as_of_kst"] = f"{record['market_as_of_date']} 05:00:00 KST (미국 마감)"
                        record["raw_source_timestamp"] = str(last_dt)
                        record["session_type"] = f"직전 확정종가 ({record['market_as_of_date']} 미국 마감)"
                        record["price_type"] = "PREVIOUS_CLOSE"
                        record["market_status"] = "CLOSED"
                        record["return_basis"] = "PREVIOUS_TRADING_DAY"
                        record["validation_status"] = "DAILY_CONFIRMED" if is_post_1630 else "PRE_1630_TEST"

            elif market_type == "VOLATILITY":
                local_dt = last_dt.astimezone(native_tz) if last_dt.tzinfo else native_tz.localize(last_dt)
                record["market_as_of_date"] = local_dt.strftime("%Y-%m-%d")
                record["actual_as_of_kst"] = f"{local_dt.strftime('%Y-%m-%d')} 05:15:00 KST (Cboe 마감)"
                record["raw_source_timestamp"] = str(last_dt)
                record["session_type"] = f"직전 확정종가 ({record['market_as_of_date']} Cboe 마감)"
                record["price_type"] = "종가"
                record["market_status"] = "CLOSED"
                record["validation_status"] = "DAILY_CONFIRMED" if is_post_1630 else "PRE_1630_TEST"

            elif market_type == "EU_EQUITY":
                local_dt = last_dt.astimezone(native_tz) if last_dt.tzinfo else native_tz.localize(last_dt)
                record["market_as_of_date"] = local_dt.strftime("%Y-%m-%d")
                record["actual_as_of_kst"] = f"{local_dt.strftime('%Y-%m-%d')} 01:30 KST (유럽 정규장 마감)"
                record["raw_source_timestamp"] = str(last_dt)
                record["session_type"] = f"직전 확정종가 ({record['market_as_of_date']} 유럽 마감)"
                record["price_type"] = "종가"
                record["market_status"] = "CLOSED"
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

        return record

    def collect(self, run_time_kst: datetime, is_post_1630: bool) -> List[Dict[str, Any]]:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=6) as executor:
            results = list(executor.map(lambda item: self._collect_single(item, run_time_kst, is_post_1630), self.indicators))
        return results
