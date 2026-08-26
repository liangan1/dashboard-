#!/usr/bin/env python3
"""
One-shot injection of enhanced US stock data into the dashboard.
Adds: VIX overview card, fund flow tables, individual stock cards with sparklines.
"""
import json, re, os, sys

DASHBOARD = '/Coze/Drive/扣子/treasury_dashboard/index.html'
DATA_FILE = '/Coze/Drive/金融分析/us_enhanced_data.json'
OUTPUT = '/Coze/Drive/扣子/treasury_dashboard/index.html'

# Load data
with open(DATA_FILE, 'r', encoding='utf-8') as f:
    data = json.load(f)

vix = data['vix']
inflow = data['inflow']
outflow = data['outflow']
top_amount = data['top_amount']
stocks = data['stocks']
fetch_time = data['fetch_time']

# Read HTML as text
with open(DASHBOARD, 'r', encoding='utf-8') as f:
    html = f.read()

orig_len = len(html)
print(f"Original: {orig_len/1024:.0f} KB")

# ===================== CSS =====================
NEW_CSS = """
  .flow-section{margin-bottom:20px}
  .flow-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
  @media(max-width:640px){.flow-grid{grid-template-columns:1fr}}
  .ftw{background:rgba(30,41,59,.6);border-radius:10px;padding:12px;border:1px solid rgba(255,255,255,.06)}
  .ftt{font-size:13px;font-weight:600;color:#f9fafb;margin-bottom:10px;display:flex;align-items:center;gap:6px}
  .ftab{width:100%;border-collapse:collapse;font-size:12px}
  .ftab th{text-align:left;padding:6px 8px;color:#9ca3af;font-weight:500;border-bottom:1px solid rgba(255,255,255,.08);font-size:11px}
  .ftab th:nth-child(n+2){text-align:right}
  .ftab td{padding:7px 8px;border-bottom:1px solid rgba(255,255,255,.04);color:#e5e7eb;white-space:nowrap}
  .ftab td:nth-child(n+2){text-align:right;font-variant-numeric:tabular-nums}
  .fn{font-weight:500}
  .fc{color:#6b7280;font-size:10px;margin-left:4px}
  .fp{color:#ef4444;font-weight:600}
  .fn2{color:#22c55e;font-weight:600}
  .sgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(155px,1fr));gap:10px;margin-bottom:16px}
  .scard{background:rgba(30,41,59,.6);border-radius:10px;padding:10px 12px;border:1px solid rgba(255,255,255,.06)}
  .sch{display:flex;justify-content:space-between;align-items:baseline}
  .ssym{font-size:13px;font-weight:700;color:#f9fafb}
  .snm{font-size:10px;color:#6b7280;margin-left:4px}
  .sprc{font-size:15px;font-weight:700;font-variant-numeric:tabular-nums}
  .schg{font-size:11px;font-weight:600;margin-top:2px}
  .schg.up{color:#ef4444}.schg.dn{color:#22c55e}
  .sspk{width:100%;height:36px;margin:6px 0 2px}
  .smeta{display:flex;justify-content:space-between;font-size:10px;color:#6b7280;margin-top:4px}
  .smeta span{font-variant-numeric:tabular-nums}
  .vov{background:rgba(30,41,59,.6);border-radius:10px;padding:12px 14px;border-top:3px solid #f97316}
  .vol{font-size:12px;color:#9ca3af;margin-bottom:4px}
  .vovv{font-size:24px;font-weight:700;font-variant-numeric:tabular-nums}
  .vovc{font-size:12px;margin-top:2px;font-weight:600}
  .vbar{height:4px;border-radius:2px;background:linear-gradient(90deg,#22c55e,#eab308,#f97316,#ef4444);margin-top:8px;position:relative}
  .vmark{position:absolute;top:-3px;width:2px;height:10px;background:#fff;border-radius:1px;transform:translateX(-50%)}
"""

html = html.replace('</style>', NEW_CSS + '\n</style>', 1)
print("CSS injected")

