#!/usr/bin/env python3
"""
US_SERIES_DATA 和 SERIES_DATA 增量更新脚本
数据源：东财(美股指数/ETF) + CNBC(美债收益率) + commodities_data(商品/比特币)

用法: python3 fetch_series_update.py [--dry-run]
"""

import json
import os
import re
import sys
import subprocess
import requests
from datetime import datetime, timedelta, timezone

# ============================================================
# 配置
# ============================================================
BASE_DIR = '/Coze/Drive/金融分析'
DASHBOARD_DIR = '/Coze/Drive/扣子/treasury_dashboard'
INDEX_HTML = os.path.join(DASHBOARD_DIR, 'index.html')
COMMODITY_DATA = os.path.join(BASE_DIR, 'commodities_data.json')
FRED_CLI = os.path.join(BASE_DIR, '.skills/skill_fred-data-skill/scripts/_cli_wrapper.py')

BJT = timezone(timedelta(hours=8))  # 北京时间 UTC+8

# 东财 secid 映射
US_INDEX_MAP = {
    'DJI': '100.DJIA',
    'IXIC': '100.NDX',
    'INX': '100.SPX',
    'SOX': '251.SOX',
    'XLK': '107.XLK', 'XLF': '107.XLF', 'XLE': '107.XLE',
    'XLV': '107.XLV', 'XLI': '107.XLI', 'XLY': '107.XLY',
    'XLP': '107.XLP', 'XLU': '107.XLU', 'XLB': '107.XLB',
    'XLRE': '107.XLRE', 'XLC': '107.XLC',
    'SMH': '105.SMH', 'SOXX': '105.SOXX',
    'GLD': '107.GLD', 'SLV': '107.SLV', 'GDX': '107.GDX',
    'USO': '107.USO', 'TLT': '105.TLT', 'VIXY': '107.VIXY',
}

# SERIES_DATA 中的 DGS 美债收益率（改用 CNBC 实时数据，不再使用 FRED 延迟数据）
# CNBC symbol -> SERIES_DATA key 映射
CNBC_DGS_MAP = {
    'US2Y': 'DGS2',
    'US5Y': 'DGS5',
    'US10Y': 'DGS10',
    'US30Y': 'DGS30',
}

# commodities_data.json 中 chart_id 到 SERIES_DATA key 的映射
COMMODITY_KEY_MAP = {
    'GOLD': 'gold',
    'CBBTCUSD': 'btc',
    'DCOILWTICO': 'wti',
    'DCOILBRENTEU': 'brent',
}

DRY_RUN = '--dry-run' in sys.argv


# ============================================================
# HTML 解析：提取 / 替换 JS 对象
# ============================================================
def extract_js_object(html, var_name):
    """从HTML中提取 const VAR_NAME = {...}; 的JSON内容
    返回 (data_dict, brace_start_pos, brace_end_pos)
    """
    pattern = rf'const\s+{var_name}\s*=\s*'
    m = re.search(pattern, html)
    if not m:
        print(f"[ERROR] 未找到 const {var_name}")
        return None, -1, -1
    brace_start = html.index('{', m.end())
    depth = 0
    pos = brace_start
    while pos < len(html):
        if html[pos] == '{':
            depth += 1
        elif html[pos] == '}':
            depth -= 1
            if depth == 0:
                break
        pos += 1
    json_str = html[brace_start:pos + 1]
    data = json.loads(json_str)
    return data, brace_start, pos + 1


def replace_html_var(html, var_name, data, start_pos, end_pos):
    """替换HTML中指定位置的JS对象（从后往前替换避免偏移）"""
    new_json = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    return html[:start_pos] + new_json + html[end_pos:]


# ============================================================
# 数据获取
# ============================================================
def fetch_us_indices():
    """从东财获取美股指数/ETF实时行情
    返回 dict: {secid_symbol: {f2: current_price, f18: prev_close, ...}}
    """
    secid_values = list(US_INDEX_MAP.values())
    params = {
        'fltt': '2',
        'fields': 'f2,f3,f4,f6,f12,f13,f14,f15,f16,f17,f18',
        'secids': ','.join(secid_values),
    }
    try:
        r = requests.get(
            'https://push2delay.eastmoney.com/api/qt/ulist.np/get',
            params=params, timeout=15
        )
        r.raise_for_status()
        result = r.json()
        if result.get('data') and result['data'].get('diff'):
            # 构建 f12 -> item 映射
            out = {}
            for item in result['data']['diff']:
                symbol = item.get('f12', '')
                out[symbol] = item
            return out
        else:
            print("[WARN] 东财API返回数据为空")
            return {}
    except Exception as e:
        print(f"[ERROR] 东财API请求失败: {e}")
        return {}


