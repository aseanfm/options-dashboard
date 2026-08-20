# -*- coding: utf-8 -*-
"""
美股期权数据抓取: S&P500 / Nasdaq100 / Russell2000
  - ETF期权: SPY / QQQ / IWM
  - 指数期权(现金交割): _SPX / _NDX / _RUT
  - 期货期权: 见 cme_fetch(CME官网, 本脚本不含)
数据源: CBOE 官方延迟行情 CDN (cdn.cboe.com, 延迟~15分钟, 含 bid/ask/IV/希腊字母/持仓量)
输出: us_data.json (与脚本同目录)
"""
import json, re, os, sys, time
from datetime import date, datetime, timezone, timedelta
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'us_data.json')
H = {'User-Agent': 'Mozilla/5.0'}
ET = timezone(timedelta(hours=-4))  # 夏令时; 仅用于展示

PRODUCTS = [
 dict(tab='SPX-ETF', idx='SPX',   iname='S&P 500',      ptype='ETF期权',  sym='SPY',  mult=100, symnm='SPY'),
 dict(tab='SPX-IDX', idx='SPX',   iname='S&P 500',      ptype='指数期权', sym='_SPX', mult=100, symnm='SPX'),
 dict(tab='SPX-FOP', idx='SPX',   iname='S&P 500',      ptype='期货期权', sym=None,   mult=50,  symnm='ES'),
 dict(tab='NDX-ETF', idx='NDX',   iname='Nasdaq 100',   ptype='ETF期权',  sym='QQQ',  mult=100, symnm='QQQ'),
 dict(tab='NDX-IDX', idx='NDX',   iname='Nasdaq 100',   ptype='指数期权', sym='_NDX', mult=100, symnm='NDX'),
 dict(tab='NDX-FOP', idx='NDX',   iname='Nasdaq 100',   ptype='期货期权', sym=None,   mult=20,  symnm='NQ'),
 dict(tab='RUT-ETF', idx='RUT',   iname='Russell 2000', ptype='ETF期权',  sym='IWM',  mult=100, symnm='IWM'),
 dict(tab='RUT-IDX', idx='RUT',   iname='Russell 2000', ptype='指数期权', sym='_RUT', mult=100, symnm='RUT'),
 dict(tab='RUT-FOP', idx='RUT',   iname='Russell 2000', ptype='期货期权', sym=None,   mult=50,  symnm='RTY'),
]

def third_fridays(today, n=4):
    """未来 n 个"第三个周五": 近2个月 + 之后2个季月(3/6/9/12)"""
    cands = []
    y, m = today.year, today.month
    for i in range(14):
        yy = y + (m-1+i)//12; mm = (m-1+i)%12+1
        d = date(yy, mm, 1); cnt = 0
        while True:
            if d.weekday() == 4:
                cnt += 1
                if cnt == 3: break
            d = date.fromordinal(d.toordinal()+1)
        if d > today: cands.append(d)
    near = cands[:2]
    qtr = [d for d in cands[2:] if d.month in (3,6,9,12)][:2]
    return near + qtr

def fetch(sym, retries=3):
    for a in range(retries):
        try:
            r = requests.get(f'https://cdn.cboe.com/api/global/delayed_quotes/options/{sym}.json',
                             headers=H, timeout=60)
            return r.json()
        except Exception as e:
            print(f'  {sym} retry {a+1}: {e}', flush=True); time.sleep(3)
    return None

def main():
    today = datetime.now(ET).date()
    exp_want = third_fridays(today)
    print('expiries:', [d.isoformat() for d in exp_want], flush=True)
    out = {'fetched_at': datetime.now(ET).isoformat(timespec='seconds'), 'products': {}}
    for p in PRODUCTS:
        if p['sym'] is None: continue
        d = fetch(p['sym'])
        if not d: print(p['tab'], 'FAIL', flush=True); continue
        data = d['data']
        spot = data.get('current_price')
        chains = {}
        for o in data['options']:
            m = re.match(r'([A-Z]+W?)(\d{6})([CP])(\d{8})', o['option'])
            if not m: continue
            exp = date(2000+int(m.group(2)[:2]), int(m.group(2)[2:4]), int(m.group(2)[4:6]))
            if exp not in exp_want: continue
            K = int(m.group(4))/1000
            if spot and abs(K/spot-1) > 0.18: continue   # 只留±18%
            cp = 'c' if m.group(3) == 'C' else 'p'
            rec = dict(ls=o.get('last_trade_price') or None, bd=o.get('bid') or None, as_=None,
                       vo=o.get('volume') or None, oi=o.get('open_interest') or None,
                       iv=(o.get('iv')*100 if o.get('iv') else None))
            rec['as'] = o.get('ask') or None
            del rec['as_']
            chains.setdefault(exp.isoformat(), {}).setdefault(K, {})[cp] = rec
        rows = {e: [dict(K=k, **v) for k, v in sorted(ks.items())] for e, ks in chains.items()}
        out['products'][p['tab']] = dict(p, spot=spot, prev=data.get('prev_day_close'),
                                         ts=d.get('timestamp'), expiries=[e.isoformat() for e in exp_want],
                                         chains=rows)
        print(p['tab'], 'spot:', spot, {e: len(r) for e, r in rows.items()}, flush=True)
    json.dump(out, open(OUT, 'w'))
    print('saved', OUT, flush=True)

if __name__ == '__main__':
    main()