# ===================== VIX OVERVIEW CARD =====================
vix_val = vix['value']
vix_pc = vix['prev_close']
vix_chg = vix['change']
vix_chg_pct = vix['change_pct']
vix_h = vix.get('high', 0)
vix_l = vix.get('low', 0)

if vix_val < 15:
    level, lc = "正常", "#22c55e"
elif vix_val < 25:
    level, lc = "偏高", "#eab308"
elif vix_val < 35:
    level, lc = "恐慌", "#f97316"
else:
    level, lc = "极度恐慌", "#ef4444"

pct = min(max((vix_val - 10) / 30 * 100, 0), 100)
chg_clr = '#ef4444' if vix_chg >= 0 else '#22c55e'
chg_str = f"{'+' if vix_chg>=0 else ''}{vix_chg:.2f} ({'+' if vix_chg_pct>=0 else ''}{vix_chg_pct:.1f}%)"

vix_card = f'''    <div class="section-subtitle">😱 VIX 恐慌指数</div>
    <section class="overview">
      <div class="vov" style="grid-column:1/-1">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <div>
            <div class="vol">CBOE 波动率指数 (VIX)</div>
            <div class="vovv" style="color:{lc}">{vix_val:.2f}</div>
            <div class="vovc" style="color:{chg_clr}">{chg_str} · {level}</div>
          </div>
          <div style="text-align:right;font-size:11px;color:#6b7280">
            <div>昨收 {vix_pc:.2f}</div>
          </div>
        </div>
        <div class="vbar"><div class="vmark" style="left:{pct:.1f}%"></div></div>
        <div style="display:flex;justify-content:space-between;font-size:10px;color:#6b7280;margin-top:4px">
          <span>10 平静</span><span>20</span><span>30 恐慌</span><span>40+ 极度恐慌</span>
        </div>
      </div>
    </section>

    <div class="section-subtitle">🏛️ 联邦债务</div>'''

old_debt = '    <div class="section-subtitle">🏛️ 联邦债务</div>'
html = html.replace(old_debt, vix_card, 1)
print("VIX overview card injected")

# ===================== FUND FLOW TABLES =====================
def fmt_flow(v):
    if not v or v == 0:
        return '0.00亿'
    yi = v / 1e8
    if abs(yi) >= 1:
        return f"{yi:.2f}亿"
    return f"{v/1e4:.0f}万"

def flow_row(it):
    cls = "fp" if it['main_net_inflow'] >= 0 else "fn2"
    pct_v = it.get('main_net_pct', 0)
    pcls = "fp" if pct_v >= 0 else "fn2"
    return (f'<tr><td><span class="fn">{it["name"]}</span>'
            f'<span class="fc">{it["code"]}</span></td>'
            f'<td class="{cls}">{fmt_flow(it["main_net_inflow"])}</td>'
            f'<td class="{pcls}">{pct_v:+.2f}%</td></tr>')

def flow_table(title, items, color):
    rows = '\n'.join(flow_row(it) for it in items[:10])
    return f'''<div class="ftw">
      <div class="ftt" style="color:{color}">{title}</div>
      <table class="ftab"><thead><tr><th>股票</th><th>主力净流入</th><th>占比</th></tr></thead>
      <tbody>{rows}</tbody></table>
    </div>'''

inflow_tbl = flow_table("🔴 主力净流入 TOP10", inflow, "#ef4444")
outflow_tbl = flow_table("🟢 主力净流出 TOP10", outflow, "#22c55e")

# Top amount table
arows = []
for it in top_amount[:10]:
    pcl = '#ef4444' if it['change_pct'] >= 0 else '#22c55e'
    ps = '+' if it['change_pct'] >= 0 else ''
    ayi = it['amount'] / 1e8
    arows.append(
        f'<tr><td><span class="fn">{it["name"]}</span>'
        f'<span class="fc">{it["code"]}</span></td>'
        f'<td>${it["price"]:.2f}</td>'
        f'<td style="color:{pcl};font-weight:600">{ps}{it["change_pct"]:.2f}%</td>'
        f'<td>{ayi:.1f}亿</td></tr>')

