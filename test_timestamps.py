import yfinance as yf
import datetime
import pytz

tickers = ['KRW=X', 'CL=F', '^HSI', '^KS11', '^GSPC', 'DX-Y.NYB', 'US2Y']

print("Testing raw timestamps from Yahoo Finance...")
for sym in tickers[:6]:
    t = yf.Ticker(sym)
    
    # 1. 1-minute recent history
    try:
        h_1m = t.history(period="1d", interval="1m")
        if len(h_1m) > 0:
            last_ts = h_1m.index[-1]
            last_ts_kst = last_ts.astimezone(pytz.timezone('Asia/Seoul'))
            print(f"[{sym}] 1m Intraday Tick: raw={last_ts}, KST={last_ts_kst.strftime('%Y-%m-%d %H:%M:%S KST')}, Close={h_1m['Close'].iloc[-1]}")
        else:
            print(f"[{sym}] 1m Intraday: EMPTY")
    except Exception as e:
        print(f"[{sym}] 1m Intraday Error: {e}")

    # 2. Daily history
    try:
        h_1d = t.history(period="5d", interval="1d")
        last_d = h_1d.index[-1]
        print(f"[{sym}] 1d Daily: raw={last_d}, date_str={last_d.strftime('%Y-%m-%d')}, Close={h_1d['Close'].iloc[-1]}")
    except Exception as e:
        print(f"[{sym}] 1d Daily Error: {e}")
    print("-" * 50)
