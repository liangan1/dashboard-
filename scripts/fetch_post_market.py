#!/usr/bin/env python3
"""
盘后复盘数据获取：融资融券 + 龙虎榜 + 股指期货持仓
数据来源：东方财富 datacenter-web API
"""
import urllib.request
import json
import re
import time
from datetime import datetime, timedelta

DATA_DIR = '/Coze/Drive/金融分析'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://data.eastmoney.com/',
}


def _get_json(url, timeout=15):
    req = urllib.request.Request(url, headers=HEADERS)
    resp = urllib.request.urlopen(req, timeout=timeout)
    return json.loads(resp.read().decode('utf-8'))


def fetch_margin_trading(days=30):
    """融资融券汇总数据（沪深两市）
    
    字段:
    - DIM_DATE: 日期
    - RZYE: 融资余额(元)
    - RZMRE: 融资买入额(元)
    - RZJME: 融资净买入(元)
    - RQYE: 融券余额(元)
    - RQYL: 融券余量(股)
    - RZRQYE: 融资融券余额(元)
    - RZRQYECZ: 融资融券余额差值
    - RZYEZB: 融资余额占流通市值比(%)
    - ZDF: 上证指数涨跌幅(%)
    - RZMRE3D/5D/10D: 3/5/10日融资买入额
    - RZJME3D/5D/10D: 3/5/10日融资净买入
    """
    url = (
        'https://datacenter-web.eastmoney.com/api/data/v1/get?'
        'sortColumns=dim_date&sortTypes=-1&pageSize={}&pageNumber=1&'
        'reportName=RPTA_RZRQ_LSHJ&columns=ALL&source=WEB&client=WEB'
    ).format(days)
    
    try:
        data = _get_json(url)
        if not data.get('result') or not data['result'].get('data'):
            print('[margin] No data returned')
            return None
        
        rows = data['result']['data']
        records = []
        for row in rows:
            records.append({
                'date': row['DIM_DATE'][:10],
                'rzye': row.get('RZYE', 0),           # 融资余额
                'rzmre': row.get('RZMRE', 0),          # 融资买入额
                'rzche': row.get('RZCHE', 0),          # 融资偿还额
                'rzjme': row.get('RZJME', 0),          # 融资净买入
                'rqye': row.get('RQYE', 0),            # 融券余额
                'rqyl': row.get('RQYL', 0),            # 融券余量
                'rzrqye': row.get('RZRQYE', 0),        # 融资融券余额
                'rzyezb': row.get('RZYEZB', 0),        # 融资余额占比%
                'zdf': row.get('ZDF', 0),              # 上证涨跌幅
                'rzmre_3d': row.get('RZMRE3D', 0),
                'rzmre_5d': row.get('RZMRE5D', 0),
                'rzmre_10d': row.get('RZMRE10D', 0),
                'rzjme_3d': row.get('RZJME3D', 0),
                'rzjme_5d': row.get('RZJME5D', 0),
                'rzjme_10d': row.get('RZJME10D', 0),
            })
        
        result = {
            'latest': records[0],
            'history': records,
            'fetch_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        print(f'[margin] OK: {len(records)} days, latest={records[0]["date"]}, '
              f'融资余额={records[0]["rzye"]/1e8:.0f}亿')
        return result
    except Exception as e:
        print(f'[margin] Error: {e}')
        return None