def fetch_fred_series(series_id, start_date=None):
    """从FRED获取时间序列数据（仅用于非DGS商品序列，如原油等）
    返回 [(date_str, value_float), ...]
    """
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=15)).strftime('%Y-%m-%d')

    cmd = [
        sys.executable, FRED_CLI, 'call', 'get-observations',
        '--param', f'series_id={series_id}',
        '--param', f'observation_start={start_date}',
        '--param', 'sort_order=desc',
        '--param', 'limit=10'
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            cwd=os.path.dirname(FRED_CLI)
        )
        if result.returncode != 0:
            print(f"[ERROR] FRED {series_id} 调用失败: {result.stderr.strip()}")
            return []
        data = json.loads(result.stdout)
        obs = data.get('observations', [])
        out = []
        for o in obs:
            d = o.get('date', '')
            v = o.get('value', '.')
            if v == '.' or v is None:
                continue
            out.append((d, float(v)))
        return out
    except Exception as e:
        print(f"[ERROR] FRED {series_id} 请求异常: {e}")
        return []


def fetch_cnbc_dgs():
    """从CNBC获取美国国债收益率实时数据
    返回 {CNBC_symbol: {'yield': float, 'date': 'YYYY-MM-DD', 'change': str, ...}}
    """
    symbols = '|'.join(CNBC_DGS_MAP.keys())  # US2Y|US5Y|US10Y|US30Y
    url = (
        'https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol'
        '?events=no&exthrs=1&noform=1&output=json&partnerId=2'
        f'&requestMethod=quick&symbols={symbols}'
    )
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            print(f"[ERROR] CNBC HTTP {r.status_code}")
            return {}
        data = r.json()
        results = data.get('FormattedQuoteResult', {}).get('FormattedQuote', [])
        out = {}
        for item in results:
            sym = item.get('symbol', '')
            last = item.get('last', '')
            last_time = item.get('last_time', '')  # 2026-08-24T20:30:43.000-0400
            
            if not last or not last_time:
                continue
            
            # 解析: "4.704%" -> 4.704
            yield_val = float(re.sub(r'[%％]', '', last))
            # 从 last_time 提取日期 (EDT/EST时区)
            date_str = last_time[:10]  # "2026-08-24"
            
            out[sym] = {
                'yield': yield_val,
                'date': date_str,
                'change': item.get('change', ''),
                'high': float(re.sub(r'[%％]', '', item.get('high', '0'))),
                'low': float(re.sub(r'[%％]', '', item.get('low', '0'))),
                'prev_close': float(re.sub(r'[%％]', '', item.get('previous_day_closing', '0'))),
                'yrhigh': float(item.get('yrhiprice', '0')),
                'yrhighdate': item.get('yrhidate', ''),
                'yrlow': float(item.get('yrloprice', '0')),
                'yrlodate': item.get('yrlodate', ''),
            }
        return out
    except Exception as e:
        print(f"[ERROR] CNBC 请求异常: {e}")
        return {}


def cleanup_phantom_dates(us_data, series_data):
    """清理幽灵数据：删除连续两天值完全相同且日期相邻的幽灵数据点
    典型场景：美股盘前运行脚本，f18(昨收)等于前一天的收盘价，导致幽灵重复。
    """
    removed = 0
    
    for data_source, data in [('US_SERIES_DATA', us_data), ('SERIES_DATA', series_data)]:
        for key, entry in data.items():
            dates = entry.get('dates_all', [])
            values = entry.get('values_all', [])
            
            if len(dates) < 2:
                continue
            
            # 从后往前找，找到日期相邻且值相同的重复点
            i = len(dates) - 1
            while i > 0:
                d1 = dates[i - 1]
                d2 = dates[i]
                v1 = values[i - 1]
                v2 = values[i]
                
                # 判断是否相邻（1-3天内，覆盖周末）
                try:
                    dt1 = datetime.strptime(d1, '%Y-%m-%d')
                    dt2 = datetime.strptime(d2, '%Y-%m-%d')
                    delta = abs((dt2 - dt1).days)
                except:
                    delta = 999
                
                if delta <= 3 and v1 == v2:
                    print(f"  [CLEAN] {data_source}.{key}: 删除幽灵数据 {d2}={v2} (与{d1}重复)")
                    dates.pop(i)
                    values.pop(i)
                    removed += 1
                i -= 1
            
            # 同步 dates_recent / values_recent
            entry['dates_recent'] = dates[-30:] if dates else []
            entry['values_recent'] = values[-30:] if values else []
    
    return removed