amount_tbl = f'''<div class="ftw" style="margin-bottom:16px">
  <div class="ftt">📊 成交额 TOP10</div>
  <table class="ftab"><thead><tr><th>股票</th><th>现价</th><th>涨跌幅</th><th style="text-align:right">成交额</th></tr></thead>
  <tbody>{''.join(arows)}</tbody></table>
</div>'''

flow_section = f'''
    <div class="section-divider"><span>💰 主力资金流向</span></div>
    <div style="font-size:11px;color:#6b7280;margin-bottom:10px">数据来源：东方财富（延时约3分钟）· 更新：{fetch_time} · 主力=超大单+大单</div>
    <div class="flow-grid">{inflow_tbl}{outflow_tbl}</div>
    <div style="margin-top:12px">{amount_tbl}</div>
'''

# ===================== STOCK CARDS =====================
categories = [
    ("科技巨头", ['AAPL','MSFT','NVDA','GOOGL','AMZN','META','TSLA','AVGO']),
    ("半导体", ['AMD','INTC','QCOM','MU']),
    ("软件/互联网", ['NFLX','CRM','ORCL','ADBE']),
    ("金融", ['JPM','V','BAC']),
    ("消费", ['WMT','COST','DIS']),
    ("热门股", ['PLTR','COIN','UBER']),
]

def stock_card(sym, s):
    name = s.get('name', sym)
    price = s.get('rt_price', s.get('latest_close', 0))
    chg_pct = s.get('rt_change_pct', 0)
    h52 = s.get('high_52w', 0)
    l52 = s.get('low_52w', 0)
    pos = min(max((price - l52) / (h52 - l52) * 100 if h52 > l52 else 50, 0), 100)
    cls = "up" if chg_pct >= 0 else "dn"
    sign = "+" if chg_pct >= 0 else ""
    bc = "#ef4444" if chg_pct >= 0 else "#22c55e"
    return f'''<div class="scard">
  <div class="sch"><div><span class="ssym">{sym}</span><span class="snm">{name}</span></div></div>
  <div style="display:flex;justify-content:space-between;align-items:baseline;margin-top:4px">
    <div class="sprc">${price:.2f}</div>
    <div class="schg {cls}">{sign}{chg_pct:.2f}%</div>
  </div>
  <div class="sspk" id="spark_{sym}"></div>
  <div style="height:3px;background:rgba(255,255,255,.08);border-radius:2px;margin:4px 0;position:relative">
    <div style="position:absolute;left:{pos:.0f}%;top:-2px;width:2px;height:7px;background:{bc};border-radius:1px;transform:translateX(-50%)"></div>
  </div>
  <div class="smeta"><span>52L {l52:.2f}</span><span>52H {h52:.2f}</span></div>
</div>'''

stock_parts = []
for cat, syms in categories:
    cards = [stock_card(s, stocks[s]) for s in syms if s in stocks]
    if cards:
        stock_parts.append(
            f'<div style="margin-bottom:16px">'
            f'<div style="font-size:13px;font-weight:600;color:#9ca3af;margin-bottom:8px;padding-left:2px">{cat}</div>'
            f'<div class="sgrid">{"".join(cards)}</div></div>')

stocks_section = f'''
    <div class="section-divider"><span>🏢 典型个股表现</span></div>
    <div style="font-size:11px;color:#6b7280;margin-bottom:10px">实时：腾讯财经 · K线：新浪财经 · 52周位置指示条（红涨绿跌）</div>
    {"".join(stock_parts)}
'''

# Inject both sections before the US stocks footer
old_footer = '''    <footer class="footer">
      数据来源：
      <a href="https://finance.sina.com.cn/stock/usstock/" target="_blank" rel="noopener noreferrer">新浪财经</a>（历史日K）·
      <a href="https://gu.qq.com/" target="_blank" rel="noopener noreferrer">腾讯财经</a>（实时行情）·
      VIX历史趋势以 VIXY ETF 作为代理指标
      <br>板块分类采用 SPDR Select Sector ETFs（XLK/XLF/XLE/XLV/XLI/XLY/XLP/XLU/XLB/XLRE/XLC）
    </footer>
  </div>'''

