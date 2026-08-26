#!/usr/bin/env python3
import json

print("=== A股资金流向 ===")
with open('a_share_data.json', 'r') as f:
    a = json.load(f)
print(f"抓取时间: {a['fetch_time']}")
print(f"行业板块: {len(a['sector_flow'])} 个")
for s in a['sector_flow'][:3]:
    print(f"  {s['name']}: {s['main_net']/1e8:+.1f}亿 ({s['chg_pct']:+.2f}%)")
print(f"概念板块: {len(a['concept_flow'])} 个")
for s in a['concept_flow'][:3]:
    print(f"  {s['name']}: {s['main_net']/1e8:+.1f}亿")
print(f"个股流入TOP: {len(a['stock_inflow'])} 只")
for s in a['stock_inflow'][:3]:
    print(f"  {s['name']}: {s['main_net']/1e8:+.1f}亿")
print(f"个股流出TOP: {len(a['stock_outflow'])} 只")
for s in a['stock_outflow'][:3]:
    print(f"  {s['name']}: {s['main_net']/1e8:+.1f}亿")
print(f"成交额TOP: {len(a['stock_volume'])} 只")
print(f"大盘资金: 主力{a['market_flow']['main_net']:+.2f}亿, 成交额{a['market_flow']['total_amount']:.0f}亿")
print(f"北向资金: {a['north_flow']}")

print()
print("=== 美股资金流向 ===")
with open('us_enhanced_data.json', 'r') as f:
    us = json.load(f)
print(f"抓取时间: {us['fetch_time']}")
print(f"资金流入TOP: {len(us['inflow'])} 只")
for s in us['inflow'][:3]:
    print(f"  {s['name']}: {s['main_net_inflow']/1e8:+.1f}亿 ({s['main_net_pct']:+.1f}%)")
print(f"资金流出TOP: {len(us['outflow'])} 只")
for s in us['outflow'][:3]:
    print(f"  {s['name']}: {s['main_net_inflow']/1e8:+.1f}亿 ({s['main_net_pct']:+.1f}%)")
print(f"成交额TOP: {len(us['top_amount'])} 只")
for s in us['top_amount'][:3]:
    print(f"  {s['name']}: {s['amount']/1e8:.1f}亿, {s['change_pct']:+.2f}%")
vix = us['vix']
print(f"VIX: {vix['value'] if vix else 'N/A'}")
