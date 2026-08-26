#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""商品数据注入 + SW更新 + GitHub推送 (独立轻量版)"""
import json, os, sys, re, time, base64, requests
from datetime import datetime

BASE_DIR = '/Coze/Drive/金融分析'
DASHBOARD_DIR = '/Coze/Drive/扣子/treasury_dashboard'
INDEX_HTML = os.path.join(DASHBOARD_DIR, 'index.html')
SW_JS = os.path.join(DASHBOARD_DIR, 'sw.js')
DEPLOY_CONFIG = os.path.join(DASHBOARD_DIR, 'deploy_config.json')
COMMODITY_DATA = os.path.join(BASE_DIR, 'commodities_data.json')
TODAY = datetime.now().strftime('%Y-%m-%d')
TODAY_COMPACT = datetime.now().strftime('%Y%m%d')

FRESHNESS_THRESHOLDS = {
    'bitcoin': 30 * 60,
    'commodity': 2 * 3600,
}

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def _fmt_price(price, decimals):
    if decimals == 0:
        return f"${price:,.0f}"
    return f"${price:,.{decimals}f}"

def _fmt_change(change, change_pct, decimals):
    cls = 'up' if change > 0 else ('down' if change < 0 else 'flat')
    arrow = '▲' if change > 0 else ('▼' if change < 0 else '—')
    if change == 0:
        if decimals == 0:
            return cls, "—0 (0.00%)"
        return cls, f"—0.{'0'*decimals} (0.00%)"
    if change > 0:
        sign = '+'
        if decimals == 0:
            return cls, f"{arrow}{sign}{change:,.0f} ({sign}{change_pct:.2f}%)"
        return cls, f"{arrow}{sign}{change:,.{decimals}f} ({sign}{change_pct:.2f}%)"
    else:
        if decimals == 0:
            return cls, f"{arrow}{change:,.0f} ({change_pct:.2f}%)"
        return cls, f"{arrow}{change:,.{decimals}f} ({change_pct:.2f}%)"

def update_tab_timestamp(html, tab_name, fetch_time_str):
    if not fetch_time_str:
        return html
    try:
        if isinstance(fetch_time_str, str):
            ft = datetime.strptime(fetch_time_str.split('.')[0], '%Y-%m-%d %H:%M:%S')
            display_time = ft.strftime('%m-%d %H:%M')
        else:
            return html
    except Exception:
        return html
    pattern = rf'(<span class="tab-update-time" data-tab="{tab_name}">)上次更新: [^<]*(</span>)'
    replacement = rf'\g<1>上次更新: {display_time}\g<2>'
    if re.search(pattern, html):
        html = re.sub(pattern, replacement, html)
    return html

def generate_freshness_html(fetch_time_str, data_type='default'):
    if not fetch_time_str:
        return '', -1
    try:
        if isinstance(fetch_time_str, str):
            ft = datetime.strptime(fetch_time_str.split('.')[0], '%Y-%m-%d %H:%M:%S')
        else:
            return '', -1
    except Exception:
        return '', -1
    age_seconds = (datetime.now() - ft).total_seconds()
    age_min = age_seconds / 60
    threshold = FRESHNESS_THRESHOLDS.get(data_type, 3600)
    if age_seconds <= threshold:
        status_html = '<span style="color: #22c55e;">✅ 实时</span>'
    elif age_seconds <= threshold * 2:
        status_html = '<span style="color: #eab308;">⏳ 稍旧</span>'
    else:
        status_html = '<span style="color: #ef4444;">⚠️ 过旧</span>'
    freshness_div = f'''<div style="font-size: 0.7em; color: #888; text-align: right; padding: 2px 8px; margin-top: -4px; margin-bottom: 4px;">
    数据时间: {fetch_time_str.split('.')[0]} | {status_html}
</div>'''
    return freshness_div, age_min

