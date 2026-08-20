# -*- coding: utf-8 -*-
"""港股期权渲染: 按标的分组(恒生/恒生中国/恒生科技), 每个标的内含3个产品子tab(指数/期货/ETF期权)"""
import json, os
from datetime import date, datetime
from math import exp

R = 0.015
HERE = os.path.dirname(os.path.abspath(__file__))

def _lastbiz_prev(y, m):
    d = date(y, m, 28); last = d
    while True:
        d = date.fromordinal(d.toordinal()+1)
        if d.month != m: break
        last = d
    while last.weekday() > 4: last = date.fromordinal(last.toordinal()-1)
    d = date.fromordinal(last.toordinal()-1)
    while d.weekday() > 4: d = date.fromordinal(d.toordinal()-1)
    return d

def _third_friday(y, m):
    d = date(y, m, 1); cnt = 0
    while True:
        if d.weekday() == 4:
            cnt += 1
            if cnt == 3: return d
        d = date.fromordinal(d.toordinal()+1)

def fmt(x, nd=2): return '—' if x is None else f'{x:,.{nd}f}'
def fmti(x): return '—' if x is None else f'{x:,.0f}'

UNDERS = [
 dict(key='HSI', iname='恒生指数', ric='.HSI'),
 dict(key='HSCE', iname='恒生中国企业指数', ric='.HSCE'),
 dict(key='HSTECH', iname='恒生科技指数', ric='.HSTECH'),
]
PTYPES = ['IDX', 'FOP', 'ETF']
PTYPE_NM = {'IDX': '指数期权', 'FOP': '期货期权', 'ETF': 'ETF期权'}

