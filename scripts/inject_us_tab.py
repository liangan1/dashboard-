#!/usr/bin/env python3
"""
将美股Tab嵌入现有看板HTML - 精确替换版
"""
import json
import os

DASHBOARD_DIR = "/Coze/Drive/扣子/treasury_dashboard"
INDEX_HTML = os.path.join(DASHBOARD_DIR, "index.html")
DATA_JSON = "/Coze/Drive/金融分析/us_stock_data.json"
OUTPUT_HTML = INDEX_HTML

US_CSS = """
  /* ===== 美股 Tab ===== */
  .us-block {
    background: linear-gradient(135deg,#0f172a 0%,#1e1b4b 100%);
    border:1px solid #1f2937; border-radius:12px;
    padding:18px; margin-bottom:16px;
  }
  .vix-card {
    background: linear-gradient(135deg,#1a1a2e,#16213e);
    border:1px solid #1f2937; border-radius:12px;
    padding:18px; margin-bottom:16px;
    border-left: 4px solid #f97316;
  }
  .vix-header { display:flex; justify-content:space-between; align-items:center; }
  .vix-title { font-size:15px; font-weight:600; color:#f9fafb; display:flex; align-items:center; gap:8px; }
  .vix-title::before { content:''; width:3px; height:16px; background:#f97316; border-radius:2px; }
  .vix-big { text-align:right; }
  .vix-big .vix-val { font-size:32px; font-weight:700; color:#f97316; font-variant-numeric:tabular-nums; }
  .vix-big .vix-level { font-size:13px; font-weight:600; margin-top:2px; }
  .vix-gauge { margin-top:14px; }
  .vix-gauge-bar {
    height:8px; border-radius:4px; background: linear-gradient(90deg, #10b981 0%, #84cc16 30%, #f59e0b 60%, #ef4444 100%);
    position:relative;
  }
  .vix-gauge-marker {
    position:absolute; top:-4px; width:4px; height:16px; background:#fff; border-radius:2px;
    transform:translateX(-50%); box-shadow:0 0 6px rgba(255,255,255,0.5);
  }
  .vix-gauge-labels { display:flex; justify-content:space-between; font-size:10px; color:#6b7280; margin-top:6px; }
  .sector-table-wrap {
    background: linear-gradient(135deg,#111827,#0f172a);
    border:1px solid #1f2937; border-radius:12px;
    padding:14px; margin-bottom:16px;
  }
  .sector-table-title {
    font-size:14px; font-weight:600; color:#f9fafb; margin-bottom:12px;
    display:flex; align-items:center; gap:8px;
  }
  .sector-table-title::before { content:''; width:3px; height:14px; background:#3b82f6; border-radius:2px; }
  .sector-table { width:100%; border-collapse:collapse; font-size:13px; }
  .sector-table th {
    text-align:left; padding:8px 6px; color:#6b7280; font-weight:500;
    border-bottom:1px solid #1f2937; font-size:11px; text-transform:uppercase; letter-spacing:0.5px;
  }
  .sector-table td {
    padding:10px 6px; border-bottom:1px solid rgba(31,41,55,0.5);
    color:#e5e7eb; font-variant-numeric:tabular-nums;
  }
  .sector-table tr:last-child td { border-bottom:none; }
  .sector-table .rank-cell { width:32px; color:#6b7280; font-weight:600; text-align:center; }
  .sector-table .name-cell { }
  .sector-dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:8px; vertical-align:middle; }
  .sector-en { font-size:10px; color:#6b7280; font-weight:400; margin-left:4px; }
  .sector-table .price-cell { text-align:right; color:#9ca3af; }
  .sector-table .chg-cell { text-align:right; font-weight:600; }
  .sector-table .chg-cell.up { color:#10b981; }
  .sector-table .chg-cell.down { color:#ef4444; }
  .us-rt-time { font-size:11px; color:#6b7280; text-align:right; margin-bottom:8px; }
  @media (min-width: 900px) {
    .us-block { padding:24px; }
    .sector-table-wrap { padding:18px; }
  }
"""


