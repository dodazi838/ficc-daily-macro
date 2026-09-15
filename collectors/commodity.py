"""
[FICC Daily Macro] 주요 원자재(Commodities) 6개 지표 수집기
"""

import pytz
import yfinance as yf
from datetime import datetime
from typing import List, Dict, Any
from collectors.base import BaseCollector
from config.settings import COMMODITY_INDICATORS, KST_TZ

class CommodityCollector(BaseCollector):
    """주요 원자재(에너지, 귀금속, 산업용금속) 6개 지표 수집기"""

    def __init__(self):
        super().__init__(name="CommodityCollector")
        self.indicators = COMMODITY_INDICATORS

    def _collect_single(self, item: Dict[str, Any], run_time_kst: datetime, is_post_1630: bool) -> Dict[str, Any]:
        run_time_str = run_time_kst.strftime("%Y-%m-%d %H:%M:%S KST")
        record = self.create_empty_record(item, run_time_kst, data_source="Yahoo Finance")
        sym = item["symbol"]
        native_tz = pytz.timezone(item.get("tz", "UTC"))

        try:
            t = yf.Ticker(sym)
            hist = t.history(period="10d", interval="1d")

            if len(hist) < 2:
                record["validation_status"] = "DELAYED"
                record["message"] = f"조회된 일봉 데이터 부족 ({len(hist)}일)"
                return record

            last_dt = hist.index[-1]
            prev_dt = hist.index[-2]
            curr_val = float(hist['Close'].iloc[-1])
            prev_val = float(hist['Close'].iloc[-2])

            # 장중 1분봉 실시간 스냅샷 확인
            intraday_ts_kst = None
            raw_intraday_ts = None
            try:
                h_1m = t.history(period="1d", interval="1m")
                if len(h_1m) > 0:
                    raw_intraday_ts = h_1m.index[-1]
                    intraday_ts_kst = raw_intraday_ts.astimezone(KST_TZ)
                    curr_val = float(h_1m['Close'].iloc[-1])
            except Exception:
                pass

            local_dt = last_dt.astimezone(native_tz) if last_dt.tzinfo else native_tz.localize(last_dt)
            record["market_as_of_date"] = local_dt.strftime("%Y-%m-%d")

            tick_str = intraday_ts_kst.strftime('%Y-%m-%d %H:%M:%S KST') if intraday_ts_kst else f"{run_time_str} (근사)"
            record["actual_as_of_kst"] = tick_str
            record["raw_source_timestamp"] = str(raw_intraday_ts) if raw_intraday_ts else str(last_dt)

            from config.holidays import is_us_equity_holiday
            us_date = run_time_kst.astimezone(native_tz).date()
            is_holiday, holiday_name = is_us_equity_holiday(us_date)
            record["is_holiday"] = is_holiday
            record["holiday_name"] = holiday_name

            chg = curr_val - prev_val
            pct_chg = (chg / prev_val) * 100.0 if prev_val != 0 else 0.0

            # 0.00%의 의미 구분: 실제 확인된 0% 변동인지, 휴장/데이터 미제공(UNAVAILABLE)인지 구분
            if abs(chg) < 1e-6:
                if is_holiday:
                    record["current"] = curr_val
                    record["prev"] = prev_val
                    record["change"] = None
                    record["pct_change"] = None
                    record["change_status"] = "UNAVAILABLE"
                    record["market_status"] = "MARKET_CLOSED"
                    record["price_type"] = "PREVIOUS_CLOSE"
                    record["return_basis"] = "PREVIOUS_TRADING_DAY"
                    record["session_type"] = f"미국 휴장({holiday_name})으로 정산가 미발표 (직전 종가 유지)"
                else:
                    record["current"] = curr_val
                    record["prev"] = prev_val
                    record["change"] = 0.0
                    record["pct_change"] = 0.0
                    record["change_status"] = "CONFIRMED"
                    record["market_status"] = "INTRADAY"
                    record["price_type"] = "현재가 (장중)"
                    record["return_basis"] = "INTRADAY"
            else:
                record["current"] = curr_val
                record["prev"] = prev_val
                record["change"] = chg
                record["pct_change"] = pct_chg
                record["change_status"] = "CONFIRMED"
                record["market_status"] = "INTRADAY"
                record["price_type"] = "현재가 (장중)"
                record["return_basis"] = "INTRADAY"

            record["message"] = "정상 수집"

        except Exception as e:
            record["validation_status"] = "ERROR"
            record["change_status"] = "UNAVAILABLE"
            record["message"] = str(e)

        return record

    def collect(self, run_time_kst: datetime, is_post_1630: bool) -> List[Dict[str, Any]]:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=6) as executor:
            results = list(executor.map(lambda item: self._collect_single(item, run_time_kst, is_post_1630), self.indicators))
        return results
