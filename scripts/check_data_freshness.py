#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""独立的数据新鲜度检查脚本，可以手动运行或定时运行"""

import json
import sys
from datetime import datetime, timedelta

# ============ 路径配置 ============
BASE_DIR = '/Coze/Drive/金融分析'
COMMODITY_DATA = f'{BASE_DIR}/commodities_data.json'
US_DATA = f'{BASE_DIR}/us_enhanced_data.json'
A_DATA = f'{BASE_DIR}/a_share_data.json'
POST_MARKET_DATA = f'{BASE_DIR}/post_market_data.json'

# 数据新鲜度阈值（秒）
FRESHNESS_THRESHOLDS = {
    'bitcoin': 30 * 60,              # 30分钟（24/7交易）
    'commodity': 2 * 3600,           # 2小时（期货市场）
    'us_stock': 24 * 3600,           # 1个交易日
    'a_share': 24 * 3600,            # 1个交易日
    'north_flow': 24 * 3600,         # 1个交易日
    'margin_trading': 5 * 24 * 3600, # 5天（数据有延迟）
    'dragon_tiger': 5 * 24 * 3600,   # 5天（数据有延迟）
    'bond_yield': 24 * 3600,         # 1个交易日
}


def check_data_freshness(data_type, fetch_time_str, now=None):
    """检查数据新鲜度

    返回: (is_fresh: bool, age_minutes: float, threshold_minutes: float)
    """
    if now is None:
        now = datetime.now()

    if not fetch_time_str:
        return False, -1, FRESHNESS_THRESHOLDS.get(data_type, 3600) / 60

    try:
        if isinstance(fetch_time_str, str):
            ft = datetime.strptime(fetch_time_str.split('.')[0], '%Y-%m-%d %H:%M:%S')
        else:
            return False, -1, FRESHNESS_THRESHOLDS.get(data_type, 3600) / 60
    except Exception as e:
        print(f"  ⚠️ [{data_type}] 时间解析失败: {fetch_time_str} ({e})")
        return False, -1, FRESHNESS_THRESHOLDS.get(data_type, 3600) / 60

    age_seconds = (now - ft).total_seconds()
    age_minutes = age_seconds / 60
    threshold = FRESHNESS_THRESHOLDS.get(data_type, 3600)
    threshold_minutes = threshold / 60
    is_fresh = age_seconds <= threshold

    status = "✅" if is_fresh else "❌"
    print(f"  {status} [{data_type}] 数据年龄: {age_minutes:.0f}分钟 (阈值: {threshold_minutes:.0f}分钟)")

    return is_fresh, age_minutes, threshold_minutes


