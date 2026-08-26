#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
集合竞价数据获取（9:25-9:30执行）
- 三大指数集合竞价价格
- 东财涨幅榜前20只高开股（含行业/题材标签）
- 东财跌幅榜前20只低开股（含行业/题材标签）
- 高开低走家数统计
- 按四层框架生成竞价总结：大盘定调→焦点股方向→板块联动→外围定锚
"""
import requests
import json
import os
from datetime import datetime
from collections import defaultdict

BASE_DIR = '/Coze/Drive/金融分析'
OUTPUT_PATH = os.path.join(BASE_DIR, 'auction_data.json')
THEMES_PATH = os.path.join(BASE_DIR, 'auction_focus_themes.json')

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; x64) AppleWebKit/537.36',
    'Referer': 'https://quote.eastmoney.com/'
}


# ─────────────── 题材映射管理 ───────────────

def load_themes():
    """加载本地题材映射文件"""
    if os.path.exists(THEMES_PATH):
        with open(THEMES_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'concepts': {}, 'industry_alias': {}, 'updated': ''}


def save_themes(themes):
    """保存题材映射"""
    themes['updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(THEMES_PATH, 'w', encoding='utf-8') as f:
        json.dump(themes, f, ensure_ascii=False, indent=2)


def get_stock_theme(code, name, industry, themes):
    """获取股票的题材标签：优先概念映射 > 行业别名 > 原始行业"""
    # 1. 手动概念映射（优先级最高）
    if code in themes.get('concepts', {}):
        return themes['concepts'][code].get('theme', industry)
    
    # 2. 行业别名映射（把细分行业归到大类）
    if industry in themes.get('industry_alias', {}):
        return themes['industry_alias'][industry]
    
    # 3. 直接用API返回的行业
    return industry if industry else '其他'


# ─────────────── 板块联动分析 ───────────────

def analyze_theme_linkage(stocks):
    """按板块归类，分析联动性
    
    返回: {
        'themes': {
            '医药': {'stocks': [...], 'direction': 'up'/'down'/'mixed', 'consensus': 0.8},
            ...
        },
        'strong_themes': [...],   # 联动性强的板块（多只同方向）
        'weak_themes': [...],     # 分化的板块（同板块涨跌不一）
    }
    """
    theme_groups = defaultdict(list)
    for s in stocks:
        theme = s.get('theme', '其他')
        if theme and theme != '其他':
            theme_groups[theme].append(s)
    
    result = {}
    strong, weak = [], []
    
    for theme, group in theme_groups.items():
        if len(group) < 2:
            result[theme] = {
                'stocks': group,
                'direction': 'up' if group[0]['gap_pct'] > 0 else 'down',
                'consensus': 1.0,
                'count': 1,
            }
            continue
        
        # 多只同板块股票 → 判断联动性
        up_count = sum(1 for s in group if s['gap_pct'] > 0.3)
        down_count = sum(1 for s in group if s['gap_pct'] < -0.3)
        total = len(group)
        
        if up_count >= total * 0.6:
            direction = 'up'
            consensus = up_count / total
        elif down_count >= total * 0.6:
            direction = 'down'
            consensus = down_count / total
        else:
            direction = 'mixed'
            consensus = max(up_count, down_count) / total
        
        avg_gap = sum(s['gap_pct'] for s in group) / total
        result[theme] = {
            'stocks': sorted(group, key=lambda x: x['gap_pct'], reverse=True),
            'direction': direction,
            'consensus': consensus,
            'avg_gap': round(avg_gap, 2),
            'count': total,
        }
        
        if consensus >= 0.6 and total >= 2:
            strong.append(theme)
        elif direction == 'mixed':
            weak.append(theme)
    
    return {
        'themes': result,
        'strong_themes': strong,
        'weak_themes': weak,
    }


# ─────────────── 总结生成 ───────────────

def generate_summary(result):
    """按四层框架生成竞价文字总结
    第一层：大盘定调
    第二层：龙头/焦点股竞价方向
    第三层：板块联动
    第四层：外围定锚（占位）
    """
    lines = []
    indices = result.get('indices', {})
    top_up = result.get('top_gap_up', [])
    top_down = result.get('top_gap_down', [])
    stats = result.get('stats', {})
    top_up = [s for s in top_up if not s.get('is_new_listing', False)]
    top_down = [s for s in top_down if not s.get('is_new_listing', False)]
    idx_list = list(indices.values())
    if idx_list:
        dirs = []
        for i in idx_list:
            if i['gap_pct'] < -0.1: dirs.append('低开')
            elif i['gap_pct'] > 0.1: dirs.append('高开')
            else: dirs.append('平开')
        if len(set(dirs)) == 1: tone = f'三大指数集体{dirs[0]}'
        else: tone = '三大指数分化开盘'
        idx_parts = '，'.join(f"{i['name']}{d}{abs(i['gap_pct']):.2f}%" for i, d in zip(idx_list, dirs))
        weak = []
        for s in top_down[:10]:
            t = s.get('theme','')
            if t and t not in weak: weak.append(t)
        hot = []
        for s in top_up[:10]:
            t = s.get('theme','')
            if t and t not in hot: hot.append(t)
        l1 = f'【大盘定调】{tone}，{idx_parts}。'
        if weak: l1 += f"{'、'.join(weak[:3])}等方向跌幅居前。"
        if hot: l1 += f"{'、'.join(hot[:3])}等方向逆势活跃。"
        uc = stats.get('gap_up_count',0); dc = stats.get('gap_down_count',0); tc = uc+dc+stats.get('flat_count',0)
        if tc > 0:
            r = uc/tc
            if r >= 0.6: l1 += '市场情绪偏暖，赚钱效应较好。'
            elif r <= 0.3: l1 += '市场情绪偏弱，防御心态为主。'
            else: l1 += '多空分歧明显，结构性行情。'
        lines.append(l1)
    focus = []
    for s in top_up[:5]: focus.append({'name':s['name'],'gap_pct':s['gap_pct'],'direction':'高开','theme':s.get('theme','')})
    for s in top_down[:2]: focus.append({'name':s['name'],'gap_pct':s['gap_pct'],'direction':'低开','theme':s.get('theme','')})
    if focus:
        uf = sum(1 for f in focus if f['direction']=='高开')
        df = sum(1 for f in focus if f['direction']=='低开')
        tf = len(focus)
        if uf >= tf*0.7: con = '方向一致偏多，情绪延续强势'
        elif df >= tf*0.7: con = '方向一致偏空，市场谨慎'
        else: con = '龙头分化，多空博弈加剧'
        sd = '，'.join(f"{f['name']}({f['direction']}{abs(f['gap_pct']):.2f}%)" for f in focus)
        lines.append(f'【焦点股方向】{sd}。{con}。')
    all_focus = top_up[:10] + top_down[:10]
    linkage = analyze_theme_linkage(all_focus)
    ti = linkage['themes']
    pt = sorted(ti.keys(), key=lambda t: (ti[t].get('count',0), ti[t].get('consensus',0)), reverse=True)
    ts = []
    for theme in pt:
        info = ti[theme]; stocks = info['stocks']
        if info.get('count',0) < 2 or not stocks: continue
        sp = []
        for s in stocks[:3]:
            if s['gap_pct']>0.3: d='高开'
            elif s['gap_pct']<-0.3: d='低开'
            else: d='平开'
            sp.append(f"{s['name']}({d}{abs(s['gap_pct']):.2f}%)")
        if info['direction']=='up': dl='联动走强'
        elif info['direction']=='down': dl='联动承压'
        elif info['direction']=='mixed': dl='内部分化'
        else: dl=''
        ts.append(f"{theme}板块{dl}（{'、'.join(sp)}）。")
    if ts:
        l3 = f'【板块联动】{ts[0]}'
        if len(ts)>1: l3 += f" 此外，{''.join(ts[1:4])}"
        lines.append(l3)
    lines.append('【外围定锚】__NEED_EXTERNAL_DATA__')
    return '\n\n'.join(lines)







# ─────────────── 数据获取 ───────────────

def fetch_indices():
    """获取三大指数实时行情（含集合竞价价格）"""
    url = "http://qt.gtimg.cn/q=sh000001,sz399001,sz399006"
    try:
        r = requests.get(url, timeout=8)
        r.encoding = 'gbk'
        lines = r.text.strip().split(';')
        
        idx_map = {
            'sh000001': '上证指数',
            'sz399001': '深证成指',
            'sz399006': '创业板指'
        }
        
        indices = {}
        for line in lines:
            line = line.strip()
            if not line or '=' not in line:
                continue
            code = line.split('=')[0].split('_')[-1].replace('v_', '')
            parts = line.split('"')[1].split('~') if '"' in line else []
            
            if len(parts) > 35 and code in idx_map:
                name = idx_map[code]
                price = float(parts[3]) if parts[3] else 0
                prev_close = float(parts[4]) if parts[4] else 0
                open_price = float(parts[5]) if parts[5] else 0
                
                gap_pct = ((open_price - prev_close) / prev_close * 100) if prev_close else 0
                
                indices[code] = {
                    'name': name,
                    'price': price,
                    'open': open_price,
                    'prev_close': prev_close,
                    'gap_pct': gap_pct,
                }
                print(f"  {name}: 开盘{open_price:.2f} 昨收{prev_close:.2f} 幅度{gap_pct:+.2f}%")
        
        return indices
    except Exception as e:
        print(f"  Error fetching indices: {e}")
        return {}


def fetch_stocks_by_gap(sort_order='desc', limit=20, themes=None):
    """获取高开/低开股票列表（含行业标签）
    
    sort_order: 'desc'=高开榜, 'asc'=低开榜
    themes: 题材映射数据
    返回按开盘价/昨收价涨幅排序的股票，附带行业/题材信息
    """
    base_url = "https://push2delay.eastmoney.com/api/qt/clist/get"
    fs_a = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
    # f100 = 所属行业
    fields = "f12,f14,f2,f3,f17,f18,f6,f100"
    
    po = 1 if sort_order == 'desc' else 0
    
    url = f"{base_url}?fid=f3&po={po}&pz={limit}&pn=1&np=1&fltt=2&invt=2&fs={fs_a}&fields={fields}"
    
    if themes is None:
        themes = load_themes()
    
    try:
        r = requests.get(url, headers=headers, timeout=10)
        d = r.json()
        
        if not d.get('data') or not d['data'].get('diff'):
            return []
        
        stocks = []
        new_industries = {}  # 记录新发现的行业映射
        
        for it in d['data']['diff']:
            code = it.get('f12', '')
            name = it.get('f14', '')
            price = it.get('f2', 0)
            chg_pct = it.get('f3', 0)
            open_price = it.get('f17', 0)
            prev_close = it.get('f18', 0)
            amount = it.get('f6', 0)
            industry = it.get('f100', '')
            
            gap_pct = ((open_price - prev_close) / prev_close * 100) if prev_close else 0
            
            # 过滤新股首日（名称以N开头，涨幅异常>100%）
            is_new_listing = name.startswith('N') and abs(gap_pct) > 100
            
            # 获取题材标签
            theme = get_stock_theme(code, name, industry, themes)
            
            stocks.append({
                'code': code,
                'name': name,
                'price': price,
                'open': open_price,
                'prev_close': prev_close,
                'gap_pct': gap_pct,
                'chg_pct': chg_pct,
                'amount': amount,
                'industry': industry,
                'theme': theme,
                'is_new_listing': is_new_listing,
            })
        
        return stocks
    except Exception as e:
        print(f"  Error fetching stocks: {e}")
        return []


def fetch_gap_stats():
    """统计高开/低开/平开家数"""
    base_url = "https://push2delay.eastmoney.com/api/qt/clist/get"
    fs_a = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
    fields = "f17,f18"
    
    gap_up = 0
    gap_down = 0
    flat = 0
    
    for page in range(1, 60):
        url = f"{base_url}?fid=f3&po=1&pz=100&pn={page}&np=1&fltt=2&invt=2&fs={fs_a}&fields={fields}"
        try:
            r = requests.get(url, headers=headers, timeout=10)
            d = r.json()
            
            if not d.get('data') or not d['data'].get('diff'):
                break
            
            items = d['data']['diff']
            for it in items:
                try:
                    open_price = float(it.get('f17', 0) or 0)
                    prev_close = float(it.get('f18', 0) or 0)
                except (ValueError, TypeError):
                    continue
                
                if prev_close == 0:
                    continue
                
                if open_price > prev_close * 1.001:
                    gap_up += 1
                elif open_price < prev_close * 0.999:
                    gap_down += 1
                else:
                    flat += 1
            
            if len(items) < 100:
                break
            
        except Exception as e:
            print(f"  Error in page {page}: {e}")
            break
    
    return {
        'gap_up_count': gap_up,
        'gap_down_count': gap_down,
        'flat_count': flat,
    }


# ─────────────── 主流程 ───────────────

def fetch_all():
    """获取全部集合竞价数据"""
    print('='*60)
    print('Fetching auction data...')
    print('='*60)
    
    # 加载题材映射
    themes = load_themes()
    
    print("\n=== 三大指数 ===")
    indices = fetch_indices()
    
    print("\n=== 高开股TOP20 ===")
    top_gap_up = fetch_stocks_by_gap(sort_order='desc', limit=20, themes=themes)
    print(f"  Got {len(top_gap_up)} stocks")
    if top_gap_up:
        # 打印行业标签
        for s in top_gap_up[:5]:
            print(f"  {s['name']}({s['theme']}) {s['gap_pct']:+.2f}%")
    
    print("\n=== 低开股TOP20 ===")
    top_gap_down = fetch_stocks_by_gap(sort_order='asc', limit=20, themes=themes)
    print(f"  Got {len(top_gap_down)} stocks")
    if top_gap_down:
        for s in top_gap_down[:5]:
            print(f"  {s['name']}({s['theme']}) {s['gap_pct']:+.2f}%")
    
    print("\n=== 高开/低开统计 ===")
    stats = fetch_gap_stats()
    print(f"  高开: {stats['gap_up_count']}  低开: {stats['gap_down_count']}  平开: {stats['flat_count']}")
    
    # 板块联动分析（过滤新股首日）
    print("\n=== 板块联动分析 ===")
    focus_up = [s for s in top_gap_up if not s.get('is_new_listing', False)]
    focus_down = [s for s in top_gap_down if not s.get('is_new_listing', False)]
    all_focus = focus_up[:10] + focus_down[:10]
    linkage = analyze_theme_linkage(all_focus)
    
    for theme in sorted(linkage['themes'].keys(), 
                        key=lambda t: linkage['themes'][t].get('count', 0),
                        reverse=True):
        info = linkage['themes'][theme]
        dir_cn = {'up': '↑走强', 'down': '↓承压', 'mixed': '↔分化'}.get(info['direction'], '?')
        stocks_str = ', '.join(s['name'] for s in info['stocks'][:3])
        consensus = info.get('consensus', 0)
        print(f"  {theme} [{dir_cn}] 共识度{consensus:.0%} ({info['count']}只) → {stocks_str}")
    
    if linkage['strong_themes']:
        print(f"  ✅ 联动板块: {', '.join(linkage['strong_themes'])}")
    if linkage['weak_themes']:
        print(f"  ⚠️ 分化板块: {', '.join(linkage['weak_themes'])}")
    
    result = {
        'fetch_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'indices': indices,
        'top_gap_up': top_gap_up,
        'top_gap_down': top_gap_down,
        'stats': stats,
        'linkage': {
            'themes': {
                t: {
                    'direction': info['direction'],
                    'consensus': info['consensus'],
                    'count': info['count'],
                    'avg_gap': info.get('avg_gap', 0),
                    'stocks': [{'code': s['code'], 'name': s['name'], 'gap_pct': s['gap_pct'], 'theme': s['theme']} 
                              for s in info['stocks']],
                }
                for t, info in linkage['themes'].items()
            },
            'strong_themes': linkage['strong_themes'],
            'weak_themes': linkage['weak_themes'],
        },
        'summary': '',  # 占位，下面生成
    }
    
    # 生成总结
    result['summary'] = generate_summary(result)
    
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"\n=== 竞价总结 ===\n")
    print(result['summary'])
    print(f"\n✅ Saved to {OUTPUT_PATH}")
    
    return result


if __name__ == '__main__':
    fetch_all()
