# -*- coding: utf-8 -*-
"""
ETF期权T型报价 Dashboard 构建脚本
输入: /mnt/agents/output/ 下的东财行情快照 JSON
  - em_underlyings.json           六大标的ETF最新行情 (secids=1.510050,1.510300,1.510500,0.159901,0.159915,1.588000)
  - em_data_0..3.json             510300 期权链 (市场前缀 10.)
  - em_510050_0..1.json           510050 期权链 (10.)
  - em_510500_0..3.json           510500 期权链 (10.)
  - em_159901_0..2.json           159901 期权链 (12.)
  - em_159915_0..2.json           159915 期权链 (12.)
  - em_588000_0..3.json           588000 期权链 (10.)
  期权链JSON来自东方财富 push2 ulist 接口, fields=f12,f14,f2,f3,f5,f6,f15,f16,f17,f18,f31,f32,f108,f124,f152
  期权价格字段除以 1e4, ETF 除以 1e3。f31=买一 f32=卖一 f108=持仓量。
输出: /mnt/agents/output/app/index.html
运行: python3 /mnt/agents/output/app/build_dashboard.py
"""
import json, re, os
from datetime import date, datetime
from math import log, sqrt, exp
from statistics import NormalDist

OUT = os.environ.get('DASH_DATA', '/mnt/agents/output')
R = 0.015
N = NormalDist().cdf

UL_META = {
 '510050': dict(name='上证50ETF'),
 '510300': dict(name='沪深300ETF'),
 '510500': dict(name='中证500ETF'),
 '159901': dict(name='深证100ETF'),
 '159915': dict(name='创业板ETF'),
 '588000': dict(name='科创50ETF'),
}
FILES = {'510050':[f'{OUT}/em_510050_{i}.json' for i in range(2)],
         '510300':[f'{OUT}/em_data_{i}.json' for i in range(4)],
         '510500':[f'{OUT}/em_510500_{i}.json' for i in range(4)],
         '159901':[f'{OUT}/em_159901_{i}.json' for i in range(3)],
         '159915':[f'{OUT}/em_159915_{i}.json' for i in range(3)],
         '588000':[f'{OUT}/em_588000_{i}.json' for i in range(4)]}

def exp_date(yymm, today):
    y = 2000+int(yymm[:2]); m = int(yymm[2:])
    # 4th Wednesday
    d = date(y, m, 1); cnt = 0
    while True:
        if d.weekday() == 2:
            cnt += 1
            if cnt == 4: return d
        d = date.fromordinal(d.toordinal()+1)

def fourth_wed(y, m):
    d = date(y, m, 1); cnt = 0
    while True:
        if d.weekday() == 2:
            cnt += 1
            if cnt == 4: return d
        d = date.fromordinal(d.toordinal()+1)

def bs_px(cp, S, K, T, r, sig):
    if T <= 0 or sig <= 0: return max(0.0, (S-K) if cp=='C' else (K-S))
    d1 = (log(S/K)+(r+sig*sig/2)*T)/(sig*sqrt(T)); d2 = d1-sig*sqrt(T)
    return S*N(d1)-K*exp(-r*T)*N(d2) if cp=='C' else K*exp(-r*T)*N(-d2)-S*N(-d1)

def bs_iv(cp, S, K, T, r, px):
    if px is None: return None
    lo = max(0.0, (S-K*exp(-r*T)) if cp=='C' else (K*exp(-r*T)-S))
    if px < lo - 1e-9: return None
    a, b = 1e-4, 6.0
    if bs_px(cp,S,K,T,r,b) < px: return None
    for _ in range(90):
        m = (a+b)/2
        if bs_px(cp,S,K,T,r,m) < px: a = m
        else: b = m
    return (a+b)/2

def margin_call(px,S,K): return (px + max(0.12*S - max(K-S,0), 0.07*S))*10000
def margin_put(px,S,K):  return min(px + max(0.12*S - max(S-K,0), 0.07*K), K)*10000