def load_commodities():
    """从 commodities_data.json 获取商品/比特币数据"""
    try:
        with open(COMMODITY_DATA, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[ERROR] 读取 commodities_data.json 失败: {e}")
        return {}


# ============================================================
# 交易日/日期判断
# ============================================================
def is_us_trading_day(dt):
    """判断是否美股交易日（简化版：仅排除周末，不含假日）"""
    return dt.weekday() < 5


def get_previous_trading_day(dt):
    """获取前一个交易日（简化版）"""
    d = dt - timedelta(days=1)
    while not is_us_trading_day(d):
        d -= timedelta(days=1)
    return d


def now_bjt():
    """当前北京时间"""
    return datetime.now(BJT)


def determine_us_update_dates(html_latest_date_str, now):
    """根据HTML最新日期和当前北京时间，确定需要追加的美股交易日
    
    逻辑：
    - 如果北京时间 > 04:00（即美股当日已收盘），可以追加到今天对应的美股交易日
    - 如果北京时间 <= 04:00（当日美股尚未收盘），最多追加到昨天对应的美股交易日
    
    返回需要追加的日期列表（可能为0个、1个或2个）
    """
    if not html_latest_date_str:
        return []
    
    latest = datetime.strptime(html_latest_date_str, '%Y-%m-%d').date()
    today_bjt = now.date()
    hour_bjt = now.hour
    
    # 确定可用的最新美股交易日
    # 北京时间04:00之后 = 美东时间已收盘（夏令时04:00对应美东16:00前一天）
    if hour_bjt >= 4:
        # 今天的美股交易日（如果今天是交易日）已收盘或正在交易中
        # 用f2（当前价/收盘价）追加今天
        if is_us_trading_day(today_bjt):
            target_today = today_bjt
        else:
            target_today = get_previous_trading_day(today_bjt)
        
        dates_to_add = []
        # 先追加昨天（如果缺失）
        yesterday_trade = get_previous_trading_day(today_bjt)
        if yesterday_trade > latest and yesterday_trade < target_today:
            dates_to_add.append(('prev_close', yesterday_trade))
        # 再追加今天
        if target_today > latest:
            dates_to_add.append(('current', target_today))
        return dates_to_add
    else:
        # 北京时间凌晨，当日美股尚未收盘
        # 只能用昨收价追加昨天的交易日
        yesterday_trade = get_previous_trading_day(today_bjt)
        if yesterday_trade > latest:
            return [('prev_close', yesterday_trade)]
        return []


# ============================================================
# US_SERIES_DATA 更新逻辑
# ============================================================
def update_us_series(us_data, api_data, now):
    """更新US_SERIES_DATA
    
    api_data: 东财API返回的 {symbol: item} 字典
    返回 (updated_data, total_points_added)
    """
    total_added = 0
    
    # 用一个代表性的key获取最新日期（DJI）
    representative = us_data.get('DJI', {})
    latest_date = representative.get('dates_all', [''])[-1]
    
    dates_to_add = determine_us_update_dates(latest_date, now)
    if not dates_to_add:
        print("[INFO] US_SERIES_DATA 已是最新，无需更新")
        return us_data, 0
    
    print(f"[INFO] 美股需要追加 {len(dates_to_add)} 个数据点:")
    for mode, d in dates_to_add:
        print(f"  - {d} ({mode})")
    
    # 反向映射：f12 symbol -> our key
    # 东财返回的f12是 DJIA/NDX/SPX 等，我们需要映射回 DJI/IXIC/INX
    f12_to_key = {}
    for our_key, secid in US_INDEX_MAP.items():
        _, symbol = secid.split('.')
        f12_to_key[symbol] = our_key
    
    for mode, target_date in dates_to_add:
        date_str = target_date.strftime('%Y-%m-%d')
        added = 0
        
        for api_symbol, item in api_data.items():
            our_key = f12_to_key.get(api_symbol)
            if not our_key or our_key not in us_data:
                continue
            
            entry = us_data[our_key]
            decimals = entry.get('decimals', 2)
            
            # 选择价格
            if mode == 'current':
                price = item.get('f2')  # 当前价/收盘价
            else:
                price = item.get('f18')  # 昨收价
            
            if price is None or price == '-':
                print(f"[WARN] {our_key} 价格无效，跳过")
                continue
            
            # 四舍五入到指定精度
            price = round(float(price), decimals)
            
            # 检查日期是否已存在
            if date_str in entry['dates_all']:
                print(f"[SKIP] {our_key} {date_str} 已存在")
                continue
            
            # 追加到 dates_all / values_all
            entry['dates_all'].append(date_str)
            entry['values_all'].append(price)
            
            # 追加到 dates_recent / values_recent (保持30天窗口)
            entry['dates_recent'].append(date_str)
            entry['values_recent'].append(price)
            # 裁剪到最近30个数据点
            if len(entry['dates_recent']) > 30:
                entry['dates_recent'] = entry['dates_recent'][-30:]
                entry['values_recent'] = entry['values_recent'][-30:]
            
            # 更新 stats
            prev_latest = entry['stats'].get('latest', 0)
            entry['stats']['latest'] = price
            entry['stats']['prev'] = prev_latest
            change = round(price - prev_latest, decimals)
            entry['stats']['change'] = change
            if prev_latest != 0:
                entry['stats']['change_pct'] = round(change / prev_latest * 100, 2)
            
            # 更新52周高低
            n_52w = min(252, len(entry['values_all']))
            recent_52w = entry['values_all'][-n_52w:]
            high_52w = max(recent_52w)
            low_52w = min(recent_52w)
            if high_52w > entry['stats'].get('high_52w', 0):
                entry['stats']['high_52w'] = high_52w
                entry['stats']['high_date'] = date_str
            if low_52w < entry['stats'].get('low_52w', float('inf')):
                entry['stats']['low_52w'] = low_52w
                entry['stats']['low_date'] = date_str
            entry['stats']['avg_52w'] = round(sum(recent_52w) / len(recent_52w), decimals)
            entry['stats']['data_points'] = len(entry['dates_all'])
            
            added += 1
        
        if added > 0:
            print(f"  [+] {date_str}: 已更新 {added} 个序列")
        total_added += added
    
    return us_data, total_added


# ============================================================
# SERIES_DATA 更新逻辑
# ============================================================
def update_series_data(series_data, commodities, cnbc_dgs=None):
    """更新 SERIES_DATA
    返回 (updated_data, total_points_added)
    """
    total_added = 0
    
    # --- DGS 美债收益率：CNBC 实时数据 ---
    if cnbc_dgs:
        for cnbc_sym, dgs_key in CNBC_DGS_MAP.items():
            if dgs_key not in series_data:
                print(f"[WARN] SERIES_DATA 中未找到 {dgs_key}")
                continue
            if cnbc_sym not in cnbc_dgs:
                print(f"[WARN] CNBC 未返回 {cnbc_sym}")
                continue
            
            entry = series_data[dgs_key]
            cnbc_data = cnbc_dgs[cnbc_sym]
            data_date = cnbc_data['date']  # e.g. "2026-08-24"
            yield_val = cnbc_data['yield']  # e.g. 4.704
            
            existing_dates = set(entry['dates_all'])
            if data_date in existing_dates:
                # 已存在，检查是否需要更新为最新值
                idx = entry['dates_all'].index(data_date)
                old_val = entry['values_all'][idx]
                if old_val == yield_val:
                    print(f"[INFO] {dgs_key} 已是最新 ({data_date}={yield_val})")
                    continue
                else:
                    # 更新已有日期的值（可能是旧数据）
                    entry['values_all'][idx] = yield_val
                    if idx < len(entry['values_recent']):
                        entry['values_recent'][idx - max(0, len(entry['dates_recent'])-30)] = yield_val
                    print(f"  [~] {dgs_key}: 更新 {data_date} 值 {old_val} -> {yield_val}")
            else:
                # 追加新日期
                entry['dates_all'].append(data_date)
                entry['values_all'].append(yield_val)
                entry['dates_recent'].append(data_date)
                entry['values_recent'].append(yield_val)
                if len(entry['dates_recent']) > 30:
                    entry['dates_recent'] = entry['dates_recent'][-30:]
                    entry['values_recent'] = entry['values_recent'][-30:]
                print(f"  [+] {dgs_key}: 追加 {data_date} = {yield_val}")
            
            total_added += 1
            
            # 更新 stats
            prev_val = entry['stats'].get('latest', 0)
            entry['stats']['latest'] = yield_val
            entry['stats']['prev'] = prev_val
            entry['stats']['change_bp'] = round((yield_val - prev_val) * 100, 1)
            
            # 52周高低（使用CNBC数据更精确）
            n_52w = min(252, len(entry['values_all']))
            recent_52w = entry['values_all'][-n_52w:]
            high_52w = max(recent_52w)
            low_52w = min(recent_52w)
            entry['stats']['high_52w'] = high_52w
            entry['stats']['high_date'] = entry['dates_all'][entry['values_all'].index(high_52w)]
            entry['stats']['low_52w'] = low_52w
            entry['stats']['low_date'] = entry['dates_all'][entry['values_all'].index(low_52w)]
            entry['stats']['avg_52w'] = round(sum(recent_52w) / len(recent_52w), 2)
    else:
        print("[WARN] CNBC 数据不可用，DGS 序列跳过更新")
    
    # --- 商品/比特币：GOLD, CBBTCUSD ---
    today_str = now_bjt().strftime('%Y-%m-%d')
    
    for series_key, commodity_key in COMMODITY_KEY_MAP.items():
        if series_key not in series_data:
            print(f"[WARN] SERIES_DATA 中未找到 {series_key}")
            continue
        if commodity_key not in commodities:
            print(f"[WARN] commodities_data.json 中未找到 {commodity_key}")
            continue
        
        entry = series_data[series_key]
        commodity = commodities[commodity_key]
        decimals = entry.get('decimals', commodity.get('decimals', 2))
        
        # 使用 commodities_data.json 的日期
        data_date = commodity.get('date', today_str)
        
        # 检查是否已存在
        if data_date in entry['dates_all']:
            print(f"[INFO] {series_key} 已是最新 (最新: {data_date})")
            continue
        
        # 获取价格
        price = commodity.get('price')
        if price is None:
            print(f"[WARN] {series_key} 价格无效")
            continue
        
        price = round(float(price), decimals)
        
        # 追加
        entry['dates_all'].append(data_date)
        entry['values_all'].append(price)
        
        entry['dates_recent'].append(data_date)
        entry['values_recent'].append(price)
        if len(entry['dates_recent']) > 30:
            entry['dates_recent'] = entry['dates_recent'][-30:]
            entry['values_recent'] = entry['values_recent'][-30:]
        
        # 更新 stats
        prev_val = entry['stats'].get('latest', 0)
        entry['stats']['latest'] = price
        entry['stats']['prev'] = prev_val
        change = round(price - prev_val, decimals)
        entry['stats']['change'] = change
        if prev_val != 0:
            entry['stats']['change_pct'] = round(change / prev_val * 100, 2)
        
        # 52周高低
        n_52w = min(252, len(entry['values_all']))
        recent_52w = entry['values_all'][-n_52w:]
        high_52w = max(recent_52w)
        low_52w = min(recent_52w)
        if high_52w >= entry['stats'].get('high_52w', 0):
            entry['stats']['high_52w'] = high_52w
            entry['stats']['high_date'] = data_date
        if low_52w <= entry['stats'].get('low_52w', float('inf')):
            entry['stats']['low_52w'] = low_52w
            entry['stats']['low_date'] = data_date
        entry['stats']['avg_52w'] = round(sum(recent_52w) / len(recent_52w), decimals)
        
        total_added += 1
        print(f"  [+] {series_key}: 追加 1 个点 -> {data_date} = {price}")
    
    return series_data, total_added


# ============================================================
# 主函数
# ============================================================
def main():
    print(f"{'='*60}")
    print(f"增量更新脚本启动 [{now_bjt().strftime('%Y-%m-%d %H:%M:%S')} BJT]")
    print(f"{'='*60}")
    
    if DRY_RUN:
        print("[DRY-RUN] 模式：仅分析，不写入HTML")
    
    # 1. 读取HTML
    print(f"\n[STEP 1] 读取 HTML: {INDEX_HTML}")
    with open(INDEX_HTML, 'r', encoding='utf-8') as f:
        html = f.read()
    print(f"  HTML大小: {len(html):,} 字符")
    
    # 2. 提取 US_SERIES_DATA
    print(f"\n[STEP 2] 提取 US_SERIES_DATA")
    us_data, us_start, us_end = extract_js_object(html, 'US_SERIES_DATA')
    if us_data is None:
        print("[FATAL] 无法提取 US_SERIES_DATA，退出")
        return
    us_latest = us_data.get('DJI', {}).get('dates_all', ['?'])[-1]
    print(f"  提取成功: {len(us_data)} 个序列, 最新日期: {us_latest}")
    
    # 3. 提取 SERIES_DATA
    print(f"\n[STEP 3] 提取 SERIES_DATA")
    series_data, s_start, s_end = extract_js_object(html, 'SERIES_DATA')
    if series_data is None:
        print("[FATAL] 无法提取 SERIES_DATA，退出")
        return
    s_latest = series_data.get('DGS10', {}).get('dates_all', ['?'])[-1]
    print(f"  提取成功: {len(series_data)} 个序列, DGS10最新: {s_latest}")
    
    # 4. 获取数据源
    now = now_bjt()
    print(f"\n[STEP 4] 获取数据源 (当前北京时间: {now.strftime('%Y-%m-%d %H:%M')})")
    
    print("  -> 东财API (美股指数/ETF)...")
    api_data = fetch_us_indices()
    print(f"  -> 获取到 {len(api_data)} 个品种")
    
    print("  -> CNBC (美债收益率)...")
    cnbc_dgs = fetch_cnbc_dgs()
    print(f"  -> 获取到 {len(cnbc_dgs)} 个品种")
    
    print("  -> commodities_data.json...")
    commodities = load_commodities()
    print(f"  -> 获取到 {len(commodities)} 个品种")
    
    # 4.5 清理幽灵数据
    print(f"\n[STEP 4.5] 清理幽灵数据")
    cleaned = cleanup_phantom_dates(us_data, series_data)
    if cleaned > 0:
        print(f"  共清理 {cleaned} 个幽灵数据点")
    else:
        print("  无幽灵数据")
    
    # 5. 更新 US_SERIES_DATA
    print(f"\n[STEP 5] 更新 US_SERIES_DATA")
    us_data, us_count = update_us_series(us_data, api_data, now)
    print(f"  共追加 {us_count} 个数据点")
    
    # 6. 更新 SERIES_DATA（CNBC + commodities）
    print(f"\n[STEP 6] 更新 SERIES_DATA")
    series_data, series_count = update_series_data(series_data, commodities, cnbc_dgs)
    print(f"  共追加 {series_count} 个数据点")
    
    # 7. 写回HTML
    need_write = us_count > 0 or series_count > 0 or cleaned > 0
    if not need_write:
        print(f"\n[DONE] 无数据需要更新")
        return
    
    if DRY_RUN:
        print(f"\n[DRY-RUN] 跳过HTML写入")
        return
    
    print(f"\n[STEP 7] 写回 HTML")
    # 从后往前替换，避免位置偏移
    if s_end > us_end:
        html = replace_html_var(html, 'SERIES_DATA', series_data, s_start, s_end)
        # 重新计算 us_start/us_end（SERIES_DATA替换可能影响位置，但US在前所以不受影响）
        html = replace_html_var(html, 'US_SERIES_DATA', us_data, us_start, us_end)
    else:
        html = replace_html_var(html, 'US_SERIES_DATA', us_data, us_start, us_end)
        html = replace_html_var(html, 'SERIES_DATA', series_data, s_start, s_end)
    
    with open(INDEX_HTML, 'w', encoding='utf-8') as f:
        f.write(html)
    
    # [STEP 8] 更新 SW 缓存版本（确保 PWA 刷新缓存）
    sw_path = os.path.join(os.path.dirname(INDEX_HTML), 'sw.js')
    if os.path.exists(sw_path):
        from datetime import datetime as _dt
        now_hhmm = _dt.now().strftime('%H%M')
        new_cache = f"treasury-dashboard-fix-{_dt.now().strftime('%Y%m%d')}-{now_hhmm}"
        with open(sw_path, 'r', encoding='utf-8') as f:
            sw_content = f.read()
        sw_content = re.sub(
            r"const CACHE_NAME\s*=\s*'[^']*'",
            f"const CACHE_NAME = '{new_cache}'",
            sw_content
        )
        with open(sw_path, 'w', encoding='utf-8') as f:
            f.write(sw_content)
        print(f"  SW 缓存版本更新为: {new_cache}")
    
    print(f"\n{'='*60}")
    print(f"更新完成!")
    print(f"  US_SERIES_DATA: 追加 {us_count} 个数据点")
    print(f"  SERIES_DATA: 追加 {series_count} 个数据点")
    print(f"  HTML已保存: {INDEX_HTML}")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()