def inject_commodities(html, data):
    meta = data.get('_meta', {})
    fetch_time = meta.get('fetch_time', '')
    
    overview_cards = [
        ('btc', '比特币', '#f7931a'),
        ('gold', '黄金', '#ffd700'),
        ('wti', '原油WTI', '#8b5cf6'),
        ('brent', '布伦特原油', '#06b6d4'),
    ]
    
    detail_blocks = [
        ('btc', '比特币', 'CBBTCUSD'),
        ('gold', '黄金', 'GOLD'),
        ('wti', 'WTI', 'DCOILWTICO'),
        ('brent', '布伦特', 'DCOILBRENTEU'),
    ]
    
    # 1. 更新总览页卡片
    comm_section_start = html.find('💰 大宗商品')
    if comm_section_start != -1:
        next_section = html.find('📈 美股指数', comm_section_start)
        if next_section == -1:
            next_section = html.find('</section>', comm_section_start) + 10
        section_html = html[comm_section_start:next_section]
        
        for key, label, color in overview_cards:
            if key not in data:
                continue
            d = data[key]
            decimals = d.get('decimals', 2)
            price_str = _fmt_price(d['price'], decimals)
            chg_cls, chg_str = _fmt_change(d['change'], d['change_pct'], decimals)
            
            label_pos = section_html.find(f'>{label}<')
            if label_pos != -1:
                val_marker = 'class="ov-value"'
                val_start = section_html.find(val_marker, label_pos)
                if val_start != -1:
                    val_content_start = section_html.find('>', val_start) + 1
                    val_content_end = section_html.find('</div>', val_content_start)
                    section_html = (section_html[:val_content_start] + price_str + 
                                   section_html[val_content_end:])
                
                chg_marker = 'class="ov-chg'
                chg_start = section_html.find(chg_marker, label_pos)
                if chg_start != -1:
                    tag_end = section_html.find('>', chg_start)
                    chg_content_start = tag_end + 1
                    chg_content_end = section_html.find('</div>', chg_content_start)
                    section_html = (section_html[:chg_start] + 
                                   f'class="ov-chg {chg_cls}">{chg_str}' + 
                                   section_html[chg_content_end:])
        
        html = html[:comm_section_start] + section_html + html[next_section:]
        log("  总览页商品卡片已更新")
    
    # 2. 更新商品Tab详细区块
    for key, title_hint, chart_id in detail_blocks:
        if key not in data:
            continue
        d = data[key]
        decimals = d.get('decimals', 2)
        price_str = _fmt_price(d['price'], decimals)
        chg_cls, chg_str = _fmt_change(d['change'], d['change_pct'], decimals)
        
        title_pos = html.find(title_hint)
        while title_pos != -1:
            block_start = html.rfind('commodity-block', 0, title_pos)
            if block_start != -1 and title_pos - block_start < 500:
                yield_pos = html.find('yield-num', title_pos)
                if yield_pos != -1:
                    yn_start = html.find('>', yield_pos) + 1
                    yn_end = html.find('</span>', yn_start)
                    if yn_end - yn_start < 50:
                        html = html[:yn_start] + price_str + html[yn_end:]
                
                yc_pos = html.find('yield-chg', title_pos)
                if yc_pos != -1:
                    span_tag_start = html.rfind('<span', max(0, title_pos), yc_pos + 1)
                    if span_tag_start == -1:
                        span_tag_start = html.rfind('<span', 0, yc_pos)
                    
                    if span_tag_start != -1:
                        after_tag = html[span_tag_start:]
                        inner_close = after_tag.find('</span>')
                        if inner_close >= 0:
                            inner_close_abs = span_tag_start + inner_close + 7
                            rest = html[inner_close_abs:]
                            stripped = rest.lstrip(' \n\t\r')
                            ws_len = len(rest) - len(stripped)
                            
                            if stripped.startswith('</span>'):
                                outer_close_abs = inner_close_abs + ws_len + 7
                            else:
                                outer_close_abs = inner_close_abs
                            
                            arrow = '▲' if d['change'] > 0 else ('▼' if d['change'] < 0 else '—')
                            sign = '+' if d['change'] > 0 else ''
                            if decimals == 0:
                                change_text = f"{arrow}{sign}{d['change']:,.0f} ({sign}{d['change_pct']:.2f}%)"
                            else:
                                change_text = f"{arrow}{sign}{d['change']:,.{decimals}f} ({sign}{d['change_pct']:.2f}%)"
                            clean = f'<span class="yield-chg {chg_cls}"><span class="chg-icon">{change_text}</span></span>'
                            html = html[:span_tag_start] + clean + html[outer_close_abs:]
                            log(f"  ✓ {title_hint} yield-chg 已更新")
                break
    
    # 3. 更新底部数据源说明
    old_note = '（美债收益率 DGS2/DGS5/DGS10/DGS30 · 联邦债务 GFDEBTN · 比特币 CBBTCUSD · 原油 DCOILWTICO/DCOILBRENTEU）'
    new_note = f'（美债收益率 FRED · 商品/比特币 新浪财经实时期货 · 更新：{fetch_time}）'
    if old_note in html:
        html = html.replace(old_note, new_note, 1)
    
    # 4. 更新商品Tab时间戳
    html = update_tab_timestamp(html, 'commodities', data.get('fetch_time') or data.get('_meta', {}).get('fetch_time'))
    
    # 5. 注入新鲜度指示器
    commodity_ft = data.get('fetch_time') or data.get('_meta', {}).get('fetch_time', '')
    freshness_html, age_min = generate_freshness_html(commodity_ft, 'commodity')
    if freshness_html:
        tab_marker = '💰 大宗商品'
        tab_pos = html.find(tab_marker)
        if tab_pos != -1:
            section_end = html.find('</div>', tab_pos)
            if section_end != -1:
                html = html[:section_end + 6] + '    ' + freshness_html + '\n    ' + html[section_end + 6:]
                log(f"  商品新鲜度指示器已注入 (年龄: {age_min:.0f}分钟)")
    
    log(f"  商品数据注入完成 ({fetch_time})")
    return html


