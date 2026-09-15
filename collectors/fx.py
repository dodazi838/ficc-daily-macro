"""
[FICC Daily Macro] 글로벌 외환(FX) 6개 지표 수집기
"""

import pytz
import yfinance as yf
from datetime import datetime
from typing import List, Dict, Any
from collectors.base import BaseCollector
from config.settings import FX_INDICATORS, KST_TZ

class FxCollector(BaseCollector):
    """글로벌 외환(FX) 6개 지표 수집기"""

    def __init__(self):
        super().__init__(name="FxCollector")
        self.indicators = FX_INDICATORS

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

            record["market_status"] = "INTRADAY"
            if sym == "KRW=X":
                is_seoul_open = (
                    (9 <= run_time_kst.hour < 15)
                    or (run_time_kst.hour == 15 and run_time_kst.minute < 30)
                )
                if is_seoul_open:
                    record["price_type"] = "서울 외환시장 현재환율"
                    record["session_type"] = "서울 외환시장 정규장 실시간가"
                    record["validation_status"] = "PRE_1630_TEST"
                else:
                    record["price_type"] = "장외/글로벌 현재환율"
                    record["session_type"] = "글로벌 장외 실시간 환율 (Offshore Spot)"
                    record["seoul_close"] = prev_val
                    record["validation_status"] = "DAILY_CONFIRMED"
            else:
                record["price_type"] = "장외/글로벌 현재환율"
                if is_post_1630:
                    record["session_type"] = "16:30 실시간 스냅샷 (Spot/Index)"
                    record["validation_status"] = "DAILY_CONFIRMED"
                else:
                    time_part = intraday_ts_kst.strftime('%H:%M') if intraday_ts_kst else run_time_kst.strftime('%H:%M')
                    record["session_type"] = f"장중 실시간 스냅샷 ({time_part} KST, 16:30 이전)"
                    record["validation_status"] = "PRE_1630_TEST"

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
