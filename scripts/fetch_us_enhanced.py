#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fetch enhanced US stock data（优化版）：
1. Individual stock K-lines (60 days) for sparklines — 缓存到当天
2. Real-time quotes from Tencent — 每次拉新（不缓存）
3. Fund flow from East Money — 每次拉新（不缓存）
4. VIX real-time value — 每次拉新（不缓存）

优化点：
- K线数据缓存到 cache/us_kline_YYYY-MM-DD.json
- 部分股票在缓存中时，只拉缺失的，然后合并
- 新浪K线请求间隔 1.5-3 秒，避免限流
"""
import requests, re, json, time, os, random
from datetime import datetime

SINA_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://finance.sina.com.cn/'
}
EM_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://quote.eastmoney.com/'
}

CACHE_DIR = '/Coze/Drive/金融分析/cache'
OUT_PATH = '/Coze/Drive/金融分析/us_enhanced_data.json'

# 典型个股（覆盖科技巨头/半导体/金融消费/热门股）
INDIVIDUAL_STOCKS = {
    # 科技巨头
    'AAPL': '苹果', 'MSFT': '微软', 'NVDA': '英伟达', 'GOOGL': '谷歌',
    'AMZN': '亚马逊', 'META': 'Meta', 'TSLA': '特斯拉', 'AVGO': '博通',
    # 半导体
    'AMD': 'AMD', 'INTC': '英特尔', 'QCOM': '高通', 'MU': '美光',
    # 软件/互联网
    'NFLX': '奈飞', 'CRM': 'Salesforce', 'ORCL': '甲骨文', 'ADBE': 'Adobe',
    # 金融
    'JPM': '摩根大通', 'V': 'Visa', 'BAC': '美银',
    # 消费
    'WMT': '沃尔玛', 'COST': 'Costco', 'DIS': '迪士尼',
    # 热门
    'PLTR': 'Palantir', 'COIN': 'Coinbase', 'UBER': 'Uber',
}


def get_kline_cache_path():
    """获取当天K线缓存文件路径"""
    today = datetime.now().strftime('%Y-%m-%d')
    return os.path.join(CACHE_DIR, f'us_kline_{today}.json')


def load_kline_cache():
    """加载当天K线缓存"""
    path = get_kline_cache_path()
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                cached = json.load(f)
            cache_date = cached.get('cache_date', '')
            today = datetime.now().strftime('%Y-%m-%d')
            if cache_date == today:
                print(f"📦 K线缓存命中: {path} ({len(cached.get('stocks', {}))} 只股票)")
                return cached.get('stocks', {})
            else:
                print(f"⏰ K线缓存日期 {cache_date} 不是今天")
        except Exception as e:
            print(f"⚠️ K线缓存读取失败: {e}")
    return {}


def save_kline_cache(stock_data):
    """保存K线数据到当天缓存"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = get_kline_cache_path()
    cache_obj = {
        'cache_date': datetime.now().strftime('%Y-%m-%d'),
        'stocks': stock_data,
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(cache_obj, f, ensure_ascii=False, separators=(',', ':'))
    print(f"💾 K线缓存已保存: {path}")


def fetch_sina_daily_k(symbol, days=90):
    """Fetch daily K-line from Sina, return last N days."""
    url = f"https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var=/US_MinKService.getDailyK?symbol={symbol}&___qn=3"
    try:
        r = requests.get(url, headers=SINA_HEADERS, timeout=10)
        m = re.search(r'var=\((\[.*?\])\)', r.text, re.DOTALL)
        if m:
            data = eval(m.group(1))
            if data and len(data) > 0:
                recent = data[-days:]
                dates = [d['d'] for d in recent]
                closes = [round(float(d['c']), 2) for d in recent]
                volumes = [int(float(d['v'])) for d in recent]
                latest = data[-1]
                # 52周高低
                one_year = data[-252:] if len(data) >= 252 else data
                high_52w = max(float(d['h']) for d in one_year)
                low_52w = min(float(d['l']) for d in one_year)
                high_date = max(one_year, key=lambda d: float(d['h']))['d']
                low_date = min(one_year, key=lambda d: float(d['l']))['d']
                return {
                    'dates': dates,
                    'closes': closes,
                    'volumes': volumes,
                    'latest_date': latest['d'],
                    'latest_close': round(float(latest['c']), 2),
                    'open': round(float(latest['o']), 2),
                    'high': round(float(latest['h']), 2),
                    'low': round(float(latest['l']), 2),
                    'volume': int(float(latest['v'])),
                    'high_52w': round(high_52w, 2),
                    'low_52w': round(low_52w, 2),
                    'high_date': high_date,
                    'low_date': low_date,
                    'total_records': len(data)
                }
    except Exception as e:
        print(f"  Sina error for {symbol}: {e}")
    return None


def fetch_tencent_realtime(symbols):
    """Fetch real-time quotes from Tencent for batch of symbols (不缓存)."""
    result = {}
    sym_list = list(symbols.keys())
    for i in range(0, len(sym_list), 15):
        batch = sym_list[i:i+15]
        q = ','.join([f"us{s}" for s in batch])
        url = f"http://qt.gtimg.cn/q={q}"
        try:
            r = requests.get(url, timeout=8)
            text = r.content.decode('gbk', errors='replace')
            for line in text.strip().split(';'):
                line = line.strip()
                if not line:
                    continue
                parts = line.split('~')
                if len(parts) > 34:
                    m = re.match(r'v_(\w+)=', line)
                    if m:
                        raw_sym = m.group(1).replace('us', '')
                    else:
                        continue
                    try:
                        result[raw_sym] = {
                            'name': parts[1],
                            'price': float(parts[3]) if parts[3] else 0,
                            'prev_close': float(parts[4]) if parts[4] else 0,
                            'open': float(parts[5]) if parts[5] else 0,
                            'change': float(parts[31]) if parts[31] else 0,
                            'change_pct': float(parts[32]) if parts[32] else 0,
                            'high': float(parts[33]) if parts[33] else 0,
                            'low': float(parts[34]) if parts[34] else 0,
                            'time': parts[30] if len(parts) > 30 else '',
                            'volume': int(float(parts[6])) if parts[6] else 0,
                        }
                    except (ValueError, IndexError):
                        pass
        except Exception as e:
            print(f"  Tencent error batch {i}: {e}")
        time.sleep(0.3)
    return result


def fetch_em_fund_flow(po=1, pz=20):
    """Fetch US stock fund flow from East Money push2delay (不缓存)."""
    fs = "m:105+t:1,m:105+t:2,m:106+t:1,m:106+t:2"
    url = (f"https://push2delay.eastmoney.com/api/qt/clist/get?"
           f"fid=f62&po={po}&pz={pz}&pn=1&np=1&fltt=2&invt=2&fs={fs}"
           f"&fields=f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87")
    try:
        r = requests.get(url, headers=EM_HEADERS, timeout=10)
        d = r.json()
        if d.get('data') and d['data'].get('diff'):
            items = []
            for it in d['data']['diff']:
                items.append({
                    'code': it.get('f12', ''),
                    'name': it.get('f14', ''),
                    'price': it.get('f2', 0),
                    'change_pct': it.get('f3', 0),
                    'main_net_inflow': it.get('f62', 0),
                    'main_net_pct': it.get('f184', 0),
                    'super_large_inflow': it.get('f66', 0),
                    'super_large_pct': it.get('f69', 0),
                    'large_inflow': it.get('f72', 0),
                    'large_pct': it.get('f75', 0),
                    'medium_inflow': it.get('f78', 0),
                    'medium_pct': it.get('f81', 0),
                    'small_inflow': it.get('f84', 0),
                    'small_pct': it.get('f87', 0),
                })
            return items
    except Exception as e:
        print(f"  EM fund flow error: {e}")
    return []


def fetch_em_top_by_amount(pz=20):
    """Fetch top stocks by trading amount (不缓存)."""
    fs = "m:105+t:1,m:105+t:2,m:106+t:1,m:106+t:2"
    url = (f"https://push2delay.eastmoney.com/api/qt/clist/get?"
           f"fid=f6&po=1&pz={pz}&pn=1&np=1&fltt=2&invt=2&fs={fs}"
           f"&fields=f12,f14,f2,f3,f5,f6,f15,f16,f17,f18")
    try:
        r = requests.get(url, headers=EM_HEADERS, timeout=10)
        d = r.json()
        if d.get('data') and d['data'].get('diff'):
            items = []
            for it in d['data']['diff']:
                items.append({
                    'code': it.get('f12', ''),
                    'name': it.get('f14', ''),
                    'price': it.get('f2', 0),
                    'change_pct': it.get('f3', 0),
                    'volume': it.get('f5', 0),
                    'amount': it.get('f6', 0),
                    'high': it.get('f15', 0),
                    'low': it.get('f16', 0),
                    'open': it.get('f17', 0),
                    'prev_close': it.get('f18', 0),
                })
            return items
    except Exception as e:
        print(f"  EM top amount error: {e}")
    return []


def fetch_vix_realtime():
    """Fetch VIX实时数据，使用新浪VIXY作为代理（腾讯VIX数据已过期）."""
    # 腾讯usVIX数据停在2026-04-15，改用新浪VIXY（恐慌指数ETF）
    url = "https://hq.sinajs.cn/list=gb_vixy"
    headers = {'Referer': 'https://finance.sina.com.cn'}
    try:
        r = requests.get(url, headers=headers, timeout=8)
        r.encoding = 'gbk'
        line = r.text.strip()
        if '=\"' in line:
            data_part = line.split('=\"')[1].rstrip('\";')
            fields = data_part.split(',')
            if len(fields) > 7:
                price = float(fields[1]) if fields[1] else 0
                change_pct = float(fields[2]) if fields[2] else 0
                change = float(fields[4]) if fields[4] else 0
                prev_close = float(fields[5]) if fields[5] else 0
                high = float(fields[6]) if fields[6] else 0
                low = float(fields[7]) if fields[7] else 0
                return {
                    'value': price,
                    'prev_close': prev_close,
                    'change': change,
                    'change_pct': change_pct,
                    'high': high,
                    'low': low,
                    'source': 'vixy',  # 标记数据源为VIXY
                }
    except Exception as e:
        print(f"  VIX error: {e}")
    return None


def fetch_klines_with_cache():
    """
    获取K线数据，优先使用当天缓存。
    部分股票在缓存中时，只拉缺失的，然后合并。
    """
    cached_stocks = load_kline_cache()
    stock_data = {}
    missing = []

    # 检查哪些股票需要拉取
    for sym, name in INDIVIDUAL_STOCKS.items():
        if sym in cached_stocks and cached_stocks[sym].get('dates'):
            stock_data[sym] = cached_stocks[sym]
            if not stock_data[sym].get('name'):
                stock_data[sym]['name'] = name
        else:
            missing.append(sym)

    print(f"\n=== K线数据：缓存 {len(stock_data)} 只，需拉取 {len(missing)} 只 ===")

    # 拉取缺失的股票
    for i, sym in enumerate(missing):
        name = INDIVIDUAL_STOCKS[sym]
        print(f"  [{i+1}/{len(missing)}] {sym} ({name})...", end=' ', flush=True)
        d = fetch_sina_daily_k(sym, days=60)
        if d:
            d['name'] = name
            stock_data[sym] = d
            print(f"OK ({d['total_records']} records, latest={d['latest_close']})")
        else:
            print("FAILED")

        # 新浪限流保护：每只股票间隔 1.5-3 秒
        if i < len(missing) - 1:
            sleep_time = random.uniform(1.5, 3.0)
            time.sleep(sleep_time)

    # 如果拉取了新数据，更新缓存
    if missing:
        # 只缓存K线相关字段，不包含实时行情
        kline_only = {}
        for sym, s in stock_data.items():
            kline_only[sym] = {
                k: v for k, v in s.items()
                if k not in ('rt_price', 'rt_change', 'rt_change_pct', 'rt_high', 'rt_low', 'rt_time')
            }
        save_kline_cache(kline_only)
    else:
        print("  ✅ 全部命中缓存，无需请求API")

    return stock_data


if __name__ == '__main__':
    # ========== 1. K线数据（有缓存）==========
    print("=== 1. K线数据（日K，缓存到当天）===")
    stock_data = fetch_klines_with_cache()

    # ========== 2. 实时行情（每次拉新，不缓存）==========
    print(f"\n=== 2. 实时行情 ({len(INDIVIDUAL_STOCKS)} stocks) ===")
    realtime = fetch_tencent_realtime(INDIVIDUAL_STOCKS)
    print(f"  Got {len(realtime)} real-time quotes")

    # ========== 3. 资金流向（每次拉新，不缓存）==========
    print("\n=== 3. 资金流向 (inflow TOP 20) ===")
    inflow = fetch_em_fund_flow(po=1, pz=20)
    print(f"  Got {len(inflow)} inflow stocks")
    for it in inflow[:5]:
        print(f"    {it['name']}: 主力净流入 {it['main_net_inflow']/1e8:.2f}亿 ({it['main_net_pct']}%)")

    print("\n=== 4. 资金流向 (outflow TOP 20) ===")
    outflow = fetch_em_fund_flow(po=0, pz=20)
    print(f"  Got {len(outflow)} outflow stocks")
    for it in outflow[:5]:
        print(f"    {it['name']}: 主力净流出 {it['main_net_inflow']/1e8:.2f}亿 ({it['main_net_pct']}%)")

    # ========== 4. 成交额TOP（每次拉新，不缓存）==========
    print("\n=== 5. 成交额 TOP 20 ===")
    top_amount = fetch_em_top_by_amount(pz=20)
    print(f"  Got {len(top_amount)} stocks")
    for it in top_amount[:5]:
        print(f"    {it['name']}: 成交额 {it['amount']/1e8:.2f}亿, 涨跌 {it['change_pct']}%")

    # ========== 5. VIX（每次拉新，不缓存）==========
    print("\n=== 6. VIX 实时 ===")
    vix = fetch_vix_realtime()
    if vix:
        print(f"  VIX = {vix['value']}, change={vix['change_pct']}%")
    else:
        print("  FAILED")

    # Merge realtime into stock_data
    for sym, rt in realtime.items():
        if sym in stock_data:
            stock_data[sym].update({
                'rt_price': rt['price'],
                'rt_change': rt['change'],
                'rt_change_pct': rt['change_pct'],
                'rt_high': rt['high'],
                'rt_low': rt['low'],
                'rt_time': rt['time'],
            })

    # Build output
    output = {
        'stocks': stock_data,
        'inflow': inflow,
        'outflow': outflow,
        'top_amount': top_amount,
        'vix': vix,
        'fetch_time': time.strftime('%Y-%m-%d %H:%M:%S'),
    }

    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, separators=(',', ':'))

    size = os.path.getsize(OUT_PATH)
    print(f"\n✅ Saved to {OUT_PATH} ({size/1024:.1f} KB)")
    print(f"   Stocks: {len(stock_data)}, Inflow: {len(inflow)}, Outflow: {len(outflow)}, TopAmount: {len(top_amount)}, VIX: {vix is not None}")
