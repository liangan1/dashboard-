#!/usr/bin/env python3
"""
fetch_commodities.py - 从新浪财经获取大宗商品实时期货数据
覆盖：WTI原油、布伦特原油、黄金、白银、铜、天然气、比特币

数据来源：新浪财经国际期货 hq.sinajs.cn
字段格式（GBK编码，逗号分隔）：
  [0] 当前价  [1] 未知  [2] 买价  [3] 卖价  [4] 最高  [5] 最低
  [6] 时间    [7] 昨收  [8] 开盘  [9] 持仓量 ... [12] 日期  [13] 中文名
"""

import json
import os
import urllib.request
import re
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(SCRIPT_DIR, 'commodities_data.json')

# 新浪期货代码映射
COMMODITY_MAP = {
    'wti': {'code': 'hf_CL', 'name': 'WTI原油', 'unit': '$/bbl', 'color': '#8b5cf6',
            'chart_id': 'DCOILWTICO', 'decimals': 2},
    'brent': {'code': 'hf_OIL', 'name': '布伦特原油', 'unit': '$/bbl', 'color': '#06b6d4',
              'chart_id': 'DCOILBRENTEU', 'decimals': 2},
    'gold': {'code': 'hf_GC', 'name': '黄金', 'unit': '$/oz', 'color': '#ffd700',
             'chart_id': 'GOLD', 'decimals': 0},
    'silver': {'code': 'hf_SI', 'name': '白银', 'unit': '$/oz', 'color': '#c0c0c0',
               'chart_id': 'SILVER', 'decimals': 3},
    'copper': {'code': 'hf_HG', 'name': '铜', 'unit': '¢/lb', 'color': '#cd7f32',
               'chart_id': 'COPPER', 'decimals': 2},
    'natgas': {'code': 'hf_NG', 'name': '天然气', 'unit': '$/MMBtu', 'color': '#3b82f6',
               'chart_id': 'NATGAS', 'decimals': 3},
}

BTC_CODE = 'btc_btcbtcusd'

SINA_URL = 'https://hq.sinajs.cn/list={codes}'
HEADERS = {
    'Referer': 'https://finance.sina.com.cn',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}


def _fetch_sina(codes):
    """批量请求新浪接口，返回原始文本（GBK解码）"""
    url = SINA_URL.format(codes=','.join(codes))
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode('gbk', errors='replace')


def _parse_hf_line(line):
    """解析国际期货 hf_xxx 行"""
    m = re.search(r'hq_str_(\w+)="(.*)"', line)
    if not m:
        return None
    code = m.group(1)
    fields = m.group(2).split(',')
    if len(fields) < 14:
        return None
    try:
        price = float(fields[0])
        prev_close = float(fields[7])
        open_price = float(fields[8])
        high = float(fields[4])
        low = float(fields[5])
        change = price - prev_close
        change_pct = (change / prev_close * 100) if prev_close else 0
        return {
            'code': code,
            'price': price,
            'prev_close': prev_close,
            'open': open_price,
            'high': high,
            'low': low,
            'change': round(change, 4),
            'change_pct': round(change_pct, 2),
            'time': fields[6],
            'date': fields[12],
            'name_cn': fields[13],
        }
    except (ValueError, IndexError):
        return None


def _parse_btc_line(line):
    """解析比特币 btc_btcbtcusd 行"""
    m = re.search(r'hq_str_(\w+)="(.*)"', line)
    if not m:
        return None
    fields = m.group(2).split(',')
    if len(fields) < 15:
        return None
    try:
        # btc格式: time, ?, ?, price, ?, prev_close, high, low, open, name, ?, date, ...
        price = float(fields[3])
        prev_close = float(fields[5])
        high = float(fields[6])
        low = float(fields[7])
        open_price = float(fields[8])
        # 比特币24/7交易，新浪prev_close字段几乎等于当前价，不可用
        # 改用开盘价(open_price)作为涨跌基准
        change = price - open_price
        change_pct = (change / open_price * 100) if open_price else 0
        return {
            'code': 'BTC',
            'price': price,
            'prev_close': prev_close,
            'open': open_price,
            'high': high,
            'low': low,
            'change': round(change, 2),
            'change_pct': round(change_pct, 2),
            'time': fields[0],
            'date': fields[11] if len(fields) > 11 else '',
            'name_cn': '比特币',
        }
    except (ValueError, IndexError):
        return None


def fetch_commodities():
    """获取所有商品数据，返回dict"""
    result = {}
    fetch_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 批量获取6个期货品种
    codes = [v['code'] for v in COMMODITY_MAP.values()]
    text = _fetch_sina(codes)

    for line in text.strip().split('\n'):
        parsed = _parse_hf_line(line)
        if parsed:
            # 反向查找key
            for key, cfg in COMMODITY_MAP.items():
                if cfg['code'] == 'hf_' + parsed['code'] or cfg['code'] == parsed['code']:
                    result[key] = {**parsed, **cfg}
                    break

    # 获取比特币（单独请求，格式不同）
    btc_text = _fetch_sina([BTC_CODE])
    for line in btc_text.strip().split('\n'):
        parsed = _parse_btc_line(line)
        if parsed:
            result['btc'] = {
                **parsed,
                'name': '比特币',
                'unit': 'USD',
                'color': '#f7931a',
                'chart_id': 'CBBTCUSD',
                'decimals': 0,
            }
            break

    result['_meta'] = {
        'fetch_time': fetch_time,
        'source': '新浪财经 hq.sinajs.cn',
        'count': len(result) - 1,
    }

    return result


def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始获取大宗商品实时数据...")
    data = fetch_commodities()

    meta = data.get('_meta', {})
    print(f"  数据源: {meta.get('source')}")
    print(f"  获取时间: {meta.get('fetch_time')}")
    print(f"  获取到 {meta.get('count')} 个品种:")

    for key in ['wti', 'brent', 'gold', 'silver', 'copper', 'natgas', 'btc']:
        if key in data:
            d = data[key]
            decimals = d.get('decimals', 2)
            fmt = f",.{decimals}f"
            print(f"    {d['name']:8s}: ${format(d['price'], fmt)} "
                  f"({'+' if d['change']>=0 else ''}{d['change']:.{decimals}f}, "
                  f"{'+' if d['change_pct']>=0 else ''}{d['change_pct']:.2f}%) "
                  f"[{d['date']} {d['time']}]")

    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n  已保存到 {OUTPUT}")
    return data


if __name__ == '__main__':
    main()