def render_hk(today):
    fp = os.path.join(HERE, 'hk_data.json')
    if not os.path.exists(fp): return '', ''
    hk = json.load(open(fp))
    spot = hk['spot']; futs = hk.get('futures', {})

    def get_S(p, mon_id):
        ric = '.' + p['idx']
        if p['ptype'] == '期货期权':
            mon_nm = datetime.strptime(mon_id, '%m%Y').strftime('%b-%y')
            for f in futs.get(ric, []):
                if f['mon'] == mon_nm and f['px']: return f['px'], '期货'
        if p['ptype'] == 'ETF期权':
            s = spot.get(p.get('sym',''), {})
            return s.get('px'), p.get('symnm', 'ETF')
        s = spot.get(ric, {})
        return s.get('px'), '指数'

    def side(q, is_call, mcls, K, k_atm, mult, days, S):
        if q is None: return ''.join(f'<td class="na {mcls}">—</td>' for _ in range(6))
        ls, bd, ask, oi, iv = q.get('ls'), q.get('bd'), q.get('as'), q.get('oi'), q.get('iv')
        mid = (bd+ask)/2 if (bd is not None and ask is not None) else None
        basis = ls if ls is not None else mid
        star = '*' if (ls is None and basis is not None) else ''
        if basis is not None and S:
            mg = ((basis + max(0.12*S - max(K-S,0), 0.07*S)) if is_call else
                  min(basis + max(0.12*S - max(S-K,0), 0.07*K), K)) * mult
            ann = basis*mult/mg*365/days
        else:
            mg = ann = None
        show_ann = (K >= k_atm-1e-9) if is_call else (K <= k_atm+1e-9)
        anns = f'{ann*100:.1f}%' if (show_ann and ann is not None) else ''
        ba = f'{fmt(bd,0)}/{fmt(ask,0)}' if (bd is not None or ask is not None) else '—'
        cells = [f'<td class="px {mcls}">{fmt(basis,0)}{star}</td>',
                 f'<td class="ba {mcls}">{ba}</td>',
                 f'<td class="{mcls}">{fmt(iv,1)}%</td>' if iv is not None else f'<td class="{mcls}">—</td>',
                 f'<td class="oi {mcls}">{fmti(oi)}</td>',
                 f'<td class="{mcls}">{fmti(mg)}</td>',
                 f'<td class="ann {"" if show_ann else "dim"} {mcls}">{anns}</td>']
        if not is_call: cells.reverse()
        return ''.join(cells)

    def row(rw, S, k_atm, mult, days):
        K = rw['K']; qc, qp = rw.get('c') or {}, rw.get('p') or {}
        if not any([qc.get('ls'), qp.get('ls'), qc.get('bd'), qp.get('bd'), qc.get('oi'), qp.get('oi')]): return ''
        atm = abs(K-k_atm) < 1e-9
        cmcls = 'itmz' if K < k_atm-1e-9 else ('atmz' if atm else 'otmz')
        pmcls = 'otmz' if K < k_atm-1e-9 else ('atmz' if atm else 'itmz')
        F = None
        bc = qc.get('ls') or ((qc['bd']+qc['as'])/2 if qc.get('bd') is not None and qc.get('as') is not None else None)
        bp = qp.get('ls') or ((qp['bd']+qp['as'])/2 if qp.get('bd') is not None and qp.get('as') is not None else None)
        if bc is not None and bp is not None and S:
            F = K + (bc-bp)*exp(R*days/365)
        mny = (K/S-1)*100 if S else 0
        ftxt = f'F {F:,.0f} <span class="fd">({(F/S-1)*100:+.2f}%)</span>' if F else ''
        return (f'<tr{" class=\"atmr\"" if atm else ""}>{side(qc,True,cmcls,K,k_atm,mult,days,S)}'
                f'<td class="kcell"><div class="k">{K:,.0f}</div><div class="mny">M {mny:+.1f}%</div><div class="fwd">{ftxt}</div></td>'
                f'{side(qp,False,pmcls,K,k_atm,mult,days,S)}</tr>')

    def panel(p, mon_id, ch):
        S, ref = get_S(p, mon_id)
        if S is None: return ''
        rows = [rw for rw in ch['rows'] if rw['K']]
        if not rows: return ''
        ks = [rw['K'] for rw in rows]
        k_atm = min(ks, key=lambda k: abs(k-S))
        y, m = int(mon_id[2:]), int(mon_id[:2])
        exp_d = _third_friday(y, m) if p['ptype'] == '期货期权' else _lastbiz_prev(y, m)
        days = max((exp_d-today).days, 1)
        body = ''.join(row(rw, S, k_atm, p['mult'], days) for rw in rows)
        return f'''<section class="panel" id="{p['tab']}-{mon_id}">
<div class="phead"><span class="pt">{y}年{m}月到期 · 参考: {ref} {S:,.2f}</span><span class="ps">到期日(约) {exp_d.isoformat()} · 剩余 {days} 天 · 快照 {ch.get('lastupd','')}</span></div>
<table class="tq"><thead><tr>
<th colspan="6" class="hc">认购 CALL</th><th class="hk">行权价 Strike<br><span class="hsub">M = 在值程度 · F = 合成远期</span></th><th colspan="6" class="hp">认沽 PUT</th></tr>
<tr class="cols"><th>最新价</th><th>买/卖</th><th>IV</th><th>持仓量</th><th>保证金*</th><th>年化*</th>
<th></th>
<th>年化*</th><th>保证金*</th><th>持仓量</th><th>IV</th><th>买/卖</th><th>最新价</th></tr></thead>
<tbody>{body}</tbody></table></section>'''

    tabs, panes = [], []
    # 产品索引按 (指数, 产品类型) 建立, 避免 tab 键(ATS代码)与标的键不一致
    pmap = {(p['idx'], p['ptype']): p for p in hk['products'].values()}
    PTNM = {'IDX': '指数期权', 'FOP': '期货期权', 'ETF': 'ETF期权'}
    for i, u in enumerate(UNDERS):
        ric = u['ric']; s = spot.get(ric, {})
        chg = s.get('chg'); px = s.get('px')
        chgs = f'<span class="up">+{chg:.2f}%</span>' if (chg or 0) >= 0 else f'<span class="dn">{chg:.2f}%</span>'
        tabs.append(f'<div class="tab{" active" if i==0 else ""}" onclick="showUL(\'hk-{u["key"]}\',this)"><div class="tn">{u["iname"]}</div><div class="ts">指数 <b>{fmt(px,2)}</b> {chgs}</div></div>')
        # 产品子tab
        subtabs, prods = [], []
        for j, pt in enumerate(PTYPES):
            p = pmap.get((u['key'], PTNM[pt]))
            if p is None:
                subtabs.append(f'<span class="subtab off">{"ETF期权 · 无此产品" if pt=="ETF" else PTYPE_NM[pt] + " · 暂无数据"}</span>')
                continue
            tabkey = p['tab']
            sub = {'IDX': f'{p["ats"]} · 现金交割', 'FOP': f'{p["ats"]} · 实物交割(期货)', 'ETF': f'{p.get("symnm","")} {p.get("sym","")}'}[pt]
            subtabs.append(f'<span class="subtab{" active" if j==0 else ""}" onclick="showProd(\'{tabkey}\',this)">{PTYPE_NM[pt]} · {sub}</span>')
            nav = ''.join(f'<a href="#{tabkey}-{m}">{int(m[:2])}月</a>' for m in p['months'])
            panels = ''.join(panel(p, m, p['chains'][m]) for m in p['months'] if m in p['chains'])
            prods.append(f'<div class="prodpane{" show" if j==0 else ""}" id="prod-{tabkey}"><div class="mnav">{nav}</div>{panels}</div>')
        panes.append(f'<div class="ulpane{" show" if i==0 else ""}" id="ul-hk-{u["key"]}"><div class="subtabs">{"".join(subtabs)}</div>{"".join(prods)}</div>')
    return ''.join(tabs), ''.join(panes)