def main():
    # --- underlying quotes ---
    ud = json.load(open(f'{OUT}/em_underlyings.json'))['data']['diff']
    ts_max = 0
    for it in ud:
        code = it['f12']
        if code in UL_META:
            UL_META[code]['S'] = it['f2']/1e3
            UL_META[code]['chg'] = (it.get('f3') or 0)/100
            ts_max = max(ts_max, it.get('f124') or 0)
    data_time = datetime.fromtimestamp(ts_max).strftime('%Y-%m-%d %H:%M') if ts_max else ''
    TODAY = datetime.fromtimestamp(ts_max).date() if ts_max else date.today()

    # expiry map: nearest cycle months Aug->this year etc. Derive from option names per run.
    def mon_to_exp(mon):
        y = TODAY.year + (1 if mon < TODAY.month else 0)
        # months offered: current, next, and two quarter months; choose nearest future 4th Wed
        d = fourth_wed(y, mon)
        if d <= TODAY:
            d = fourth_wed(y+1, mon)
        return d

    def parse_file(path):
        d = json.load(open(path))
        out = []
        for it in d['data']['diff']:
            nm = it['f14']
            mm = re.match(r'(.+?)(购|沽)(\d+)月(\d+)(A?)', nm)
            if not mm: continue
            mon = int(mm.group(3))
            q = dict(code=it['f12'], name=nm, cp='C' if mm.group(2)=='购' else 'P',
                     K=int(mm.group(4))/1000, adj=mm.group(5)=='A', mon=mon,
                     px=(it['f2']/1e4 if it['f2'] else None),
                     bid=(it['f31']/1e4 if it.get('f31') else None),
                     ask=(it['f32']/1e4 if it.get('f32') else None),
                     vol=it.get('f5') or 0, oi=it.get('f108') or 0, ts=it.get('f124'))
            q['mid'] = round((q['bid']+q['ask'])/2,4) if (q['bid'] and q['ask']) else None
            q['basis'] = q['px'] if q['px'] else q['mid']
            q['exp_date'] = mon_to_exp(mon)
            out.append(q)
        return out

    allq = {}
    for ul, files in FILES.items():
        seen = {}
        for p in files:
            if not os.path.exists(p): continue
            for r in parse_file(p): seen[r['code']] = r
        allq[ul] = list(seen.values())

    for ul, meta in UL_META.items():
        S = meta['S']
        byks = {}
        for q in allq[ul]:
            T = max((q['exp_date']-TODAY).days,0)/365
            days = max((q['exp_date']-TODAY).days,1)
            q['T']=T; q['days']=days
            q['iv'] = bs_iv(q['cp'],S,q['K'],T,R,q['basis']) if q['basis'] else None
            if q['basis']:
                q['margin'] = margin_call(q['basis'],S,q['K']) if q['cp']=='C' else margin_put(q['basis'],S,q['K'])
                q['ann'] = q['basis']*10000/q['margin']*365/days
            else:
                q['margin']=None; q['ann']=None
            byks.setdefault((q['exp_date'],q['K']),{})[q['cp']] = q
        meta['strikes'] = byks

    # ---------- HTML ----------
    def fmt(x, nd=4): return '—' if x is None else f'{x:.{nd}f}'
    def fmti(x): return '—' if x is None else f'{x:,.0f}'

    def row_html(qc, qp, K, S, k_atm):
        def side(q, is_call, mcls):
            if q is None: return ''.join(f'<td class="na {mcls}">—</td>' for _ in range(5))
            star = '*' if (q['px'] is None and q['basis'] is not None) else ''
            px = fmt(q['basis']); iv = '—' if q['iv'] is None else f"{q['iv']*100:.1f}%"
            oi = fmti(q['oi']); mg = fmti(q['margin'])
            show_ann = (K >= k_atm-1e-9) if is_call else (K <= k_atm+1e-9)
            ann = f"{q['ann']*100:.1f}%" if (show_ann and q['ann'] is not None) else ''
            cells = [f'<td class="px {mcls}">{px}{star}</td>', f'<td class="{mcls}">{iv}</td>',
                     f'<td class="oi {mcls}">{oi}</td>', f'<td class="{mcls}">{mg}</td>',
                     f'<td class="ann {"" if show_ann else "dim"} {mcls}">{ann}</td>']
            if not is_call: cells.reverse()
            return ''.join(cells)
        F = None; fm = ''
        if qc and qp and qc['basis'] and qp['basis']:
            T = qc['T']
            cm = qc['mid'] if qc['mid'] else qc['basis']; pm = qp['mid'] if qp['mid'] else qp['basis']
            F = K + (cm-pm)*exp(R*T)
            fm = 'mid' if (qc['mid'] and qp['mid']) else 'last'
        mny = (K/S-1)*100
        ftxt = f'F {F:.4f} <span class="fd">({(F/S-1)*100:+.2f}%)</span> <span class="fs">{fm}</span>' if F else ''
        atm = abs(K-k_atm)<1e-9
        cmcls = 'itmz' if K < k_atm-1e-9 else ('atmz' if atm else 'otmz')
        pmcls = 'otmz' if K < k_atm-1e-9 else ('atmz' if atm else 'itmz')
        return (f'<tr{" class=\"atmr\"" if atm else ""}>{side(qc,True,cmcls)}'
                f'<td class="kcell"><div class="k">{K:.3f}</div><div class="mny">M {mny:+.1f}%</div><div class="fwd">{ftxt}</div></td>'
                f'{side(qp,False,pmcls)}</tr>')

    def panel_html(ul, exp_d):
        meta = UL_META[ul]; S = meta['S']
        rows = [(K, d) for (e,K),d in meta['strikes'].items() if e==exp_d]
        if not rows: return ''
        rows.sort()
        ks = [K for K,_ in rows]
        k_atm = min(ks, key=lambda k: abs(k-S))
        days = (exp_d-TODAY).days
        body = ''.join(row_html(d_.get('C'), d_.get('P'), K, S, k_atm) for K,d_ in rows)
        return f'''<section class="panel" id="{ul}-{exp_d.isoformat()}">
<div class="phead"><span class="pt">{exp_d.year}年{exp_d.month}月到期</span><span class="ps">到期日 {exp_d.isoformat()} · 剩余 {days} 天 · {len(rows)} 个行权价</span></div>
<table class="tq"><thead><tr>
<th colspan="5" class="hc">认购 CALL</th><th class="hk">行权价 Strike<br><span class="hsub">M = 在值程度 · F = 合成远期</span></th><th colspan="5" class="hp">认沽 PUT</th></tr>
<tr class="cols"><th>最新价</th><th>隐波IV</th><th>持仓量</th><th>保证金/手</th><th>年化*</th>
<th></th>
<th>年化*</th><th>保证金/手</th><th>持仓量</th><th>隐波IV</th><th>最新价</th></tr></thead>
<tbody>{body}</tbody></table></section>'''

    CSS = open(os.path.join(os.path.dirname(__file__),'dashboard.css')).read()
    JS = '''
function showMarket(id,btn){
 document.querySelectorAll('.mkpane').forEach(p=>p.classList.remove('show'));
 document.getElementById('mk-'+id).classList.add('show');
 document.querySelectorAll('.mtab').forEach(t=>t.classList.remove('active'));
 btn.classList.add('active');
 window.scrollTo({top:0});
}
function showUL(id,btn){
 var mk = btn.closest('.mkpane') || document;
 mk.querySelectorAll('.ulpane').forEach(p=>p.classList.remove('show'));
 document.getElementById('ul-'+id).classList.add('show');
 mk.querySelectorAll('.tabs .tab').forEach(t=>t.classList.remove('active'));
 btn.classList.add('active');
 window.scrollTo({top:0});
}
function showProd(id,btn){
 var ul = btn.closest('.ulpane') || document;
 ul.querySelectorAll('.prodpane').forEach(p=>p.classList.remove('show'));
 document.getElementById('prod-'+id).classList.add('show');
 ul.querySelectorAll('.subtab').forEach(t=>t.classList.remove('active'));
 btn.classList.add('active');
}
'''
    tabs, panes = [], []
    for i,(ul,meta) in enumerate(UL_META.items()):
        chg = f'<span class="up">+{meta["chg"]:.2f}%</span>' if meta['chg']>=0 else f'<span class="dn">{meta["chg"]:.2f}%</span>'
        tabs.append(f'<div class="tab{" active" if i==0 else ""}" onclick="showUL(\'{ul}\',this)"><div class="tn">{ul} {meta["name"]}</div><div class="ts">标的 <b>{meta["S"]:.3f}</b> {chg}</div></div>')
        exp_ds = sorted({e for (e,K) in meta['strikes']})
        nav = ''.join(f'<a href="#{ul}-{e.isoformat()}">{e.month}月</a>' for e in exp_ds)
        panels = ''.join(panel_html(ul,e) for e in exp_ds)
        panes.append(f'<div class="ulpane{" show" if i==0 else ""}" id="ul-{ul}"><div class="mnav">{nav}</div>{panels}</div>')

    # ---- 港股 (恒生/恒生中国/恒生科技 × 指数/期货/ETF期权) ----
    try:
        import hk_render
        hk_tabs, hk_panes = hk_render.render_hk(TODAY)
    except Exception as e:
        print('hk_render skipped:', e)
        hk_tabs, hk_panes = '', ''
    # ---- 美股 (S&P500/Nasdaq100/Russell2000 × ETF/指数/期货期权) ----
    try:
        import us_render
        us_tabs, us_panes = us_render.render_us(TODAY)
    except Exception as e:
        print('us_render skipped:', e)
        us_tabs, us_panes = '', ''

    cn_block = f'<div class="tabs">{"".join(tabs)}</div>{"".join(panes)}'
    hk_block = (f'<div class="tabs hk">{hk_tabs}</div>{hk_panes}' if hk_tabs
                else '<div class="hkempty">港股数据暂未更新</div>')
    us_block = (f'<div class="tabs us">{us_tabs}</div>{us_panes}' if us_tabs
                else '<div class="hkempty">美股数据暂未更新</div>')

    mtabs = ('<div class="mtabs">'
             '<div class="mtab active" onclick="showMarket(\'cn\',this)">A 股<small>ETF期权 · 东财实时</small></div>'
             '<div class="mtab" onclick="showMarket(\'hk\',this)">港 股<small>指数/期货/ETF期权 · 港交所延迟</small></div>'
             '<div class="mtab" onclick="showMarket(\'us\',this)">美 股<small>ETF/指数/期货期权 · CBOE·CME延迟</small></div>'
             '</div>')
    markets = (f'<div class="mkpane show" id="mk-cn">{cn_block}</div>'
               f'<div class="mkpane" id="mk-hk">{hk_block}</div>'
               f'<div class="mkpane" id="mk-us">{us_block}</div>')

    html = f'''<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>全球指数期权 T型报价 · {TODAY.isoformat()}</title><style>{CSS}</style></head><body>
<div class="wrap">
<header><h1>全球指数期权 T 型报价</h1><span class="badge">LIVE</span>
<span class="hmeta">A股：东财实时 · 港股：港交所延迟快照 · 美股：CBOE/CME 延迟 · 更新 {data_time}</span></header>
{mtabs}
{markets}
<footer>
<b>口径说明</b><br>
· 最新价：东财快照最新成交价；带 * 表示当日无成交，以买卖中间价替代。IV 由该价格经 Black-Scholes 反解（无风险利率 1.5%，未含股息调整）。<br>
· 维持保证金/手：按交易所 ETF 期权开仓保证金公式以最新价近似估算（合约单位 10,000），认购 = (权利金 + max(12%×S − 虚值额, 7%×S))×10000，认沽 = min(权利金 + max(12%×S − 虚值额, 7%×K), K)×10000，实盘中实值程度深时以结算价为准，此处仅供参考。<br>
· 年化*：卖出开仓 1 手的权利金收入 ÷ 保证金 × 365 ÷ 剩余天数；仅对虚值/平值一侧显示（认购 K≥ATM，认沽 K≤ATM），深度实值一侧保证金占用大、该指标无意义故留空。<br>
· M：在值程度 (K/S − 1)；F：合成远期 K + (C − P)·e^(rT)，优先取买卖中间价（标注 mid），盘口缺失时取最新价（标注 last）；括号内为 F 相对标的现价距离。<br>
· 持仓量：东财快照 open interest（张）。510500 名称带 A 的为分红调整非标准合约。深市（159901/159915）与沪市规则一致，合约单位同为 10,000。<br>
· 部分合约为收盘后快照，盘口为空时中间价自动回退为最新价。数据仅供研究，不构成投资建议。<br>
<br>
<b>港股板块（恒生指数 HSI / 恒生中国企业指数 HSCEI / 恒生科技指数 HSTECH）</b><br>
· 数据源：港交所官网行情组件（www1.hkex.com.hk，免费延迟行情，盘口为快照值）；IV 为港交所公布值，无需反解。<br>
· 三类产品：指数期权（HSI/HHI/HTI，现金交割，合约乘数 HK$50/点）；期货期权（PHS/PHH/PTE，实物交割为对应月份期货）；ETF期权（2800 盈富基金每手 500 股、2828 恒生中国企业ETF 每手 200 股，实物交割）。恒生科技指数无 ETF 期权（港交所未对恒生科技ETF开设股票期权）。<br>
· 期货期权的 M/F 以同月到期的期货价格为参考（仅有近两个月期货报价，远月回退用指数）；其余以指数/ETF 现价为参考。<br>
· 保证金*：港交所按 SPAN 全组合风险计收，无法用行情精确推算；此处借用上交所 ETF 期权公式近似估算（港元/张），仅供参考。<br>
· 年化*：同 A 股口径（权利金收入 ÷ 估算保证金 × 365 ÷ 剩余天数），仅虚值/平值一侧显示。到期日为近似值（指数/ETF期权=当月最后交易日前一交易日，期货期权=当月第三个周五，未剔香港公众假期）。<br>
<br>
<b>美股板块（S&P 500 / Nasdaq 100 / Russell 2000）</b><br>
· 数据源：ETF期权（SPY/QQQ/IWM，实物交割）与指数期权（SPX/NDX/RUT，现金交割，乘数 $100/点）来自 CBOE 官方延迟报价（约 15 分钟，含 IV 与 Greeks，IV 为 CBOE 公布值）；期货期权（ES/NQ/RTY，实物交割为对应月份期货）来自 CME 官网延迟行情（≥10 分钟，仅平值附近±10档，仅有最新价/前结算/涨跌/成交量，无盘口与持仓）。<br>
· 保证金*：借用上交所公式近似估算（美元/张，乘数 $100），仅供横向对比参考；美国实际按 Reg-T/SPAN 计收。<br>
· 年化*：同口径（权利金 ÷ 估算保证金 × 365 ÷ 剩余天数），仅虚值/平值一侧显示；利率取 r = 4%。F 对 ETF/指数期权按买卖中间价计算，期货期权按前结算价计算（标注 settle）。<br>
· 行情为延时快照，仅平值附近档位；数据仅供研究，不构成投资建议。
</footer></div>
<script>{JS}</script></body></html>'''
    open(os.path.join(os.path.dirname(__file__),'index.html'),'w').write(html)
    print(f'[{datetime.now().isoformat(timespec="seconds")}] index.html written, {len(html)} bytes, data_time={data_time}')

if __name__ == '__main__':
    main()
