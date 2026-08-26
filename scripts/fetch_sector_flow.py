import requests, json, time

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://quote.eastmoney.com/'
}
base = "https://push2delay.eastmoney.com/api/qt/clist/get"

# 拉取全部美股个股（多页），含行业f100和资金流向字段
all_stocks = []
for page in range(1, 15):  # up to 14 pages * 100 = 1400 stocks
    url = f"{base}?fid=f6&po=1&pz=100&pn={page}&np=1&fltt=2&invt=2&fs=m:105+t:1,m:105+t:2,m:106+t:1,m:106+t:2&fields=f12,f14,f2,f3,f4,f5,f6,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f100"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        d = r.json()
        if not d.get('data') or not d['data'].get('diff'):
            break
        items = d['data']['diff']
        if not items:
            break
        all_stocks.extend(items)
        print(f"Page {page}: got {len(items)} stocks (total {len(all_stocks)})")
        if len(items) < 100:
            break
        time.sleep(0.3)
    except Exception as e:
        print(f"Page {page} error: {e}")
        break

print(f"\nTotal stocks fetched: {len(all_stocks)}")

# Aggregate by industry
industries = {}
for it in all_stocks:
    ind = it.get('f100', '') or '其他'
    if ind == '-' or not ind:
        ind = '其他'
    if ind not in industries:
        industries[ind] = {
            'count': 0, 'total_flow': 0, 'total_amount': 0,
            'up': 0, 'down': 0, 'flat': 0,
            'super_large': 0, 'large': 0, 'medium': 0, 'small': 0,
            'top_inflow': [], 'top_outflow': [],
            'avg_chg': 0, 'chg_sum': 0
        }
    flow = it.get('f62', 0) or 0
    amt = it.get('f6', 0) or 0
    chg = it.get('f3', 0) or 0
    industries[ind]['count'] += 1
    industries[ind]['total_flow'] += flow
    industries[ind]['total_amount'] += amt
    industries[ind]['chg_sum'] += chg
    if chg > 0: industries[ind]['up'] += 1
    elif chg < 0: industries[ind]['down'] += 1
    else: industries[ind]['flat'] += 1
    industries[ind]['super_large'] += it.get('f66', 0) or 0
    industries[ind]['large'] += it.get('f72', 0) or 0
    industries[ind]['medium'] += it.get('f78', 0) or 0
    industries[ind]['small'] += it.get('f84', 0) or 0
    industries[ind]['top_inflow'].append({'name': it.get('f14',''), 'code': it.get('f12',''), 'flow': flow, 'chg': chg})
    industries[ind]['top_outflow'].append({'name': it.get('f14',''), 'code': it.get('f12',''), 'flow': flow, 'chg': chg})

for ind in industries:
    info = industries[ind]
    info['avg_chg'] = info['chg_sum'] / info['count'] if info['count'] else 0
    info['top_inflow'] = sorted(info['top_inflow'], key=lambda x: x['flow'], reverse=True)[:5]
    info['top_outflow'] = sorted(info['top_outflow'], key=lambda x: x['flow'])[:5]
    # Convert to yi (亿)
    info['total_flow_yi'] = round(info['total_flow'] / 1e8, 2)
    info['total_amount_yi'] = round(info['total_amount'] / 1e8, 2)
    info['super_large_yi'] = round(info['super_large'] / 1e8, 2)
    info['large_yi'] = round(info['large'] / 1e8, 2)
    info['medium_yi'] = round(info['medium'] / 1e8, 2)
    info['small_yi'] = round(info['small'] / 1e8, 2)
    for s in info['top_inflow'] + info['top_outflow']:
        s['flow_yi'] = round(s['flow'] / 1e8, 2)

# Sort by total flow
sorted_ind = sorted(industries.items(), key=lambda x: x[1]['total_flow'], reverse=True)

print(f"\n=== 行业板块资金流向（基于{len(all_stocks)}只美股聚合）===")
print(f"{'行业':<12} {'净流入(亿)':>10} {'成交额(亿)':>10} {'涨/跌':>8} {'均涨幅%':>8}")
for ind, info in sorted_ind:
    print(f"{ind:<12} {info['total_flow_yi']:>+10.2f} {info['total_amount_yi']:>10.0f} {info['up']:>3}/{info['down']:<3} {info['avg_chg']:>+7.2f}%")

# Save
output = {
    'total_stocks': len(all_stocks),
    'industries': []
}
for ind, info in sorted_ind:
    output['industries'].append({
        'name': ind,
        'count': info['count'],
        'total_flow_yi': info['total_flow_yi'],
        'total_amount_yi': info['total_amount_yi'],
        'up': info['up'], 'down': info['down'], 'flat': info['flat'],
        'avg_chg': round(info['avg_chg'], 2),
        'super_large_yi': info['super_large_yi'],
        'large_yi': info['large_yi'],
        'medium_yi': info['medium_yi'],
        'small_yi': info['small_yi'],
        'top_inflow': info['top_inflow'],
        'top_outflow': info['top_outflow']
    })

with open('sector_flow_data.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"\nSaved to sector_flow_data.json")
