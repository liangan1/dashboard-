#!/usr/bin/env python3
"""统计每个模块的数据量，用于建立验证基准"""
import json, os, re

BASE = '/Coze/Drive/金融分析'
HTML = '/Coze/Drive/扣子/treasury_dashboard/index.html'

with open(os.path.join(BASE, 'a_share_data.json'), 'r') as f:
    a = json.load(f)
with open(os.path.join(BASE, 'us_enhanced_data.json'), 'r') as f:
    us = json.load(f)

# Check A-share spark data
aspark = {}
aspark_path = os.path.join(BASE, 'a_share_spark.json')
if os.path.exists(aspark_path):
    with open(aspark_path, 'r') as f:
        aspark = json.load(f)

# Read HTML to count embedded data
with open(HTML, 'r', encoding='utf-8') as f:
    html = f.read()

print("=" * 60)
print("数据模块统计")
print("=" * 60)

print("\n🇨🇳 A股模块")
print("-" * 40)
items = [
    ("大盘指数", len(a.get('indices', {})), 6),
    ("行业板块资金流向", len(a.get('sector_flow', [])), 100),
    ("概念板块资金流向", len(a.get('concept_flow', [])), 50),
    ("个股流入TOP", len(a.get('stock_inflow', [])), 20),
    ("个股流出TOP", len(a.get('stock_outflow', [])), 20),
    ("个股成交额TOP", len(a.get('stock_volume', [])), 20),
    ("大盘资金分层", 1 if a.get('market_flow', {}).get('main_net') is not None else 0, 1),
    ("北向资金", 1 if a.get('north_flow') else 0, 1),
    ("涨幅榜TOP", len(a.get('limit_up', [])), 10),
    ("跌幅榜TOP", len(a.get('limit_down', [])), 10),
]
for name, actual, expected in items:
    status = "✅" if actual >= expected else "⚠️"
    print(f"  {status} {name}: {actual} (期望≥{expected})")

# A股 spark
if isinstance(aspark, dict):
    spark_count = len(aspark)
elif isinstance(aspark, list):
    spark_count = len(aspark)
else:
    spark_count = 0
print(f"  {'✅' if spark_count >= 9 else '⚠️'} A股K线迷你图: {spark_count} (期望≥9)")

print(f"\n🇺🇸 美股模块")
print("-" * 40)
us_items = [
    ("个股K线数据", len(us.get('stocks', {})), 25),
    ("资金流入TOP", len(us.get('inflow', [])), 20),
    ("资金流出TOP", len(us.get('outflow', [])), 20),
    ("成交额TOP", len(us.get('top_amount', [])), 20),
    ("VIX数据", 1 if us.get('vix') and us['vix'].get('value', 0) > 0 else 0, 1),
]
for name, actual, expected in us_items:
    status = "✅" if actual >= expected else "⚠️"
    print(f"  {status} {name}: {actual} (期望≥{expected})")

# Count realtime quotes in stocks
stocks = us.get('stocks', {})
rt_count = sum(1 for s in stocks.values() if s.get('rt_price', 0) > 0)
print(f"  {'✅' if rt_count >= 20 else '⚠️'} 实时行情: {rt_count} (期望≥20)")

# Check HTML embedded data
print(f"\n📄 HTML内嵌数据")
print("-" * 40)
# Count sparkline entries in HTML
spark_matches = re.findall(r'"[A-Z]+"\s*:\s*\{', html)
aspark_matches = re.findall(r'ASPARK\s*=\s*\{([^}]*)\}', html)
print(f"  HTML文件大小: {len(html):,} 字符")
print(f"  SPARK变量存在: {'✅' if 'var SPARK' in html or 'var SPARK=' in html else '❌'}")
print(f"  ASPARK变量存在: {'✅' if 'ASPARK' in html else '❌'}")
print(f"  美股板块数据: {'✅' if 'SECTOR_CHART' in html else '❌'}")
print(f"  美债收益率数据: {'✅' if 'SERIES_DATA' in html else '❌'}")

# Count sector flow table rows
sector_rows = len(re.findall(r'<tr[^>]*>.*?</tr>', html[html.find('page-a-shares'):html.find('page-a-shares')+50000], re.DOTALL))
print(f"  A股Tab区块存在: {'✅' if 'page-a-shares' in html else '❌'}")
print(f"  美股Tab区块存在: {'✅' if 'page-us-stocks' in html else '❌'}")

# Summary
print(f"\n{'=' * 60}")
print("验证基准汇总（用于自动校验）")
print("=" * 60)
validation = {
    "a_shares": {
        "indices": 6,
        "sector_flow": 100,
        "concept_flow": 50,
        "stock_inflow": 20,
        "stock_outflow": 20,
        "stock_volume": 20,
        "market_flow": 1,
        "limit_up": 10,
        "limit_down": 10,
        "aspark": 9
    },
    "us_stocks": {
        "stocks_kline": 25,
        "inflow": 20,
        "outflow": 20,
        "top_amount": 20,
        "vix": 1,
        "realtime": 20
    }
}
print(json.dumps(validation, indent=2, ensure_ascii=False))
# Save for use
with open(os.path.join(BASE, 'validation_rules.json'), 'w') as f:
    json.dump(validation, f, indent=2)
print(f"\n已保存验证规则到 validation_rules.json")
