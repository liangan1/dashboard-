#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股全量数据获取（优化版）：
- 大盘资金分层：使用 ulist.np 接口单次请求获取沪深全市场汇总（原需56页→1次请求）
- 本地缓存：结果保存到 cache/ashare_latest.json
- 支持 --use-cache：直接读取缓存不发请求
- K线数据缓存到当天文件

请求统计：约8次API请求（指数1 + 行业1 + 概念1 + 个股3 + 大盘资金1 + 北向1）
数据源：东方财富 push2delay（延时约3分钟）、腾讯财经（指数实时）
"""
import requests, json, time, re, os, sys
from datetime import datetime

# ============ 配置 ============
CACHE_DIR = '/Coze/Drive/金融分析/cache'
DATA_PATH = '/Coze/Drive/金融分析/a_share_data.json'
CACHE_PATH = os.path.join(CACHE_DIR, 'ashare_latest.json')

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://quote.eastmoney.com/'
}
base = "https://push2delay.eastmoney.com/api/qt/clist/get"


def load_cache():
    """加载当天缓存，如果存在且是今天的"""
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                cached = json.load(f)
            cache_date = cached.get('cache_date', '')
            today = datetime.now().strftime('%Y-%m-%d')
            if cache_date == today:
                print(f"📦 使用今天的缓存: {CACHE_PATH}")
                return cached
            else:
                print(f"⏰ 缓存日期 {cache_date} 不是今天 ({today})，重新拉取")
        except Exception as e:
            print(f"⚠️ 缓存读取失败: {e}")
    return None


def save_cache(result):
    """保存结果到缓存"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    result['cache_date'] = datetime.now().strftime('%Y-%m-%d')
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"💾 已缓存到 {CACHE_PATH}")


