# -*- coding: utf-8 -*-
"""
全球指数期权T型报价 - GitHub Actions 版编排脚本
1) 抓取东财A股ETF期权行情 -> data/em_*.json
2) 抓取港交所港股期权行情 -> hk_data.json (hk_fetch.py)
3) 抓取CBOE美股期权行情 -> us_data.json (us_fetch.py)
   注: 美股期货期权(ES/NQ/RTY)取自 cme_data.json(CME官网延迟行情, 浏览器手工转录, 需定期更新)
4) 重建 index.html (build_dashboard.py, DASH_DATA=data)
在仓库根目录运行: python3 fetch_build.py
依赖: requests
"""
import json, os, sys, time, subprocess
import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, 'data')
os.makedirs(DATA, exist_ok=True)

ULS = ['510050', '510300', '510500', '159901', '159915', '588000']
USEC = {'510050':'1.510050','510300':'1.510300','510500':'1.510500',
        '159901':'0.159901','159915':'0.159915','588000':'1.588000'}
# build_dashboard.py 的读取文件名约定(510300历史命名为 em_data_*)
OUTNAME = {'510300':'em_data_{i}.json'}
FIELDS = 'f12,f14,f2,f3,f5,f6,f15,f16,f17,f18,f31,f32,f108,f124,f152'
API = 'https://push2.eastmoney.com/api/qt/ulist.np/get'
HDRS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://quote.eastmoney.com/'}

def em_get(secids, retries=3):
    for a in range(retries):
        try:
            r = requests.get(API, params={'secids': ','.join(secids), 'fields': FIELDS},
                             headers=HDRS, timeout=20)
            d = r.json()
            if d.get('data') and d['data'].get('diff'):
                return d['data']['diff']
        except Exception as e:
            print(f'  retry {a+1}: {e}', flush=True)
            time.sleep(3)
    return []

def main():
    # 标的行情(失败则保留 data/ 里的种子快照, 不中断)
    diff = em_get([USEC[u] for u in ULS])
    if diff:
        json.dump({'data': {'diff': diff}}, open(os.path.join(DATA, 'em_underlyings.json'), 'w'))
        print('underlyings ok', flush=True)
    else:
        print('WARN: 东财标的行情抓取失败(可能网络受限), 沿用种子快照', flush=True)

    # 期权链(分块60个; 某块抓空则保留旧文件)
    for ul in ULS:
        secids = [s for s in open(os.path.join(DATA, f'secids_{ul}.txt')).read().strip().split(',') if s]
        pat = OUTNAME.get(ul, f'em_{ul}_' + '{i}.json')
        for i in range(0, len(secids), 60):
            chunk = secids[i:i+60]
            diff = em_get(chunk)
            fp = os.path.join(DATA, pat.format(i=i//60))
            if diff:
                json.dump({'data': {'diff': diff}}, open(fp, 'w'))
            else:
                print(f'WARN: {ul} chunk {i//60} 抓取为空, 沿用旧文件', flush=True)
            print(ul, 'chunk', i//60, len(diff), flush=True)
            time.sleep(0.5)

    # 港股
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'hk_fetch.py')], capture_output=True, text=True)
    print(r.stdout[-800:], flush=True)

    # 美股 (CBOE 延迟报价: ETF+指数期权; 期货期权来自 cme_data.json, 需人工/浏览器更新)
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'us_fetch.py')], capture_output=True, text=True)
    print(r.stdout[-800:], flush=True)

    # 构建页面
    env = dict(os.environ, DASH_DATA=DATA)
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'build_dashboard.py')], capture_output=True, text=True, env=env)
    print(r.stdout[-500:], r.stderr[-500:] if r.returncode else '', flush=True)
    if r.returncode: sys.exit(1)

if __name__ == '__main__':
    main()
