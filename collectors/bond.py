"""
[FICC Daily Macro] 국내외 국채 벤치마크 6개 지표 수집기
- 한국 국고채 3Y, 10Y: KOFIA(금융투자협회) 공식 XML 서비스
- 미국 국채 2Y, 10Y / 일본 국채 10Y / 독일 국채 10Y: CNBC Quote API
"""

import datetime
import dateutil.parser
import pytz
import requests
import xml.etree.ElementTree as ET
from typing import List, Dict, Any
from collectors.base import BaseCollector
from config.settings import BOND_INDICATORS, TARGET_DAILY_TIME_STR, KST_TZ
from config.holidays import is_us_bond_holiday

class BondCollector(BaseCollector):
    """국내 및 글로벌 벤치마크 국채 금리 수집기"""

    def __init__(self):
        super().__init__(name="BondCollector")
        self.indicators = BOND_INDICATORS

    def collect(self, run_time_kst: datetime.datetime, is_post_1630: bool) -> List[Dict[str, Any]]:
        korean_results = self._fetch_kofia_bonds(run_time_kst, is_post_1630)
        global_results = self._fetch_cnbc_bonds(run_time_kst, is_post_1630)

        # 6개 표준 순서대로 정렬하여 반환
        ordered_results = []
        for item in self.indicators:
            name = item["name"]
            if name in korean_results:
                ordered_results.append(korean_results[name])
            elif name in global_results:
                ordered_results.append(global_results[name])
            else:
                # 혹시 모를 누락 시 빈 레코드 추가
                empty_rec = self.create_empty_record(item, run_time_kst, data_source=item.get("source", "UNKNOWN"))
                empty_rec["message"] = "데이터 수집 실패"
                ordered_results.append(empty_rec)

        return ordered_results

    def _fetch_kofia_bonds(self, run_time_kst: datetime.datetime, is_post_1630: bool) -> Dict[str, Dict[str, Any]]:
        """KOFIA 공식 XML 서비스로부터 한국 국고채 3Y, 10Y 최종호가수익률 수집"""
        report_date = run_time_kst.strftime("%Y-%m-%d")
        run_time_str = run_time_kst.strftime("%Y-%m-%d %H:%M:%S KST")
        url = "https://www.kofiabond.or.kr/proframeWeb/XMLSERVICES/"
        headers = {
            "Content-Type": "application/xml; charset=UTF-8",
            "User-Agent": "Mozilla/5.0"
        }

        results = {}
        for name, eng_key in [("한국 국고채 3년", "KTB 3y"), ("한국 국고채 10년", "KTB10y")]:
            results[name] = {
                "category": "BOND",
                "name": name,
                "symbol": eng_key,
                "unit": "%",
                "report_date": report_date,
                "target_time_kst": TARGET_DAILY_TIME_STR,
                "run_time_kst": run_time_str,
                "market_as_of_date": "N/A",
                "actual_as_of_kst": "N/A",
                "raw_source_timestamp": "PROVIDER_TIMESTAMP_UNAVAILABLE",
                "price_type": "최종호가수익률 (KOFIA/민평)",
                "session_type": "16:30 미고시 상태",
                "data_source": "KOFIA 공식 XML",
                "current": None,
                "prev": None,
                "change": None,
                "pct_change": None,
                "bp_change": None,
                "validation_status": "DELAYED",
                "message": "데이터 미고시/탐색 중"
            }

        # 최근 7영업일 역순 탐색
        for offset in range(7):
            query_date = run_time_kst - datetime.timedelta(days=offset)
            if query_date.weekday() >= 5:  # 주말 제외
                continue
            date_str = query_date.strftime("%Y%m%d")
            xml_data = f"""<message>
                <proframeHeader>
                    <pfmAppName>BIS-KOFIABOND</pfmAppName>
                    <pfmSvcName>BISLastAskPrcROPSrchSO</pfmSvcName>
                    <pfmFnName>listDay</pfmFnName>
                </proframeHeader>
                <systemHeader></systemHeader>
                <BISComDspDatDTO>
                    <val1>{date_str}</val1>
                </BISComDspDatDTO>
            </message>"""

            try:
                resp = requests.post(url, data=xml_data.encode('utf-8'), headers=headers, timeout=5)
                if resp.status_code == 200 and "<BISComDspDatDTO>" in resp.text:
                    root = ET.fromstring(resp.text)
                    items = root.findall(".//BISComDspDatDTO")

                    found_valid = False
                    for item in items:
                        eng_tag = item.find("val9")
                        curr_tag = item.find("val4")
                        prev_tag = item.find("val6")

                        eng_name = eng_tag.text.strip() if eng_tag is not None and eng_tag.text else ""

                        if curr_tag is not None and curr_tag.text and curr_tag.text.strip() != "":
                            try:
                                curr_val = float(curr_tag.text.strip())
                                prev_val = float(prev_tag.text.strip()) if prev_tag is not None and prev_tag.text else curr_val
                                chg_p = curr_val - prev_val
                                bp_chg = chg_p * 100.0
                                pct_chg = (chg_p / prev_val * 100.0) if prev_val != 0 else 0.0

                                target_name = None
                                if "KTB 3y" in eng_name:
                                    target_name = "한국 국고채 3년"
                                elif "KTB10y" in eng_name:
                                    target_name = "한국 국고채 10년"

                                if target_name:
                                    is_today = (query_date.strftime('%Y-%m-%d') == report_date)

                                    if is_today and is_post_1630:
                                        session_desc = "당일 확정고시 (16:30 최종호가)"
                                        val_st = "DAILY_CONFIRMED"
                                    elif is_today and not is_post_1630:
                                        session_desc = "당일 장중 고시 (16:30 이전 미확정)"
                                        val_st = "PRE_1630_TEST"
                                    else:
                                        session_desc = f"직전 확정고시 ({query_date.strftime('%Y-%m-%d')} 16:30 발표치)"
                                        val_st = "PRE_1630_TEST"

                                    results[target_name] = {
                                        "category": "BOND",
                                        "name": target_name,
                                        "symbol": eng_name,
                                        "unit": "%",
                                        "report_date": report_date,
                                        "target_time_kst": TARGET_DAILY_TIME_STR,
                                        "run_time_kst": run_time_str,
                                        "market_as_of_date": query_date.strftime("%Y-%m-%d"),
                                        "actual_as_of_kst": f"{query_date.strftime('%Y-%m-%d')} 16:30:00 KST (공식고시)",
                                        "raw_source_timestamp": date_str,
                                        "price_type": "최종호가수익률 (KOFIA/민평)",
                                        "market_status": "CLOSED" if (is_today and is_post_1630) else "INTRADAY",
                                        "current": curr_val,
                                        "prev": prev_val,
                                        "change": chg_p,
                                        "pct_change": pct_chg,
                                        "bp_change": bp_chg,
                                        "session_type": session_desc,
                                        "data_source": "KOFIA 공식 XML",
                                        "is_holiday": False,
                                        "holiday_name": None,
                                        "return_basis": "DAILY",
                                        "validation_status": val_st,
                                        "message": "고시 확인" if is_today else "당일 16:30 미고시로 직전일 고시값 사용"
                                    }
                                    found_valid = True
                            except ValueError:
                                continue
                    if found_valid:
                        break
            except Exception:
                continue

        return results

    def _fetch_cnbc_bonds(self, run_time_kst: datetime.datetime, is_post_1630: bool) -> Dict[str, Dict[str, Any]]:
        """CNBC Quote API로부터 글로벌 벤치마크 국채 수익률 수집"""
        report_date = run_time_kst.strftime("%Y-%m-%d")
        run_time_str = run_time_kst.strftime("%Y-%m-%d %H:%M:%S KST")

        symbols = {
            "미국 국채 2년": {"cnbc_sym": "US2Y", "market_type": "US_BOND", "tz": "America/New_York"},
            "미국 국채 10년": {"cnbc_sym": "US10Y", "market_type": "US_BOND", "tz": "America/New_York"},
            "일본 국채 10년": {"cnbc_sym": "JP10Y-JP", "market_type": "JP_BOND", "tz": "Asia/Tokyo"},
            "독일 국채 10년": {"cnbc_sym": "DE10Y-DE", "market_type": "DE_BOND", "tz": "Europe/Berlin"}
        }

        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        url = f"https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?symbols={'|'.join([v['cnbc_sym'] for v in symbols.values()])}&requestMethod=itv&output=json"

        results = {}
        try:
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                quotes = resp.json().get('FormattedQuoteResult', {}).get('FormattedQuote', [])
                for q in quotes:
                    sym = q.get('symbol')
                    matched_name = None
                    matched_meta = None
                    for name, meta in symbols.items():
                        if meta["cnbc_sym"] == sym:
                            matched_name = name
                            matched_meta = meta
                            break

                    if matched_name:
                        last_str = q.get('last', '').replace('%', '')
                        prev_str = q.get('previous_day_closing', '').replace('%', '')
                        raw_time = q.get('last_time', '')

                        record = {
                            "category": "BOND",
                            "name": matched_name,
                            "symbol": sym,
                            "unit": "%",
                            "report_date": report_date,
                            "target_time_kst": TARGET_DAILY_TIME_STR,
                            "run_time_kst": run_time_str,
                            "market_as_of_date": "N/A",
                            "actual_as_of_kst": "N/A",
                            "raw_source_timestamp": raw_time if raw_time else "PROVIDER_TIMESTAMP_UNAVAILABLE",
                            "price_type": "Benchmark Cash Yield",
                            "market_status": "INTRADAY",
                            "session_type": "",
                            "data_source": "CNBC Quote API",
                            "is_holiday": False,
                            "holiday_name": None,
                            "return_basis": "DAILY",
                            "current": None,
                            "prev": None,
                            "change": None,
                            "pct_change": None,
                            "bp_change": None,
                            "validation_status": "ERROR",
                            "message": ""
                        }

                        if last_str and prev_str:
                            curr_yield = float(last_str)
                            prev_yield = float(prev_str)
                            chg_p = curr_yield - prev_yield
                            bp_chg = chg_p * 100.0
                            pct_chg = (chg_p / prev_yield * 100.0) if prev_yield != 0 else 0.0

                            record["current"] = curr_yield
                            record["prev"] = prev_yield
                            record["change"] = chg_p
                            record["bp_change"] = bp_chg
                            record["pct_change"] = pct_chg

                            m_tz = pytz.timezone(matched_meta["tz"])
                            if raw_time:
                                try:
                                    dt = dateutil.parser.parse(raw_time)
                                    local_dt = dt.astimezone(m_tz)
                                    record["market_as_of_date"] = local_dt.strftime("%Y-%m-%d")
                                    kst_dt = dt.astimezone(KST_TZ)
                                    record["actual_as_of_kst"] = kst_dt.strftime("%Y-%m-%d %H:%M:%S KST")
                                except Exception:
                                    record["market_as_of_date"] = raw_time[:10]
                                    record["actual_as_of_kst"] = raw_time

                            m_type = matched_meta["market_type"]
                            record["is_holiday"] = False
                            record["holiday_name"] = None
                            record["return_basis"] = "DAILY"

                            if m_type == "US_BOND":
                                us_current_date = run_time_kst.astimezone(m_tz).date()
                                is_holiday, holiday_name = is_us_bond_holiday(us_current_date)
                                record["is_holiday"] = is_holiday
                                record["holiday_name"] = holiday_name
                                if is_holiday:
                                    record["session_type"] = f"미국 국채시장 휴장 ({holiday_name}) 직전 종가"
                                    record["price_type"] = "PREVIOUS_CLOSE"
                                    record["market_status"] = "MARKET_CLOSED"
                                    record["return_basis"] = "PREVIOUS_TRADING_DAY"
                                    record["validation_status"] = "DAILY_CONFIRMED"
                                else:
                                    is_us_bond_open = (run_time_kst.hour >= 21 or run_time_kst.hour < 6)
                                    if is_us_bond_open:
                                        record["session_type"] = "미국 국채 정규장 실시간 호가"
                                        record["price_type"] = "Benchmark Cash Yield"
                                        record["market_status"] = "INTRADAY"
                                        record["return_basis"] = "INTRADAY"
                                        record["validation_status"] = "DAILY_CONFIRMED"
                                    else:
                                        record["session_type"] = f"직전 확정종가 ({record['market_as_of_date']} 미국 마감)"
                                        record["price_type"] = "PREVIOUS_CLOSE"
                                        record["market_status"] = "CLOSED"
                                        record["return_basis"] = "PREVIOUS_TRADING_DAY"
                                        record["validation_status"] = "DAILY_CONFIRMED" if is_post_1630 else "PRE_1630_TEST"
                            elif m_type == "DE_BOND":
                                # 독일/유럽 국채 거래 시간: 프랑크푸르트 기준 08:00 ~ 17:30 CEST (KST 15:00 ~ 익일 00:30)
                                is_de_open = (15 <= run_time_kst.hour <= 23) or (run_time_kst.hour == 0 and run_time_kst.minute <= 30)
                                is_de_closed = not is_de_open
                                record["is_holiday"] = False
                                record["holiday_name"] = None
                                if is_de_closed:
                                    record["market_status"] = "CLOSED"
                                    record["price_type"] = "PREVIOUS_CLOSE"
                                    record["return_basis"] = "DAILY"
                                    record["session_type"] = f"직전 확정종가 ({record['market_as_of_date']} 유럽 마감)"
                                    record["validation_status"] = "DAILY_CONFIRMED" if is_post_1630 else "PRE_1630_TEST"
                                else:
                                    record["market_status"] = "INTRADAY"
                                    record["price_type"] = "Benchmark Cash Yield"
                                    record["return_basis"] = "INTRADAY"
                                    record["session_type"] = "유럽 국채 정규장 실시간 호가"
                                    record["validation_status"] = "DAILY_CONFIRMED" if is_post_1630 else "PRE_1630_TEST"
                            elif m_type == "JP_BOND":
                                is_jp_closed = (run_time_kst.hour >= 15)
                                record["is_holiday"] = False
                                record["holiday_name"] = None
                                if is_jp_closed:
                                    record["session_type"] = f"당일 확정종가 ({record['market_as_of_date']} 도쿄 마감)"
                                    record["price_type"] = "PREVIOUS_CLOSE"
                                    record["market_status"] = "CLOSED"
                                    record["return_basis"] = "DAILY"
                                    record["validation_status"] = "DAILY_CONFIRMED" if is_post_1630 else "PRE_1630_TEST"
                                else:
                                    record["session_type"] = f"당일 장중 금리 ({run_time_kst.strftime('%H:%M')} 미확정)"
                                    record["price_type"] = "Benchmark Cash Yield"
                                    record["market_status"] = "INTRADAY"
                                    record["return_basis"] = "INTRADAY"
                                    record["validation_status"] = "PRE_1630_TEST"

                            results[matched_name] = record
                        else:
                            m_type = matched_meta["market_type"]
                            if m_type == "US_BOND":
                                m_tz = pytz.timezone(matched_meta["tz"])
                                us_current_date = run_time_kst.astimezone(m_tz).date()
                                is_holiday, holiday_name = is_us_bond_holiday(us_current_date)
                                record["is_holiday"] = is_holiday
                                record["holiday_name"] = holiday_name
                                if is_holiday:
                                    record["session_type"] = f"미국 국채시장 휴장 ({holiday_name}) 직전 종가"
                                    record["price_type"] = "PREVIOUS_CLOSE"
                                    record["market_status"] = "MARKET_CLOSED"
                                    record["return_basis"] = "PREVIOUS_TRADING_DAY"
                                    record["validation_status"] = "DAILY_CONFIRMED"
                            results[matched_name] = record

        except Exception as e:
            for name, meta in symbols.items():
                m_tz = pytz.timezone(meta["tz"])
                m_type = meta["market_type"]
                is_hol = False
                hol_name = None
                ret_basis = "DAILY"
                m_status = "CLOSED"
                p_type = "PREVIOUS_CLOSE"
                s_type = "수집 오류"

                if m_type == "US_BOND":
                    us_current_date = run_time_kst.astimezone(m_tz).date()
                    is_hol, hol_name = is_us_bond_holiday(us_current_date)
                    if is_hol:
                        s_type = f"미국 국채시장 휴장 ({hol_name}) 직전 종가"
                        p_type = "PREVIOUS_CLOSE"
                        m_status = "MARKET_CLOSED"
                        ret_basis = "PREVIOUS_TRADING_DAY"
                    else:
                        m_status = "INTRADAY" if (run_time_kst.hour >= 21 or run_time_kst.hour < 6) else "CLOSED"
                        ret_basis = "INTRADAY" if m_status == "INTRADAY" else "PREVIOUS_TRADING_DAY"
                        p_type = "Benchmark Cash Yield" if m_status == "INTRADAY" else "PREVIOUS_CLOSE"

                results[name] = {
                    "category": "BOND",
                    "name": name,
                    "symbol": meta["cnbc_sym"],
                    "unit": "%",
                    "report_date": report_date,
                    "target_time_kst": TARGET_DAILY_TIME_STR,
                    "run_time_kst": run_time_str,
                    "market_as_of_date": "N/A",
                    "actual_as_of_kst": "N/A",
                    "raw_source_timestamp": "PROVIDER_TIMESTAMP_UNAVAILABLE",
                    "price_type": p_type,
                    "market_status": m_status,
                    "session_type": s_type,
                    "data_source": "CNBC Quote API",
                    "is_holiday": is_hol,
                    "holiday_name": hol_name,
                    "return_basis": ret_basis,
                    "current": None,
                    "prev": None,
                    "change": None,
                    "pct_change": None,
                    "bp_change": None,
                    "validation_status": "DAILY_CONFIRMED" if is_hol else "ERROR",
                    "message": str(e)
                }

        return results
