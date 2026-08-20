# -*- coding: utf-8 -*-
"""美股期权渲染: S&P500/Nasdaq100/Russell2000, 每个标的内含3个产品子tab(ETF/指数/期货期权)
数据源: CBOE 延迟报价(ETF+指数期权, 含IV/Greeks/持仓) + CME官网延迟行情(期货期权, 仅Last/结算/量)"""
import json, os
from datetime import date, datetime
from math import exp

R = 0.04  # 美元无风险利率约4%
HERE = os.path.dirname(os.path.abspath(__file__))

def fmt(x, nd=2): return '—' if x is None else f'{x:,.{nd}f}'
def fmti(x): return '—' if x is None else f'{x:,.0f}'

UNDERS = [
 dict(key='SPX', iname='S&P 500 标普500'),
 dict(key='NDX', iname='Nasdaq 100 纳斯达克100'),
 dict(key='RUT', iname='Russell 2000 罗素2000'),
]
PTYPES = ['ETF', 'IDX', 'FOP']
PTYPE_NM = {'ETF': 'ETF期权', 'IDX': '指数期权', 'FOP': '期货期权'}


def render_us(today):
    fp = os.path.join(HERE, 'us_data.json')
    if not os.path.exists(fp): return '', ''
    us = json.load(open(fp))
    cme_fp = os.path.join(HERE, 'cme_data.json')
    cme = json.load(open(cme_fp)) if os.path.exists(cme_fp) else {'products': {}, 'fetched_at': ''}

    def side(q, is_call, mcls, K, k_atm, mult, days, S):
        if not q: return ''.join(f'<td class="na {mcls}">—</td>' for _ in range(6))
        ls, bd, ask, oi, iv = q.get('ls'), q.get('bd'), q.get('as'), q.get('oi'), q.get('iv')
        mid = (bd+ask)/2 if (bd is not None and ask is not None) else None
        basis = mid if mid is not None else ls
        star = '*' if (mid is None and basis is not None) else ''
        if basis is not None and S:
            mg = ((basis + max(0.12*S - max(K-S,0), 0.07*S)) if is_call else
                  min(basis + max(0.12*S - max(S-K,0), 0.07*K), K)) * mult
            ann = basis*mult/mg*365/days
        else:
            mg = ann = None
        show_ann = (K >= k_atm-1e-9) if is_call else (K <= k_atm+1e-9)
        anns = f'{ann*100:.0f}%' if (show_ann and ann is not None) else ''
        ba = f'{fmt(bd)}/{fmt(ask)}' if (bd is not None or ask is not None) else '—'
        cells = [f'<td class="px {mcls}">{fmt(basis)}{star}</td>',
                 f'<td class="ba {mcls}">{ba}</td>',
                 f'<td class="{mcls}">{iv:.1f}%</td>' if iv is not None else f'<td class="{mcls}">—</td>',
                 f'<td class="oi {mcls}">{fmti(oi)}</td>',
                 f'<td class="{mcls}">${fmti(mg)}</td>' if mg else f'<td class="{mcls}">—</td>',
                 f'<td class="ann {"" if show_ann else "dim"} {mcls}">{anns}</td>']
        if not is_call: cells.reverse()
        return ''.join(cells)

    def row(rw, S, k_atm, mult, days):
        K = rw['K']; qc, qp = rw.get('c') or {}, rw.get('p') or {}
        atm = abs(K-k_atm) < 1e-9
        cmcls = 'itmz' if K < k_atm-1e-9 else ('atmz' if atm else 'otmz')
        pmcls = 'otmz' if K < k_atm-1e-9 else ('atmz' if atm else 'itmz')
        F = None
        bc = ((qc['bd']+qc['as'])/2 if qc.get('bd') is not None and qc.get('as') is not None else qc.get('ls'))
        bp = ((qp['bd']+qp['as'])/2 if qp.get('bd') is not None and qp.get('as') is not None else qp.get('ls'))
        if bc is not None and bp is not None and S:
            F = K + (bc-bp)*exp(R*days/365)
        mny = (K/S-1)*100 if S else 0
        ftxt = f'F {F:,.0f} <span class="fd">({(F/S-1)*100:+.2f}%)</span>' if F else ''
        return (f'<tr{" class=\"atmr\"" if atm else ""}>{side(qc,True,cmcls,K,k_atm,mult,days,S)}'
                f'<td class="kcell"><div class="k">{K:,.0f}</div><div class="mny">M {mny:+.1f}%</div><div class="fwd">{ftxt}</div></td>'
                f'{side(qp,False,pmcls,K,k_atm,mult,days,S)}</tr>')

    def panel(tabkey, exp_s, rows, S, ref, mult):
        if not rows: return ''
        exp_d = date.fromisoformat(exp_s)
        days = max((exp_d-today).days, 1)
        # 稀疏化: moneyness -20%..+20%, 每1%取一个最接近的代表性行权价
        avail = sorted({rw['K'] for rw in rows})
        picks = []
        for m in range(-20, 21):
            tgt = S * (1 + m / 100)
            k = min(avail, key=lambda x: abs(x - tgt))
            if not picks or k != picks[-1]:
                picks.append(k)
        kset = set(picks)
        rows = [rw for rw in rows if rw['K'] in kset]
        ks = [rw['K'] for rw in rows]
        k_atm = min(ks, key=lambda k: abs(k-S))
        body = ''.join(row(rw, S, k_atm, mult, days) for rw in rows)
        return f'''<section class="panel" id="{tabkey}-{exp_s}">
<div class="phead"><span class="pt">{exp_d.year}年{exp_d.month}月到期 · 参考: {ref} {S:,.2f}</span><span class="ps">到期日 {exp_s} · 剩余 {days} 天 · M -20%~+20% 每1%一档共 {len(rows)} 档</span></div>
<table class="tq"><thead><tr>
<th colspan="6" class="hc">认购 CALL</th><th class="hk">行权价 Strike<br><span class="hsub">M = 在值程度 · F = 合成远期</span></th><th colspan="6" class="hp">认沽 PUT</th></tr>
<tr class="cols"><th>最新价</th><th>买/卖</th><th>IV</th><th>持仓量</th><th>保证金*</th><th>年化*</th>
<th></th>
<th>年化*</th><th>保证金*</th><th>持仓量</th><th>IV</th><th>买/卖</th><th>最新价</th></tr></thead>
<tbody>{body}</tbody></table></section>'''

    def fop_panel(tabkey, P):
        S = P['future_px']; exp_d = date.fromisoformat(P['expiry'])
        days = max((exp_d-today).days, 1)
        rows = P['rows']
        k_atm = min((r['K'] for r in rows), key=lambda k: abs(k-S))
        qc, qp = next(r['c'] for r in rows if r['K']==k_atm), next(r['p'] for r in rows if r['K']==k_atm)
        F = None
        if qc.get('settle') is not None and qp.get('settle') is not None:
            F = k_atm + (qc['settle']-qp['settle'])*exp(R*days/365)
        trs = []
        for r in rows:
            K = r['K']; atm = abs(K-k_atm) < 1e-9
            mny = (K/S-1)*100
            ftxt = f'F {F:,.0f} <span class="fd">({(F/S-1)*100:+.2f}%)</span> <span class="fs">settle</span>' if (atm and F) else ''
            def c4(x):
                if not x: return ''.join('<td class="na">—</td>' for _ in range(4))
                return (f'<td class="px">{fmt(x.get("ls"))}</td><td>{fmt(x.get("settle"))}</td>'
                        f'<td>{x.get("chg") or "—"}</td><td class="oi">{fmti(x.get("vo"))}</td>')
            ccells = c4(r['c'])
            # put side reversed order: 成交量/涨跌/前结算/最新价
            p = r['p']
            if p:
                pr = (f'<td class="oi">{fmti(p.get("vo"))}</td><td>{p.get("chg") or "—"}</td>'
                      f'<td>{fmt(p.get("settle"))}</td><td class="px">{fmt(p.get("ls"))}</td>')
            else:
                pr = ''.join('<td class="na">—</td>' for _ in range(4))
            trs.append(f'<tr{" class=\"atmr\"" if atm else ""}>{ccells}'
                       f'<td class="kcell"><div class="k">{K:,.0f}</div><div class="mny">M {mny:+.1f}%</div><div class="fwd">{ftxt}</div></td>'
                       f'{pr}</tr>')
        return f'''<section class="panel" id="{tabkey}-{P['expiry']}">
<div class="phead"><span class="pt">{exp_d.year}年{exp_d.month}月到期 · 参考: 期货 {P['future_code']} {S:,.2f}（{P['future_chg']}）</span><span class="ps">到期日 {P['expiry']} · 剩余 {days} 天 · 平值附近±10档 · CME延迟≥10分钟</span></div>
<table class="tq"><thead><tr>
<th colspan="4" class="hc">认购 CALL</th><th class="hk">行权价 Strike<br><span class="hsub">M = 在值程度 · F = 合成远期(按结算价)</span></th><th colspan="4" class="hp">认沽 PUT</th></tr>
<tr class="cols"><th>最新价</th><th>前结算</th><th>涨跌</th><th>成交量</th>
<th></th>
<th>成交量</th><th>涨跌</th><th>前结算</th><th>最新价</th></tr></thead>
<tbody>{''.join(trs)}</tbody></table></section>'''

    tabs, panes = [], []
    for i, u in enumerate(UNDERS):
        key = u['key']
        p0 = us['products'].get(f'{key}-ETF') or us['products'].get(f'{key}-IDX')
        px = p0['spot'] if p0 else None
        tabs.append(f'<div class="tab{" active" if i==0 else ""}" onclick="showUL(\'us-{key}\',this)"><div class="tn">{u["iname"]}</div><div class="ts">参考 <b>{fmt(px,2)}</b></div></div>')
        subtabs, prods = [], []
        for j, pt in enumerate(PTYPES):
            tabkey = f'{key}-{pt}'
            if pt == 'FOP':
                P = cme['products'].get(tabkey)
                if P is None:
                    subtabs.append(f'<span class="subtab off">期货期权 · 暂无数据</span>')
                    continue
                sub = f'{P["future_code"]} · 实物交割(期货)'
                subtabs.append(f'<span class="subtab{" active" if j==0 else ""}" onclick="showProd(\'{tabkey}\',this)">{PTYPE_NM[pt]} · {sub}</span>')
                prods.append(f'<div class="prodpane{" show" if j==0 else ""}" id="prod-{tabkey}">{fop_panel(tabkey, P)}</div>')
                continue
            p = us['products'].get(tabkey)
            if p is None:
                subtabs.append(f'<span class="subtab off">{PTYPE_NM[pt]} · 无此产品</span>')
                continue
            sub = (f'{p["symnm"]} · 实物交割(股票)' if pt == 'ETF' else f'{p["symnm"]} · 现金交割 · 乘数${p["mult"]}/点')
            subtabs.append(f'<span class="subtab{" active" if j==0 else ""}" onclick="showProd(\'{tabkey}\',this)">{PTYPE_NM[pt]} · {sub}</span>')
            ref = f'ETF {p["symnm"]}' if pt == 'ETF' else f'指数 {p["symnm"]}'
            nav = ''.join(f'<a href="#{tabkey}-{e}">{int(e[5:7])}月</a>' for e in p['expiries'] if e in p['chains'])
            panels = ''.join(panel(tabkey, e, p['chains'][e], p['spot'], ref, p['mult']) for e in p['expiries'] if e in p['chains'])
            prods.append(f'<div class="prodpane{" show" if j==0 else ""}" id="prod-{tabkey}"><div class="mnav">{nav}</div>{panels}</div>')
        panes.append(f'<div class="ulpane{" show" if i==0 else ""}" id="ul-us-{key}"><div class="subtabs">{"".join(subtabs)}</div>{"".join(prods)}</div>')
    return ''.join(tabs), ''.join(panes)


if __name__ == '__main__':
    t, p = render_us(date(2026, 8, 17))
    print(len(t), len(p))
