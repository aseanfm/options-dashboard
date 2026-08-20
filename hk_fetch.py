# -*- coding: utf-8 -*-
"""
港交所港股期权数据抓取: 恒生指数/恒生中国企业指数/恒生科技指数
  - 指数期权(现金交割): HSI / HHI / HTI
  - 期货期权(实物交割): PHS / PHH / PTE
  - ETF期权: TRF(2800盈富基金) / HCF(2828恒生中国企业ETF); 恒生科技ETF无期权
数据源: 港交所官网行情组件 (www1.hkex.com.hk/hkexwidget), 免费延迟行情
输出: /mnt/agents/output/hk_data.json
"""
import json, time, re, os, sys
from datetime import date, datetime, timezone, timedelta
import requests

TOKEN = 'evLtsLsBNAUVTPxtGqVeG9PW3DSwcLeVJOqQNvVnrBioLhXYnHICjxHigiuK%2bp%2bV'
BASE = 'https://www1.hkex.com.hk/hkexwidget/data/'
H = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.hkex.com.hk/'}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hk_data.json')
CN = timezone(timedelta(hours=8))

def wapi(api, retries=3, **kw):
    qs = '&'.join(f'{k}={v}' for k, v in kw.items())
    for a in range(retries):
        try:
            u = f'{BASE}{api}?lang=eng&token={TOKEN}&{qs}&qid={int(time.time()*1000)}&callback=cb'
            r = requests.get(u, headers=H, timeout=25)
            txt = r.text
            if txt.startswith('cb('): txt = txt[3:-1]
            return json.loads(txt)
        except Exception as e:
            print(f'  {api} retry {a+1}: {e}', flush=True); time.sleep(2)
    return None

def num(s):
    if s in (None, '', '-'): return None
    return float(str(s).replace(',', ''))

PRODUCTS = [
 dict(tab='HSI-IDX', idx='HSI',    iname='恒生指数',         ptype='指数期权', ats='HSI', mult=50),
 dict(tab='HSI-FOP', idx='HSI',    iname='恒生指数',         ptype='期货期权', ats='PHS', mult=50),
 dict(tab='HSI-ETF', idx='HSI',    iname='恒生指数',         ptype='ETF期权',  ats='TRF', mult=500, sym='2800', symnm='盈富基金'),
 dict(tab='HHI-IDX', idx='HSCE',   iname='恒生中国企业指数', ptype='指数期权', ats='HHI', mult=50),
 dict(tab='HHI-FOP', idx='HSCE',   iname='恒生中国企业指数', ptype='期货期权', ats='PHH', mult=50),
 dict(tab='HHI-ETF', idx='HSCE',   iname='恒生中国企业指数', ptype='ETF期权',  ats='HCF', mult=200, sym='2828', symnm='恒生中国企业ETF'),
 dict(tab='HTI-IDX', idx='HSTECH', iname='恒生科技指数',     ptype='指数期权', ats='HTI', mult=50),
 dict(tab='HTI-FOP', idx='HSTECH', iname='恒生科技指数',     ptype='期货期权', ats='PTE', mult=50),
]

def pick_months(conlist):
    """近2个月 + 之后2个季月(3/6/9/12)"""
    ids = [c['id'] for c in conlist]
    near = ids[:2]
    qtr = [i for i in ids[2:] if i[:2] in ('03','06','09','12')][:2]
    return near + qtr

def main():
    out = {'fetched_at': datetime.now(CN).isoformat(timespec='seconds'), 'spot': {}, 'futures': {}, 'products': {}}
    # 指数现货
    d = wapi('getmarketoverview')
    for it in d['data']['indices']:
        if it['ric'] in ('.HSI', '.HSCE', '.HSTECH'):
            out['spot'][it['ric']] = dict(px=num(it['ls']), chg=num(it['pc']), ts=it.get('ts'))
    # 期货近月
    for ric in ['.HSI', '.HSCE', '.HSTECH']:
        d = wapi('getmarketoverviewfutures', ric=ric)
        if d and d['data'].get('futures'):
            out['futures'][ric] = [{'mon': f['nm'], 'px': num(f['ls']), 'oi': num(f.get('oi'))} for f in d['data']['futures']]
    # ETF现货
    for sym in ['2800', '2828']:
        d = wapi('getequityquote', sym=sym)
        q = d['data']['quote']
        out['spot'][sym] = dict(px=num(q.get('ls')), chg=num(q.get('pc')))
    # 期权链
    for p in PRODUCTS:
        d = wapi('getoptioncontractlist', ats=p['ats'])
        if not d or d['data'].get('responsecode') != '000':
            print(p['tab'], 'contract list FAIL', flush=True); continue
        months = pick_months(d['data']['conlist'])
        chains = {}
        for con in months:
            d = wapi('getderivativesoption', ats=p['ats'], con=con, type=0)
            if not d or d['data'].get('responsecode') != '000':
                print(p['tab'], con, 'chain FAIL', flush=True); continue
            rows = []
            for o in d['data'].get('optionlist', []):
                rows.append(dict(K=num(o['strike']),
                                 c={k: num(v) for k, v in o['c'].items()},
                                 p={k: num(v) for k, v in o['p'].items()}))
            chains[con] = dict(lastupd=d['data'].get('lastupd'), rows=rows)
            print(p['tab'], con, len(rows), 'strikes', flush=True)
            time.sleep(0.3)
        out['products'][p['tab']] = dict(p, months=months, chains=chains)
    json.dump(out, open(OUT, 'w'), ensure_ascii=False)
    print('saved', OUT, flush=True)

if __name__ == '__main__':
    main()
