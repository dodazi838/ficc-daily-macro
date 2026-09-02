import yfinance as yf

tickers = {
    'KOSPI': '^KS11',
    'KOSDAQ': '^KQ11',
    'VIX': '^VIX',
    'S&P 500': '^GSPC',
    'DJI': '^DJI',
    'NASDAQ': '^IXIC',
    'Shanghai': '000001.SS',
    'HangSeng': '^HSI',
    'Nikkei': '^N225',
    'EuroStoxx50': '^STOXX50E',
    'DXY': 'DX-Y.NYB',
    'USD/KRW': 'KRW=X',
    'USD/JPY': 'JPY=X',
    'USD/CNH (CNH=F)': 'CNH=F',
    'USD/CNH (USDCNH=X)': 'USDCNH=X',
    'USD/CNH (CNH=X)': 'CNH=X',
    'EUR/USD': 'EURUSD=X',
    'GBP/USD': 'GBPUSD=X',
    'US_2Y (2YY=F)': '2YY=F',
    'US_2Y (^TWO)': '^TWO',
    'US_10Y (^TNX)': '^TNX',
    'JP_10Y (^JP10YT)': '^JP10YT',
    'JP_10Y (JP10YT=RR)': 'JP10YT=RR',
    'DE_10Y (^DE10YT)': '^DE10YT',
    'DE_10Y (DE10YT=RR)': 'DE10YT=RR',
    'WTI': 'CL=F',
    'Brent': 'BZ=F',
    'Gold': 'GC=F',
    'Silver': 'SI=F',
    'Copper': 'HG=F',
    'NatGas': 'NG=F'
}

for k, sym in tickers.items():
    try:
        h = yf.Ticker(sym).history(period='5d')
        if len(h) >= 2:
            last = h['Close'].iloc[-1]
            prev = h['Close'].iloc[-2]
            pct = (last - prev) / prev * 100
            print(f"{k:20} | {sym:12} | OK: Last={last:.4f} (Chg {pct:+.2f}%) | Date={h.index[-1].strftime('%Y-%m-%d')}")
        elif len(h) == 1:
            last = h['Close'].iloc[-1]
            print(f"{k:20} | {sym:12} | 1-Day: Last={last:.4f} | Date={h.index[-1].strftime('%Y-%m-%d')}")
        else:
            print(f"{k:20} | {sym:12} | EMPTY (No Data)")
    except Exception as e:
        print(f"{k:20} | {sym:12} | ERROR: {e}")