new_footer = '''    <footer class="footer">
      数据来源：
      <a href="https://finance.sina.com.cn/stock/usstock/" target="_blank" rel="noopener noreferrer">新浪财经</a>（历史日K）·
      <a href="https://gu.qq.com/" target="_blank" rel="noopener noreferrer">腾讯财经</a>（实时/VIX）·
      <a href="https://quote.eastmoney.com/" target="_blank" rel="noopener noreferrer">东方财富</a>（资金流向）·
      VIX趋势以VIXY ETF代理 · 板块：SPDR Select Sector ETFs
    </footer>
  </div>'''

new_content = flow_section + stocks_section + new_footer
html = html.replace(old_footer, new_content, 1)
print("Fund flow + stocks sections injected")

# ===================== SPARKLINE JS =====================
spark = {}
for sym, s in stocks.items():
    spark[sym] = {"d": s["dates"], "c": s["closes"]}
spark_js = json.dumps(spark, separators=(',', ':'))

sparkline_code = f'''
// === 个股Sparklines ===
var SPARK={spark_js};
var spCharts=[];
function initSparks(){{
  if(spCharts.length>0)return;
  Object.keys(SPARK).forEach(function(sym){{
    var el=document.getElementById('spark_'+sym);
    if(!el||!window.echarts)return;
    var ch=echarts.init(el,null,{{renderer:'canvas'}});
    spCharts.push(ch);
    var d=SPARK[sym];
    var up=d.c[d.c.length-1]>=d.c[0];
    var col=up?'#ef4444':'#22c55e';
    var bg=up?'rgba(239,68,68,.1)':'rgba(34,197,94,.1)';
    ch.setOption({{
      grid:{{left:0,right:0,top:2,bottom:0}},
      xAxis:{{type:'category',show:false,data:d.d,boundaryGap:false}},
      yAxis:{{type:'value',show:false,scale:true}},
      series:[{{type:'line',data:d.c,smooth:true,symbol:'none',
        lineStyle:{{width:1.5,color:col}},
        areaStyle:{{color:{{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[
          {{offset:0,color:bg}},{{offset:1,color:'rgba(0,0,0,0)'}}]}}}}}}],
      animation:false
    }});
  }});
}}
'''

# Insert before "function initUsCharts"
marker = 'function initUsCharts()'
if marker in html:
    html = html.replace(marker, sparkline_code + '\n' + marker, 1)
    print("Sparkline JS inserted")
else:
    print("WARNING: initUsCharts not found!")
    sys.exit(1)

# Add initSparks() call in tab switch
old_tab = "if (target === 'us-stocks') initUsCharts();"
new_tab = "if (target === 'us-stocks') { initUsCharts(); initSparks(); }"
html = html.replace(old_tab, new_tab, 1)
print("Tab switch init added")

# Add spCharts to resize
old_rs = "usCharts.forEach(c => c && c.resize && c.resize());\n});"
new_rs = "usCharts.forEach(c => c && c.resize && c.resize());\n  spCharts.forEach(c => c && c.resize && c.resize());\n});"
# Only replace the window resize listener (last occurrence)
idx = html.rfind(old_rs)
if idx >= 0:
    html = html[:idx] + new_rs + html[idx+len(old_rs):]
    print("Resize handler updated")

# ===================== WRITE =====================
with open(OUTPUT, 'w', encoding='utf-8') as f:
    f.write(html)

final = os.path.getsize(OUTPUT)
print(f"\nDone! {orig_len/1024:.0f} KB -> {final/1024:.0f} KB")

# Verify
with open(OUTPUT, 'r', encoding='utf-8') as f:
    v = f.read()
checks = ['vov', 'STOCK_SPARK' if False else 'SPARK', 'initSparks', '主力净流入 TOP10',
          '主力净流出 TOP10', '成交额 TOP10', '典型个股表现', '</html>']
for c in checks:
    print(f"  {'OK' if c in v else 'MISSING'}: {c}")
sc = len(re.findall(r'class="scard"', v))
print(f"  Stock cards: {sc}")