def main():
    with open(DATA_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    with open(INDEX_HTML, "r", encoding="utf-8") as f:
        html = f.read()

    series = data["series"]
    h = data["html"]
    today = data["date"]
    vix = h["vix_card"]
    vix_pct = min(100, max(0, (vix["price"] - 10) / 30 * 100)) if vix["price"] else 50

    # 1. 插入CSS
    html = html.replace("</style>", US_CSS + "\n</style>")

    # 2. Tab栏: 在"更多"按钮前插入"美股"按钮
    old_more_btn = '''  <button class="tab-btn" data-tab="more">
    <span class="tab-icon">⚙️</span>
    <span class="tab-label">更多</span>
  </button>'''
    new_tabs = '''  <button class="tab-btn" data-tab="us-stocks">
    <span class="tab-icon">🇺🇸</span>
    <span class="tab-label">美股</span>
  </button>
  <button class="tab-btn" data-tab="more">
    <span class="tab-icon">⚙️</span>
    <span class="tab-label">更多</span>
  </button>'''
    assert old_more_btn in html, "找不到更多按钮"
    html = html.replace(old_more_btn, new_tabs)

    # 3. 在 page-more 之前插入美股页面
    us_page = f'''  <!-- Tab 4: 美股 -->
  <div class="tab-page" id="page-us-stocks">
    <div class="section-divider"><span>📈 美股三大指数</span></div>
    <div class="us-rt-time">数据更新: {h['rt_time']} · 历史数据: 新浪财经 · 实时行情: 腾讯财经</div>

    <section class="overview">
{h['overview_cards']}
    </section>

    <div class="section-subtitle">😱 VIX 恐慌指数</div>
    <div class="vix-card">
      <div class="vix-header">
        <div class="vix-title">CBOE 波动率指数 (VIX)</div>
        <div class="vix-big">
          <div class="vix-val">{vix['price']:.2f}</div>
          <div class="vix-level" style="color:{vix['level_color']}">{vix['level']}</div>
        </div>
      </div>
      <div class="vix-gauge">
        <div class="vix-gauge-bar">
          <div class="vix-gauge-marker" style="left:{vix_pct:.1f}%"></div>
        </div>
        <div class="vix-gauge-labels">
          <span>10 极度贪婪</span>
          <span>20 中性</span>
          <span>30 恐慌</span>
          <span>40+ 极度恐慌</span>
        </div>
      </div>
    </div>

    <div class="section-divider"><span>📊 指数详情与走势</span></div>
{h['index_blocks']}

{h['vixy_chart']}

    <div class="section-divider"><span>🏭 11大板块ETF涨跌</span></div>
    <div class="sector-table-wrap">
      <div class="sector-table-title">板块ETF当日表现（SPDR Sector ETFs）</div>
      <table class="sector-table">
        <thead>
          <tr><th>#</th><th>板块</th><th style="text-align:right">现价</th><th style="text-align:right">涨跌幅</th></tr>
        </thead>
        <tbody>
{h['sector_table_rows']}
        </tbody>
      </table>
      <div id="sectorBarChart" style="height:340px;margin-top:16px;"></div>
    </div>

    <div class="section-divider"><span>🔬 行业/主题ETF</span></div>
    <div class="sector-table-wrap">
      <div class="sector-table-title">重点行业ETF（半导体/贵金属/原油/长债）</div>
      <table class="sector-table">
        <thead>
          <tr><th>品种</th><th style="text-align:right">现价</th><th style="text-align:right">涨跌幅</th><th style="text-align:right">52周高</th><th style="text-align:right">52周低</th></tr>
        </thead>
        <tbody>
{h['theme_table_rows']}
        </tbody>
      </table>
    </div>

    <footer class="footer">
      数据来源：
      <a href="https://finance.sina.com.cn/stock/usstock/" target="_blank" rel="noopener noreferrer">新浪财经</a>（历史日K）·
      <a href="https://gu.qq.com/" target="_blank" rel="noopener noreferrer">腾讯财经</a>（实时行情）·
      VIX历史趋势以 VIXY ETF 作为代理指标
      <br>板块分类采用 SPDR Select Sector ETFs（XLK/XLF/XLE/XLV/XLI/XLY/XLP/XLU/XLB/XLRE/XLC）
    </footer>
  </div>

  <!-- Tab 5: 更多 -->'''

    html = html.replace('  <!-- Tab 4: 更多 -->', us_page)

    # 4. 在 DEBT_DATES 之前插入 US_SERIES_DATA 和板块图表数据
    us_series_json = json.dumps(series, ensure_ascii=False)
    sc = h["sector_chart"]
    data_js = f"""const US_SERIES_DATA = {us_series_json};
const SECTOR_CHART_NAMES = {sc['names']};
const SECTOR_CHART_VALUES = {sc['values']};
const SECTOR_CHART_COLORS = {sc['colors']};
"""
    html = html.replace("const DEBT_DATES", data_js + "const DEBT_DATES")

    # 5. 替换现有Tab切换JS，加入美股图表初始化
    old_tab_js = """// Tab 切换逻辑
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const target = btn.dataset.tab;
    document.querySelectorAll('.tab-page').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById('page-' + target).classList.add('active');
    btn.classList.add('active');

    // 延迟初始化对应 Tab 的图表
    if (target === 'bonds') initBondCharts();
    if (target === 'commodities') initCommodityCharts();

    // 已初始化的图表需要 resize
    setTimeout(() => allCharts.forEach(c => c && c.resize && c.resize()), 50);
  });
});

window.addEventListener('resize', () => allCharts.forEach(c => c && c.resize && c.resize()));"""

    new_tab_js = """// ============ 美股图表 ============
let usChartsInitialized = false;
let usCharts = [];

function initUsCharts() {
  if (usChartsInitialized) return;
  const indexIds = ['DJI','IXIC','INX','SOX'];
  indexIds.forEach(sid => {
    if (US_SERIES_DATA[sid]) {
      const s = US_SERIES_DATA[sid];
      usCharts.push(makeLineChart('chart_'+sid+'_1y', s.dates_all, s.values_all, s.color, s.color+'33', '$', ''));
      usCharts.push(makeLineChart('chart_'+sid+'_30d', s.dates_recent, s.values_recent, s.color, s.color+'33', '$', ''));
    }
  });
  if (US_SERIES_DATA['VIXY']) {
    const s = US_SERIES_DATA['VIXY'];
    usCharts.push(makeLineChart('chart_VIXY_1y', s.dates_all, s.values_all, s.color, s.color+'33', '$', ''));
    usCharts.push(makeLineChart('chart_VIXY_30d', s.dates_recent, s.values_recent, s.color, s.color+'33', '$', ''));
  }
  // 板块涨跌条形图
  const sectorChart = echarts.init(document.getElementById('sectorBarChart'), null, {renderer:'canvas'});
  const sn = SECTOR_CHART_NAMES.slice().reverse();
  const sv = SECTOR_CHART_VALUES.slice().reverse();
  const sc = SECTOR_CHART_COLORS.slice().reverse();
  sectorChart.setOption({
    tooltip:{ trigger:'axis', axisPointer:{type:'shadow'}, ...tooltipStyle,
      formatter: function(p) { return p[0].name+'<br/><b>'+p[0].value.toFixed(2)+'%</b>'; }
    },
    grid:{ left:'3%', right:'10%', bottom:'3%', top:'3%', containLabel:true },
    xAxis:{ type:'value', ...axisStyle, axisLabel:{...axisStyle.axisLabel, formatter:'{value}%'} },
    yAxis:{ type:'category', data:sn, ...axisStyle, axisLabel:{...axisStyle.axisLabel, fontSize:12} },
    series:[{
      type:'bar', barWidth:'60%',
      data: sv.map((v,i) => ({ value:v, itemStyle:{ color:sc[i], borderRadius:[0,4,4,0] } })),
      label:{ show:true, position:'right', fontSize:11,
        formatter: function(p) { return p.value.toFixed(2)+'%'; },
        color: function(p) { return p.value >= 0 ? '#10b981' : '#ef4444'; }
      }
    }]
  });
  usCharts.push(sectorChart);
  usChartsInitialized = true;
}

// Tab 切换逻辑
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const target = btn.dataset.tab;
    document.querySelectorAll('.tab-page').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById('page-' + target).classList.add('active');
    btn.classList.add('active');

    if (target === 'bonds') initBondCharts();
    if (target === 'commodities') initCommodityCharts();
    if (target === 'us-stocks') initUsCharts();

    setTimeout(() => {
      allCharts.forEach(c => c && c.resize && c.resize());
      usCharts.forEach(c => c && c.resize && c.resize());
    }, 80);
  });
});

window.addEventListener('resize', () => {
  allCharts.forEach(c => c && c.resize && c.resize());
  usCharts.forEach(c => c && c.resize && c.resize());
});"""

    assert old_tab_js in html, "找不到现有Tab切换JS"
    html = html.replace(old_tab_js, new_tab_js)

    # 6. 更新日期
    html = html.replace(
        '<title>全球资产每日看板 - 2026-08-23</title>',
        f'<title>全球资产每日看板 - {today}</title>'
    )
    html = html.replace(
        '<div class="date">2026-08-23</div>',
        f'<div class="date">{today}</div>'
    )

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    size_kb = os.path.getsize(OUTPUT_HTML) / 1024
    print(f"✅ 已更新 {OUTPUT_HTML}")
    print(f"   文件大小: {size_kb:.1f} KB")
    print(f"   新增: 美股Tab (4指数 + VIX + 11板块ETF + 7主题ETF)")


if __name__ == "__main__":
    main()