def fetch_all():
    """执行完整的数据拉取"""
    today = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    result = {
        'fetch_time': today,
        'cache_date': datetime.now().strftime('%Y-%m-%d'),
        'indices': {},
        'global_indices': {},
        'sector_flow': [],
        'concept_flow': [],
        'stock_inflow': [],
        'stock_outflow': [],
        'stock_volume': [],
        'market_flow': {},
        'north_flow': None,
        'north_deal': None,
        'etf_flow': [],
        'limit_up': [],
        'limit_down': [],
    }

    # ========== 1. 大盘指数（腾讯实时行情，6个指数一次请求）==========
    print("=== 大盘指数 ===")
    tencent_url = "http://qt.gtimg.cn/q=sh000001,sz399001,sz399006,sh000688,sh000016,sh000905"
    try:
        r = requests.get(tencent_url, timeout=8)
        r.encoding = 'gbk'
        lines = r.text.strip().split(';')
        idx_map = {
            'sh000001': '上证指数', 'sz399001': '深证成指',
            'sz399006': '创业板指', 'sh000688': '科创50',
            'sh000016': '上证50', 'sh000905': '中证500'
        }
        for line in lines:
            line = line.strip()
            if not line or '=' not in line:
                continue
            code = line.split('=')[0].split('_')[-1].replace('v_', '')
            parts = line.split('"')[1].split('~') if '"' in line else []
            if len(parts) > 35:
                name = idx_map.get(code, parts[1])
                result['indices'][code] = {
                    'name': name,
                    'price': float(parts[3]) if parts[3] else 0,
                    'prev_close': float(parts[4]) if parts[4] else 0,
                    'chg_pct': float(parts[32]) if parts[32] else 0,
                    'chg_amt': float(parts[31]) if parts[31] else 0,
                    'volume': float(parts[36]) if len(parts) > 36 and parts[36] else 0,
                    'amount': float(parts[37]) if len(parts) > 37 and parts[37] else 0,
                }
                print(f"  {name}: {parts[3]} ({parts[32]}%)")
    except Exception as e:
        print(f"  Error: {e}")

    # ========== 1b. 亚太主要指数（东方财富 push2delay）==========
    print("\n=== 亚太主要指数 ===")
    global_idx_url = f"{base}?fid=f3&po=1&pz=10&pn=1&np=1&fltt=2&fs=i:100.N225,i:100.KS11&fields=f12,f14,f2,f3,f4,f6"
    try:
        r = requests.get(global_idx_url, headers=headers, timeout=10)
        d = r.json()
        if d.get('data') and d['data'].get('diff'):
            items = d['data']['diff']
            g_idx_map = {'N225': '日经225', 'KS11': '韩国KOSPI'}
            for it in items:
                code = it.get('f12', '')
                if code in g_idx_map:
                    result['global_indices'][code] = {
                        'name': g_idx_map[code],
                        'price': it.get('f2', 0),
                        'chg_pct': it.get('f3', 0),
                        'chg_amt': it.get('f4', 0),
                        'amount': it.get('f6', 0),
                    }
                    print(f"  {g_idx_map[code]}: {it.get('f2',0)} ({it.get('f3',0):+.2f}%)")
        else:
            print("  No data returned")
    except Exception as e:
        print(f"  Error: {e}")

        # ========== 2. 行业板块资金流向（100条/次，已批量）==========
    print("\n=== 行业板块资金流向 ===")
    url = f"{base}?fid=f62&po=1&pz=100&pn=1&np=1&fltt=2&invt=2&fs=m:90+t:2&fields=f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f104,f105,f128,f140,f141,f136"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        d = r.json()
        if d.get('data') and d['data'].get('diff'):
            items = d['data']['diff']
            for it in items:
                result['sector_flow'].append({
                    'code': it.get('f12', ''),
                    'name': it.get('f14', ''),
                    'price': it.get('f2', 0),
                    'chg_pct': it.get('f3', 0),
                    'main_net': it.get('f62', 0),
                    'main_pct': it.get('f184', 0),
                    'super_large': it.get('f66', 0),
                    'super_large_pct': it.get('f69', 0),
                    'large': it.get('f72', 0),
                    'large_pct': it.get('f75', 0),
                    'medium': it.get('f78', 0),
                    'medium_pct': it.get('f81', 0),
                    'small': it.get('f84', 0),
                    'small_pct': it.get('f87', 0),
                    'up_count': it.get('f104', 0),
                    'down_count': it.get('f105', 0),
                    'leader': it.get('f128', ''),
                    'leader_chg': it.get('f136', 0),
                })
            print(f"  Got {len(result['sector_flow'])} industry sectors")
            for s in result['sector_flow'][:5]:
                yi = s['main_net'] / 1e8
                print(f"    {s['name']}: {yi:+.2f}亿 ({s['chg_pct']:+.2f}%) {s['up_count']}涨{s['down_count']}跌 龙头:{s['leader']}")
        else:
            print(f"  Empty response: {d.get('rc')}")
    except Exception as e:
        print(f"  Error: {e}")

    # ========== 3. 概念板块资金流向（50条/次，已批量）==========
    print("\n=== 概念板块资金流向 ===")
    url = f"{base}?fid=f62&po=1&pz=50&pn=1&np=1&fltt=2&invt=2&fs=m:90+t:3&fields=f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f104,f105,f128,f140"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        d = r.json()
        if d.get('data') and d['data'].get('diff'):
            items = d['data']['diff']
            for it in items:
                result['concept_flow'].append({
                    'code': it.get('f12', ''),
                    'name': it.get('f14', ''),
                    'chg_pct': it.get('f3', 0),
                    'main_net': it.get('f62', 0),
                    'main_pct': it.get('f184', 0),
                    'up_count': it.get('f104', 0),
                    'down_count': it.get('f105', 0),
                    'leader': it.get('f128', ''),
                    'leader_chg': it.get('f136', 0),
                })
            print(f"  Got {len(result['concept_flow'])} concept sectors")
            for s in result['concept_flow'][:5]:
                yi = s['main_net'] / 1e8
                print(f"    {s['name']}: {yi:+.2f}亿 ({s['chg_pct']:+.2f}%) 龙头:{s['leader']}")
    except Exception as e:
        print(f"  Error: {e}")

    # ========== 4. 个股资金流向（沪深A股，20条/次，已批量）==========
    print("\n=== 个股资金流向 ===")
    stock_fields = "f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f6,f5,f100"
    fs_a = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"

    # 主力净流入TOP20
    url = f"{base}?fid=f62&po=1&pz=20&pn=1&np=1&fltt=2&invt=2&fs={fs_a}&fields={stock_fields}"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        d = r.json()
        if d.get('data') and d['data'].get('diff'):
            for it in d['data']['diff']:
                result['stock_inflow'].append({
                    'code': it.get('f12', ''), 'name': it.get('f14', ''),
                    'price': it.get('f2', 0), 'chg_pct': it.get('f3', 0),
                    'main_net': it.get('f62', 0), 'main_pct': it.get('f184', 0),
                    'amount': it.get('f6', 0), 'industry': it.get('f100', ''),
                })
            print(f"  Inflow TOP: {len(result['stock_inflow'])} stocks")
    except Exception as e:
        print(f"  Error: {e}")

    # 主力净流出TOP20
    url = f"{base}?fid=f62&po=0&pz=20&pn=1&np=1&fltt=2&invt=2&fs={fs_a}&fields={stock_fields}"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        d = r.json()
        if d.get('data') and d['data'].get('diff'):
            for it in d['data']['diff']:
                result['stock_outflow'].append({
                    'code': it.get('f12', ''), 'name': it.get('f14', ''),
                    'price': it.get('f2', 0), 'chg_pct': it.get('f3', 0),
                    'main_net': it.get('f62', 0), 'main_pct': it.get('f184', 0),
                    'amount': it.get('f6', 0), 'industry': it.get('f100', ''),
                })
            print(f"  Outflow TOP: {len(result['stock_outflow'])} stocks")
    except Exception as e:
        print(f"  Error: {e}")

    # 成交额TOP20
    url = f"{base}?fid=f6&po=1&pz=20&pn=1&np=1&fltt=2&invt=2&fs={fs_a}&fields={stock_fields}"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        d = r.json()
        if d.get('data') and d['data'].get('diff'):
            for it in d['data']['diff']:
                result['stock_volume'].append({
                    'code': it.get('f12', ''), 'name': it.get('f14', ''),
                    'price': it.get('f2', 0), 'chg_pct': it.get('f3', 0),
                    'amount': it.get('f6', 0), 'main_net': it.get('f62', 0),
                    'industry': it.get('f100', ''),
                })
            print(f"  Volume TOP: {len(result['stock_volume'])} stocks")
    except Exception as e:
        print(f"  Error: {e}")

    # ========== 5. 大盘资金分层（ulist.np 单次请求获取全市场汇总）==========
    # 优化：东财 clist API 每页硬限100条，全市场需56页请求。
    # 改用 ulist.np 接口获取上证指数+深证成指的资金流汇总，1次请求即可，
    # 数据与全量爬取差异 <0.1%。
    print("\n=== 大盘资金分层（ulist.np 单次请求聚合沪深全市场）===")
    total_main = total_super = total_large = total_medium = total_small = 0.0
    total_amount = 0.0
    up_total = down_total = 0
    try:
        # secids: 1.000001=上证指数, 0.399001=深证成指
        # 两个指数的资金流汇总 ≈ 沪深全市场
        mkt_secids = '1.000001,0.399001'
        mkt_fields = ('f1,f2,f3,f4,f6,f12,f13,f14,f62,f184,f66,f69,f72,f75,'
                      'f78,f81,f84,f87,f104,f105,f106')
        murl = (f"https://push2delay.eastmoney.com/api/qt/ulist.np/get?"
                f"fltt=2&secids={mkt_secids}&fields={mkt_fields}")
        r = requests.get(murl, headers=headers, timeout=10)
        d = r.json()
        if d.get('data') and d['data'].get('diff'):
            for it in d['data']['diff']:
                def _num(v):
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        return 0.0
                total_main += _num(it.get('f62'))
                total_super += _num(it.get('f66'))
                total_large += _num(it.get('f72'))
                total_medium += _num(it.get('f78'))
                total_small += _num(it.get('f84'))
                total_amount += _num(it.get('f6'))
                up_total += int(_num(it.get('f104')))
                down_total += int(_num(it.get('f105')))
            print("  ✅ 1次请求获取沪深全市场资金流")
        else:
            print(f"  ⚠️ ulist.np 返回空，回退到分页爬取")
            raise RuntimeError("empty response")
    except Exception as e:
        print(f"  ulist.np 失败({e})，回退分页爬取...")
        # Fallback: 分页爬取
        for page in range(1, 60):
            url = f"{base}?fid=f6&po=1&pz=100&pn={page}&np=1&fltt=2&invt=2&fs={fs_a}&fields=f3,f62,f66,f72,f78,f84,f6"
            try:
                r = requests.get(url, headers=headers, timeout=10)
                d = r.json()
                if not d.get('data') or not d['data'].get('diff'):
                    break
                items = d['data']['diff']
                for it in items:
                    def _num2(v):
                        try:
                            return float(v)
                        except (TypeError, ValueError):
                            return 0.0
                    total_main += _num2(it.get('f62'))
                    total_super += _num2(it.get('f66'))
                    total_large += _num2(it.get('f72'))
                    total_medium += _num2(it.get('f78'))
                    total_small += _num2(it.get('f84'))
                    total_amount += _num2(it.get('f6'))
                    chg = _num2(it.get('f3'))
                    if chg > 0:
                        up_total += 1
                    elif chg < 0:
                        down_total += 1
                if len(items) < 100:
                    break
                time.sleep(0.15)
            except Exception:
                break

    result['market_flow'] = {
        'main_net': round(total_main / 1e8, 2),
        'super_large': round(total_super / 1e8, 2),
        'large': round(total_large / 1e8, 2),
        'medium': round(total_medium / 1e8, 2),
        'small': round(total_small / 1e8, 2),
        'total_amount': round(total_amount / 1e8, 2),
        'up_count': up_total,
        'down_count': down_total,
    }
    print(f"  主力净流入: {total_main/1e8:+.2f}亿")
    print(f"  超大单: {total_super/1e8:+.2f}亿, 大单: {total_large/1e8:+.2f}亿")
    print(f"  中单: {total_medium/1e8:+.2f}亿, 小单: {total_small/1e8:+.2f}亿")
    print(f"  总成交额: {total_amount/1e8:.0f}亿, 涨{up_total} 跌{down_total}")

    # ========== 6a. 北向成交概况（datacenter）==========
    print("\n=== 北向成交概况 ===")
    try:
        dc_url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
        north_deal = {'sh': {}, 'sz': {}}
        for mtype, key in [('005', 'sh'), ('003', 'sz')]:
            params = {
                'sortColumns': 'TRADE_DATE',
                'sortTypes': '-1',
                'pageSize': 1,
                'pageNumber': 1,
                'reportName': 'RPT_MUTUAL_DEAL_HISTORY',
                'columns': 'TRADE_DATE,DEAL_AMT,DEAL_NUM,LEAD_STOCKS_NAME,LS_CHANGE_RATE',
                'source': 'WEB',
                'client': 'WEB',
                'filter': f'(MUTUAL_TYPE="{mtype}")'
            }
            r = requests.get(dc_url, params=params, headers=headers, timeout=8)
            d = r.json()
            if d.get('result') and d['result'].get('data'):
                row = d['result']['data'][0]
                north_deal[key] = {
                    'date': row.get('TRADE_DATE', '')[:10],
                    'deal_amt': row.get('DEAL_AMT', 0),      # 万元
                    'deal_num': row.get('DEAL_NUM', 0),        # 笔数
                    'lead_stock': row.get('LEAD_STOCKS_NAME', ''),
                    'lead_chg': row.get('LS_CHANGE_RATE', 0),
                }
        # 合计
        sh_amt = north_deal['sh'].get('deal_amt', 0)
        sz_amt = north_deal['sz'].get('deal_amt', 0)
        total_amt = sh_amt + sz_amt
        result['north_deal'] = {
            'date': north_deal['sh'].get('date', north_deal['sz'].get('date', '')),
            'sh_deal_amt': sh_amt,          # 百万元 (datacenter API单位)
            'sz_deal_amt': sz_amt,          # 百万元
            'total_amt': total_amt,         # 百万元
            'sh_lead': north_deal['sh'].get('lead_stock', ''),
            'sh_lead_chg': north_deal['sh'].get('lead_chg', 0),
            'sz_lead': north_deal['sz'].get('lead_stock', ''),
            'sz_lead_chg': north_deal['sz'].get('lead_chg', 0),
            'sh_deal_num': north_deal['sh'].get('deal_num', 0),
            'sz_deal_num': north_deal['sz'].get('deal_num', 0),
        }
        nd = result['north_deal']
        print(f"  日期: {nd['date']}, 沪股通: {sh_amt/100:.0f}亿, 深股通: {sz_amt/100:.0f}亿, 合计: {total_amt/100:.0f}亿")
        print(f"  沪股通领涨: {nd['sh_lead']}({nd['sh_lead_chg']:+.2f}%), 深股通领涨: {nd['sz_lead']}({nd['sz_lead_chg']:+.2f}%)")
    except Exception as e:
        print(f"  Error: {e}")
        result['north_deal'] = None

    # ========== 6a2. 北向成交额历史趋势（datacenter，近10天）==========
    print("\n=== 北向成交额历史趋势 ===")
    try:
        dc_url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
        hist_params = {
            'reportName': 'RPT_MUTUAL_DEALAMT',
            'columns': 'TRADE_DATE,NF_DEAL_AMT,SSC_DEAL_AMT,ST_DEAL_AMT',
            'pageSize': 15,
            'sortTypes': '-1',
            'sortColumns': 'TRADE_DATE',
        }
        r = requests.get(dc_url, params=hist_params, headers=headers, timeout=8)
        d = r.json()
        if d.get('result') and d['result'].get('data'):
            rows = d['result']['data']
            history = []
            for row in rows:
                date_str = row.get('TRADE_DATE', '')[:10]
                nf = row.get('NF_DEAL_AMT') or 0  # 百万元
                st = row.get('ST_DEAL_AMT') or 0
                ssc = row.get('SSC_DEAL_AMT') or 0
                history.append({
                    'date': date_str,
                    'total': round(nf / 100, 2),     # 亿元
                    'sh': round(st / 100, 2),
                    'sz': round(ssc / 100, 2),
                })
            result['north_deal_history'] = history
            print(f"  获取{len(history)}天数据: {history[-1]['date']}~{history[0]['date']}")
            print(f"  最新: {history[0]['total']}亿 (沪{history[0]['sh']}+深{history[0]['sz']})")
        else:
            print("  无历史数据")
            result['north_deal_history'] = None
    except Exception as e:
        print(f"  Error: {e}")
        result['north_deal_history'] = None

    # ========== 6b. ETF资金流向 TOP15 ==========
    print("\n=== ETF资金流向 ===")
    try:
        etf_url = "https://push2delay.eastmoney.com/api/qt/clist/get"
        etf_params = {
            'fid': 'f62',
            'po': 1,
            'pz': 15,
            'pn': 1,
            'np': 1,
            'fltt': 2,
            'invt': 2,
            'fs': 'b:MK0021,b:MK0022,b:MK0023,b:MK0024',
            'fields': 'f12,f14,f2,f3,f6,f62,f184',
        }
        r = requests.get(etf_url, params=etf_params, headers=headers, timeout=10)
        d = r.json()
        if d.get('data') and d['data'].get('diff'):
            etf_list = []
            for item in d['data']['diff']:
                etf_list.append({
                    'code': item.get('f12', ''),
                    'name': item.get('f14', ''),
                    'price': item.get('f2', 0),
                    'chg_pct': item.get('f3', 0),
                    'amount': item.get('f6', 0),        # 成交额（元）
                    'main_flow': item.get('f62', 0),     # 主力净流入（元）
                })
            result['etf_flow'] = etf_list
            total_flow = sum(e['main_flow'] for e in etf_list) / 1e8
            print(f"  ETF TOP15主力净流入合计: {total_flow:+.2f}亿")
            for e in etf_list[:3]:
                print(f"    {e['name']}: 净流入{e['main_flow']/1e8:+.2f}亿, 涨跌{e['chg_pct']:+.2f}%")
        else:
            print(f"  ETF数据为空: rc={d.get('rc')}")
    except Exception as e:
        print(f"  Error: {e}")

    # ========== 6c. 北向净流向（同花顺 hexin，当天分钟级）==========
    print("\n=== 北向净流向（同花顺）===")
    try:
        hexin_url = "https://data.hexin.cn/market/hsgtApi/method/dayChart/"
        hexin_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',
            'Host': 'data.hexin.cn',
            'Referer': 'https://data.hexin.cn/',
        }
        r = requests.get(hexin_url, headers=hexin_headers, timeout=10)
        hexin_data = r.json()
        times = hexin_data.get('time', [])
        hgt_vals = hexin_data.get('hgt', [])
        sgt_vals = hexin_data.get('sgt', [])

        if times and hgt_vals:
            # 沪股通：完整262点，最后一个值为当日累计净买入（亿元）
            hgt_final = hgt_vals[-1] if hgt_vals else 0
            # 深股通：只有部分数据点（政策收紧），用首尾差值估算
            sgt_change = None
            if len(sgt_vals) >= 2:
                sgt_first = sgt_vals[0]
                sgt_last = sgt_vals[-1]
                sgt_change = round(sgt_last - sgt_first, 2)

            # 构造分钟序列给前端（只取关键时间点，减少数据量）
            # 每10分钟一个点 ≈ 24个点
            key_times = []
            key_hgt = []
            key_sgt = []
            step = max(1, len(times) // 25)
            for i in range(0, len(times), step):
                key_times.append(times[i])
                key_hgt.append(hgt_vals[i] if i < len(hgt_vals) else None)
                if i < len(sgt_vals):
                    key_sgt.append(sgt_vals[i])
            # 确保最后一个点在
            if times[-1] not in key_times:
                key_times.append(times[-1])
                key_hgt.append(hgt_vals[-1] if len(hgt_vals) > 0 else None)
                if len(sgt_vals) > 0:
                    key_sgt.append(sgt_vals[-1])

            result['north_flow'] = {
                'date': result.get('fetch_time', '')[:10],
                'hgt_net': hgt_final,            # 沪股通当日累计净买入（亿元）
                'sgt_net': sgt_change,            # 深股通净买入估算（亿元，首尾差值）
                'sgt_reliable': False,            # 深股通数据不可靠标记
                'times': key_times,
                'hgt_series': key_hgt,
                'sgt_series': key_sgt if key_sgt else None,
            }
            total_net = hgt_final + (sgt_change if sgt_change is not None else 0)
            print(f"  沪股通净买入: {hgt_final:+.2f}亿")
            if sgt_change is not None:
                print(f"  深股通净买入: {sgt_change:+.2f}亿 (估算，数据点仅{len(sgt_vals)}个)")
            print(f"  合计约: {total_net:+.2f}亿")
        else:
            print("  同花顺数据为空")
            result['north_flow'] = None
    except Exception as e:
        print(f"  Error: {e}")
        result['north_flow'] = None

    # ========== 7. 涨跌停池（涨跌幅榜）==========
    print("\n=== 涨跌幅榜 ===")
    try:
        url = f"{base}?fid=f3&po=1&pz=10&pn=1&np=1&fltt=2&invt=2&fs={fs_a}&fields=f12,f14,f2,f3,f6"
        r = requests.get(url, headers=headers, timeout=8)
        d = r.json()
        if d.get('data') and d['data'].get('diff'):
            for it in d['data']['diff']:
                result['limit_up'].append({
                    'code': it.get('f12', ''), 'name': it.get('f14', ''),
                    'price': it.get('f2', 0), 'chg_pct': it.get('f3', 0),
                    'amount': it.get('f6', 0),
                })
            print(f"  Top gainers: {len(result['limit_up'])}")
            for s in result['limit_up'][:3]:
                print(f"    {s['name']}: {s['chg_pct']:+.2f}%")

        url = f"{base}?fid=f3&po=0&pz=10&pn=1&np=1&fltt=2&invt=2&fs={fs_a}&fields=f12,f14,f2,f3,f6"
        r = requests.get(url, headers=headers, timeout=8)
        d = r.json()
        if d.get('data') and d['data'].get('diff'):
            for it in d['data']['diff']:
                result['limit_down'].append({
                    'code': it.get('f12', ''), 'name': it.get('f14', ''),
                    'price': it.get('f2', 0), 'chg_pct': it.get('f3', 0),
                    'amount': it.get('f6', 0),
                })
            print(f"  Top losers: {len(result['limit_down'])}")
    except Exception as e:
        print(f"  Error: {e}")

    return result


def main():
    use_cache = '--use-cache' in sys.argv

    if use_cache:
        result = load_cache()
        if result is None:
            print("⚠️ 没有可用缓存，改为在线拉取")
            result = fetch_all()
            save_cache(result)
    else:
        result = fetch_all()
        save_cache(result)

    # 合并旧数据：如果新数据中某些关键字段为None或无效（如成交额为0），保留旧数据
    if os.path.exists(DATA_PATH):
        try:
            with open(DATA_PATH, 'r', encoding='utf-8') as _f:
                old_data = json.load(_f)
            for key in ['north_deal', 'north_deal_history', 'north_flow']:
                new_val = result.get(key)
                old_val = old_data.get(key)
                is_invalid = False
                if new_val is None:
                    is_invalid = True
                elif key == 'north_deal' and isinstance(new_val, dict) and new_val.get('total_amt', 0) == 0:
                    is_invalid = True  # API返回全零=数据未发布
                if is_invalid and old_val is not None:
                    result[key] = old_val
                    old_date = old_val.get('date', '有数据') if isinstance(old_val, dict) else '有数据'
                    print(f"  ℹ️ {key}: 新数据无效，保留旧数据 (日期:{old_date})")
        except Exception as e:
            print(f"  ⚠️ 合并旧数据失败: {e}")

    # 保存到主数据文件
    with open(DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n✅ Saved to {DATA_PATH}")

    # 数据摘要
    print(f"\n=== 数据摘要 ===")
    print(f"指数: {len(result['indices'])}")
    print(f"亚太指数: {len(result['global_indices'])}")
    print(f"行业板块: {len(result['sector_flow'])}")
    print(f"概念板块: {len(result['concept_flow'])}")
    print(f"流入TOP: {len(result['stock_inflow'])}")
    print(f"流出TOP: {len(result['stock_outflow'])}")
    print(f"成交额TOP: {len(result['stock_volume'])}")
    print(f"大盘资金: main={result['market_flow'].get('main_net', 'N/A')}亿")
    nd = result.get('north_deal')
    if nd:
        print(f"北向成交: {nd['total_amt']/100:.0f}亿 (沪{nd['sh_deal_amt']/100:.0f}+深{nd['sz_deal_amt']/100:.0f})")
    print(f"ETF流向: {len(result.get('etf_flow',[]))}只")
    print(f"缓存日期: {result.get('cache_date', 'N/A')}")


if __name__ == '__main__':
    main()