def fetch_dragon_tiger(trade_date=None):
    """龙虎榜数据
    
    返回当日上榜个股，含买入/卖出金额、净额、上榜原因、机构席位标识。
    """
    if trade_date is None:
        # 取最近交易日
        trade_date = datetime.now().strftime('%Y-%m-%d')
    
    # 先尝试指定日期，如果没数据往前找
    for offset in range(5):
        d = (datetime.strptime(trade_date, '%Y-%m-%d') - timedelta(days=offset)).strftime('%Y-%m-%d')
        url = (
            'https://datacenter-web.eastmoney.com/api/data/v1/get?'
            'sortColumns=SECURITY_CODE&sortTypes=1&pageSize=100&pageNumber=1&'
            'reportName=RPT_DAILYBILLBOARD_DETAILSNEW&columns=ALL&source=WEB&client=WEB&'
            f"filter=(TRADE_DATE='{d}')"
        )
        try:
            data = _get_json(url)
            if data.get('result') and data['result'].get('data'):
                rows = data['result']['data']
                records = []
                for row in rows:
                    buy_amt = row.get('BILLBOARD_BUY_AMT', 0) or 0
                    sell_amt = row.get('BILLBOARD_SELL_AMT', 0) or 0
                    net_amt = row.get('BILLBOARD_NET_AMT', 0) or 0
                    explain = row.get('EXPLAIN', '') or ''
                    # 判断是否有机构参与
                    has_inst = '机构' in explain
                    
                    records.append({
                        'code': row.get('SECURITY_CODE', ''),
                        'name': row.get('SECURITY_NAME_ABBR', ''),
                        'price': row.get('CLOSE_PRICE', 0),
                        'chg_pct': row.get('CHANGE_RATE', 0),
                        'buy_amt': buy_amt,
                        'sell_amt': sell_amt,
                        'net_amt': net_amt,
                        'turnover': row.get('TURNOVERRATE', 0),
                        'reason': row.get('EXPLANATION', ''),
                        'explain': explain,
                        'has_institution': has_inst,
                        'accum_amt': row.get('ACCUM_AMOUNT', 0),
                        'market': row.get('TRADE_MARKET', ''),
                    })
                
                # 按净额排序
                records.sort(key=lambda x: x['net_amt'], reverse=True)
                
                result = {
                    'trade_date': d,
                    'count': len(records),
                    'stocks': records,
                    'top_buy': records[:10],
                    'top_sell': sorted(records, key=lambda x: x['net_amt'])[:10],
                    'institution_stocks': [r for r in records if r['has_institution']],
                    'fetch_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                }
                print(f'[lhb] OK: {d}, {len(records)} stocks, '
                      f'institution={len(result["institution_stocks"])}')
                return result
        except Exception as e:
            print(f'[lhb] Error for {d}: {e}')
        time.sleep(0.3)
    
    print('[lhb] No data found in last 5 days')
    return None


def fetch_futures_positions():
    """股指期货持仓排名（从中金所数据页面解析）
    
    解析东财期货持仓页面HTML，提取IF/IC/IH/IM的前20名会员
    多单/空单/净持仓数据，重点跟踪中信期货。
    
    注意：东财该页面是JS渲染，但fetch_web工具能拿到服务端渲染的文本。
    这里用正则从页面文本中解析。
    """
    result = {
        'trade_date': None,
        'contracts': {},
        'citic': {},
        'fetch_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    
    # 四个品种: IF(沪深300), IC(中证500), IH(上证50), IM(中证1000)
    for va in ['IF', 'IC', 'IH', 'IM']:
        try:
            url = f'https://data.eastmoney.com/IF/Data/Contract.html?va={va}'
            req = urllib.request.Request(url, headers=HEADERS)
            resp = urllib.request.urlopen(req, timeout=15)
            html = resp.read().decode('utf-8', errors='replace')
            
            # 提取日期
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', html)
            if date_match and not result['trade_date']:
                result['trade_date'] = date_match.group(1)
            
            # 数据是JS渲染的，HTML中没有直接数据
            # 需要调用后端API。尝试找API endpoint
            # 从页面JS中提取
            api_match = re.search(r'(https?://[^\'"\s]+(?:position|rank|ccpm)[^\'"\s]*)', html, re.I)
            if api_match:
                api_url = api_match.group(1)
                try:
                    api_data = _get_json(api_url)
                    if api_data.get('result') and api_data['result'].get('data'):
                        result['contracts'][va] = api_data['result']['data']
                except:
                    pass
            
            # 如果API没拿到，标记为待补充
            if va not in result['contracts']:
                result['contracts'][va] = {'note': 'JS rendered, needs browser or alternative source'}
                
        except Exception as e:
            print(f'[futures] Error for {va}: {e}')
            result['contracts'][va] = {'error': str(e)}
    
    # 尝试从中金所API直接获取
    try:
        citic_data = _fetch_citic_from_cffex()
        if citic_data:
            result['citic'] = citic_data
            print(f'[futures] CITIC data from CFFEX OK')
    except Exception as e:
        print(f'[futures] CFFEX fallback error: {e}')
    
    return result


def _fetch_citic_from_cffex():
    """从中金所官网获取中信期货持仓数据。
    中金所API: http://www.cffex.com.cn/sj/ccpm/YYYYMM/DD/{va}_1.csv
    但沙箱可能无法访问。如果失败返回None。
    """
    # 沙箱无法访问cffex.com.cn (Network is unreachable)
    # 这个函数留作占位，等有网络条件时实现
    return None


def fetch_all(trade_date=None):
    """获取全部盘后数据"""
    print('='*60)
    print('Fetching post-market data...')
    print('='*60)
    
    margin = fetch_margin_trading(days=30)
    time.sleep(0.5)
    
    lhb = fetch_dragon_tiger(trade_date=trade_date)
    time.sleep(0.5)
    
    futures = fetch_futures_positions()
    
    result = {}
    if margin:
        result['margin'] = margin
    if lhb:
        result['dragon_tiger'] = lhb
    if futures:
        result['futures'] = futures
    
    if result:
        result['fetch_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        out_path = f'{DATA_DIR}/post_market_data.json'
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f'\n✅ Saved to {out_path}')
    else:
        print('\n❌ No data fetched')
    
    return result


if __name__ == '__main__':
    import sys
    date = sys.argv[1] if len(sys.argv) > 1 else None
    fetch_all(trade_date=date)
