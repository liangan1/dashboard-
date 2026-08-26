#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
构建A股Tab并注入看板：
- 替换原来的"更多"占位Tab
- 结构与美股Tab一致：吸顶导航 + 市场脉搏 + 板块资金 + 个股资金 + 典型个股
"""
import json, os

DASHBOARD = '/Coze/Drive/扣子/treasury_dashboard/index.html'
DATA = '/Coze/Drive/金融分析/a_share_data.json'
SPARK = '/Coze/Drive/金融分析/a_share_spark.json'

with open(DASHBOARD, 'r', encoding='utf-8') as f:
    html = f.read()
with open(DATA, 'r', encoding='utf-8') as f:
    d = json.load(f)
with open(SPARK, 'r', encoding='utf-8') as f:
    sp = json.load(f)

def fmt_yi(val):
    """Format value in 元 to 亿/万"""
    if val is None: return '-'
    yi = val / 1e8
    if abs(yi) >= 1:
        return f"{yi:+.2f}亿" if yi != 0 else "0"
    wan = val / 1e4
    return f"{wan:+.0f}万"

def fmt_amount(val):
    if val is None: return '-'
    yi = val / 1e8
    return f"{yi:.1f}亿" if yi >= 1 else f"{val/1e4:.0f}万"

def color_chg(val):
    try: val = float(val)
    except: return "#9ca3af"
    if val > 0: return '#ef4444'
    if val < 0: return '#22c55e'
    return '#9ca3af'

def color_flow(val):
    try: val = float(val)
    except: return "#9ca3af"
    if val > 0: return '#ef4444'
    if val < 0: return '#22c55e'
    return '#9ca3af'

# ========== Build data objects ==========
indices = d['indices']
sectors = d['sector_flow']
concepts = d['concept_flow']
stk_in = d['stock_inflow']
stk_out = d['stock_outflow']
stk_vol = d['stock_volume']
mf = d['market_flow']
top_gainers = d['limit_up']
top_losers = d['limit_down']
spark_stocks = sp['stocks']
spark_indices = sp['indices']

# ========== 1. Sub-nav ==========
subnav = '''
    <div class="us-subnav" id="aSubnav">
      <a href="#a-pulse" class="us-subnav-link active">🔥 市场脉搏</a>
      <a href="#a-sector" class="us-subnav-link">🏭 行业资金</a>
      <a href="#a-concept" class="us-subnav-link">💡 概念板块</a>
      <a href="#a-fund" class="us-subnav-link">💰 个股资金</a>
      <a href="#a-stocks" class="us-subnav-link">🏢 龙头个股</a>
    </div>
'''

# ========== 2. Market Pulse ==========
idx_cards = ''
idx_colors = {
    'sh000001': '#ef4444', 'sz399001': '#22c55e', 'sz399006': '#3b82f6',
    'sh000688': '#f59e0b', 'sh000016': '#8b5cf6', 'sh000905': '#06b6d4'
}
for code, idx in indices.items():
    c = idx_colors.get(code, '#6b7280')
    chg_cls = 'up' if idx['chg_pct'] > 0 else ('down' if idx['chg_pct'] < 0 else '')
    arrow = '▲' if idx['chg_pct'] > 0 else ('▼' if idx['chg_pct'] < 0 else '—')
    idx_cards += f'''<div class="ov-card" style="border-top:3px solid {c};padding:10px">
      <div class="ov-label" style="font-size:11px">{idx['name']}</div>
      <div class="ov-value" style="font-size:18px">{idx['price']:,.2f}</div>
      <div class="ov-chg {chg_cls}" style="font-size:12px">{arrow}{idx['chg_pct']:+.2f}%</div>
    </div>
'''

# Top inflow/outflow sectors for heatmap (top 6 each)
inflow_secs = sorted([s for s in sectors if s['main_net'] > 0], key=lambda x: x['main_net'], reverse=True)[:6]
outflow_secs = sorted([s for s in sectors if s['main_net'] < 0], key=lambda x: x['main_net'])[:6]
max_flow = max(abs(s['main_net']) for s in sectors) if sectors else 1

heatmap = ''
for s in inflow_secs + outflow_secs:
    flow_yi = s['main_net'] / 1e8
    c = color_flow(flow_yi)
    opacity = min(abs(flow_yi) / max_flow * 0.4 + 0.08, 0.5)
    sign = '+' if flow_yi > 0 else ''
    heatmap += f'''<div style="background:{c}{int(opacity*255):02x};border:1px solid {c}44;border-radius:8px;padding:8px 6px;text-align:center;cursor:default" title="{s['name']}: {sign}{flow_yi:.2f}亿, {s['up_count']}涨{s['down_count']}跌, 涨幅{s['chg_pct']:+.2f}%">
      <div style="font-size:10px;color:#9ca3af;margin-bottom:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{s['name']}</div>
      <div style="font-size:14px;font-weight:700;color:{c}">{sign}{flow_yi:.1f}</div>
      <div style="font-size:10px;color:#6b7280">{s['up_count']}↑{s['down_count']}↓</div>
    </div>
'''

# Market flow summary
pulse = f'''
    <div id="a-pulse" style="scroll-margin-top:60px">
      <div class="section-divider"><span>🔥 市场脉搏</span></div>
      <div class="us-rt-time">数据更新: {d['fetch_time']} · 东方财富（延时约3分钟）· 新浪财经（K线）</div>
      
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px">
        {idx_cards}
      </div>
      
      <!-- 大盘资金总览 -->
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px">
        <div style="background:rgba(239,68,68,.08);border:1px solid rgba(239,68,68,.2);border-radius:8px;padding:10px">
          <div style="font-size:11px;color:#9ca3af">主力净流入</div>
          <div style="font-size:20px;font-weight:700;color:{color_flow(mf['main_net'])}">{mf['main_net']:+.2f}亿</div>
          <div style="font-size:10px;color:#6b7280">全市场聚合</div>
        </div>
        <div style="background:rgba(59,130,246,.08);border:1px solid rgba(59,130,246,.2);border-radius:8px;padding:10px">
          <div style="font-size:11px;color:#9ca3af">两市成交额</div>
          <div style="font-size:20px;font-weight:700;color:#60a5fa">{mf['total_amount']:.0f}亿</div>
          <div style="font-size:10px;color:#6b7280">沪深合计</div>
        </div>
        <div style="background:rgba(245,158,11,.08);border:1px solid rgba(245,158,11,.2);border-radius:8px;padding:10px">
          <div style="font-size:11px;color:#9ca3af">涨跌家数</div>
          <div style="font-size:20px;font-weight:700"><span style="color:#ef4444">{mf['up_count']}↑</span> <span style="color:#22c55e">{mf['down_count']}↓</span></div>
          <div style="font-size:10px;color:#6b7280">全市场</div>
        </div>
        <div style="background:rgba(139,92,246,.08);border:1px solid rgba(139,92,246,.2);border-radius:8px;padding:10px">
          <div style="font-size:11px;color:#9ca3af">超大单净额</div>
          <div style="font-size:20px;font-weight:700;color:{color_flow(mf['super_large'])}">{mf['super_large']:+.2f}亿</div>
          <div style="font-size:10px;color:#6b7280">大单{mf['large']:+.2f}亿</div>
        </div>
      </div>
      
      <!-- 资金分层 -->
      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap">
        <div style="flex:1;min-width:100px;background:rgba(255,255,255,.03);border-radius:6px;padding:8px 10px">
          <div style="font-size:10px;color:#6b7280">超大单</div>
          <div style="font-size:14px;font-weight:600;color:{color_flow(mf['super_large'])}">{mf['super_large']:+.2f}亿</div>
        </div>
        <div style="flex:1;min-width:100px;background:rgba(255,255,255,.03);border-radius:6px;padding:8px 10px">
          <div style="font-size:10px;color:#6b7280">大单</div>
          <div style="font-size:14px;font-weight:600;color:{color_flow(mf['large'])}">{mf['large']:+.2f}亿</div>
        </div>
        <div style="flex:1;min-width:100px;background:rgba(255,255,255,.03);border-radius:6px;padding:8px 10px">
          <div style="font-size:10px;color:#6b7280">中单</div>
          <div style="font-size:14px;font-weight:600;color:{color_flow(mf['medium'])}">{mf['medium']:+.2f}亿</div>
        </div>
        <div style="flex:1;min-width:100px;background:rgba(255,255,255,.03);border-radius:6px;padding:8px 10px">
          <div style="font-size:10px;color:#6b7280">小单</div>
          <div style="font-size:14px;font-weight:600;color:{color_flow(mf['small'])}">{mf['small']:+.2f}亿</div>
        </div>
      </div>
      
      <!-- 行业资金热力图 -->
      <div style="font-size:13px;font-weight:600;color:#9ca3af;margin-bottom:8px;padding-left:2px">行业板块资金热力图（主力净流入 亿元）</div>
      <div style="display:grid;grid-template-columns:repeat(6,1fr);gap:6px;margin-bottom:12px">
        {heatmap}
      </div>
      
      <!-- 涨跌停速览 -->
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:6px">
        <div style="background:rgba(239,68,68,.05);border:1px solid rgba(239,68,68,.15);border-radius:8px;padding:10px">
          <div style="font-size:12px;font-weight:600;color:#ef4444;margin-bottom:6px">🔴 涨幅榜 TOP5</div>
          {''.join(f'<div style="display:flex;justify-content:space-between;padding:3px 0;font-size:12px"><span>{s["name"]} ({s["code"]})</span><span style="color:#ef4444;font-weight:600">{s["chg_pct"]:+.2f}%</span></div>' for s in top_gainers[:5])}
        </div>
        <div style="background:rgba(34,197,94,.05);border:1px solid rgba(34,197,94,.15);border-radius:8px;padding:10px">
          <div style="font-size:12px;font-weight:600;color:#22c55e;margin-bottom:6px">🟢 跌幅榜 TOP5</div>
          {''.join(f'<div style="display:flex;justify-content:space-between;padding:3px 0;font-size:12px"><span>{s["name"]} ({s["code"]})</span><span style="color:#22c55e;font-weight:600">{s["chg_pct"]:+.2f}%</span></div>' for s in top_losers[:5])}
        </div>
      </div>
    </div>
'''

# ========== 3. Sector Fund Flow Table ==========
sector_rows = ''
for s in sectors:
    flow = s['main_net'] / 1e8
    c = color_flow(flow)
    bar_pct = abs(flow) / max_flow * 100 if max_flow else 0
    super_yi = s['super_large'] / 1e8
    large_yi = s['large'] / 1e8
    sign = '+' if flow > 0 else ''
    leader = s.get('leader', '')
    sector_rows += f'''<tr>
      <td><span style="font-weight:600;color:#e5e7eb">{s['name']}</span><div style="font-size:10px;color:#6b7280">{s['up_count']}涨{s['down_count']}跌</div></td>
      <td style="min-width:110px">
        <div style="display:flex;align-items:center;gap:6px">
          <div style="flex:1;height:16px;background:rgba(255,255,255,.04);border-radius:3px;position:relative;overflow:hidden">
            <div style="position:absolute;{"right" if flow<0 else "left"}:0;width:{bar_pct:.1f}%;height:100%;background:{c}33;border-radius:3px"></div>
          </div>
          <span style="font-weight:700;color:{c};white-space:nowrap;font-size:12px">{sign}{flow:.2f}亿</span>
        </div>
      </td>
      <td style="text-align:right;font-size:11px;color:{color_flow(super_yi)}">{"+" if super_yi>0 else ""}{super_yi:.2f}</td>
      <td style="text-align:right;font-size:11px;color:{color_flow(large_yi)}">{"+" if large_yi>0 else ""}{large_yi:.2f}</td>
      <td style="text-align:right"><span style="color:{color_chg(s['chg_pct'])};font-weight:600;font-size:12px">{s['chg_pct']:+.2f}%</span></td>
      <td style="font-size:11px"><span style="color:#e5e7eb">{leader}</span> <span style="color:{color_chg(float(s.get('leader_chg',0) or 0))}">{"+" if float(s.get('leader_chg',0) or 0)>0 else ""}{float(s.get('leader_chg',0) or 0):.1f}%</span></td>
    </tr>'''

sector_section = f'''
    <div id="a-sector" style="scroll-margin-top:60px"></div>
    <div class="section-divider"><span>🏭 行业板块资金流向</span></div>
    <div style="font-size:11px;color:#6b7280;margin-bottom:10px">共{len(sectors)}个行业板块 · 数据源：东方财富 · 主力=超大单+大单</div>
    <div style="overflow-x:auto">
    <table class="ftab" style="width:100%;font-size:12px">
      <thead><tr><th>行业</th><th>主力净流入</th><th style="text-align:right">超大单</th><th style="text-align:right">大单</th><th style="text-align:right">涨幅</th><th>龙头股</th></tr></thead>
      <tbody>{sector_rows}</tbody>
    </table>
    </div>
'''

# ========== 4. Concept Sectors ==========
concept_rows = ''
max_concept_flow = max(abs(c['main_net']) for c in concepts) if concepts else 1
# Show top 20 by absolute flow
concepts_sorted = sorted(concepts, key=lambda x: abs(x['main_net']), reverse=True)[:20]
for c in concepts_sorted:
    flow = c['main_net'] / 1e8
    col = color_flow(flow)
    bar_pct = abs(flow) / max_concept_flow * 100
    sign = '+' if flow > 0 else ''
    concept_rows += f'''<tr>
      <td><span style="font-weight:600;color:#e5e7eb">{c['name']}</span></td>
      <td style="min-width:110px">
        <div style="display:flex;align-items:center;gap:6px">
          <div style="flex:1;height:16px;background:rgba(255,255,255,.04);border-radius:3px;position:relative;overflow:hidden">
            <div style="position:absolute;{"right" if flow<0 else "left"}:0;width:{bar_pct:.1f}%;height:100%;background:{col}33"></div>
          </div>
          <span style="font-weight:700;color:{col};white-space:nowrap;font-size:12px">{sign}{flow:.2f}亿</span>
        </div>
      </td>
      <td style="text-align:right;font-size:11px;color:#9ca3af">{c['up_count']}涨{c['down_count']}跌</td>
      <td style="text-align:right"><span style="color:{color_chg(c['chg_pct'])};font-weight:600;font-size:12px">{c['chg_pct']:+.2f}%</span></td>
      <td style="font-size:11px;color:#e5e7eb">{c.get('leader','')}</td>
    </tr>'''

concept_section = f'''
    <div id="a-concept" style="scroll-margin-top:60px"></div>
    <div class="section-divider"><span>💡 概念板块资金流向</span></div>
    <div style="font-size:11px;color:#6b7280;margin-bottom:10px">资金净流入/流出绝对值TOP20概念板块 · 数据源：东方财富</div>
    <div style="overflow-x:auto">
    <table class="ftab" style="width:100%;font-size:12px">
      <thead><tr><th>概念</th><th>主力净流入</th><th style="text-align:right">涨跌</th><th style="text-align:right">涨幅</th><th>龙头</th></tr></thead>
      <tbody>{concept_rows}</tbody>
    </table>
    </div>
'''

# ========== 5. Individual Stock Fund Flow ==========
def stock_flow_rows(stocks, is_inflow=True):
    rows = ''
    for s in stocks:
        flow_yi = s['main_net'] / 1e8
        c = '#ef4444' if is_inflow else '#22c55e'
        if not is_inflow and flow_yi > 0: c = '#ef4444'
        if is_inflow and flow_yi < 0: c = '#22c55e'
        chg_c = color_chg(s['chg_pct'])
        rows += f'''<tr>
          <td><span class="fn">{s['name']}</span><span class="fc">{s['code']}</span><div style="font-size:10px;color:#6b7280">{s.get('industry','')}</div></td>
          <td><span style="color:{'#ef4444' if s['chg_pct']>0 else '#22c55e'};font-weight:600">{s['chg_pct']:+.2f}%</span></td>
          <td class="{"fp" if is_inflow else "fn2"}" style="color:{c};font-weight:700">{flow_yi:+.2f}亿</td>
          <td style="text-align:right;color:#9ca3af;font-size:11px">{s.get('main_pct',0):+.1f}%</td>
          <td style="text-align:right;color:#9ca3af;font-size:11px">{s['amount']/1e8:.1f}亿</td>
        </tr>'''
    return rows

inflow_table = stock_flow_rows(stk_in, True)
outflow_table = stock_flow_rows(stk_out, False)

# Volume table
vol_rows = ''
for s in stk_vol:
    flow_yi = s.get('main_net', 0) / 1e8
    chg_c = color_chg(s['chg_pct'])
    vol_rows += f'''<tr>
      <td><span class="fn">{s['name']}</span><span class="fc">{s['code']}</span></td>
      <td>¥{s['price']:.2f}</td>
      <td><span style="color:{chg_c};font-weight:600">{s['chg_pct']:+.2f}%</span></td>
      <td style="color:{color_flow(flow_yi)};font-size:11px">{flow_yi:+.2f}亿</td>
      <td style="text-align:right">{s['amount']/1e8:.1f}亿</td>
    </tr>'''

fund_section = f'''
    <div id="a-fund" style="scroll-margin-top:60px"></div>
    <div class="section-divider"><span>💰 个股主力资金流向</span></div>
    <div style="font-size:11px;color:#6b7280;margin-bottom:10px">数据源：东方财富（延时约3分钟）· 主力=超大单+大单</div>
    <div class="flow-grid">
      <div class="ftw">
        <div class="ftt" style="color:#ef4444">🔴 主力净流入 TOP20</div>
        <table class="ftab"><thead><tr><th>股票</th><th>涨跌</th><th>主力净流入</th><th style="text-align:right">占比</th><th style="text-align:right">成交额</th></tr></thead>
        <tbody>{inflow_table}</tbody></table>
      </div>
      <div class="ftw">
        <div class="ftt" style="color:#22c55e">🟢 主力净流出 TOP20</div>
        <table class="ftab"><thead><tr><th>股票</th><th>涨跌</th><th>主力净流出</th><th style="text-align:right">占比</th><th style="text-align:right">成交额</th></tr></thead>
        <tbody>{outflow_table}</tbody></table>
      </div>
    </div>
    <div style="margin-top:12px">
      <div class="ftw" style="margin-bottom:16px">
        <div class="ftt">📊 成交额 TOP20</div>
        <table class="ftab"><thead><tr><th>股票</th><th>现价</th><th>涨跌幅</th><th>主力净额</th><th style="text-align:right">成交额</th></tr></thead>
        <tbody>{vol_rows}</tbody></table>
      </div>
    </div>
'''

# ========== 6. Stock Cards with Sparklines ==========
# Group stocks by sector
stock_groups = {}
for sym, s in spark_stocks.items():
    sec = s.get('sector', '其他')
    if sec not in stock_groups:
        stock_groups[sec] = []
    stock_groups[sec].append((sym, s))

stock_cards_html = ''
for group_name, stocks_list in stock_groups.items():
    cards = ''
    for sym, s in stocks_list:
        # Get latest price change from data if available
        code = sym[2:]  # remove sh/sz
        price_info = ''
        chg_pct = 0
        for stk in stk_in + stk_out + stk_vol:
            if stk['code'] == code:
                chg_pct = stk['chg_pct']
                price_info = f'¥{stk["price"]:.2f}'
                break
        if not price_info:
            # Use last close from sparkline
            last = s['c'][-1]
            prev = s['c'][-2] if len(s['c']) > 1 else last
            chg_pct = ((last - prev) / prev * 100) if prev else 0
            price_info = f'¥{last:.2f}'
        
        chg_cls = 'up' if chg_pct > 0 else ('dn' if chg_pct < 0 else '')
        # 52-week range approximation from 60 days
        hi = max(s['c'])
        lo = min(s['c'])
        last = s['c'][-1]
        pos_pct = ((last - lo) / (hi - lo) * 100) if hi > lo else 50
        pos_color = '#ef4444' if chg_pct > 0 else '#22c55e'
        
        cards += f'''<div class="scard">
          <div class="sch"><div><span class="ssym">{sym[2:]}</span><span class="snm">{s['name']}</span></div></div>
          <div style="display:flex;justify-content:space-between;align-items:baseline;margin-top:4px">
            <div class="sprc">{price_info}</div>
            <div class="schg {chg_cls}">{chg_pct:+.2f}%</div>
          </div>
          <div class="sspk" id="aspark_{sym}"></div>
          <div style="height:3px;background:rgba(255,255,255,.08);border-radius:2px;margin:4px 0;position:relative">
            <div style="position:absolute;left:{pos_pct:.0f}%;top:-2px;width:2px;height:7px;background:{pos_color};border-radius:1px;transform:translateX(-50%)"></div>
          </div>
          <div class="smeta"><span>低 {lo:.2f}</span><span>高 {hi:.2f}</span></div>
        </div>'''
    
    stock_cards_html += f'''
    <div style="margin-bottom:16px">
      <div style="font-size:13px;font-weight:600;color:#9ca3af;margin-bottom:8px;padding-left:2px">{group_name}</div>
      <div class="sgrid">{cards}</div>
    </div>'''

stocks_section = f'''
    <div id="a-stocks" style="scroll-margin-top:60px"></div>
    <div class="section-divider"><span>🏢 龙头个股表现</span></div>
    <div style="font-size:11px;color:#6b7280;margin-bottom:10px">K线：新浪财经（近60日）· 实时：东方财富 · 位置条为60日高低区间</div>
    {stock_cards_html}
    <div style="text-align:center;padding:16px;color:#6b7280;font-size:11px">
      数据来源：<a href="https://quote.eastmoney.com/" target="_blank" rel="noopener noreferrer">东方财富</a>（资金流向/行情）· 
      <a href="https://finance.sina.com.cn/" target="_blank" rel="noopener noreferrer">新浪财经</a>（K线）
    </div>
'''

# ========== 7. Assemble full A-share tab ==========
a_tab = f'''<div class="tab-page" id="page-a-shares">
    {subnav}
    {pulse}
    {sector_section}
    {concept_section}
    {fund_section}
    {stocks_section}
  '''

# ========== 8. Inject into HTML ==========
# Replace the "更多" tab with A-share tab
more_start = html.find('<div class="tab-page" id="page-more">')
if more_start == -1:
    print("ERROR: Could not find page-more")
    exit(1)

# Find the end of page-more (before tab-bar)
tab_bar_pos = html.find('<nav class="tab-bar"', more_start)
more_block = html[more_start:tab_bar_pos]
print(f"Replacing more block: {len(more_block)} chars")

html = html[:more_start] + a_tab + '\n\n    ' + html[tab_bar_pos:]

# ========== 9. Update tab bar ==========
old_more_btn = '''<button class="tab-btn" data-tab="more">
        <span class="tab-icon">⚙️</span>
        <span class="tab-label">更多</span>
      </button>'''
new_a_btn = '''<button class="tab-btn" data-tab="a-shares">
        <span class="tab-icon">🇨🇳</span>
        <span class="tab-label">A股</span>
      </button>'''
if old_more_btn in html:
    html = html.replace(old_more_btn, new_a_btn)
    print("Updated tab bar button")
else:
    print("WARNING: Could not find more button to replace")

# ========== 10. Add A-share sparkline JS data ==========
spark_js = 'var ASPARK=' + json.dumps(spark_stocks, ensure_ascii=False) + ';'

# Find the SPARK data line and add ASPARK after it
spark_marker = 'var SPARK='
spark_pos = html.find(spark_marker)
if spark_pos != -1:
    # Find end of this line
    line_end = html.find('\n', spark_pos)
    html = html[:line_end] + '\n    ' + spark_js + html[line_end:]
    print("Added ASPARK data")

# ========== 11. Add A-share sparkline init function ==========
init_a_sparks_js = '''
    function initASparks(){
      if (typeof ASPARK === 'undefined') return;
      Object.keys(ASPARK).forEach(function(sym){
        var el=document.getElementById('aspark_'+sym);
        if(!el||el.getAttribute('data-rendered'))return;
        var d=ASPARK[sym];
        if(!d||!d.c||!d.c.length)return;
        var chart=echarts.init(el,null,{renderer:'canvas'});
        var up=d.c[d.c.length-1]>=d.c[0];
        var color=up?'#ef4444':'#22c55e';
        chart.setOption({
          grid:{left:0,right:0,top:2,bottom:2},
          xAxis:{type:'category',show:false,data:d.d},
          yAxis:{type:'value',show:false,scale:true},
          series:[{type:'line',data:d.c,smooth:true,symbol:'none',lineStyle:{width:1.5,color:color},
            areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:color+'44'},{offset:1,color:color+'00'}])}}]
        });
        el.setAttribute('data-rendered','1');
        window.addEventListener('resize',function(){chart.resize()});
      });
    }
'''

# Add initASparks before the tab switch logic
tab_switch_marker = "if (target === 'us-stocks') { initUsCharts(); initSparks(); }"
if tab_switch_marker in html:
    html = html.replace(tab_switch_marker, 
        tab_switch_marker + "\n    if (target === 'a-shares') initASparks();")
    # Add function definition before the switch
    script_end = html.find('</script>', html.find(tab_switch_marker))
    html = html[:script_end] + init_a_sparks_js + '\n    ' + html[script_end:]
    print("Added initASparks function")

# ========== 12. Add A-share subnav scroll spy ==========
a_subnav_js = '''
    (function(){
      var links=document.querySelectorAll('#aSubnav .us-subnav-link');
      if(!links.length)return;
      var sections=[];
      links.forEach(function(link){
        var href=link.getAttribute('href');
        if(href&&href.charAt(0)==='#'){
          var el=document.querySelector(href);
          if(el)sections.push({el:el,link:link});
        }
      });
      function onScroll(){
        var current=sections[0];
        sections.forEach(function(s){
          if(s.el.getBoundingClientRect().top<=100)current=s;
        });
        links.forEach(function(l){l.classList.remove('active')});
        if(current)current.link.classList.add('active');
      }
      window.addEventListener('scroll',onScroll,{passive:true});
      links.forEach(function(link){
        link.addEventListener('click',function(e){
          e.preventDefault();
          var target=document.querySelector(link.getAttribute('href'));
          if(target){
            var top=target.getBoundingClientRect().top+window.pageYOffset-56;
            window.scrollTo({top:top,behavior:'smooth'});
          }
        });
      });
    })();
'''

last_script_end = html.rfind('</script>')
if last_script_end != -1:
    html = html[:last_script_end] + a_subnav_js + '\n    ' + html[last_script_end:]
    print("Added A-share subnav JS")

# ========== 13. Save ==========
with open(DASHBOARD, 'w', encoding='utf-8') as f:
    f.write(html)

size = os.path.getsize(DASHBOARD)
print(f"\n✅ Done! File size: {size:,} bytes ({size/1024:.0f} KB)")

# Verify
checks = [
    ('page-a-shares', 'A-share tab page'),
    ('aSubnav', 'A-share subnav'),
    ('市场脉搏', 'Pulse'),
    ('行业板块资金流向', 'Sector flow'),
    ('概念板块资金流向', 'Concept flow'),
    ('个股主力资金流向', 'Stock flow'),
    ('龙头个股表现', 'Stock cards'),
    ('ASPARK', 'ASPARK data'),
    ('initASparks', 'Init function'),
    ('data-tab="a-shares"', 'Tab button'),
    ('page-more', 'More page (should be gone)'),
]
for term, name in checks:
    found = term in html
    expect = name != 'More page (should be gone)'
    ok = found == expect
    print(f"  {'✅' if ok else '❌'} {name}: {'found' if found else 'not found'}")