def validate_all_data():
    """验证所有数据文件的新鲜度"""
    results = {}
    now = datetime.now()

    # 1. 商品数据
    try:
        with open(COMMODITY_DATA, 'r', encoding='utf-8') as f:
            data = json.load(f)
        ft = data.get('fetch_time', '') or data.get('_meta', {}).get('fetch_time', '')

        # 比特币单独检查
        btc_data = data.get('btc', {})
        btc_ft = btc_data.get('fetch_time', ft) if btc_data else ft

        is_fresh, age, threshold = check_data_freshness('commodity', ft, now)
        results['commodity'] = {'fresh': is_fresh, 'age_min': age, 'fetch_time': ft}

        if btc_data and btc_ft:
            is_fresh_btc, age_btc, _ = check_data_freshness('bitcoin', btc_ft, now)
            results['bitcoin'] = {'fresh': is_fresh_btc, 'age_min': age_btc, 'fetch_time': btc_ft}
    except FileNotFoundError:
        print(f"  ⚠️ 商品数据文件不存在: {COMMODITY_DATA}")
        results['commodity'] = {'fresh': False, 'age_min': -1}
    except Exception as e:
        print(f"  ⚠️ 商品数据验证失败: {e}")
        results['commodity'] = {'fresh': False, 'age_min': -1}

    # 2. 美股数据
    try:
        with open(US_DATA, 'r', encoding='utf-8') as f:
            data = json.load(f)
        ft = data.get('fetch_time', '')
        is_fresh, age, threshold = check_data_freshness('us_stock', ft, now)
        results['us_stock'] = {'fresh': is_fresh, 'age_min': age, 'fetch_time': ft}
    except FileNotFoundError:
        print(f"  ⚠️ 美股数据文件不存在: {US_DATA}")
        results['us_stock'] = {'fresh': False, 'age_min': -1}
    except Exception as e:
        print(f"  ⚠️ 美股数据验证失败: {e}")
        results['us_stock'] = {'fresh': False, 'age_min': -1}

    # 3. A股数据
    try:
        with open(A_DATA, 'r', encoding='utf-8') as f:
            data = json.load(f)
        ft = data.get('fetch_time', '')
        is_fresh, age, threshold = check_data_freshness('a_share', ft, now)
        results['a_share'] = {'fresh': is_fresh, 'age_min': age, 'fetch_time': ft}
    except FileNotFoundError:
        print(f"  ⚠️ A股数据文件不存在: {A_DATA}")
        results['a_share'] = {'fresh': False, 'age_min': -1}
    except Exception as e:
        print(f"  ⚠️ A股数据验证失败: {e}")
        results['a_share'] = {'fresh': False, 'age_min': -1}

    # 4. 盘后数据（融资融券+龙虎榜）
    try:
        with open(POST_MARKET_DATA, 'r', encoding='utf-8') as f:
            data = json.load(f)

        margin = data.get('margin', {})
        margin_ft = margin.get('fetch_time', '')
        is_fresh, age, _ = check_data_freshness('margin_trading', margin_ft, now)
        results['margin_trading'] = {'fresh': is_fresh, 'age_min': age, 'fetch_time': margin_ft}

        dt = data.get('dragon_tiger', {})
        dt_ft = dt.get('fetch_time', '')
        is_fresh, age, _ = check_data_freshness('dragon_tiger', dt_ft, now)
        results['dragon_tiger'] = {'fresh': is_fresh, 'age_min': age, 'fetch_time': dt_ft}
    except FileNotFoundError:
        print(f"  ⚠️ 盘后数据文件不存在: {POST_MARKET_DATA}")
        results['margin_trading'] = {'fresh': False, 'age_min': -1}
        results['dragon_tiger'] = {'fresh': False, 'age_min': -1}
    except Exception as e:
        print(f"  ⚠️ 盘后数据验证失败: {e}")

    # 汇总
    print()
    print("=" * 50)
    all_fresh = all(r.get('fresh', False) for r in results.values())
    stale_items = [k for k, v in results.items() if not v.get('fresh', False)]

    if all_fresh:
        print("✅ 所有数据新鲜度验证通过")
    else:
        print(f"❌ 以下数据过旧: {', '.join(stale_items)}")

    return results


def main():
    print(f"🔍 数据新鲜度检查 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    results = validate_all_data()

    # 打印详细报告
    print()
    print("详细报告:")
    print("-" * 70)
    for data_type, result in results.items():
        fresh = "✅" if result.get('fresh') else "❌"
        age = result.get('age_min', -1)
        ft = result.get('fetch_time', 'N/A')
        threshold = FRESHNESS_THRESHOLDS.get(data_type, 3600)
        threshold_min = threshold / 60
        if age >= 0:
            age_display = f"{age:8.0f}分钟"
            if age > threshold_min * 2:
                status = "⚠️ 过旧"
            elif age > threshold_min:
                status = "⏳ 稍旧"
            else:
                status = "✅ 实时"
            print(f"  {fresh} {data_type:20s} 年龄: {age_display}  阈值: {threshold_min:6.0f}分钟  状态: {status}")
            print(f"     获取时间: {ft}")
        else:
            print(f"  ❌ {data_type:20s} 无法验证")

    # 返回退出码
    all_fresh = all(r.get('fresh', False) for r in results.values())
    if all_fresh:
        print("\n✅ 全部通过")
        return 0
    else:
        stale = [k for k, v in results.items() if not v.get('fresh', False)]
        print(f"\n❌ 过旧数据: {', '.join(stale)}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
