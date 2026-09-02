import datetime
import requests
import xml.etree.ElementTree as ET
import yfinance as yf
import pandas as pd
import json

def test_all_28():
    print("Testing CNBC global benchmark yields...")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    url = 'https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?symbols=US2Y|US10Y|JP10Y-JP|DE10Y-DE&requestMethod=itv&output=json'
    r = requests.get(url, headers=headers, timeout=10)
    print("CNBC Status:", r.status_code)
    if r.status_code == 200:
        quotes = r.json().get('FormattedQuoteResult', {}).get('FormattedQuote', [])
        for q in quotes:
            print(f"CNBC {q.get('symbol')}: name={q.get('name')}, last={q.get('last')}, prev={q.get('previous_day_closing')}, chg={q.get('change')}, last_time={q.get('last_time')}")

    print("\nTesting KOFIA...")
    # KOFIA
    kofia_url = "https://www.kofiabond.or.kr/proframeWeb/XMLSERVICES/"
    today = datetime.datetime.today()
    for offset in range(5):
        q_date = today - datetime.timedelta(days=offset)
        if q_date.weekday() >= 5:
            continue
        d_str = q_date.strftime("%Y%m%d")
        xml_data = f"""<message>
            <proframeHeader>
                <pfmAppName>BIS-KOFIABOND</pfmAppName>
                <pfmSvcName>BISLastAskPrcROPSrchSO</pfmSvcName>
                <pfmFnName>listDay</pfmFnName>
            </proframeHeader>
            <systemHeader></systemHeader>
            <BISComDspDatDTO>
                <val1>{d_str}</val1>
            </BISComDspDatDTO>
        </message>"""
        resp = requests.post(kofia_url, data=xml_data.encode('utf-8'), headers={'Content-Type': 'application/xml; charset=UTF-8'}, timeout=10)
        if resp.status_code == 200 and "<BISComDspDatDTO>" in resp.text:
            root = ET.fromstring(resp.text)
            items = root.findall(".//BISComDspDatDTO")
            if len(items) > 0:
                print(f"KOFIA Date {d_str} success, items={len(items)}")
                for item in items:
                    raw_name = item.find("val1").text if item.find("val1") is not None else ""
                    eng_name = item.find("val9").text if item.find("val9") is not None else ""
                    if "KTB" in eng_name or "국고" in raw_name:
                        curr_val = item.find("val4").text if item.find("val4") is not None else ""
                        prev_val = item.find("val6").text if item.find("val6") is not None else ""
                        print(f"  {raw_name} ({eng_name}): curr={curr_val}%, prev={prev_val}%")
                break

if __name__ == "__main__":
    test_all_28()