# ============ MAIN ============
log("====== 🛒 商品数据注入 + 推送 ======")

# 1. 加载商品数据
log("--- 1. 加载商品数据 ---")
with open(COMMODITY_DATA, 'r', encoding='utf-8') as f:
    data = json.load(f)
count = data.get('_meta', {}).get('count', 0)
log(f"  品种数: {count}, 获取时间: {data.get('_meta', {}).get('fetch_time', '?')}")

# 2. 读取HTML并注入
log("--- 2. 注入商品数据到 HTML ---")
with open(INDEX_HTML, 'r', encoding='utf-8') as f:
    html = f.read()
log(f"  HTML大小: {len(html):,} chars")

html = inject_commodities(html, data)

log("  保存HTML...")
with open(INDEX_HTML, 'w', encoding='utf-8') as f:
    f.write(html)
log(f"  HTML 已保存 ({len(html):,} chars)")

# 3. 更新SW版本
log("--- 3. 更新 Service Worker ---")
cache_name = f'treasury-dashboard-commodity-{TODAY_COMPACT}'
with open(SW_JS, 'r', encoding='utf-8') as f:
    sw_content = f.read()
sw_content = re.sub(
    r"const CACHE_NAME\s*=\s*'[^']*'",
    f"const CACHE_NAME = '{cache_name}'",
    sw_content
)
with open(SW_JS, 'w', encoding='utf-8') as f:
    f.write(sw_content)
log(f"SW 缓存版本更新为: {cache_name}")

# 4. GitHub推送
log("--- 4. 推送到 GitHub ---")
with open(DEPLOY_CONFIG, 'r', encoding='utf-8') as f:
    config = json.load(f)
token = config['github_token']
repo = config['github_repo']

headers = {
    'Authorization': f'token {token}',
    'Accept': 'application/vnd.github.v3+json',
}
api_base = f'https://api.github.com/repos/{repo}/contents'

for file_path in [INDEX_HTML, SW_JS]:
    filename = os.path.basename(file_path)
    url = f'{api_base}/{filename}'
    
    log(f"  获取远程 SHA: {filename}")
    sha = None
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            sha = r.json().get('sha')
    except Exception as e:
        log(f"  ⚠️ 获取 SHA 失败: {e}")
    
    with open(file_path, 'rb') as f:
        content = base64.b64encode(f.read()).decode('utf-8')
    
    payload = {
        'message': f'chore: 商品数据更新 {TODAY}',
        'content': content,
    }
    if sha:
        payload['sha'] = sha
    
    log(f"  推送 {filename}...")
    try:
        r = requests.put(url, headers=headers, json=payload, timeout=60)
        if r.status_code in (200, 201):
            log(f"  ✅ {filename} 推送成功")
        else:
            log(f"  ❌ {filename} 推送失败: {r.status_code} {r.text[:200]}")
    except Exception as e:
        log(f"  ❌ {filename} 推送异常: {e}")
    
    time.sleep(0.5)

log("====== ✅ 商品数据更新完成 ======")
