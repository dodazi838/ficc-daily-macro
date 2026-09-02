import requests
from bs4 import BeautifulSoup
import yfinance as yf
import pandas as pd

def test_fetch():
    print("Testing yfinance...")
    tickers = {
        "KOSPI": "^KS11",
        "KOSDAQ": "^KQ11",
        "S&P 500": "^GSPC",
        "NASDAQ": "^IXIC",
        "Nikkei 225": "^N225",
        "USD/KRW": "KRW=X",
        "DXY": "DX-Y.NYB",
        "USD/JPY": "JPY=X",
        "EUR/USD": "EURUSD=X",
        "US 10Y Yield": "^TNX",
        "US 2Y Yield": "2YY=F",
        "WTI Crude": "CL=F",
        "Gold": "GC=F",
        "Copper": "HG=F"
    }
    
    for name, sym in tickers.items():
        try:
            t = yf.Ticker(sym)
            hist = t.history(period="5d")
            if len(hist) >= 2:
                last_val = hist['Close'].iloc[-1]
                prev_val = hist['Close'].iloc[-2]
                change = last_val - prev_val
                pct = (change / prev_val) * 100
                print(f"[{name}] {last_val:.2f} (chg: {change:+.2f}, {pct:+.2f}%)")
            elif len(hist) == 1:
                last_val = hist['Close'].iloc[-1]
                print(f"[{name}] {last_val:.2f} (only 1 day data)")
            else:
                print(f"[{name}] No data found for {sym}")
        except Exception as e:
            print(f"[{name}] Error: {e}")

    print("\nTesting Naver Finance Korean Bond Scraping...")
    # Naver Market Index: KTB 3Y and 10Y
    # URL: https://finance.naver.com/marketindex/interestDailyQuote.naver?marketindexCd=IRGD_KTB3Y
    # URL: https://finance.naver.com/marketindex/interestDailyQuote.naver?marketindexCd=IRGD_KTB10Y
    headers = {"User-Agent": "Mozilla/5.0"}
    for bond_cd, name in [("IRGD_KTB3Y", "국고채 3년"), ("IRGD_KTB10Y", "국고채 10년")]:
        try:
            url = f"https://finance.naver.com/marketindex/interestDailyQuote.naver?marketindexCd={bond_cd}"
            resp = requests.get(url, headers=headers)
            soup = BeautifulSoup(resp.text, "html.parser")
            table = soup.find("table", class_="tbl_type")
            rows = table.find_all("tr")
            # First row with data
            first_data_row = None
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 3:
                    date = cols[0].text.strip()
                    val = float(cols[1].text.strip())
                    chg_text = cols[2].text.strip()
                    img = cols[2].find("img")
                    sign = 1
                    if img and "down" in img.get("src", ""):
                        sign = -1
                    chg_val = float(chg_text) * sign
                    first_data_row = (date, val, chg_val)
                    break
            if first_data_row:
                bp_chg = first_data_row[2] * 100
                print(f"[{name}] Date: {first_data_row[0]}, Yield: {first_data_row[1]:.3f}%, Change: {first_data_row[2]:+.3f}%p ({bp_chg:+.1f} bp)")
        except Exception as e:
            print(f"[{name}] Naver scrape error: {e}")

if __name__ == "__main__":
    test_fetch()
