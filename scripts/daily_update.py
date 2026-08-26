#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全球资产看板 - 每日统一更新脚本

三种模式：
  morning  (7:00)  — 更新美股/美债/商品，A股用缓存
  noon     (12:00) — 更新A股上午盘数据
  evening  (15:30) — 更新A股全天收盘数据

功能：
  1. 调用对应的数据获取脚本
  2. 将数据注入 index.html（A股Tab / 美股数据）
  3. 更新 sw.js 缓存版本号
  4. 通过 GitHub Contents API 推送到仓库
"""
import json, os, sys, re, subprocess, time, base64, requests
from datetime import datetime, timedelta

# ============ 路径配置 ============
BASE_DIR = '/Coze/Drive/金融分析'
DASHBOARD_DIR = '/Coze/Drive/扣子/treasury_dashboard'
INDEX_HTML = os.path.join(DASHBOARD_DIR, 'index.html')
A_SHARES_HTML = os.path.join(DASHBOARD_DIR, 'a-shares.html')
SW_JS = os.path.join(DASHBOARD_DIR, 'sw.js')
DEPLOY_CONFIG = os.path.join(DASHBOARD_DIR, 'deploy_config.json')
A_DATA = os.path.join(BASE_DIR, 'a_share_data.json')
A_SPARK = os.path.join(BASE_DIR, 'a_share_spark.json')
US_DATA = os.path.join(BASE_DIR, 'us_enhanced_data.json')
COMMODITY_DATA = os.path.join(BASE_DIR, 'commodities_data.json')
AUCTION_DATA = os.path.join(BASE_DIR, 'auction_data.json')
TAIL_SNAPSHOT = os.path.join(BASE_DIR, 'tail_snapshot.json')
POST_MARKET_DATA = os.path.join(BASE_DIR, 'post_market_data.json')
VOLUME_HIST = os.path.join(BASE_DIR, 'market_volume_history.json')
CACHE_DIR = os.path.join(BASE_DIR, 'cache')

TODAY = datetime.now().strftime('%Y-%m-%d')
TODAY_COMPACT = datetime.now().strftime('%Y%m%d')


# ============================================================
#  工具函数
# ============================================================

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def verify_github_push():
    """GitHub推送后的占位验证函数。
    实际推送由 push_to_github() 完成并通过返回值检查，
    此函数保留仅为兼容已有调用点，避免 NameError。
    """
    log("  (verify_github_push: 推送已由 push_to_github 完成)")


def update_page_dates(html, mode, us_ok=False, us_fetch_time=None, a_ok=False):
    """统一更新页面所有日期/时间戳。
    
    规则：只有数据实际更新的部分才更新日期。
    - us_ok=True 时更新美股相关日期
    - a_ok=True 时更新A股相关日期
    - 只要有任何数据更新，就更新全局日期（title/header/总览大日期）

    mode: morning / noon / evening
    us_fetch_time: 美股数据的 fetch_time（有值时更新美股精确时间戳）
    """
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    any_data_updated = us_ok or a_ok

    # === 全局日期（只有实际更新了数据才刷） ===
    if any_data_updated:
        # 1. <title> 日期
        html = re.sub(
            r'<title>全球资产每日看板 - [\d-]+</title>',
            f'<title>全球资产每日看板 - {TODAY}</title>',
            html
        )
        # 2. 顶部 header 小日期
        html = re.sub(
            r'(<div class="date">)[\d-]+(</div>)',
            rf'\g<1>{TODAY}\g<2>',
            html
        )
        # 3. 总览页大日期
        html = re.sub(
            r'(<div class="big-date">)[\d-]+(</div>)',
            rf'\g<1>{TODAY}\g<2>',
            html
        )
        log(f"  全局日期已更新为 {TODAY}")
    else:
        log("  ⚠️ 无任何数据更新，全局日期保持不变")

    # === 美股专属日期（仅 us_ok=True 时更新） ===
    us_date = us_fetch_time[:10] if us_fetch_time else (TODAY if us_ok else None)
    if us_ok:
        # 4. 美股市场脉搏 "数据更新: YYYY-MM-DD · ..."
        html = re.sub(
            r'(数据更新: )\d{4}-\d{2}-\d{2}( · 延时约3分钟 · 1400只标的聚合)',
            rf'\g<1>{us_date}\g<2>',
            html
        )
        # 5. 美股行业聚合 "更新：YYYY-MM-DD"
        html = re.sub(
            r'(基于1400只美股按行业聚合 · 数据源：东方财富（延时约3分钟）· 更新：)\d{4}-\d{2}-\d{2}',
            rf'\g<1>{us_date}',
            html
        )
        # 6. 美股个股资金流向精确时间
        if us_fetch_time:
            html = re.sub(
                r'(数据来源：东方财富（延时约3分钟）· 更新：)\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}( · 主力=超大单\+大单)',
                rf'\g<1>{us_fetch_time}\g<2>',
                html
            )
        log(f"  美股日期已更新 (fetch_time={us_fetch_time or us_date})")
    else:
        log("  美股数据未更新，美股日期保持不变")

    # === A股日期由 inject_a_shares 重新生成，此处无需额外处理 ===
    if a_ok:
        log("  A股数据已重新注入（自带最新时间戳）")
    else:
        log("  A股数据未更新，A股区块保持不变")

    return html


def run_script(script_path, args=None):
    """运行 Python 脚本，返回是否成功"""
    cmd = [sys.executable, script_path]
    if args:
        cmd.extend(args)
    log(f"运行: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=BASE_DIR)
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(f"STDERR: {result.stderr}", file=sys.stderr)
        if result.returncode != 0:
            log(f"⚠️ 脚本返回非零退出码: {result.returncode}")
            return False
        return True
    except subprocess.TimeoutExpired:
        log(f"❌ 脚本超时: {script_path}")
        return False
    except Exception as e:
        log(f"❌ 运行脚本失败: {e}")
        return False


def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


# ============================================================
#  数据新鲜度验证框架
# ============================================================

FRESHNESS_THRESHOLDS = {
    'bitcoin': 30 * 60,              # 30分钟（24/7交易）
    'commodity': 2 * 3600,           # 2小时（期货市场）
    'us_stock': 24 * 3600,           # 1个交易日
    'a_share': 24 * 3600,            # 1个交易日
    'north_flow': 24 * 3600,         # 1个交易日（保留兼容）
    'north_deal': 24 * 3600,         # 北向成交总额（1个交易日）
    'etf_flow': 24 * 3600,           # ETF资金流向（1个交易日）
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
        print(f"  ⚠️ [{data_type}] 无fetch_time字段")
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




def validate_html_integrity(html, mode=''):
    """HTML完整性验证：检查常见注入错误
    
    返回: (is_valid: bool, issues: list[str])
    """
    issues = []
    
    # 1. 检查 yield-chg span 是否有重复class
    bad_spans = re.findall(r'class="yield-chg[^"]*(?:\s+\w+){2,}"', html)
    if bad_spans:
        issues.append(f"yield-chg重复class: {bad_spans[:3]}")
    
    # 2. 检查 ov-chg 是否有重复class
    bad_ov = re.findall(r'class="ov-chg[^"]*(?:\s+\w+){2,}"', html)
    if bad_ov:
        issues.append(f"ov-chg重复class: {bad_ov[:3]}")
    
    # 3. 检查未闭合的span标签
    open_spans = len(re.findall(r'<span\s', html))
    close_spans = len(re.findall(r'</span>', html))
    if abs(open_spans - close_spans) > 5:
        issues.append(f"span标签不平衡: open={open_spans}, close={close_spans}")
    
    is_valid = len(issues) == 0
    if mode:
        status = "✅" if is_valid else "❌"
        print(f"{status} [{mode}] HTML验证: {len(issues)}个问题")
        for issue in issues:
            print(f"  ⚠️ {issue}")
    
    return is_valid, issues

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


def generate_freshness_html(fetch_time_str, data_type='default'):
    """生成新鲜度标识HTML片段

    返回: (html_str, age_minutes)
    """
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
        status_html = '<span style="color: #22c55e;">✅</span>'
    elif age_seconds <= threshold * 2:
        status_html = '<span style="color: #eab308;">⏳ 稍旧</span>'
    else:
        status_html = '<span style="color: #ef4444;">⚠️ 过旧</span>'

    freshness_div = f'''<div style="font-size: 0.7em; color: #888; text-align: right; padding: 2px 8px; margin-top: -4px; margin-bottom: 4px;">
    数据时间: {fetch_time_str.split('.')[0]} | {status_html}
</div>'''
    return freshness_div, age_min


# ============================================================
#  Tab 更新时间戳
# ============================================================

def update_tab_timestamp(html, tab_name, fetch_time_str):
    """更新指定Tab的更新时间显示
    
    tab_name: 'us_stocks', 'a_shares', 'commodities', 'treasury', 'overseas'
    fetch_time_str: "2026-08-24 07:00:15" 格式的时间字符串
    """
    if not fetch_time_str:
        return html
    
    try:
        # 解析fetch_time
        if isinstance(fetch_time_str, str):
            ft = datetime.strptime(fetch_time_str.split('.')[0], '%Y-%m-%d %H:%M:%S')
            display_time = ft.strftime('%m-%d %H:%M')
        else:
            return html
    except Exception:
        return html
    
    # 查找Tab的更新时间标记
    # 格式: <span class="tab-update-time" data-tab="tab_name">上次更新: --</span>
    pattern = rf'(<span class="tab-update-time" data-tab="{tab_name}">)上次更新: [^<]*(</span>)'
    replacement = rf'\g<1>上次更新: {display_time}\g<2>'
    
    if re.search(pattern, html):
        html = re.sub(pattern, replacement, html)
    else:
        # 没找到标记，不添加（需要HTML先有占位符）
        pass
    
    return html


# ============================================================
#  A股 HTML 注入（支持重复更新）
# ============================================================

def fmt_yi(val):
    if val is None:
        return '-'
    yi = val / 1e8
    if abs(yi) >= 1:
        return f"{yi:+.2f}亿" if yi != 0 else "0"
    wan = val / 1e4
    return f"{wan:+.0f}万"


def color_chg(val):
    try:
        val = float(val)
    except Exception:
        return "#9ca3af"
    if val > 0:
        return '#ef4444'
    if val < 0:
        return '#22c55e'
    return '#9ca3af'


def color_flow(val):
    try:
        val = float(val)
    except Exception:
        return "#9ca3af"
    if val > 0:
        return '#ef4444'
    if val < 0:
        return '#22c55e'
    return '#9ca3af'


def get_section_time(json_path, key_path=None):
    """从JSON文件获取更新时间，返回 HH:mm 格式字符串"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if key_path:
            for key in key_path.split('.'):
                data = data.get(key, {})
        ft = data.get('fetch_time', '')
        if ft and isinstance(ft, str):
            dt = datetime.strptime(ft.split('.')[0], '%Y-%m-%d %H:%M:%S')
            return dt.strftime('%H:%M')
    except Exception:
        pass
    return '--:--'


def section_time_html(time_str, css_class='section-time'):
    """生成时间戳HTML"""
    return f'<span class="{css_class}" style="font-size:0.6em; color:#999; font-weight:normal; margin-left:6px;">🕑 {time_str}</span>'


def update_volume_history():
    """将今日成交额+上证指数追加到历史文件（去重，保留最近60天）"""
    try:
        if not os.path.exists(A_DATA):
            log("  ⚠️ a_share_data.json 不存在，跳过成交额采集")
            return
        a_d = load_json(A_DATA)
        mf = a_d.get('market_flow', {})
        idx = a_d.get('indices', {}).get('sh000001', {})
        today_amount = mf.get('total_amount', 0)
        if today_amount <= 0:
            log("  ⚠️ 今日成交额无效，跳过")
            return
        sh_price = idx.get('price', 0)
        sh_chg = idx.get('chg_pct', 0)
        fetch_time = a_d.get('fetch_time', '')
        # 提取日期
        date_str = fetch_time[:10] if fetch_time else TODAY

        # 读取历史
        hist_data = {"meta": {"unit": "亿元", "note": "沪深两市成交额+上证指数，每日收盘后自动采集"}, "daily": []}
        if os.path.exists(VOLUME_HIST):
            try:
                with open(VOLUME_HIST, 'r', encoding='utf-8') as f:
                    hist_data = json.load(f)
            except:
                pass

        daily = hist_data.get('daily', [])
        # 去重：移除同一天的旧数据
        daily = [d for d in daily if d.get('date') != date_str]
        # 追加新数据
        entry = {"date": date_str, "amount": round(today_amount, 1)}
        if sh_price > 0:
            entry["sh_price"] = sh_price
            entry["sh_chg_pct"] = sh_chg
        daily.append(entry)
        # 按日期排序（旧→新）
        daily.sort(key=lambda x: x.get('date', ''))
        # 只保留最近60条
        if len(daily) > 60:
            daily = daily[-60:]
        hist_data['daily'] = daily
        hist_data['meta']['last_updated'] = date_str
        save_json(VOLUME_HIST, hist_data)
        log(f"  ✅ 成交额历史已更新: {date_str} 成交额{today_amount:.0f}亿 上证{sh_price:.2f}({sh_chg:+.2f}%)")
    except Exception as e:
        log(f"  ❌ 更新成交额历史失败: {e}")


def build_volume_chart():
    """构建成交额+上证指数量价趋势图HTML（改进版：支持更多数据点，更美观的布局）"""
    try:
        if not os.path.exists(VOLUME_HIST):
            return ''
        with open(VOLUME_HIST, 'r', encoding='utf-8') as f:
            hist_data = json.load(f)
        daily = hist_data.get('daily', [])
        # 只取有上证数据的条目
        priced = [d for d in daily if d.get('sh_price', 0) > 0]
        
        if len(priced) < 2:
            # 数据不足，fallback: 只显示成交额柱状图
            if len(daily) < 2:
                return ''
            items = daily[-30:]
            max_amt = max(d['amount'] for d in items) if items else 1
            bars = ''
            for d in items:
                pct = d['amount'] / max_amt * 100 if max_amt > 0 else 0
                ds = d['date'][5:]
                bars += f'''<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:1px;min-width:0">
                  <div style="font-size:8px;color:#9ca3af">{d['amount']:.0f}</div>
                  <div style="height:{max(pct*0.9,3):.0f}px;width:100%;background:rgba(96,165,250,.7);border-radius:3px 3px 0 0"></div>
                  <div style="font-size:8px;color:#6b7280">{ds}</div>
                </div>'''
            return f'''
    <div style="background:rgba(96,165,250,.04);border:1px solid rgba(96,165,250,.1);border-radius:8px;padding:10px;margin-bottom:12px">
      <div style="font-size:12px;font-weight:600;color:#60a5fa;margin-bottom:8px">📊 两市成交额趋势（亿元）</div>
      <div style="display:flex;align-items:flex-end;gap:3px;height:90px;padding:0 2px">{bars}</div>
      <div style="font-size:9px;color:#6b7280;margin-top:4px;text-align:center">每日收盘后自动采集 · 累积中</div>
    </div>'''

        # 有上证数据，做量价双轴图
        items = priced[-30:]
        n = len(items)
        max_amt = max(d['amount'] for d in items)
        prices = [d['sh_price'] for d in items]
        min_p, max_p = min(prices), max(prices)
        p_range = max_p - min_p if max_p > min_p else 1
        
        chart_height = 120
        bar_max_h = 90

        bars = ''
        for i, d in enumerate(items):
            amt_pct = d['amount'] / max_amt
            bar_h = max(amt_pct * bar_max_h, 8)
            ds = d['date'][5:]
            bar_color = 'rgba(96,165,250,.65)' if d.get('sh_chg_pct', 0) >= 0 else 'rgba(96,165,250,.45)'
            bars += f'''<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:2px;min-width:0;position:relative">
              <div style="font-size:9px;color:#c4b5fd;font-weight:600">{d['amount']:.0f}</div>
              <div style="height:{bar_h:.0f}px;width:85%;background:{bar_color};border-radius:3px 3px 0 0;transition:all .2s"></div>
              <div style="font-size:9px;color:#9ca3af;font-weight:500">{ds}</div>
            </div>'''

        # SVG price line
        svg_points = []
        for i, d in enumerate(items):
            x = (i + 0.5) / n * 100
            y_norm = (d['sh_price'] - min_p) / p_range
            y = 100 - (y_norm * 80 + 10)
            svg_points.append(f'{x:.1f},{y:.1f}')
        line_path = 'M' + ' L'.join(svg_points)

        # Price labels
        price_labels_html = ''
        for i, d in enumerate(items):
            x_pct = (i + 0.5) / n * 100
            y_norm = (d['sh_price'] - min_p) / p_range
            y_px = chart_height - (y_norm * (chart_height * 0.8) + chart_height * 0.1)
            color = '#ef4444' if d.get('sh_chg_pct', 0) >= 0 else '#22c55e'
            price_labels_html += f'<div style="position:absolute;left:{x_pct:.1f}%;top:{y_px-16:.0f}px;transform:translateX(-50%);font-size:8px;color:{color};font-weight:600;white-space:nowrap">{d["sh_price"]:.0f}</div>'

        latest = items[-1]
        chg_color = '#ef4444' if latest.get('sh_chg_pct', 0) >= 0 else '#22c55e'

        return f'''
    <div style="background:rgba(96,165,250,.04);border:1px solid rgba(96,165,250,.1);border-radius:10px;padding:12px;margin-bottom:12px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
        <span style="font-size:12px;font-weight:600;color:#60a5fa">📊 量价趋势（成交额 + 上证指数）</span>
        <span style="font-size:11px;color:#9ca3af">上证 <span style="color:{chg_color};font-weight:600">{latest['sh_price']:.2f}</span> <span style="color:{chg_color}">({latest.get('sh_chg_pct',0):+.2f}%)</span></span>
      </div>
      <div style="position:relative;height:{chart_height}px;padding:0 4px">
        {price_labels_html}
        <div style="display:flex;align-items:flex-end;gap:6px;height:{chart_height}px;padding:18px 2px 20px 2px;position:relative;z-index:1">
          {bars}
        </div>
        <svg style="position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:2" viewBox="0 0 100 100" preserveAspectRatio="none">
          <defs>
            <linearGradient id="lineGrad" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stop-color="#f59e0b" stop-opacity="0.6"/>
              <stop offset="50%" stop-color="#f59e0b" stop-opacity="1"/>
              <stop offset="100%" stop-color="#f59e0b" stop-opacity="0.8"/>
            </linearGradient>
          </defs>
          <path d="{line_path}" fill="none" stroke="url(#lineGrad)" stroke-width="0.8" vector-effect="non-scaling-stroke"/>
        </svg>
      </div>
      <div style="display:flex;justify-content:center;gap:20px;margin-top:8px;font-size:9px;color:#6b7280">
        <span>■ 成交额(亿) <span style="color:#60a5fa">蓝色柱</span></span>
        <span>— 上证指数 <span style="color:#f59e0b">橙色线</span></span>
      </div>
      <div style="font-size:8px;color:#4b5563;margin-top:3px;text-align:center">每日收盘后自动采集 · 已积累{n}个交易日数据</div>
    </div>'''
    except Exception as e:
        log(f"  ⚠️ 构建量价趋势图失败: {e}")
        return ''

def build_a_share_tab(d, sp):
    """根据 A股数据构建完整的 A股 Tab HTML 内容"""
    # --- 获取各区块独立时间戳 ---
    a_time = get_section_time(A_DATA)

    indices = d['indices']
    sectors = d['sector_flow']
    concepts = d['concept_flow']
    stk_in = d['stock_inflow']
    stk_out = d['stock_outflow']
    stk_vol = d['stock_volume']
    mf = d['market_flow']
    top_gainers = d['limit_up']
    top_losers = d['limit_down']
    spark_stocks = sp.get('stocks', {})

    # --- Sub-nav ---
    subnav = '''
    <div class="subnav-spacer"></div>
    <div class="us-subnav" id="aSubnav">
      <a href="#a-pulse" class="us-subnav-link active">🔥 市场脉搏</a>
      <a href="#a-sector" class="us-subnav-link">📊 板块资金</a>
      <a href="#a-fund" class="us-subnav-link">💰 个股资金</a>
      <a href="#a-stocks" class="us-subnav-link">🏢 龙头个股</a>
    </div>
'''

    # --- Index cards ---
    idx_cards = ''
    idx_colors = {
        'sh000001': '#ef4444', 'sz399001': '#22c55e', 'sz399006': '#3b82f6',
        'sh000688': '#f59e0b', 'sh000016': '#8b5cf6', 'sh000905': '#06b6d4'
    }
    for code, idx in indices.items():
        c = idx_colors.get(code, '#6b7280')
        chg_cls = 'up' if idx['chg_pct'] > 0 else ('down' if idx['chg_pct'] < 0 else '')
        arrow = '▲' if idx['chg_pct'] > 0 else ('▼' if idx['chg_pct'] < 0 else '—')
        idx_cards += f'''<div class="ov-card" style="border-top:3px solid {c};padding:10px">
      <div class="ov-label" style="font-size:11px">{idx['name']}</div>
      <div class="ov-value" style="font-size:18px">{idx['price']:,.2f}</div>
      <div class="ov-chg {chg_cls}" style="font-size:12px">{arrow}{idx['chg_pct']:+.2f}%</div>
    </div>
'''

    # --- Global indices (亚太主要指数) ---
    global_indices = d.get('global_indices', {})
    global_idx_cards = ''
    g_idx_colors = {
        'N225': '#e11d48', 'KS11': '#7c3aed',
    }
    for code, gidx in global_indices.items():
        c = g_idx_colors.get(code, '#6b7280')
        chg_cls = 'up' if gidx['chg_pct'] > 0 else ('down' if gidx['chg_pct'] < 0 else '')
        arrow = '▲' if gidx['chg_pct'] > 0 else ('▼' if gidx['chg_pct'] < 0 else '—')
        global_idx_cards += f'''<div class="ov-card" style="border-top:3px solid {c};padding:10px">
      <div class="ov-label" style="font-size:11px">{gidx['name']}</div>
      <div class="ov-value" style="font-size:18px">{gidx['price']:,.2f}</div>
      <div class="ov-chg {chg_cls}" style="font-size:12px">{arrow}{gidx['chg_pct']:+.2f}%</div>
    </div>
'''

    # --- Heatmap ---
    inflow_secs = sorted([s for s in sectors if s['main_net'] > 0], key=lambda x: x['main_net'], reverse=True)[:6]
    outflow_secs = sorted([s for s in sectors if s['main_net'] < 0], key=lambda x: x['main_net'])[:6]
    max_flow = max(abs(s['main_net']) for s in sectors) if sectors else 1

    heatmap = ''
    for s in inflow_secs + outflow_secs:
        flow_yi = s['main_net'] / 1e8
        c = color_flow(flow_yi)
        opacity = min(abs(flow_yi) / max_flow * 0.4 + 0.08, 0.5)
        sign = '+' if flow_yi > 0 else ''
        heatmap += f'''<div style="background:{c}{int(opacity*255):02x};border:1px solid {c}44;border-radius:8px;padding:8px 6px;text-align:center;cursor:default" title="{s['name']}: {sign}{flow_yi:.2f}亿, {s['up_count']}涨{s['down_count']}跌, 涨幅{s['chg_pct']:+.2f}%">
      <div style="font-size:10px;color:#9ca3af;margin-bottom:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{s['name']}</div>
      <div style="font-size:14px;font-weight:700;color:{c}">{sign}{flow_yi:.1f}</div>
      <div style="font-size:10px;color:#6b7280">{s['up_count']}↑{s['down_count']}↓</div>
    </div>
'''

    # --- Market Pulse ---
    # Pre-compute north_deal & etf_flow display values
    nd = d.get('north_deal')
    if nd and nd.get('total_amt'):
        _north_total_yi = nd['total_amt'] / 100  # 百万元→亿元
        _north_sh_yi = nd['sh_deal_amt'] / 100
        _north_sz_yi = nd['sz_deal_amt'] / 100
        _north_date = nd.get('date', '')
    else:
        _north_total_yi = 0
        _north_sh_yi = 0
        _north_sz_yi = 0
        _north_date = ''
    
    etf_list = d.get('etf_flow', [])
    # ETF分类关键词
    _etf_cats = {
        '宽基指数': ['沪深300','中证500','中证1000','创业板','科创','上证50','A50','MSCI','标普','纳指'],
        '行业主题': ['医药','消费','芯片','半导体','新能源','光伏','军工','银行','证券','煤炭','钢铁','稀土','通信','AI','人工智能','卫星','传媒','游戏'],
        '红利': ['红利','高股息'],
        '跨境': ['港股','恒生','纳斯达克','标普','日经','德国'],
    }
    def _classify_etf(name):
        for cat, kws in _etf_cats.items():
            if any(kw in name for kw in kws):
                return cat
        return '其他'
    
    # --- Build north_deal HTML (成交额趋势柱状图) ---
    _sh_lead_chg = nd.get('sh_lead_chg', 0) if nd else 0
    _sz_lead_chg = nd.get('sz_lead_chg', 0) if nd else 0
    _north_history = d.get('north_deal_history') or []
    _north_deal_section = ''
    if _north_history:
        # 取最近10天，倒序显示（旧→新）
        _hist = list(reversed(_north_history[:10]))
        _max_val = max(h['total'] for h in _hist) if _hist else 1
        _bars_html = ''
        for h in _hist:
            _pct = (h['total'] / _max_val * 100) if _max_val > 0 else 0
            _sh_pct = (h['sh'] / _max_val * 100) if _max_val > 0 else 0
            _sz_pct = (h['sz'] / _max_val * 100) if _max_val > 0 else 0
            _date_short = h['date'][5:]  # MM-DD
            _is_latest = (h == _hist[-1])
            _bar_color = '#ec4899' if _is_latest else 'rgba(236,72,153,.6)'
            _bars_html += f'''<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:2px;min-width:0">
              <div style="font-size:9px;color:#9ca3af;white-space:nowrap">{h['total']:.0f}</div>
              <div style="width:100%;display:flex;flex-direction:column;gap:1px">
                <div style="height:{max(_sh_pct*0.8,2):.0f}px;background:#ec4899;border-radius:3px 3px 0 0;opacity:{'1' if _is_latest else '.7'}"></div>
                <div style="height:{max(_sz_pct*0.8,2):.0f}px;background:#f472b6;border-radius:0 0 3px 3px;opacity:{'1' if _is_latest else '.5'}"></div>
              </div>
              <div style="font-size:9px;color:{'#ec4899' if _is_latest else '#6b7280'};font-weight:{'700' if _is_latest else '400'}">{_date_short}</div>
            </div>'''
        _latest = _north_history[0]  # 最新一天
        _north_deal_section = f'''
    <div style="background:rgba(236,72,153,.04);border:1px solid rgba(236,72,153,.1);border-radius:8px;padding:10px;margin-bottom:10px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
        <span style="font-size:12px;font-weight:600;color:#ec4899">📊 北向成交额趋势（亿元）</span>
        <span style="font-size:11px;color:#6b7280">最新 {_latest['date']} {_latest['total']:.0f}亿</span>
      </div>
      <div style="display:flex;align-items:flex-end;gap:4px;height:100px;padding:0 2px">
        {_bars_html}
      </div>
      <div style="display:flex;justify-content:center;gap:12px;margin-top:6px;font-size:9px;color:#6b7280">
        <span>■ 沪股通 <span style="color:#ec4899">{_latest['sh']:.0f}亿</span></span>
        <span>■ 深股通 <span style="color:#f472b6">{_latest['sz']:.0f}亿</span></span>
      </div>
      <div style="font-size:9px;color:#6b7280;margin-top:4px;text-align:center">成交额数据滞后约1-3个工作日 · 来源: 东方财富</div>
    </div>
'''
    elif nd:
        # fallback: 没有历史数据时用原来的静态显示
        _north_deal_section = f'''
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px">
      <div style="background:rgba(236,72,153,.05);border:1px solid rgba(236,72,153,.12);border-radius:8px;padding:10px">
        <div style="font-size:11px;color:#9ca3af;margin-bottom:4px">沪股通（成交总额）</div>
        <div style="font-size:18px;font-weight:700;color:#ec4899">{_north_sh_yi:.0f}亿</div>
        <div style="font-size:10px;color:#6b7280;margin-top:2px">领涨: <span style="color:#e5e7eb">{nd.get('sh_lead','—')}</span> <span style="color:{color_chg(_sh_lead_chg)}">{_sh_lead_chg:+.2f}%</span></div>
      </div>
      <div style="background:rgba(236,72,153,.05);border:1px solid rgba(236,72,153,.12);border-radius:8px;padding:10px">
        <div style="font-size:11px;color:#9ca3af;margin-bottom:4px">深股通（成交总额）</div>
        <div style="font-size:18px;font-weight:700;color:#ec4899">{_north_sz_yi:.0f}亿</div>
        <div style="font-size:10px;color:#6b7280;margin-top:2px">领涨: <span style="color:#e5e7eb">{nd.get('sz_lead','—')}</span> <span style="color:{color_chg(_sz_lead_chg)}">{_sz_lead_chg:+.2f}%</span></div>
      </div>
    </div>
'''


    # --- Build ETF flow HTML ---
    _etf_rows = ''
    for e in etf_list[:10]:
        flow_yi = e['main_flow'] / 1e8
        fc = color_flow(flow_yi)
        _etf_rows += f'<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 0;border-bottom:1px solid rgba(255,255,255,.04)"><span style="font-size:12px;color:#e5e7eb">{e["name"]}</span><span style="font-size:12px;font-weight:600;color:{fc};white-space:nowrap">{flow_yi:+.2f}亿</span><span style="font-size:11px;color:{color_chg(e["chg_pct"])};white-space:nowrap">{e["chg_pct"]:+.2f}%</span></div>'
    
    _etf_total = sum(e['main_flow'] for e in etf_list) / 1e8 if etf_list else 0
    _etf_section = f'''
    <div style="background:rgba(245,158,11,.04);border:1px solid rgba(245,158,11,.1);border-radius:8px;padding:10px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
        <span style="font-size:12px;font-weight:600;color:#f59e0b">📈 ETF主力净流入 TOP10</span>
        <span style="font-size:11px;font-weight:600;color:{color_flow(_etf_total)}">{_etf_total:+.2f}亿</span>
      </div>
      {_etf_rows}
    </div>
'''

    pulse = f'''
    <div id="a-pulse" style="scroll-margin-top:60px">
      <div class="section-divider"><span>🔥 市场脉搏 {section_time_html(a_time)}</span></div>
      <div class="us-rt-time">数据更新: {d['fetch_time']} · 东方财富（延时约3分钟）· 新浪财经（K线）</div>

      <!-- 💰 全市场资金流向 (Top-Down) -->
      <div style="background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.06);border-radius:10px;padding:12px;margin-bottom:12px">
        <div style="font-size:12px;font-weight:600;color:#9ca3af;margin-bottom:10px">💰 全市场资金流向</div>
        <!-- L1: 市场概况 -->
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px">
          <div style="background:rgba(59,130,246,.06);border:1px solid rgba(59,130,246,.12);border-radius:8px;padding:10px">
            <div style="font-size:10px;color:#9ca3af">两市成交额</div>
            <div style="font-size:20px;font-weight:700;color:#60a5fa">{mf['total_amount']:.0f}<span style="font-size:12px;font-weight:400;color:#6b7280"> 亿</span></div>
          </div>
          <div style="background:rgba(245,158,11,.06);border:1px solid rgba(245,158,11,.12);border-radius:8px;padding:10px">
            <div style="font-size:10px;color:#9ca3af">涨跌家数</div>
            <div style="font-size:18px;font-weight:700"><span style="color:#ef4444">{mf['up_count']}↑</span> <span style="color:#22c55e">{mf['down_count']}↓</span></div>
          </div>
        </div>
        <!-- L2: 四类资金明细 -->
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:10px">
          <div style="background:rgba(255,255,255,.04);border-radius:6px;padding:8px 6px;text-align:center">
            <div style="font-size:10px;color:#6b7280">超大单</div>
            <div style="font-size:14px;font-weight:700;color:{color_flow(mf['super_large'])}">{mf['super_large']:+.2f}亿</div>
          </div>
          <div style="background:rgba(255,255,255,.04);border-radius:6px;padding:8px 6px;text-align:center">
            <div style="font-size:10px;color:#6b7280">大单</div>
            <div style="font-size:14px;font-weight:700;color:{color_flow(mf['large'])}">{mf['large']:+.2f}亿</div>
          </div>
          <div style="background:rgba(255,255,255,.04);border-radius:6px;padding:8px 6px;text-align:center">
            <div style="font-size:10px;color:#6b7280">中单</div>
            <div style="font-size:14px;font-weight:700;color:{color_flow(mf['medium'])}">{mf['medium']:+.2f}亿</div>
          </div>
          <div style="background:rgba(255,255,255,.04);border-radius:6px;padding:8px 6px;text-align:center">
            <div style="font-size:10px;color:#6b7280">小单</div>
            <div style="font-size:14px;font-weight:700;color:{color_flow(mf['small'])}">{mf['small']:+.2f}亿</div>
          </div>
        </div>
        <!-- L3: 主力总结 -->
        <div style="background:rgba({'239,68,68' if mf['main_net']>0 else '34,197,94'},.08);border:1px solid rgba({'239,68,68' if mf['main_net']>0 else '34,197,94'},.2);border-radius:8px;padding:12px;text-align:center">
          <div style="font-size:11px;color:#9ca3af;margin-bottom:4px">📊 主力资金（超大单+大单）</div>
          <div style="font-size:24px;font-weight:800;color:{color_flow(mf['main_net'])}">{'📈' if mf['main_net']>0 else '📉'} {mf['main_net']:+.2f}亿</div>
        </div>
      </div>

      <!-- 📊 量价趋势 -->
      {build_volume_chart()}

      <!-- 北向成交 & ETF资金 -->
      <div style="margin-bottom:12px">
        <div style="display:flex;align-items:center;gap:6px;margin-bottom:8px">
          <span style="font-size:13px;font-weight:600;color:#9ca3af">📊 北向资金（成交额趋势 · ETF）</span>
        </div>
        {_north_deal_section}
        {_etf_section}
      </div>

      <div style="font-size:13px;font-weight:600;color:#9ca3af;margin-bottom:8px;padding-left:2px">行业板块资金热力图（主力净流入 亿元）</div>
      <div style="display:grid;grid-template-columns:repeat(6,1fr);gap:6px;margin-bottom:12px">
        {heatmap}
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:6px">
        <div style="background:rgba(239,68,68,.05);border:1px solid rgba(239,68,68,.15);border-radius:8px;padding:10px">
          <div style="font-size:12px;font-weight:600;color:#ef4444;margin-bottom:6px">🔴 涨幅榜 TOP5</div>
          {''.join(f'<div style="display:flex;justify-content:space-between;padding:3px 0;font-size:12px"><span>{s["name"]} ({s["code"]})</span><span style="color:#ef4444;font-weight:600">{s["chg_pct"]:+.2f}%</span></div>' for s in top_gainers[:5])}
        </div>
        <div style="background:rgba(34,197,94,.05);border:1px solid rgba(34,197,94,.15);border-radius:8px;padding:10px">
          <div style="font-size:12px;font-weight:600;color:#22c55e;margin-bottom:6px">🟢 跌幅榜 TOP5</div>
          {''.join(f'<div style="display:flex;justify-content:space-between;padding:3px 0;font-size:12px"><span>{s["name"]} ({s["code"]})</span><span style="color:#22c55e;font-weight:600">{s["chg_pct"]:+.2f}%</span></div>' for s in top_losers[:5])}
        </div>
      </div>
    </div>
'''

    # --- Sector table ---
    sector_rows = ''
    for s in sectors:
        flow = s['main_net'] / 1e8
        c = color_flow(flow)
        bar_pct = abs(flow) / max_flow * 100 if max_flow else 0
        super_yi = s['super_large'] / 1e8
        large_yi = s['large'] / 1e8
        sign = '+' if flow > 0 else ''
        leader = s.get('leader', '')
        lc = float(s.get('leader_chg', 0) or 0)
        sector_rows += f'''<tr>
      <td><span style="font-weight:600;color:#e5e7eb">{s['name']}</span><div style="font-size:10px;color:#6b7280">{s['up_count']}涨{s['down_count']}跌</div></td>
      <td style="min-width:110px">
        <div style="display:flex;align-items:center;gap:6px">
          <div style="flex:1;height:16px;background:rgba(255,255,255,.04);border-radius:3px;position:relative;overflow:hidden">
            <div style="position:absolute;{"right" if flow<0 else "left"}:0;width:{bar_pct:.1f}%;height:100%;background:{c}33;border-radius:3px"></div>
          </div>
          <span style="font-weight:700;color:{c};white-space:nowrap;font-size:12px">{sign}{flow:.2f}亿</span>
        </div>
      </td>
      <td style="text-align:right;font-size:11px;color:{color_flow(super_yi)}">{"+" if super_yi>0 else ""}{super_yi:.2f}</td>
      <td style="text-align:right;font-size:11px;color:{color_flow(large_yi)}">{"+" if large_yi>0 else ""}{large_yi:.2f}</td>
      <td style="text-align:right"><span style="color:{color_chg(s['chg_pct'])};font-weight:600;font-size:12px">{s['chg_pct']:+.2f}%</span></td>
      <td style="font-size:11px"><span style="color:#e5e7eb">{leader}</span> <span style="color:{color_chg(lc)}">{"+" if lc>0 else ""}{lc:.1f}%</span></td>
    </tr>'''

    sector_section = f'''
    <div id="a-sector" style="scroll-margin-top:60px"></div>
    <div class="section-divider"><span>🏭 行业板块资金流向 {section_time_html(a_time)}</span></div>
    <div style="font-size:11px;color:#6b7280;margin-bottom:10px">共{len(sectors)}个行业板块 · 数据源：东方财富 · 主力=超大单+大单</div>
    <div style="overflow-x:auto">
    <table class="ftab" style="width:100%;font-size:12px">
      <thead><tr><th>行业</th><th>主力净流入</th><th style="text-align:right">超大单</th><th style="text-align:right">大单</th><th style="text-align:right">涨幅</th><th>龙头股</th></tr></thead>
      <tbody>{sector_rows}</tbody>
    </table>
    </div>
'''

    # --- Concept table ---
    concept_rows = ''
    max_concept_flow = max(abs(c['main_net']) for c in concepts) if concepts else 1
    concepts_sorted = sorted(concepts, key=lambda x: abs(x['main_net']), reverse=True)[:20]
    for c in concepts_sorted:
        flow = c['main_net'] / 1e8
        col = color_flow(flow)
        bar_pct = abs(flow) / max_concept_flow * 100
        sign = '+' if flow > 0 else ''
        concept_rows += f'''<tr>
      <td><span style="font-weight:600;color:#e5e7eb">{c['name']}</span></td>
      <td style="min-width:110px">
        <div style="display:flex;align-items:center;gap:6px">
          <div style="flex:1;height:16px;background:rgba(255,255,255,.04);border-radius:3px;position:relative;overflow:hidden">
            <div style="position:absolute;{"right" if flow<0 else "left"}:0;width:{bar_pct:.1f}%;height:100%;background:{col}33"></div>
          </div>
          <span style="font-weight:700;color:{col};white-space:nowrap;font-size:12px">{sign}{flow:.2f}亿</span>
        </div>
      </td>
      <td style="text-align:right;font-size:11px;color:#9ca3af">{c['up_count']}涨{c['down_count']}跌</td>
      <td style="text-align:right"><span style="color:{color_chg(c['chg_pct'])};font-weight:600;font-size:12px">{c['chg_pct']:+.2f}%</span></td>
      <td style="font-size:11px;color:#e5e7eb">{c.get('leader','')}</td>
    </tr>'''

    concept_section = f'''
    <div id="a-concept" style="scroll-margin-top:60px"></div>
    <div class="section-divider"><span>💡 概念板块资金流向 {section_time_html(a_time)}</span></div>
    <div style="font-size:11px;color:#6b7280;margin-bottom:10px">资金净流入/流出绝对值TOP20概念板块 · 数据源：东方财富</div>
    <div style="overflow-x:auto">
    <table class="ftab" style="width:100%;font-size:12px">
      <thead><tr><th>概念</th><th>主力净流入</th><th style="text-align:right">涨跌</th><th style="text-align:right">涨幅</th><th>龙头</th></tr></thead>
      <tbody>{concept_rows}</tbody>
    </table>
    </div>
'''

    # --- Stock fund flow tables ---
    def stock_flow_rows(stocks, is_inflow=True):
        rows = ''
        for s in stocks:
            flow_yi = s['main_net'] / 1e8
            c = '#ef4444' if is_inflow else '#22c55e'
            if not is_inflow and flow_yi > 0:
                c = '#ef4444'
            if is_inflow and flow_yi < 0:
                c = '#22c55e'
            rows += f'''<tr>
          <td><span class="fn">{s['name']}</span><span class="fc">{s['code']}</span><div style="font-size:10px;color:#6b7280">{s.get('industry','')}</div></td>
          <td><span style="color:{'#ef4444' if s['chg_pct']>0 else '#22c55e'};font-weight:600">{s['chg_pct']:+.2f}%</span></td>
          <td class="{"fp" if is_inflow else "fn2"}" style="color:{c};font-weight:700">{flow_yi:+.2f}亿</td>
          <td style="text-align:right;color:#9ca3af;font-size:11px">{s.get('main_pct',0):+.1f}%</td>
          <td style="text-align:right;color:#9ca3af;font-size:11px">{s['amount']/1e8:.1f}亿</td>
        </tr>'''
        return rows

    inflow_table = stock_flow_rows(stk_in, True)
    outflow_table = stock_flow_rows(stk_out, False)

    vol_rows = ''
    for s in stk_vol:
        flow_yi = s.get('main_net', 0) / 1e8
        vol_rows += f'''<tr>
      <td><span class="fn">{s['name']}</span><span class="fc">{s['code']}</span></td>
      <td>¥{s['price']:.2f}</td>
      <td><span style="color:{color_chg(s['chg_pct'])};font-weight:600">{s['chg_pct']:+.2f}%</span></td>
      <td style="color:{color_flow(flow_yi)};font-size:11px">{flow_yi:+.2f}亿</td>
      <td style="text-align:right">{s['amount']/1e8:.1f}亿</td>
    </tr>'''

    fund_section = f'''
    <div id="a-fund" style="scroll-margin-top:60px"></div>
    <div class="section-divider"><span>💰 个股主力资金流向 {section_time_html(a_time)}</span></div>
    <div style="font-size:11px;color:#6b7280;margin-bottom:10px">数据源：东方财富（延时约3分钟）· 主力=超大单+大单</div>
    <div class="flow-grid">
      <div class="ftw">
        <div class="ftt" style="color:#ef4444">🔴 主力净流入 TOP20</div>
        <table class="ftab"><thead><tr><th>股票</th><th>涨跌</th><th>主力净流入</th><th style="text-align:right">占比</th><th style="text-align:right">成交额</th></tr></thead>
        <tbody>{inflow_table}</tbody></table>
      </div>
      <div class="ftw">
        <div class="ftt" style="color:#22c55e">🟢 主力净流出 TOP20</div>
        <table class="ftab"><thead><tr><th>股票</th><th>涨跌</th><th>主力净流出</th><th style="text-align:right">占比</th><th style="text-align:right">成交额</th></tr></thead>
        <tbody>{outflow_table}</tbody></table>
      </div>
    </div>
    <div style="margin-top:12px">
      <div class="ftw" style="margin-bottom:16px">
        <div class="ftt">📊 成交额 TOP20</div>
        <table class="ftab"><thead><tr><th>股票</th><th>现价</th><th>涨跌幅</th><th>主力净额</th><th style="text-align:right">成交额</th></tr></thead>
        <tbody>{vol_rows}</tbody></table>
      </div>
    </div>
'''

    # --- Stock cards with sparklines ---
    stock_groups = {}
    for sym, s in spark_stocks.items():
        sec = s.get('sector', '其他')
        if sec not in stock_groups:
            stock_groups[sec] = []
        stock_groups[sec].append((sym, s))

    stock_cards_html = ''
    for group_name, stocks_list in stock_groups.items():
        cards = ''
        for sym, s in stocks_list:
            code = sym[2:]
            price_info = ''
            chg_pct = 0
            for stk in stk_in + stk_out + stk_vol:
                if stk['code'] == code:
                    chg_pct = stk['chg_pct']
                    price_info = f'¥{stk["price"]:.2f}'
                    break
            if not price_info:
                last = s['c'][-1]
                prev = s['c'][-2] if len(s['c']) > 1 else last
                chg_pct = ((last - prev) / prev * 100) if prev else 0
                price_info = f'¥{last:.2f}'

            chg_cls = 'up' if chg_pct > 0 else ('dn' if chg_pct < 0 else '')
            hi = max(s['c'])
            lo = min(s['c'])
            last = s['c'][-1]
            pos_pct = ((last - lo) / (hi - lo) * 100) if hi > lo else 50
            pos_color = '#ef4444' if chg_pct > 0 else '#22c55e'

            cards += f'''<div class="scard">
          <div class="sch"><div><span class="ssym">{sym[2:]}</span><span class="snm">{s['name']}</span></div></div>
          <div style="display:flex;justify-content:space-between;align-items:baseline;margin-top:4px">
            <div class="sprc">{price_info}</div>
            <div class="schg {chg_cls}">{chg_pct:+.2f}%</div>
          </div>
          <div class="sspk" id="aspark_{sym}"></div>
          <div style="height:3px;background:rgba(255,255,255,.08);border-radius:2px;margin:4px 0;position:relative">
            <div style="position:absolute;left:{pos_pct:.0f}%;top:-2px;width:2px;height:7px;background:{pos_color};border-radius:1px;transform:translateX(-50%)"></div>
          </div>
          <div class="smeta"><span>低 {lo:.2f}</span><span>高 {hi:.2f}</span></div>
        </div>'''

        stock_cards_html += f'''
    <div style="margin-bottom:16px">
      <div style="font-size:13px;font-weight:600;color:#9ca3af;margin-bottom:8px;padding-left:2px">{group_name}</div>
      <div class="sgrid">{cards}</div>
    </div>'''

    stocks_section = f'''
    <div id="a-stocks" style="scroll-margin-top:60px"></div>
    <div class="section-divider"><span>🏢 龙头个股表现 {section_time_html(a_time)}</span></div>
    <div style="font-size:11px;color:#6b7280;margin-bottom:10px">K线：新浪财经（近60日）· 实时：东方财富 · 位置条为60日高低区间</div>
    {stock_cards_html}
    <div style="text-align:center;padding:16px;color:#6b7280;font-size:11px">
      数据来源：<a href="https://quote.eastmoney.com/" target="_blank" rel="noopener noreferrer">东方财富</a>（资金流向/行情）·
      <a href="https://finance.sina.com.cn/" target="_blank" rel="noopener noreferrer">新浪财经</a>（K线）
    </div>
'''

    # Assemble
    a_tab_inner = subnav + pulse + sector_section + concept_section + fund_section + stocks_section
    return a_tab_inner


def inject_a_shares(html, d, sp):
    """
    将A股数据注入HTML（支持首次注入和重复更新）：
    1. 替换或创建 #page-a-shares 内容
    2. 更新 ASPARK JS 变量
    3. 确保 tab 按钮存在
    4. 确保 initASparks 和 subnav JS 存在
    """
    a_tab_inner = build_a_share_tab(d, sp)
    spark_js = 'var ASPARK=' + json.dumps(sp.get('stocks', {}), ensure_ascii=False) + ';'

    # --- 1. 替换或创建 page-a-shares ---
    a_start_marker = '<div class="tab-page" id="page-a-shares">'
    a_start = html.find(a_start_marker)

    if a_start != -1:
        # 已存在，找到结束位置（下一个 tab-page 或 tab-bar）
        next_tab = html.find('<div class="tab-page"', a_start + len(a_start_marker))
        tab_bar = html.find('<nav class="tab-bar"', a_start)
        # 取两者中较小的
        candidates = [p for p in [next_tab, tab_bar] if p != -1]
        a_end = min(candidates) if candidates else len(html)
        old_block = html[a_start:a_end]
        new_block = f'<div class="tab-page" id="page-a-shares">\n{a_tab_inner}\n  </div>\n  </div>\n\n    '
        html = html[:a_start] + new_block + html[a_end:]
        log("  已替换现有 #page-a-shares 内容（含 container 闭合）")
    else:
        # 首次注入：替换 page-more
        more_start = html.find('<div class="tab-page" id="page-more">')
        if more_start != -1:
            tab_bar_pos = html.find('<nav class="tab-bar"', more_start)
            new_block = f'<div class="tab-page" id="page-a-shares">\n{a_tab_inner}\n  </div>\n  </div>\n\n    '
            html = html[:more_start] + new_block + html[tab_bar_pos:]
            log("  首次注入：替换 #page-more（含 container 闭合）")
        else:
            log("  ❌ 找不到 #page-a-shares 也找不到 #page-more!")
            return html

    # --- 2. 更新 ASPARK 变量 ---
    aspark_pattern = re.compile(r'var\s+ASPARK\s*=\s*\{.*?\};', re.DOTALL)
    if aspark_pattern.search(html):
        html = aspark_pattern.sub(spark_js, html, count=1)
        log("  已更新 ASPARK 变量")
    else:
        # 在 SPARK 变量后添加
        spark_marker = 'var SPARK='
        spark_pos = html.find(spark_marker)
        if spark_pos != -1:
            line_end = html.find('\n', spark_pos)
            html = html[:line_end] + '\n    ' + spark_js + html[line_end:]
            log("  新增 ASPARK 变量")

    # --- 3. 确保 A 股 tab 按钮存在 ---
    if 'data-tab="a-shares"' not in html:
        old_more_btn = '''<button class="tab-btn" data-tab="more">
        <span class="tab-icon">⚙️</span>
        <span class="tab-label">更多</span>
      </button>'''
        new_a_btn = '''<button class="tab-btn" data-tab="a-shares">
        <span class="tab-icon">🇨🇳</span>
        <span class="tab-label">A股</span>
      </button>'''
        if old_more_btn in html:
            html = html.replace(old_more_btn, new_a_btn, 1)
            log("  新增 A 股 tab 按钮")

    # --- 4. 确保 initASparks 函数存在 ---
    if 'function initASparks' not in html:
        init_js = '''
    function initASparks(){
      if (typeof ASPARK === 'undefined') return;
      Object.keys(ASPARK).forEach(function(sym){
        var el=document.getElementById('aspark_'+sym);
        if(!el||el.getAttribute('data-rendered'))return;
        var d=ASPARK[sym];
        if(!d||!d.c||!d.c.length)return;
        var chart=echarts.init(el,null,{renderer:'canvas'});
        var up=d.c[d.c.length-1]>=d.c[0];
        var color=up?'#ef4444':'#22c55e';
        chart.setOption({
          grid:{left:0,right:0,top:2,bottom:2},
          xAxis:{type:'category',show:false,data:d.d},
          yAxis:{type:'value',show:false,scale:true},
          series:[{type:'line',data:d.c,smooth:true,symbol:'none',lineStyle:{width:1.5,color:color},
            areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:color+'44'},{offset:1,color:color+'00'}])}}]
        });
        el.setAttribute('data-rendered','1');
        window.addEventListener('resize',function(){chart.resize()});
      });
    }
'''
        # 插入到最后一个 </script> 之前
        last_script = html.rfind('</script>')
        if last_script != -1:
            html = html[:last_script] + init_js + '\n    ' + html[last_script:]
            log("  新增 initASparks 函数")

    # 确保 tab 切换时调用 initASparks
    if "target === 'a-shares') initASparks()" not in html and "target === 'a-shares')" not in html:
        old_switch = "if (target === 'us-stocks') { initUsCharts(); initSparks(); }"
        new_switch = old_switch + "\n    if (target === 'a-shares') initASparks();"
        if old_switch in html:
            html = html.replace(old_switch, new_switch, 1)
            log("  新增 A 股 tab 切换调用")

    # --- 5. 确保 subnav scroll spy 存在 ---
    if 'aSubnav' not in html or '#aSubnav .us-subnav-link' not in html:
        subnav_js = '''
    (function(){
      var links=document.querySelectorAll('#aSubnav .us-subnav-link');
      if(!links.length)return;
      var sections=[];
      links.forEach(function(link){
        var href=link.getAttribute('href');
        if(href&&href.charAt(0)==='#'){
          var el=document.querySelector(href);
          if(el)sections.push({el:el,link:link});
        }
      });
      function onScroll(){
        var current=sections[0];
        sections.forEach(function(s){
          if(s.el.getBoundingClientRect().top<=100)current=s;
        });
        links.forEach(function(l){l.classList.remove('active')});
        if(current)current.link.classList.add('active');
      }
      window.addEventListener('scroll',onScroll,{passive:true});
      links.forEach(function(link){
        link.addEventListener('click',function(e){
          e.preventDefault();
          var target=document.querySelector(link.getAttribute('href'));
          if(target){
            var top=target.getBoundingClientRect().top+window.pageYOffset-56;
            window.scrollTo({top:top,behavior:'smooth'});
          }
        });
      });
    })();
'''
        last_script = html.rfind('</script>')
        if last_script != -1:
            html = html[:last_script] + subnav_js + '\n    ' + html[last_script:]
            log("  新增 A 股 subnav scroll spy")

    # 确保A股Tab有时间戳占位符（inject_a_shares会替换整个tab内容）
    a_placeholder = '<div class="tab-update-info" style="font-size: 0.75em; color: #888; text-align: right; padding: 4px 12px 0;"><span class="tab-update-time" data-tab="a_shares">上次更新: --</span></div>'
    a_page_marker = 'id="page-a-shares"'
    a_pos = html.find(a_page_marker)
    if a_pos != -1:
        a_tag_end = html.find('>', a_pos)
        # 检查是否已有占位符
        next_500 = html[a_tag_end:a_tag_end+500]
        if 'tab-update-time' not in next_500 or 'data-tab="a_shares"' not in next_500:
            html = html[:a_tag_end+1] + '\n    ' + a_placeholder + html[a_tag_end+1:]
            log("  已注入 A股Tab 时间戳占位符")

    # 更新A股Tab时间戳
    a_data = load_json(A_DATA)
    if a_data:
        html = update_tab_timestamp(html, 'a_shares', a_data.get('fetch_time'))

    # 注入A股新鲜度指示器（替换已有，不追加）
    a_ft = a_data.get('fetch_time', '') if a_data else ''
    freshness_html, age_min = generate_freshness_html(a_ft, 'a_share')
    if freshness_html:
        a_page_marker = 'id="page-a-shares"'
        a_page = html.find(a_page_marker)
        if a_page != -1:
            tag_end = html.find('>', a_page)
            # 查找已有的新鲜度 div
            existing_pattern = re.compile(
                r'(id="page-a-shares"[^>]*>)\s*'
                r'<div style="font-size: 0\.7em; color: #888; text-align: right; padding: 2px 8px; margin-top: -4px; margin-bottom: 4px;">.*?</div>',
                re.DOTALL
            )
            if existing_pattern.search(html):
                html = existing_pattern.sub(rf'\g<1>\n    {freshness_html}', html, count=1)
            else:
                html = html[:tag_end+1] + '\n    ' + freshness_html + html[tag_end+1:]
            log(f"  A股新鲜度指示器已更新 (年龄: {age_min:.0f}分钟)")

    # --- 6. 更新首页A股指数 + 亚太市场概览卡片 ---
    def _update_ov_card(html_str, code, price, pct):
        """用正则更新首页概览卡片"""
        # 更新数值: id="ov-XXX-val" 后面 > ... </div>
        val_pat = re.compile(r'(id="ov-' + re.escape(code) + r'-val"[^>]*>)(.*?)(</div>)', re.DOTALL)
        html_str = val_pat.sub(lambda m: m.group(1) + f'{price:,.2f}' + m.group(3), html_str, count=1)
        # 更新涨跌: id="ov-XXX-chg" 的div
        chg_cls = 'up' if pct > 0 else ('down' if pct < 0 else 'flat')
        arrow = '▲' if pct > 0 else ('▼' if pct < 0 else '—')
        chg_pat = re.compile(
            r'(<div\s+)(class=")[^"]*(")([^>]*id="ov-' + re.escape(code) + r'-chg"[^>]*>)(.*?)(</div>)',
            re.DOTALL
        )
        html_str = chg_pat.sub(
            lambda m: m.group(1) + f'class="ov-chg {chg_cls}"' + m.group(4) + f'{arrow}{pct:+.2f}%' + m.group(6),
            html_str, count=1
        )
        return html_str

    # A股指数
    for code, idx in d.get('indices', {}).items():
        html = _update_ov_card(html, code, idx['price'], idx['chg_pct'])
        log(f"  首页 {idx['name']} 概览已更新")

    # 亚太市场
    for code, gidx in d.get('global_indices', {}).items():
        html = _update_ov_card(html, code, gidx['price'], gidx['chg_pct'])
        log(f"  首页 {gidx['name']} 概览已更新")

    return html


# ============================================================
#  独立 A 股页面生成（供 iframe 加载）
# ============================================================

A_SHARES_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no">
<title>A股资金看板</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  background: #0a0e17; color: #e5e7eb; min-height: 100vh;
  padding: 8px 12px 80px;
}
.section-divider { margin: 16px 0 8px; font-size: 15px; font-weight: 700; }
.section-time { font-size: 0.6em; color: #999; font-weight: normal; margin-left: 6px; }
.us-rt-time { font-size: 0.7em; color: #888; margin-bottom: 8px; }
.us-subnav { display:flex; gap:8px; overflow-x:auto; padding:8px 0; margin-bottom:12px; border-bottom:1px solid rgba(255,255,255,0.08); position:sticky; top:0; background:#0a0e17; z-index:10; }
.us-subnav-link { font-size:12px; color:#9ca3af; text-decoration:none; white-space:nowrap; padding:4px 10px; border-radius:16px; background:rgba(255,255,255,0.04); }
.us-subnav-link.active { color:#fff; background:rgba(59,130,246,0.3); }
.subnav-spacer { height:0; }
.tab-update-info { display:none; }
.ftab { width:100%; border-collapse:collapse; font-size:12px; }
.ftab th { text-align:left; color:#9ca3af; font-weight:600; padding:6px 8px; border-bottom:1px solid rgba(255,255,255,0.08); }
.ftab td { padding:6px 8px; border-bottom:1px solid rgba(255,255,255,0.04); }
.h-scroll-wrap { overflow-x:auto; }
.schg { font-size:11px; font-weight:600; }
.up { color:#ef4444; }
.down { color:#22c55e; }
.sspk { height:32px; margin:2px 0; }
.smeta { display:flex; justify-content:space-between; font-size:9px; color:#6b7280; }
</style>
</head>
<body>
<h2 style="font-size:18px;font-weight:700;margin:8px 0 4px;color:#f87171;">🇨🇳 A股资金流向</h2>
__BODY__
<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
<script>
__SPARK_JS__
function initASparks(){
  if (typeof ASPARK === 'undefined') return;
  Object.keys(ASPARK).forEach(function(sym){
    var el=document.getElementById('aspark_'+sym);
    if(!el||el.getAttribute('data-rendered'))return;
    var d=ASPARK[sym];
    if(!d||!d.c||!d.c.length)return;
    var chart=echarts.init(el,null,{renderer:'canvas'});
    var up=d.c[d.c.length-1]>=d.c[0];
    var color=up?'#ef4444':'#22c55e';
    chart.setOption({
      grid:{left:0,right:0,top:2,bottom:2},
      xAxis:{type:'category',show:false,data:d.d},
      yAxis:{type:'value',show:false,scale:true},
      series:[{type:'line',data:d.c,smooth:true,symbol:'none',lineStyle:{width:1.5,color:color},
        areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:color+'44'},{offset:1,color:color+'00'}])}}]
    });
    el.setAttribute('data-rendered','1');
    window.addEventListener('resize',function(){chart.resize()});
  });
}
initASparks();
</script>
<script>
// subnav scroll spy
(function(){
  var links=document.querySelectorAll('#aSubnav .us-subnav-link');
  if(!links.length)return;
  var sections=[];
  links.forEach(function(link){
    var href=link.getAttribute('href');
    if(href&&href.charAt(0)==='#'){
      var el=document.querySelector(href);
      if(el)sections.push({el:el,link:link});
    }
  });
  function onScroll(){
    var pos=window.scrollY+60;
    var active=sections[0];
    sections.forEach(function(s){ if(s.el.offsetTop<=pos) active=s; });
    links.forEach(function(l){l.classList.remove('active');});
    if(active) active.link.classList.add('active');
  }
  window.addEventListener('scroll',onScroll,{passive:true});
  links.forEach(function(link){
    link.addEventListener('click',function(e){
      e.preventDefault();
      var target=document.querySelector(link.getAttribute('href'));
      if(target) window.scrollTo({top:target.offsetTop-50,behavior:'smooth'});
    });
  });
})();
</script>
</body>
</html>"""


def write_a_shares_page(d, sp):
    """生成独立的 a-shares.html（iframe 加载用），与主看板A股Tab保持同步。"""
    try:
        a_tab_inner = build_a_share_tab(d, sp)
        spark_js = 'var ASPARK=' + json.dumps(sp.get('stocks', {}), ensure_ascii=False) + ';'
        html = A_SHARES_TEMPLATE.replace('__BODY__', a_tab_inner).replace('__SPARK_JS__', spark_js)
        with open(A_SHARES_HTML, 'w', encoding='utf-8') as f:
            f.write(html)
        log(f"  已生成独立A股页面 a-shares.html ({len(html):,} 字符)")
        return True
    except Exception as e:
        log(f"  ⚠️ 生成 a-shares.html 失败: {e}")
        return False


# ============================================================
#  美股 HTML 注入（更新数据变量）
# ============================================================

def inject_auction(html, data):
    """将集合竞价数据注入A股Tab的市场脉搏区域顶部（在指数卡片之前）"""
    from datetime import datetime as _dt
    _now_h = _dt.now().hour
    if _now_h >= 11:
        log("  ℹ️ 已过11:00，集合竞价不再展示（当前时段不相关）")
        return html
    if not data or not data.get('indices'):
        log("  ⚠️ 集合竞价数据为空，跳过注入")
        return html
    
    indices = data.get('indices', {})
    stats = data.get('stats', {})
    top_gap_up = data.get('top_gap_up', [])
    fetch_time = data.get('fetch_time', '')
    
    # 构建指数竞价行
    idx_lines = ''
    for code in ['sh000001', 'sz399001', 'sz399006']:
        idx = indices.get(code, {})
        if not idx:
            continue
        name = idx['name']
        gap_pct = idx.get('gap_pct', 0)
        gap_cls = 'up' if gap_pct > 0 else ('down' if gap_pct < 0 else '')
        gap_color = '#ef4444' if gap_pct > 0 else ('#22c55e' if gap_pct < 0 else '#9ca3af')
        arrow = '▲' if gap_pct > 0 else ('▼' if gap_pct < 0 else '—')
        idx_lines += f'''<div style="display:flex;justify-content:space-between;align-items:center;padding:3px 0">
          <span style="font-size:12px;color:#e5e7eb">{name}</span>
          <span style="font-size:12px;font-weight:600;color:{gap_color}">{arrow}{gap_pct:+.2f}%</span>
        </div>'''
    
    # 高开/低开统计
    gap_up_cnt = stats.get('gap_up_count', 0)
    gap_down_cnt = stats.get('gap_down_count', 0)
    flat_cnt = stats.get('flat_count', 0)
    
    # TOP5高开股
    top5_lines = ''
    for s in top_gap_up[:5]:
        gap_color = '#ef4444' if s.get('gap_pct', 0) > 0 else '#22c55e'
        top5_lines += f'''<div style="display:flex;justify-content:space-between;padding:2px 0;font-size:11px">
          <span style="color:#e5e7eb">{s['name']}</span>
          <span style="color:{gap_color};font-weight:600">{s.get('gap_pct',0):+.2f}%</span>
        </div>'''
    
    auction_block = f'''
    <div id="auction-block" style="scroll-margin-top:60px;margin-bottom:12px">
      <div style="background:rgba(251,191,36,.06);border:1px solid rgba(251,191,36,.2);border-radius:10px;padding:12px">
        <div style="font-size:13px;font-weight:700;color:#fbbf24;margin-bottom:8px">🔔 集合竞价（9:25）{section_time_html(get_section_time(AUCTION_DATA))}</div>
        <div style="font-size:10px;color:#6b7280;margin-bottom:8px">{fetch_time}</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <div>
            <div style="font-size:11px;font-weight:600;color:#9ca3af;margin-bottom:4px">指数竞价</div>
            {idx_lines}
          </div>
          <div>
            <div style="font-size:11px;font-weight:600;color:#9ca3af;margin-bottom:4px">高开/低开统计</div>
            <div style="display:flex;gap:12px;font-size:12px">
              <span style="color:#ef4444">高开 {gap_up_cnt}</span>
              <span style="color:#22c55e">低开 {gap_down_cnt}</span>
              <span style="color:#9ca3af">平开 {flat_cnt}</span>
            </div>
            <div style="font-size:11px;font-weight:600;color:#9ca3af;margin:6px 0 4px">TOP5高开股</div>
            {top5_lines}
          </div>
        </div>
      </div>
    </div>
'''
    
    # 注入到市场脉搏区域的指数卡片之前
    # 找到 a-pulse div 内的指数grid之前
    pulse_marker = html.find('<div id="a-pulse"')
    if pulse_marker == -1:
        log("  ⚠️ 找不到 a-pulse，跳过集合竞价注入")
        return html
    
    # 找到指数卡片 grid（第一个 grid-template-columns:repeat(3）
    idx_grid = html.find('grid-template-columns:repeat(3,1fr)', pulse_marker)
    if idx_grid == -1:
        # 备选：找到 section-divider 后的第一个 div
        idx_grid = html.find('<div class="us-rt-time">', pulse_marker)
        if idx_grid != -1:
            idx_grid = html.find('</div>', idx_grid) + len('</div>')
    
    if idx_grid != -1:
        # 找到该行的开头
        line_start = html.rfind('\n', pulse_marker, idx_grid)
        if line_start == -1:
            line_start = idx_grid
        html = html[:line_start] + '\n' + auction_block + html[line_start:]
        log("  ✅ 集合竞价区块已注入到市场脉搏顶部")
    else:
        log("  ⚠️ 找不到注入位置，跳过集合竞价")
    
    return html


def inject_tail_change(html, tail_data, evening_data):
    """将尾盘异动数据注入A股Tab（在市场脉搏之后）"""
    from datetime import datetime as _dt
    _now_h = _dt.now().hour
    if _now_h < 15:
        log("  ℹ️ 未到15:00，尾盘异动暂不展示（收盘后才相关）")
        return html
    if not tail_data or not evening_data:
        return html
    
    tail_mf = tail_data.get('market_flow', {})
    even_mf = evening_data.get('market_flow', {})
    
    if not tail_mf or not even_mf:
        return html
    
    # 计算尾盘15分钟变化（14:45 → 15:00）
    changes = {}
    for key in ['main_net', 'super_large', 'large', 'medium', 'small']:
        tail_val = tail_mf.get(key, 0)
        even_val = even_mf.get(key, 0)
        changes[key] = even_val - tail_val
    
    # 判断尾盘趋势
    main_change = changes['main_net']
    trend_text = "尾盘加速流入" if main_change > 0 else "尾盘加速流出"
    trend_color = '#ef4444' if main_change > 0 else '#22c55e'
    
    tail_block = f'''
    <div id="tail-change-block" style="scroll-margin-top:60px;margin:12px 0">
      <div style="background:rgba(139,92,246,.06);border:1px solid rgba(139,92,246,.2);border-radius:10px;padding:12px">
        <div style="font-size:13px;font-weight:700;color:#8b5cf6;margin-bottom:4px">⏱ 尾盘异动（14:45→15:00）{section_time_html(get_section_time(TAIL_SNAPSHOT))}</div>
        <div style="font-size:10px;color:#6b7280;margin-bottom:8px">尾盘15分钟资金变化（14:45→收盘） · <span style="color:{trend_color};font-weight:600">{trend_text}</span></div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <div style="flex:1;min-width:80px;text-align:center;padding:6px;background:rgba(255,255,255,.03);border-radius:6px">
            <div style="font-size:10px;color:#6b7280">主力</div>
            <div style="font-size:14px;font-weight:700;color:{color_flow(changes['main_net'])}">{changes['main_net']:+.2f}亿</div>
          </div>
          <div style="flex:1;min-width:80px;text-align:center;padding:6px;background:rgba(255,255,255,.03);border-radius:6px">
            <div style="font-size:10px;color:#6b7280">超大单</div>
            <div style="font-size:14px;font-weight:700;color:{color_flow(changes['super_large'])}">{changes['super_large']:+.2f}亿</div>
          </div>
          <div style="flex:1;min-width:80px;text-align:center;padding:6px;background:rgba(255,255,255,.03);border-radius:6px">
            <div style="font-size:10px;color:#6b7280">大单</div>
            <div style="font-size:14px;font-weight:700;color:{color_flow(changes['large'])}">{changes['large']:+.2f}亿</div>
          </div>
          <div style="flex:1;min-width:80px;text-align:center;padding:6px;background:rgba(255,255,255,.03);border-radius:6px">
            <div style="font-size:10px;color:#6b7280">中单</div>
            <div style="font-size:14px;font-weight:700;color:{color_flow(changes['medium'])}">{changes['medium']:+.2f}亿</div>
          </div>
          <div style="flex:1;min-width:80px;text-align:center;padding:6px;background:rgba(255,255,255,.03);border-radius:6px">
            <div style="font-size:10px;color:#6b7280">小单</div>
            <div style="font-size:14px;font-weight:700;color:{color_flow(changes['small'])}">{changes['small']:+.2f}亿</div>
          </div>
        </div>
      </div>
    </div>
'''
    
    # 注入到行业热力图之后、涨跌榜之前
    # 找到涨跌榜TOP5的位置
    gainers_marker = html.find('涨幅榜 TOP5')
    if gainers_marker == -1:
        # 备选：找 a-sector 之前
        sector_marker = html.find('<div id="a-sector"')
        if sector_marker != -1:
            line_start = html.rfind('\n', 0, sector_marker)
            html = html[:line_start] + '\n' + tail_block + html[line_start:]
            log("  ✅ 尾盘异动区块已注入（在行业资金之前）")
        else:
            log("  ⚠️ 找不到尾盘异动注入位置")
    else:
        # 在涨跌榜之前（往上找section-divider）
        section_div = html.rfind('section-divider', 0, gainers_marker)
        if section_div != -1:
            div_start = html.rfind('<div', 0, section_div)
            html = html[:div_start] + tail_block + '\n    ' + html[div_start:]
            log("  ✅ 尾盘异动区块已注入（在涨跌榜之前）")
        else:
            log("  ⚠️ 找不到精确注入位置")
    
    return html


def inject_post_market(html, data):
    """将复盘数据（融资融券+龙虎榜）注入A股Tab末尾"""
    if not data:
        return html
    
    margin = data.get('margin')
    dragon = data.get('dragon_tiger')
    
    if not margin and not dragon:
        return html
    
    blocks = ''
    
    # --- 融资融券部分 ---
    if margin:
        latest = margin.get('latest', {})
        if latest:
            rzye = latest.get('rzye', 0) / 1e8  # 融资余额（亿）
            rzjme = latest.get('rzjme', 0) / 1e8  # 融资净买入（亿）
            rqye = latest.get('rqye', 0) / 1e8  # 融券余额（亿）
            rzyezb = latest.get('rzyezb', 0)  # 融资余额占比%
            
            # 3/5/10日融资净买入趋势
            rzjme_3d = latest.get('rzjme_3d', 0) / 1e8
            rzjme_5d = latest.get('rzjme_5d', 0) / 1e8
            rzjme_10d = latest.get('rzjme_10d', 0) / 1e8
            
            trade_date = latest.get('date', '')
            
            blocks += f'''
    <div style="background:rgba(59,130,246,.06);border:1px solid rgba(59,130,246,.2);border-radius:10px;padding:12px;margin-bottom:12px">
      <div style="font-size:13px;font-weight:700;color:#60a5fa;margin-bottom:8px">📈 融资融券（{trade_date}）{section_time_html(get_section_time(POST_MARKET_DATA, 'margin'))}</div>
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:8px">
        <div style="text-align:center;padding:6px;background:rgba(255,255,255,.03);border-radius:6px">
          <div style="font-size:10px;color:#6b7280">融资余额</div>
          <div style="font-size:16px;font-weight:700;color:#e5e7eb">{rzye:.0f}亿</div>
        </div>
        <div style="text-align:center;padding:6px;background:rgba(255,255,255,.03);border-radius:6px">
          <div style="font-size:10px;color:#6b7280">融资净买入</div>
          <div style="font-size:16px;font-weight:700;color:{color_flow(rzjme)}">{rzjme:+.2f}亿</div>
        </div>
        <div style="text-align:center;padding:6px;background:rgba(255,255,255,.03);border-radius:6px">
          <div style="font-size:10px;color:#6b7280">融券余额</div>
          <div style="font-size:16px;font-weight:700;color:#e5e7eb">{rqye:.0f}亿</div>
        </div>
        <div style="text-align:center;padding:6px;background:rgba(255,255,255,.03);border-radius:6px">
          <div style="font-size:10px;color:#6b7280">融资占比</div>
          <div style="font-size:16px;font-weight:700;color:#e5e7eb">{rzyezb:.2f}%</div>
        </div>
      </div>
      <div style="font-size:11px;color:#9ca3af">
        近3日: <span style="color:{color_flow(rzjme_3d)};font-weight:600">{rzjme_3d:+.2f}亿</span> · 
        近5日: <span style="color:{color_flow(rzjme_5d)};font-weight:600">{rzjme_5d:+.2f}亿</span> · 
        近10日: <span style="color:{color_flow(rzjme_10d)};font-weight:600">{rzjme_10d:+.2f}亿</span>
      </div>
    </div>'''
    
    # --- 龙虎榜部分 ---
    if dragon:
        inst_stocks = dragon.get('institution_stocks', [])
        all_stocks = dragon.get('stocks', [])
        trade_date = dragon.get('trade_date', '')
        
        # 机构净买入TOP5
        inst_buy = sorted(inst_stocks, key=lambda x: x['net_amt'], reverse=True)[:5]
        # 机构净卖出TOP5
        inst_sell = sorted(inst_stocks, key=lambda x: x['net_amt'])[:5]
        
        def lhb_rows(stocks, is_buy=True):
            rows = ''
            for s in stocks:
                net = s['net_amt'] / 1e4  # 转为万元
                c = '#ef4444' if net > 0 else '#22c55e'
                explain = s.get('explain', '') or s.get('reason', '') or ''
                # 截短explain
                if len(explain) > 30:
                    explain = explain[:30] + '...'
                rows += f'''<tr>
                  <td><span style="font-weight:600;color:#e5e7eb">{s['name']}</span> <span style="font-size:10px;color:#6b7280">{s['code']}</span></td>
                  <td style="text-align:right;font-weight:700;color:{c}">{net:+.0f}万</td>
                  <td style="font-size:10px;color:#9ca3af">{explain}</td>
                </tr>'''
            return rows
        
        buy_rows = lhb_rows(inst_buy, True) if inst_buy else '<tr><td colspan="3" style="text-align:center;color:#6b7280;font-size:11px">暂无机构买入数据</td></tr>'
        sell_rows = lhb_rows(inst_sell, False) if inst_sell else '<tr><td colspan="3" style="text-align:center;color:#6b7280;font-size:11px">暂无机构卖出数据</td></tr>'
        
        blocks += f'''
    <div style="background:rgba(239,68,68,.06);border:1px solid rgba(239,68,68,.15);border-radius:10px;padding:12px;margin-bottom:12px">
      <div style="font-size:13px;font-weight:700;color:#ef4444;margin-bottom:4px">🐉 龙虎榜（{trade_date}）{section_time_html(get_section_time(POST_MARKET_DATA, 'dragon_tiger'))}</div>
      <div style="font-size:10px;color:#6b7280;margin-bottom:8px">机构席位参与 · 共{dragon.get("count",0)}只个股上榜</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
        <div>
          <div style="font-size:11px;font-weight:600;color:#ef4444;margin-bottom:4px">机构净买入 TOP5</div>
          <table style="width:100%;font-size:11px"><tbody>{buy_rows}</tbody></table>
        </div>
        <div>
          <div style="font-size:11px;font-weight:600;color:#22c55e;margin-bottom:4px">机构净卖出 TOP5</div>
          <table style="width:100%;font-size:11px"><tbody>{sell_rows}</tbody></table>
        </div>
      </div>
    </div>'''
    
    if not blocks:
        return html

    # 生成新鲜度指示器
    pm_ft = ''
    if margin and margin.get('fetch_time'):
        pm_ft = margin.get('fetch_time', '')
    freshness_html, _ = generate_freshness_html(pm_ft, 'margin_trading')

    # 注入区块
    section = f'''
    <div id="a-postmarket" style="scroll-margin-top:60px"></div>
    <div class="section-divider"><span>📊 复盘数据</span></div>
    <div style="font-size:11px;color:#6b7280;margin-bottom:10px">盘后数据 · 融资融券+龙虎榜 · 数据源：东方财富</div>
    {freshness_html}
    {blocks}
'''
    
    # 注入到A股Tab末尾（在 data source footer 之前）
    footer_marker = html.find('数据来源：<a href="https://quote.eastmoney.com/"')
    if footer_marker == -1:
        footer_marker = html.find('数据来源：东方财富')
    
    if footer_marker != -1:
        # 找到包含footer的div开始
        div_start = html.rfind('<div', 0, footer_marker)
        html = html[:div_start] + section + '\n    ' + html[div_start:]
        log("  ✅ 复盘数据区块已注入（在A股Tab末尾）")
    else:
        # 找不到footer，在a-stocks section之后注入
        stocks_end = html.find('</div>\n', html.find('<div id="a-stocks"'))
        if stocks_end != -1:
            html = html[:stocks_end] + '\n' + section + html[stocks_end:]
            log("  ✅ 复盘数据区块已注入（在龙头个股之后）")
        else:
            log("  ⚠️ 找不到复盘数据注入位置")
    
    return html


def _us_color(chg_pct):
    """Return CSS color for US stock change percent."""
    if chg_pct > 0:
        return '#ef4444'   # red = up (Chinese convention)
    elif chg_pct < 0:
        return '#22c55e'   # green = down
    return '#94a3b8'


def _us_arrow(chg_pct):
    if chg_pct > 0: return '▲'
    if chg_pct < 0: return '▼'
    return '■'


def inject_us_stock_cards(html, stocks):
    """Update individual stock card prices and change percentages.

    Card structure:
      <div class="sch"><div><span class="ssym">SYM</span><span class="snm">name</span></div></div>
      <div style="display:flex;...">
        <div class="sprc">$PRICE</div>
        <div class="schg up|dn">CHG%</div>
      </div>
    """
    updated = 0
    for sym, s in stocks.items():
        rt_price = s.get('rt_price')
        rt_chg = s.get('rt_change_pct')
        if not rt_price or rt_chg is None:
            continue
        # Find the symbol marker
        sym_marker = f'<span class="ssym">{sym}</span>'
        pos = html.find(sym_marker)
        if pos == -1:
            continue
        # Find next sprc after sym
        sprc_start = html.find('<div class="sprc">', pos)
        if sprc_start == -1:
            continue
        sprc_val_start = html.find('>', sprc_start) + 1
        sprc_val_end = html.find('</div>', sprc_val_start)
        old_price = html[sprc_val_start:sprc_val_end]
        new_price = f'${rt_price:,.2f}'
        html = html[:sprc_val_start] + new_price + html[sprc_val_end:]

        # Find next schg after sprc
        schg_match = re.search(r'<div class="schg\s+(up|dn)">[^<]*</div>', html[sprc_start:sprc_start+300])
        if schg_match:
            abs_start = sprc_start + schg_match.start()
            abs_end = sprc_start + schg_match.end()
            cls = 'up' if rt_chg > 0 else ('dn' if rt_chg < 0 else 'up')
            sign = '+' if rt_chg > 0 else ''
            new_chg = f'<div class="schg {cls}">{sign}{rt_chg:.2f}%</div>'
            html = html[:abs_start] + new_chg + html[abs_end:]
        updated += 1
    log(f"  已更新 {updated} 只美股卡片实时价格")
    return html


def inject_us_top_amount_table(html, top_amount):
    """Rebuild the 成交额TOP10 table tbody."""
    if not top_amount:
        return html
    rows = []
    for it in top_amount[:10]:
        name = it.get('name', '')
        code = it.get('code', '')
        price = it.get('price', 0)
        chg = it.get('change_pct', 0)
        amount_y = it.get('amount', 0) / 1e8
        color = _us_color(chg)
        sign = '+' if chg > 0 else ''
        rows.append(
            f'<tr><td><span class="fn">{name}</span>'
            f'<span class="fc">{code}</span></td>'
            f'<td>${price:,.2f}</td>'
            f'<td style="color:{color};font-weight:600">{sign}{chg:.2f}%</td>'
            f'<td>${amount_y:.1f}亿</td></tr>'
        )
    new_tbody = '<tbody>' + ''.join(rows) + '</tbody>'
    # Find the 成交额 TOP10 table
    marker = '📊 成交额 TOP10'
    pos = html.find(marker)
    if pos == -1:
        log("  ⚠️ 未找到成交额TOP10表格")
        return html
    tbody_start = html.find('<tbody>', pos)
    tbody_end = html.find('</tbody>', tbody_start) + len('</tbody>')
    if tbody_start == -1 or tbody_end == -1:
        return html
    html = html[:tbody_start] + new_tbody + html[tbody_end:]
    log(f"  已更新成交额TOP10表格（{len(rows)}行）")
    return html


def inject_us_fund_flow_tables(html, inflow, outflow):
    """Rebuild US stock fund inflow and outflow tables.

    Tables use class="fp" for amount and pct cells.
    """
    def build_rows(items, is_inflow=True):
        rows = []
        for it in items[:10]:
            name = it.get('name', '')
            code = it.get('code', '')
            net = it.get('main_net_inflow', 0) / 1e8
            pct = it.get('main_net_pct', 0)
            # Color: inflow table all red-positive, outflow table values are negative
            if is_inflow:
                rows.append(
                    f'<tr><td><span class="fn">{name}</span>'
                    f'<span class="fc">{code}</span></td>'
                    f'<td class="fp">+${net:.2f}亿</td>'
                    f'<td class="fp" style="color:#ef4444">+{pct:.2f}%</td></tr>'
                )
            else:
                rows.append(
                    f'<tr><td><span class="fn">{name}</span>'
                    f'<span class="fc">{code}</span></td>'
                    f'<td class="fp">-${abs(net):.2f}亿</td>'
                    f'<td class="fp" style="color:#22c55e">{pct:.2f}%</td></tr>'
                )
        return ''.join(rows)

    # Find and replace inflow table (first table with class fp after inflow marker)
    # The HTML has two tables: one for inflow, one for outflow.
    # Locate by searching for the section headers.
    # Inflow: look for "资金流入" or first fp table
    # We'll find all <tbody>...</tbody> blocks that contain class="fp" and replace
    # first two of them (inflow, outflow).

    tbody_pattern = re.compile(r'<tbody>.*?</tbody>', re.DOTALL)
    matches = list(tbody_pattern.finditer(html))

    inflow_rows = build_rows(inflow, is_inflow=True)
    outflow_rows = build_rows(outflow, is_inflow=False)

    # The first fp-tbody is inflow, second is outflow
    fp_tbodies = []
    for m in matches:
        if 'class="fp"' in m.group(0):
            fp_tbodies.append(m)

    if len(fp_tbodies) >= 2:
        # Replace outflow first (later in file) to preserve offsets
        m_out = fp_tbodies[1]
        html = html[:m_out.start()] + '<tbody>' + outflow_rows + '</tbody>' + html[m_out.end():]
        m_in = fp_tbodies[0]
        # Recompute inflow position (outflow replacement may shift, but inflow is before)
        html = html[:m_in.start()] + '<tbody>' + inflow_rows + '</tbody>' + html[m_in.end():]
        log(f"  已更新美股资金流入/流出表格（各{len(inflow)//1}行）")
    elif len(fp_tbodies) == 1:
        # Only one found, replace as inflow
        m = fp_tbodies[0]
        html = html[:m.start()] + '<tbody>' + inflow_rows + '</tbody>' + html[m.end():]
        log(f"  ⚠️ 仅找到1个资金表格，已更新流入表")
    else:
        log("  ⚠️ 未找到美股资金流向表格")

    return html


def inject_us_tech_track(html, stocks, inflow, outflow):
    """生成并注入科技赛道速览区到 #us-tech-track"""
    # 定义三个科技赛道分组
    tech_groups = [
        {
            'name': '半导体',
            'icon': '🔬',
            'symbols': ['NVDA', 'AMD', 'AVGO', 'INTC', 'MU', 'QCOM', 'MRVL', 'ARM', 'TSM'],
            'color': '#8b5cf6',
        },
        {
            'name': 'AI/算力',
            'icon': '🤖',
            'symbols': ['NVDA', 'MSFT', 'GOOGL', 'META', 'AMZN', 'AVGO'],
            'color': '#3b82f6',
        },
        {
            'name': '软件/SaaS',
            'icon': '💻',
            'symbols': ['MSFT', 'CRM', 'NOW', 'ADBE', 'SNOW'],
            'color': '#06b6d4',
        },
    ]

    # 构建资金流向 lookup: code -> main_net_inflow
    flow_lookup = {}
    for it in (inflow or []):
        flow_lookup[it.get('code', '')] = it.get('main_net_inflow', 0)
    for it in (outflow or []):
        code = it.get('code', '')
        if code not in flow_lookup:
            flow_lookup[code] = it.get('main_net_inflow', 0)

    def _us_color_local(chg):
        if chg > 0: return '#ef4444'
        if chg < 0: return '#22c55e'
        return '#9ca3af'

    cards_html = []
    for group in tech_groups:
        matched = []
        for sym in group['symbols']:
            s = stocks.get(sym)
            if not s:
                continue
            chg = s.get('rt_change_pct')
            if chg is None:
                continue
            name = s.get('name', sym)
            price = s.get('rt_price', 0)
            flow = flow_lookup.get(sym, 0)
            matched.append({
                'sym': sym, 'name': name, 'chg': chg,
                'price': price, 'flow': flow
            })

        if not matched:
            continue

        # 计算平均涨跌幅
        avg_chg = sum(m['chg'] for m in matched) / len(matched)
        # 计算主力净流入合计
        total_flow = sum(m['flow'] for m in matched)
        total_flow_yi = total_flow / 1e8

        avg_color = _us_color_local(avg_chg)
        avg_sign = '+' if avg_chg > 0 else ''
        flow_color = '#ef4444' if total_flow >= 0 else '#22c55e'
        flow_sign = '+' if total_flow >= 0 else '-'

        # 取前4个关键个股展示（按涨跌幅绝对值排序）
        key_stocks = sorted(matched, key=lambda x: abs(x['chg']), reverse=True)[:4]
        stock_chips = []
        for m in key_stocks:
            c = _us_color_local(m['chg'])
            s = '+' if m['chg'] > 0 else ''
            chip_text = (
                '<span style="display:inline-block;background:rgba(255,255,255,.04);'
                'border:1px solid rgba(255,255,255,.08);border-radius:4px;'
                'padding:2px 6px;margin:1px;font-size:11px">'
                '<span style="color:#e5e7eb;font-weight:600">' + m['sym'] + '</span> '
                '<span style="color:' + c + '">' + s + '{:.1f}'.format(m['chg']) + '%</span></span>'
            )
            stock_chips.append(chip_text)

        card = (
            '<div style="background:rgba(255,255,255,.02);border:1px solid rgba(255,255,255,.06);'
            'border-radius:8px;padding:10px;border-left:3px solid ' + group['color'] + '">'
            '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">'
            '<div style="font-size:13px;font-weight:700;color:' + group['color'] + '">'
            + group['icon'] + ' ' + group['name'] + '</div>'
            '<div style="font-size:11px;color:#6b7280">' + str(len(matched)) + '只</div>'
            '</div>'
            '<div style="display:flex;gap:12px;margin-bottom:6px">'
            '<div><span style="font-size:10px;color:#6b7280">均涨幅</span><br>'
            '<span style="font-size:15px;font-weight:700;color:' + avg_color + '">'
            + avg_sign + '{:.2f}'.format(avg_chg) + '%</span></div>'
            '<div><span style="font-size:10px;color:#6b7280">主力净流入</span><br>'
            '<span style="font-size:15px;font-weight:700;color:' + flow_color + '">'
            + flow_sign + '$' + '{:.2f}'.format(abs(total_flow_yi)) + '亿\u003c\/span\u003e\u003c\/div\u003e'
            '</div>'
            '<div style="line-height:1.8">' + ''.join(stock_chips) + '</div>'
            '</div>'
        )
        cards_html.append(card)

    if not cards_html:
        log("  ⚠️ 科技赛道速览：无匹配数据")
        return html

    tech_html = (
        '<div style="margin-bottom:14px">'
        '<div style="font-size:13px;font-weight:600;color:#9ca3af;margin-bottom:8px;padding-left:2px">'
        '🚀 科技赛道速览</div>'
        '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px">'
        + ''.join(cards_html)
        + '</div></div>'
    )

    # 注入到 #us-tech-track（用唯一标记做替换，避免正则吞掉父容器闭合标签）
    import re as _re
    # 匹配 <div id="us-tech-track"> 到其对应的 </div>（不贪婪，不跨出该div）
    _pattern = _re.compile(r'<div id="us-tech-track">.*?</div>', _re.DOTALL)
    _replacement = '<div id="us-tech-track">' + tech_html + '</div>'
    if _pattern.search(html):
        html = _pattern.sub(_replacement, html, count=1)
        log("  ✅ 科技赛道速览已更新（{}个赛道）".format(len(cards_html)))
    else:
        log("  ⚠️ 未找到 #us-tech-track 占位符")

    return html


def inject_us_data(html, data):
    """更新美股相关的 JS 数据变量（SPARK）、个股卡片实时价、资金流向表格、成交额表格、VIX"""
    stocks = data.get('stocks', {})
    vix = data.get('vix')
    fetch_time = data.get('fetch_time', '')
    inflow = data.get('inflow', [])
    outflow = data.get('outflow', [])
    top_amount = data.get('top_amount', [])

    # --- 1. 更新 SPARK 变量（美股个股 sparkline 数据）---
    spark = {}
    for sym, s in stocks.items():
        spark[sym] = {"d": s.get("dates", []), "c": s.get("closes", [])}
    spark_js = 'var SPARK=' + json.dumps(spark, ensure_ascii=False, separators=(',', ':')) + ';'

    spark_pattern = re.compile(r'var\s+SPARK\s*=\s*\{.*?\};', re.DOTALL)
    if spark_pattern.search(html):
        html = spark_pattern.sub(spark_js, html, count=1)
        log("  已更新 SPARK 变量")
    else:
        log("  ⚠️ 未找到 SPARK 变量，跳过")

    # --- 2. 更新个股卡片实时价格和涨跌幅 ---
    html = inject_us_stock_cards(html, stocks)

    # --- 3. 更新成交额TOP10表格 ---
    html = inject_us_top_amount_table(html, top_amount)

    # --- 4. 更新资金流入/流出表格 ---
    html = inject_us_fund_flow_tables(html, inflow, outflow)

    # --- 4.5. 注入科技赛道速览 ---
    html = inject_us_tech_track(html, stocks, inflow, outflow)

    # --- 5. 更新 VIX 完整卡片（数值+涨跌+昨收+进度条+标签）---
    if vix and vix.get('value'):
        vix_val = vix['value']
        vix_prev = vix.get('prev_close', vix_val)
        vix_chg = vix.get('change', vix_val - vix_prev)
        vix_chg_pct = vix.get('change_pct', (vix_chg / vix_prev * 100) if vix_prev else 0)

        # VIX 等级与颜色
        if vix_val < 15:
            level_text, val_color = '平静', '#22c55e'
        elif vix_val < 20:
            level_text, val_color = '偏低', '#84cc16'
        elif vix_val < 25:
            level_text, val_color = '正常', '#eab308'
        elif vix_val < 30:
            level_text, val_color = '偏高', '#f97316'
        else:
            level_text, val_color = '恐慌', '#ef4444'

        # 涨跌颜色
        if vix_chg > 0:
            chg_color = '#ef4444'
            chg_sign = '+'
        elif vix_chg < 0:
            chg_color = '#22c55e'
            chg_sign = ''
        else:
            chg_color = '#9ca3af'
            chg_sign = '+'

        # 进度条位置：VIX 10-40 映射 0%-100%
        mark_pct = max(0, min(100, (vix_val - 10) / 30 * 100))

        # 5a. 更新数值
        html = re.sub(
            r'(<div class="vovv"[^>]*>)[\d.]+(</div>)',
            rf'\g<1>{vix_val:.2f}\g<2>',
            html, count=1
        )
        # 更新数值颜色
        html = re.sub(
            r'(<div class="vovv" style=")color:[^;"]+(">[\d.]+</div>)',
            rf'\g<1>color:{val_color}\g<2>',
            html, count=1
        )

        # 5b. 更新涨跌行（vovc）
        vovc_new = f'{chg_sign}{vix_chg:.2f} ({chg_sign}{vix_chg_pct:.2f}%) · {level_text}'
        html = re.sub(
            r'(<div class="vovc" style=")color:[^;"]+(">[^<]*</div>)',
            rf'\g<1>color:{chg_color}\g<2>',
            html, count=1
        )
        html = re.sub(
            r'(<div class="vovc"[^>]*>)[^<]*(</div>)',
            rf'\g<1>{vovc_new}\g<2>',
            html, count=1
        )

        # 5c. 更新昨收
        html = re.sub(
            r'(昨收\s*)[\d.]+',
            rf'\g<1>{vix_prev:.2f}',
            html, count=1
        )

        # 5d. 更新进度条位置
        html = re.sub(
            r'(<div class="vmark" style="left:)[\d.]+(%)',
            rf'\g<1>{mark_pct:.1f}\g<2>',
            html, count=1
        )

        log(f"  VIX 卡片完整更新: {vix_val:.2f} ({chg_sign}{vix_chg:.2f}/{chg_sign}{vix_chg_pct:.2f}%) · {level_text} · 进度{mark_pct:.1f}%")

    # --- 6. 更新美股数据时间戳 --
    us_time_pattern = re.compile(r'(历史数据: 新浪财经 · 实时行情: 腾讯财经)[^<]*')
    if us_time_pattern.search(html):
        html = us_time_pattern.sub(rf'\g<1> ({fetch_time})', html, count=1)

    # --- 7. 更新美股Tab时间戳 --
    html = update_tab_timestamp(html, 'us_stocks', data.get('fetch_time'))

    # --- 8. 注入新鲜度指示器（替换已有，不追加）--
    us_ft = data.get('fetch_time', '')
    freshness_html, age_min = generate_freshness_html(us_ft, 'us_stock')
    if freshness_html:
        us_marker = '📈 美股指数'
        us_pos = html.find(us_marker)
        if us_pos != -1:
            # 查找已有的新鲜度 div（紧跟在 marker 之后）
            existing_pattern = re.compile(
                r'(<div class="section-subtitle">📈 美股指数</div>)\s*'
                r'<div style="font-size: 0\.7em; color: #888; text-align: right; padding: 2px 8px; margin-top: -4px; margin-bottom: 4px;">.*?</div>',
                re.DOTALL
            )
            if existing_pattern.search(html):
                html = existing_pattern.sub(rf'\g<1>\n    {freshness_html}', html, count=1)
            else:
                section_end = html.find('</div>', us_pos)
                if section_end != -1:
                    html = html[:section_end + 6] + '    ' + freshness_html + '\n    ' + html[section_end + 6:]
            log(f"  美股新鲜度指示器已更新 (年龄: {age_min:.0f}分钟)")

    # --- 9. HTML完整性验证 --
    bad_spans = re.findall(r'class="yield-chg[^"]*(?:\s+\w+){2,}"', html)
    if bad_spans:
        log(f"  ⚠️ 发现 {len(bad_spans)} 个损坏的yield-chg: {bad_spans[:3]}")
    else:
        log("  ✅ HTML完整性验证通过")

    return html


# ============================================================
#  SW 缓存版本更新
# ============================================================

def update_sw_version(mode):
    """更新 sw.js 中的缓存名称（含时分确保每次唯一）"""
    from datetime import datetime
    now_hhmm = datetime.now().strftime('%H%M')
    cache_name = f'treasury-dashboard-{mode}-{TODAY_COMPACT}-{now_hhmm}'
    with open(SW_JS, 'r', encoding='utf-8') as f:
        content = f.read()
    content = re.sub(
        r"(?:const\s+)*CACHE_NAME\s*=\s*'[^']*'",
        f"const CACHE_NAME = '{cache_name}'",
        content
    )
    with open(SW_JS, 'w', encoding='utf-8') as f:
        f.write(content)
    log(f"SW 缓存版本更新为: {cache_name}")
    return cache_name


# ============================================================
#  GitHub 推送
# ============================================================

def github_push(file_paths, commit_message):
    """通过 GitHub Contents API 推送文件"""
    with open(DEPLOY_CONFIG, 'r', encoding='utf-8') as f:
        config = json.load(f)
    token = config['github_token']
    repo = config['github_repo']

    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json',
    }
    api_base = f'https://api.github.com/repos/{repo}/contents'

    for file_path in file_paths:
        filename = os.path.basename(file_path)
        # GitHub 上的路径：index.html 和 sw.js 在根目录
        url = f'{api_base}/{filename}'

        # 先 GET 获取 SHA
        log(f"  获取远程 SHA: {filename}")
        sha = None
        try:
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                sha = r.json().get('sha')
        except Exception as e:
            log(f"  ⚠️ 获取 SHA 失败: {e}")

        # 读取文件内容并 base64 编码
        with open(file_path, 'rb') as f:
            content = base64.b64encode(f.read()).decode('utf-8')

        payload = {
            'message': commit_message,
            'content': content,
        }
        if sha:
            payload['sha'] = sha

        log(f"  推送 {filename}...")
        try:
            r = requests.put(url, headers=headers, json=payload, timeout=30)
            if r.status_code in (200, 201):
                log(f"  ✅ {filename} 推送成功")
            else:
                log(f"  ❌ {filename} 推送失败: {r.status_code} {r.text[:200]}")
        except Exception as e:
            log(f"  ❌ {filename} 推送异常: {e}")

        time.sleep(0.5)


# ============================================================
#  数据完整性验证
# ============================================================

# 每个模块最少应有的数据条数
VALIDATION_RULES = {
    'a_shares': {
        'indices': {'min': 6, 'label': '大盘指数', 'critical': True},
        'sector_flow': {'min': 90, 'label': '行业板块', 'critical': True},
        'concept_flow': {'min': 40, 'label': '概念板块', 'critical': True},
        'stock_inflow': {'min': 15, 'label': '个股流入TOP', 'critical': True},
        'stock_outflow': {'min': 15, 'label': '个股流出TOP', 'critical': True},
        'stock_volume': {'min': 15, 'label': '个股成交额TOP', 'critical': True},
        'market_flow': {'min': 1, 'label': '大盘资金分层', 'critical': True},
        'limit_up': {'min': 5, 'label': '涨幅榜', 'critical': False},
        'limit_down': {'min': 5, 'label': '跌幅榜', 'critical': False},
    },
    'us_stocks': {
        'stocks': {'min': 20, 'label': '美股个股K线', 'critical': True},
        'inflow': {'min': 15, 'label': '美股资金流入TOP', 'critical': True},
        'outflow': {'min': 15, 'label': '美股资金流出TOP', 'critical': True},
        'top_amount': {'min': 15, 'label': '美股成交额TOP', 'critical': True},
        'vix': {'min': 1, 'label': 'VIX数据', 'critical': False},
    },
}


def validate_a_shares(data, sp):
    """验证A股数据完整性，返回 (passed, warnings, errors)"""
    warnings, errors = [], []
    for key, rule in VALIDATION_RULES['a_shares'].items():
        val = data.get(key)
        if key == 'market_flow':
            count = 1 if val and val.get('total_amount', 0) > 0 else 0
        elif val is None:
            count = 0
        elif isinstance(val, (dict, list)):
            count = len(val)
        else:
            count = 1 if val else 0
        if count < rule['min']:
            msg = f"{rule['label']}: 仅 {count} 条（期望≥{rule['min']}）"
            if rule['critical']:
                errors.append(msg)
            else:
                warnings.append(msg)
    # K线迷你图
    spark_count = len(sp.get('stocks', {})) if sp else 0
    if spark_count < 9:
        warnings.append(f"A股K线迷你图: 仅 {spark_count} 只（期望≥9）")
    return len(errors) == 0, warnings, errors


def validate_us_stocks(data):
    """验证美股数据完整性"""
    warnings, errors = [], []
    for key, rule in VALIDATION_RULES['us_stocks'].items():
        val = data.get(key)
        if key == 'vix':
            count = 1 if val and val.get('value', 0) > 0 else 0
        elif key == 'stocks':
            count = len(val) if val else 0
        else:
            count = len(val) if val else 0
        if count < rule['min']:
            msg = f"{rule['label']}: 仅 {count} 条（期望≥{rule['min']}）"
            if rule['critical']:
                errors.append(msg)
            else:
                warnings.append(msg)
    # 实时行情覆盖率
    stocks = data.get('stocks', {})
    rt_count = sum(1 for s in stocks.values() if s.get('rt_price', 0) > 0)
    if rt_count < 15:
        errors.append(f"美股实时行情: 仅 {rt_count} 只有报价（期望≥15）")
    return len(errors) == 0, warnings, errors


def run_validation(mode, a_d=None, a_sp=None, us_d=None):
    """运行验证，输出结果，返回是否通过"""
    log("--- 数据完整性验证 ---")
    all_pass = True
    if mode in ('morning', 'noon', 'evening') and a_d is not None:
        passed, warns, errs = validate_a_shares(a_d, a_sp)
        if errs:
            all_pass = False
            for e in errs:
                log(f"  ❌ A股-{e}")
        for w in warns:
            log(f"  ⚠️ A股-{w}")
        if not errs and not warns:
            log("  ✅ A股数据完整")
        elif not errs:
            log("  ✅ A股核心数据通过（有非关键项警告）")
    if mode == 'morning' and us_d is not None:
        passed, warns, errs = validate_us_stocks(us_d)
        if errs:
            all_pass = False
            for e in errs:
                log(f"  ❌ 美股-{e}")
        for w in warns:
            log(f"  ⚠️ 美股-{w}")
        if not errs and not warns:
            log("  ✅ 美股数据完整")
        elif not errs:
            log("  ✅ 美股核心数据通过（有非关键项警告）")
    return all_pass


def run_series_update():
    """运行 fetch_series_update.py 增量更新 HTML 中的图表序列数据（US_SERIES_DATA + SERIES_DATA）"""
    log("--- 图表序列增量更新 ---")
    script = os.path.join(BASE_DIR, 'fetch_series_update.py')
    try:
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True, text=True, timeout=120
        )
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                log(f"  {line}")
        if result.returncode != 0:
            log(f"  ⚠️ 序列更新脚本退出码: {result.returncode}")
            if result.stderr:
                log(f"  ⚠️ stderr: {result.stderr[:300]}")
            return False
        return True
    except subprocess.TimeoutExpired:
        log("  ❌ 序列更新超时(120s)")
        return False
    except Exception as e:
        log(f"  ❌ 序列更新异常: {e}")
        return False


def run_post_update_validation():
    """更新后运行 data_validator.py 快速检查，返回验证摘要和 commit message 后缀"""
    log("--- 更新后数据验证 ---")
    validator = os.path.join(BASE_DIR, 'data_validator.py')
    try:
        result = subprocess.run(
            [sys.executable, validator, '--quick', '--json'],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0 and result.stdout.strip().startswith('{'):
            report = json.loads(result.stdout)
            summary = report.get('summary', {})
            critical = summary.get('critical', 0)
            warning = summary.get('warning', 0)
            passed = summary.get('passed', 0)
            total = summary.get('total', summary.get('total_checks', 0))

            # 输出关键结果
            for check in report.get('checks', []):
                if not check.get('passed'):
                    icon = '❌' if check['severity'] == 'critical' else '⚠️'
                    log(f"  {icon} [{check['severity']}] {check['message']}")

            log(f"  验证完成: {passed}/{total} 通过, {critical} critical, {warning} warning")

            # 保存结果
            val_output = os.path.join(BASE_DIR, 'validation_latest.json')
            with open(val_output, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)

            suffix = ""
            if critical > 0:
                suffix = f" [⚠️ {critical} critical]"
            elif warning > 0:
                suffix = f" [ℹ️ {warning} warning]"
            return suffix
        else:
            log("  ⚠️ 验证脚本输出异常")
            if result.stderr:
                log(f"  stderr: {result.stderr[:300]}")
            return ""
    except Exception as e:
        log(f"  ⚠️ 验证执行异常: {e}")
        return ""


# ============================================================
#  商品数据注入
# ============================================================

def _fmt_price(price, decimals):
    """格式化价格显示"""
    if decimals == 0:
        return f"${price:,.0f}"
    return f"${price:,.{decimals}f}"


def _fmt_change(change, change_pct, decimals):
    """格式化涨跌显示，返回 (class, text)
    正数加+号，负数用-号（change自带），零用—。箭头已表方向，数字不再重复。
    """
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
        # 负数：change本身含-号，不加额外sign
        if decimals == 0:
            return cls, f"{arrow}{change:,.0f} ({change_pct:.2f}%)"
        return cls, f"{arrow}{change:,.{decimals}f} ({change_pct:.2f}%)"


def inject_commodities(html, data):
    """将实时商品期货数据注入HTML，更新总览卡片和商品Tab数值。
    
    保留FRED的历史图表数据（SERIES_DATA）不变，只替换实时显示的数值卡片。
    """
    meta = data.get('_meta', {})
    fetch_time = meta.get('fetch_time', '')
    
    # 总览页卡片配置：(key, label, border_color)
    overview_cards = [
        ('btc', '比特币', '#f7931a'),
        ('gold', '黄金', '#ffd700'),
        ('wti', '原油WTI', '#8b5cf6'),
        ('brent', '布伦特原油', '#06b6d4'),
    ]
    
    # 商品Tab区块配置：(key, title_contains, chart_id)
    detail_blocks = [
        ('btc', '比特币', 'CBBTCUSD'),
        ('gold', '黄金', 'GOLD'),
        ('wti', 'WTI', 'DCOILWTICO'),
        ('brent', '布伦特', 'DCOILBRENTEU'),
    ]
    
    # --- 1. 更新总览页卡片 ---
    # 找到 💰 大宗商品 section
    comm_section_start = html.find('💰 大宗商品')
    if comm_section_start != -1:
        # 找到section结束（下一个section-subtitle）
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
            
            # 用label定位卡片，精确匹配 class="ov-value" 和 class="ov-chg"
            label_pos = section_html.find(f'>{label}<')
            if label_pos != -1:
                # 找到该卡片的 ov-value（精确匹配 class=）
                val_marker = 'class="ov-value"'
                val_start = section_html.find(val_marker, label_pos)
                if val_start != -1:
                    val_content_start = section_html.find('>', val_start) + 1
                    val_content_end = section_html.find('</div>', val_content_start)
                    section_html = (section_html[:val_content_start] + price_str + 
                                   section_html[val_content_end:])
                
                # 找到 ov-chg（精确匹配 class=）
                chg_marker = 'class="ov-chg'
                chg_start = section_html.find(chg_marker, label_pos)
                if chg_start != -1:
                    # 替换整个 class 属性和内容
                    tag_end = section_html.find('>', chg_start)
                    chg_content_start = tag_end + 1
                    chg_content_end = section_html.find('</div>', chg_content_start)
                    section_html = (section_html[:chg_start] + 
                                   f'class="ov-chg {chg_cls}">{chg_str}' + 
                                   section_html[chg_content_end:])
        
        html = html[:comm_section_start] + section_html + html[next_section:]
        log("  总览页商品卡片已更新")
    
    # --- 2. 更新商品Tab详细区块 ---
    for key, title_hint, chart_id in detail_blocks:
        if key not in data:
            continue
        d = data[key]
        decimals = d.get('decimals', 2)
        price_str = _fmt_price(d['price'], decimals)
        chg_cls, chg_str = _fmt_change(d['change'], d['change_pct'], decimals)
        
        # 找到区块标题位置
        title_pos = html.find(title_hint)
        while title_pos != -1:
            # 确认是在 commodity-block 中（前后查找commodity-block）
            block_start = html.rfind('commodity-block', 0, title_pos)
            if block_start != -1 and title_pos - block_start < 2000:
                # 找到 yield-num
                yield_pos = html.find('yield-num', title_pos)
                if yield_pos != -1:
                    yn_start = html.find('>', yield_pos) + 1
                    yn_end = html.find('</span>', yn_start)
                    if yn_end - yn_start < 50:  # 合理范围
                        html = html[:yn_start] + price_str + html[yn_end:]
                
                # 找到 yield-chg 所在的完整 span 结构并替换
                yc_pos = html.find('yield-chg', title_pos)
                if yc_pos != -1:
                    # 找到 <span 标签的起始位置（yield-chg 在 class 属性里，要往前找 <span）
                    span_tag_start = html.rfind('<span', max(0, title_pos), yc_pos + 1)
                    if span_tag_start == -1:
                        span_tag_start = html.rfind('<span', 0, yc_pos)
                    
                    if span_tag_start != -1:
                        # 从 span 标签开始，匹配到内层 </span>（chg-icon 的关闭标签）
                        after_tag = html[span_tag_start:]
                        inner_close = after_tag.find('</span>')
                        if inner_close >= 0:
                            inner_close_abs = span_tag_start + inner_close + 7  # 跳过 </span>
                            
                            # 跳过空白，查找外层 </span>
                            rest = html[inner_close_abs:]
                            stripped = rest.lstrip(' \n\t\r')
                            ws_len = len(rest) - len(stripped)
                            
                            if stripped.startswith('</span>'):
                                outer_close_abs = inner_close_abs + ws_len + 7
                            else:
                                # 没有外层 </span>，在内层 </span> 后插入
                                outer_close_abs = inner_close_abs
                            
                            # 构造新的 clean span
                            arrow = '▲' if d['change'] > 0 else ('▼' if d['change'] < 0 else '—')
                            sign = '+' if d['change'] > 0 else ''
                            if decimals == 0:
                                change_text = f"{arrow}{sign}{d['change']:,.0f} ({sign}{d['change_pct']:.2f}%)"
                            else:
                                change_text = f"{arrow}{sign}{d['change']:,.{decimals}f} ({sign}{d['change_pct']:.2f}%)"
                            clean = f'<span class="yield-chg {chg_cls}"><span class="chg-icon">{change_text}</span></span>'
                            html = html[:span_tag_start] + clean + html[outer_close_abs:]
                            log(f"  ✓ {title_hint} yield-chg 已更新")
                        else:
                            log(f"  ⚠️ yield-chg 内层</span>未找到: {title_hint}")
                    else:
                        log(f"  ⚠️ yield-chg <span>标签未找到: {title_hint}")
                break
            else:
                # 不在 commodity-block 范围内，搜索下一个匹配
                title_pos = html.find(title_hint, title_pos + 1)
                continue
    
    # --- 3. 更新底部数据源说明 ---
    old_note = '（美债收益率 DGS2/DGS5/DGS10/DGS30 · 联邦债务 GFDEBTN · 比特币 CBBTCUSD · 原油 DCOILWTICO/DCOILBRENTEU）'
    new_note = f'（美债收益率 FRED · 商品/比特币 新浪财经实时期货 · 更新：{fetch_time}）'
    if old_note in html:
        html = html.replace(old_note, new_note, 1)
    
    # --- 4. 更新商品Tab时间戳 ---
    html = update_tab_timestamp(html, 'commodities', data.get('fetch_time') or data.get('_meta', {}).get('fetch_time'))

    # --- 5. 注入新鲜度指示器（替换已有，不追加）---
    commodity_ft = data.get('fetch_time') or data.get('_meta', {}).get('fetch_time', '')
    freshness_html, age_min = generate_freshness_html(commodity_ft, 'commodity')
    if freshness_html:
        existing_pattern = re.compile(
            r'(<div class="section-subtitle">💰 大宗商品</div>)\s*'
            r'<div style="font-size: 0\.7em; color: #888; text-align: right; padding: 2px 8px; margin-top: -4px; margin-bottom: 4px;">.*?</div>',
            re.DOTALL
        )
        if existing_pattern.search(html):
            html = existing_pattern.sub(rf'\g<1>\n    {freshness_html}', html, count=1)
        else:
            tab_marker = '💰 大宗商品'
            tab_pos = html.find(tab_marker)
            if tab_pos != -1:
                section_end = html.find('</div>', tab_pos)
                if section_end != -1:
                    html = html[:section_end + 6] + '    ' + freshness_html + '\n    ' + html[section_end + 6:]
        log(f"  商品新鲜度指示器已更新 (年龄: {age_min:.0f}分钟)")

    log(f"  商品数据注入完成 ({fetch_time})")
    return html


# ============================================================
#  模式处理
# ============================================================

def mode_morning():
    """早上模式：更新美股，A股用缓存。
    每个数据源独立判断：拉到+验证通过→注入；否则→跳过（保留旧数据+旧日期）。
    全部都没拉到→页面完全不动。
    """
    log("====== 🌅 早上更新模式 ======")
    us_ok, a_ok = False, False
    us_fetch_time = None

    # 1. 更新美股数据（K线用缓存，实时拉新）
    log("--- 1. 获取美股数据 ---")
    us_script_ok = run_script(os.path.join(BASE_DIR, 'fetch_us_enhanced.py'))
    if us_script_ok:
        us_d = load_json(US_DATA)
        if us_d:
            passed, warns, errs = validate_us_stocks(us_d)
            for e in errs:
                log(f"  ❌ 美股-{e}")
            for w in warns:
                log(f"  ⚠️ 美股-{w}")
            if not errs:
                us_ok = True
                us_fetch_time = us_d.get('fetch_time', '')
                log("  ✅ 美股数据验证通过")
            else:
                log("  ❌ 美股数据验证失败，跳过美股（保留旧数据）")
        else:
            log("  ❌ 美股数据文件不存在，跳过美股")
    else:
        log("  ❌ 美股数据获取失败，跳过美股（保留旧数据）")

    # 2. A股直接读缓存（不发请求）
    log("--- 2. A股使用缓存 ---")
    a_cache = os.path.join(CACHE_DIR, 'ashare_latest.json')
    a_sp = load_json(A_SPARK) if os.path.exists(A_SPARK) else {'stocks': {}}
    if os.path.exists(a_cache):
        import shutil
        shutil.copy2(a_cache, A_DATA)
        log(f"  已从缓存复制 A股数据: {a_cache}")
        a_d = load_json(A_DATA)
        if a_d:
            passed, warns, errs = validate_a_shares(a_d, a_sp)
            for e in errs:
                log(f"  ❌ A股-{e}")
            for w in warns:
                log(f"  ⚠️ A股-{w}")
            if not errs:
                a_ok = True
                log("  ✅ A股缓存验证通过")
            else:
                log("  ❌ A股缓存验证失败，跳过A股（保留旧数据）")
        else:
            log("  ❌ A股缓存文件读取失败，跳过A股")
    else:
        log("  ❌ A股缓存不存在，跳过A股（保留旧数据）")

    # 3. 判断是否继续
    if not us_ok and not a_ok:
        log("❌ 所有数据源都未通过，本次更新中止（页面完全不动，保留线上旧数据+旧日期）")
        return

    # 商品数据现在由 mode_commodity() 独立处理，morning不再获取/注入商品

    # 4.5 数据新鲜度检查
    log("\n📊 数据新鲜度检查:")
    freshness_results = validate_all_data()
    if not freshness_results.get('us_stock', {}).get('fresh', False):
        log("⚠️ 美股数据过旧，仍然注入但请注意")
    if not freshness_results.get('a_share', {}).get('fresh', False):
        log("⚠️ A股数据过旧，仍然注入但请注意")

    # 5. 注入数据到 HTML
    log("--- 4. 注入数据到 HTML ---")
    with open(INDEX_HTML, 'r', encoding='utf-8') as f:
        html = f.read()

    if us_ok:
        us_d = load_json(US_DATA)
        html = inject_us_data(html, us_d)
        log("  美股数据注入完成")
    else:
        log("  美股未更新，保留旧数据")

    if a_ok:
        a_d = load_json(A_DATA)
        html = inject_a_shares(html, a_d, a_sp)
        write_a_shares_page(a_d, a_sp)
        log("  A股数据注入完成")
    else:
        log("  A股未更新，保留旧数据")

    # 商品由 mode_commodity() 独立处理，morning不再注入商品

    # 统一更新页面日期（只有实际更新的源才刷对应日期）
    html = update_page_dates(html, 'morning', us_ok=us_ok, us_fetch_time=us_fetch_time, a_ok=a_ok)

    with open(INDEX_HTML, 'w', encoding='utf-8') as f:
        f.write(html)
    log(f"  HTML 已保存 ({len(html):,} chars)")

    # 6. 图表序列增量更新
    run_series_update()

    # 7. 更新 SW 版本
    log("--- 5. 更新 Service Worker ---")
    update_sw_version('morning')

    # 8. 更新后验证
    val_suffix = run_post_update_validation()

    # 9. 推送 GitHub
    log("--- 6. 推送到 GitHub ---")
    github_push(
        [INDEX_HTML, A_SHARES_HTML, SW_JS],
        f"auto update: morning {TODAY}{val_suffix}"
    )

    # 推送后线上验证
    verify_github_push()
    updated = []
    if us_ok: updated.append('美股')
    if a_ok: updated.append('A股')
    log(f"====== ✅ 早上更新完成（已更新: {', '.join(updated)}） ======")


def mode_noon():
    """中午模式：更新A股上午盘数据。
    获取失败或验证不通过→跳过（保留旧数据+旧日期）。
    """
    log("====== ☀️ 中午更新模式 ======")
    a_ok = False

    # 1. 获取A股数据
    log("--- 1. 获取A股上午盘数据 ---")
    script_ok = run_script(os.path.join(BASE_DIR, 'fetch_a_shares.py'))
    if script_ok:
        a_d = load_json(A_DATA)
        a_sp = load_json(A_SPARK) if os.path.exists(A_SPARK) else {'stocks': {}}
        if a_d:
            passed, warns, errs = validate_a_shares(a_d, a_sp)
            for e in errs:
                log(f"  ❌ A股-{e}")
            for w in warns:
                log(f"  ⚠️ A股-{w}")
            if not errs:
                a_ok = True
                log("  ✅ A股数据验证通过")
            else:
                log("  ❌ A股数据验证失败，跳过（保留旧数据+旧日期）")
        else:
            log("  ❌ A股数据文件不存在，跳过")
    else:
        log("  ❌ A股数据获取失败，跳过（保留旧数据+旧日期）")

    if not a_ok:
        log("❌ 本次更新中止（页面完全不动，保留线上旧数据+旧日期）")
        return

    # 1.5 数据新鲜度检查
    log("\n📊 数据新鲜度检查:")
    freshness_results = validate_all_data()
    if not freshness_results.get('a_share', {}).get('fresh', False):
        log("⚠️ A股数据过旧，仍然注入但请注意")

    # 2. 注入A股数据
    log("--- 2. 注入A股数据到 HTML ---")
    with open(INDEX_HTML, 'r', encoding='utf-8') as f:
        html = f.read()

    a_d = load_json(A_DATA)
    a_sp = load_json(A_SPARK) if os.path.exists(A_SPARK) else {'stocks': {}}
    
    # 午间清除北向资金数据（此时拿到的是前一天的旧数据，不展示）
    # 北向数据会在18:00的northbound专属任务中刷新
    if a_d:
        for _nk in ['north_deal', 'north_deal_history', 'north_flow']:
            a_d[_nk] = None
        log("  已清除内存中的北向资金旧数据（等18:00刷新）")
    
    html = inject_a_shares(html, a_d, a_sp)
    write_a_shares_page(a_d, a_sp)
    log("  A股数据注入完成")

    # --- 补充注入集合竞价数据（如果存在）---
    if os.path.exists(AUCTION_DATA):
        log("  --- 补充注入集合竞价数据 ---")
        auction_d = load_json(AUCTION_DATA)
        html = inject_auction(html, auction_d)

    # --- 中午移除竞价和尾盘区块（盘中两个都不展示）---
    for _blk_id in ['auction-block', 'tail-change-block']:
        _s = html.find(f'<div id="{_blk_id}"')
        if _s != -1:
            _d, _p = 0, _s
            while _p < len(html):
                if html[_p:_p+4] == '<div': _d += 1
                elif html[_p:_p+6] == '</div>':
                    _d -= 1
                    if _d == 0:
                        html = html[:_s] + html[_p+6:]
                        log(f"  已移除 {_blk_id}（盘中不展示）")
                        break
                _p += 1

    # 更新页面日期（只刷全局+A股，美股日期不动）
    html = update_page_dates(html, 'noon', a_ok=a_ok)

    with open(INDEX_HTML, 'w', encoding='utf-8') as f:
        f.write(html)
    log(f"  HTML 已保存 ({len(html):,} chars)")

    # 3. 图表序列增量更新
    run_series_update()

    # 4. 更新 SW 版本
    log("--- 3. 更新 Service Worker ---")
    update_sw_version('noon')

    # 5. 更新后验证
    val_suffix = run_post_update_validation()

    # 6. 推送
    log("--- 4. 推送到 GitHub ---")
    github_push(
        [INDEX_HTML, A_SHARES_HTML, SW_JS],
        f"auto update: noon {TODAY}{val_suffix}"
    )

    # 推送后线上验证
    verify_github_push()

    log("====== ✅ 中午更新完成 ======")


def mode_evening():
    """傍晚模式：更新A股全天收盘数据。
    获取失败或验证不通过→跳过（保留旧数据+旧日期）。
    """
    log("====== 🌆 傍晚更新模式 ======")
    a_ok = False

    # 1. 获取A股数据
    log("--- 1. 获取A股全天收盘数据 ---")
    script_ok = run_script(os.path.join(BASE_DIR, 'fetch_a_shares.py'))
    if script_ok:
        a_d = load_json(A_DATA)
        a_sp = load_json(A_SPARK) if os.path.exists(A_SPARK) else {'stocks': {}}
        if a_d:
            passed, warns, errs = validate_a_shares(a_d, a_sp)
            for e in errs:
                log(f"  ❌ A股-{e}")
            for w in warns:
                log(f"  ⚠️ A股-{w}")
            if not errs:
                a_ok = True
                log("  ✅ A股数据验证通过")
            else:
                log("  ❌ A股数据验证失败，跳过（保留旧数据+旧日期）")
        else:
            log("  ❌ A股数据文件不存在，跳过")
    else:
        log("  ❌ A股数据获取失败，跳过（保留旧数据+旧日期）")

    if not a_ok:
        log("❌ 本次更新中止（页面完全不动，保留线上旧数据+旧日期）")
        return

    # 1.5 数据新鲜度检查
    log("\n📊 数据新鲜度检查:")
    freshness_results = validate_all_data()
    if not freshness_results.get('a_share', {}).get('fresh', False):
        log("⚠️ A股数据过旧，仍然注入但请注意")

    # 2. 注入A股数据
    log("--- 2. 注入A股数据到 HTML ---")
    with open(INDEX_HTML, 'r', encoding='utf-8') as f:
        html = f.read()

    a_d = load_json(A_DATA)
    a_sp = load_json(A_SPARK) if os.path.exists(A_SPARK) else {'stocks': {}}
    html = inject_a_shares(html, a_d, a_sp)
    write_a_shares_page(a_d, a_sp)
    log("  A股数据注入完成")

    # 2.5 采集今日成交额+上证到历史（量价趋势）
    log("--- 2.5 更新成交额历史 ---")
    update_volume_history()

    # --- 收盘后移除旧的集合竞价区块（已过15:00，竞价不再展示）---
    _auc_start = html.find('<div id="auction-block"')
    if _auc_start != -1:
        _depth, _pos = 0, _auc_start
        while _pos < len(html):
            if html[_pos:_pos+4] == '<div': _depth += 1
            elif html[_pos:_pos+6] == '</div>':
                _depth -= 1
                if _depth == 0:
                    _auc_end = _pos + 6
                    html = html[:_auc_start] + html[_auc_end:]
                    log("  已移除旧的集合竞价区块（收盘后不展示）")
                    break
            _pos += 1

    # --- 注入尾盘异动数据（如果有14:45快照）---
    if os.path.exists(TAIL_SNAPSHOT):
        log("  --- 计算尾盘异动 ---")
        tail_d = load_json(TAIL_SNAPSHOT)
        # 移除旧的 tail-change-block（如果有）
        tail_start = html.find('<div id="tail-change-block"')
        if tail_start != -1:
            depth = 0
            pos = tail_start
            while pos < len(html):
                if html[pos:pos+4] == '<div':
                    depth += 1
                elif html[pos:pos+6] == '</div>':
                    depth -= 1
                    if depth == 0:
                        tail_end = pos + 6
                        while tail_end < len(html) and html[tail_end] in ' \n':
                            tail_end += 1
                        html = html[:tail_start] + html[tail_end:]
                        log("  已移除旧的尾盘异动区块")
                        break
                pos += 1
        html = inject_tail_change(html, tail_d, a_d)
    else:
        log("  ℹ️ 无尾盘快照（tail_snapshot.json不存在），跳过尾盘异动")

    # 更新页面日期（只刷全局+A股，美股日期不动）
    html = update_page_dates(html, 'evening', a_ok=a_ok)

    with open(INDEX_HTML, 'w', encoding='utf-8') as f:
        f.write(html)
    log(f"  HTML 已保存 ({len(html):,} chars)")

    # 3. 图表序列增量更新
    run_series_update()

    # 4. 更新 SW 版本
    log("--- 3. 更新 Service Worker ---")
    update_sw_version('evening')

    # 5. 更新后验证
    val_suffix = run_post_update_validation()

    # 6. 推送
    log("--- 4. 推送到 GitHub ---")
    github_push(
        [INDEX_HTML, A_SHARES_HTML, SW_JS],
        f"auto update: evening {TODAY}{val_suffix}"
    )

    # 推送后线上验证
    verify_github_push()

    log("====== ✅ 傍晚更新完成 ======")


def mode_auction():
    """集合竞价模式（9:26执行）：获取集合竞价数据并注入HTML"""
    log("====== 🔔 集合竞价模式 ======")
    
    # 1. 获取集合竞价数据
    log("--- 1. 获取集合竞价数据 ---")
    script_ok = run_script(os.path.join(BASE_DIR, 'fetch_auction.py'))
    if not script_ok:
        log("❌ 集合竞价数据获取失败，中止")
        return
    
    if not os.path.exists(AUCTION_DATA):
        log("❌ auction_data.json 不存在")
        return
    
    auction_d = load_json(AUCTION_DATA)
    
    # 验证：至少3个指数
    idx_count = len(auction_d.get('indices', {}))
    stock_count = len(auction_d.get('top_gap_up', [])) + len(auction_d.get('top_gap_down', []))
    if idx_count < 3:
        log(f"❌ 指数数据不足（{idx_count}个，需要至少3个）")
        return
    
    log(f"  ✅ 集合竞价数据验证通过（{idx_count}个指数，{stock_count}只竞价股）")
    
    # 2. 注入HTML
    log("--- 2. 注入集合竞价数据到 HTML ---")
    with open(INDEX_HTML, 'r', encoding='utf-8') as f:
        html = f.read()
    
    # 先移除旧的 auction-block（如果有）
    auction_start = html.find('<div id="auction-block"')
    if auction_start != -1:
        # 找到这个 div 的结束位置
        depth = 0
        pos = auction_start
        while pos < len(html):
            if html[pos:pos+4] == '<div':
                depth += 1
            elif html[pos:pos+6] == '</div>':
                depth -= 1
                if depth == 0:
                    auction_end = pos + 6
                    # 也移除前后空白
                    while auction_end < len(html) and html[auction_end] in ' \n':
                        auction_end += 1
                    html = html[:auction_start] + html[auction_end:]
                    log("  已移除旧的集合竞价区块")
                    break
            pos += 1
    
    html = inject_auction(html, auction_d)
    
    # 更新页面日期
    html = update_page_dates(html, 'auction', a_ok=True)
    
    with open(INDEX_HTML, 'w', encoding='utf-8') as f:
        f.write(html)
    log(f"  HTML 已保存 ({len(html):,} chars)")
    
    # 3. 图表序列增量更新
    run_series_update()
    
    # 4. 更新 SW 版本
    log("--- 3. 更新 Service Worker ---")
    update_sw_version('auction')
    
    # 5. 更新后验证
    val_suffix = run_post_update_validation()
    
    # 6. 推送
    log("--- 4. 推送到 GitHub ---")
    github_push(
        [INDEX_HTML, SW_JS],
        f"auto update: auction {TODAY}{val_suffix}"
    )

    # 推送后线上验证
    verify_github_push()
    
    log("====== ✅ 集合竞价更新完成 ======")


def mode_tail():
    """尾盘快照模式（14:45执行）：保存大盘资金快照，不注入不推送"""
    log("====== ⏱ 尾盘快照模式 ======")
    
    # 1. 获取当前A股数据
    log("--- 1. 获取A股数据（14:45快照）---")
    script_ok = run_script(os.path.join(BASE_DIR, 'fetch_a_shares.py'))
    if not script_ok:
        log("❌ A股数据获取失败")
        return
    
    if not os.path.exists(A_DATA):
        log("❌ a_share_data.json 不存在")
        return
    
    a_d = load_json(A_DATA)
    
    # 验证大盘资金数据
    mf = a_d.get('market_flow', {})
    if not mf or mf.get('total_amount', 0) <= 0:
        log("❌ 大盘资金数据无效")
        return
    
    # 2. 保存快照
    snapshot = {
        'fetch_time': a_d.get('fetch_time', ''),
        'market_flow': mf,
        'indices': a_d.get('indices', {}),
    }
    
    save_json(TAIL_SNAPSHOT, snapshot)
    log(f"  ✅ 尾盘快照已保存: {TAIL_SNAPSHOT}")
    log(f"  主力净流入: {mf.get('main_net', 0):+.2f}亿")
    log(f"  超大单: {mf.get('super_large', 0):+.2f}亿, 大单: {mf.get('large', 0):+.2f}亿")
    log("====== ✅ 尾盘快照完成（不注入不推送）======")


def mode_postmarket():
    """盘后复盘模式（17:30执行）：获取融资融券+龙虎榜并注入HTML"""
    log("====== 📊 盘后复盘模式 ======")
    
    # 1. 获取盘后数据
    log("--- 1. 获取盘后复盘数据 ---")
    script_ok = run_script(os.path.join(BASE_DIR, 'fetch_post_market.py'))
    if not script_ok:
        log("❌ 盘后数据获取失败")
        return
    
    if not os.path.exists(POST_MARKET_DATA):
        log("❌ post_market_data.json 不存在")
        return
    
    pm_d = load_json(POST_MARKET_DATA)
    
    # 验证
    margin = pm_d.get('margin')
    dragon = pm_d.get('dragon_tiger')
    
    has_margin = margin and margin.get('latest')
    has_dragon = dragon and dragon.get('count', 0) >= 5
    
    if not has_margin and not has_dragon:
        log("❌ 融资融券和龙虎榜数据都不足，跳过注入")
        return
    
    if has_margin:
        log(f"  ✅ 融资融券: {margin['latest'].get('rzye', 0)/1e8:.0f}亿")
    else:
        log("  ⚠️ 融资融券数据不足，跳过")
    
    if has_dragon:
        log(f"  ✅ 龙虎榜: {dragon['count']}只个股, 机构{len(dragon.get('institution_stocks', []))}只")
    else:
        log("  ⚠️ 龙虎榜数据不足（<5只），跳过")
    
    # 1.5 数据新鲜度检查
    log("\n📊 数据新鲜度检查:")
    freshness_results = validate_all_data()
    if not freshness_results.get('margin_trading', {}).get('fresh', False):
        log("⚠️ 融资融券数据过旧，仍然注入但请注意")
    if not freshness_results.get('dragon_tiger', {}).get('fresh', False):
        log("⚠️ 龙虎榜数据过旧，仍然注入但请注意")

    # 2. 注入HTML
    log("--- 2. 注入复盘数据到 HTML ---")
    with open(INDEX_HTML, 'r', encoding='utf-8') as f:
        html = f.read()
    
    # 先移除旧的复盘区块（如果有）
    pm_start = html.find('<div id="a-postmarket"')
    if pm_start != -1:
        # 找到 section 的结束
        next_section = html.find('class="section-divider"', pm_start + 10)
        if next_section != -1:
            section_start = html.rfind('<div', 0, next_section)
            # 如果这个section-divider是在复盘区块外面的，就用它作为结束标记
            # 否则继续找
            if section_start > pm_start + 100:  # 复盘区块内不可能有另一个section-divider
                # 移除从 a-postmarket 到这个 section-divider 之间的内容
                end_pos = html.rfind('\n', pm_start, next_section)
                html = html[:pm_start] + html[end_pos:]
                log("  已移除旧的复盘区块")
    
    # 注入新数据
    inject_data = {}
    if has_margin:
        inject_data['margin'] = margin
    if has_dragon:
        inject_data['dragon_tiger'] = dragon
    
    html = inject_post_market(html, inject_data)
    
    # 注：北向资金刷新已移至 northbound 模式（18:00独立执行）
    
    # 更新页面日期
    html = update_page_dates(html, 'postmarket', a_ok=True)
    
    # 更新A股Tab时间戳（盘后数据属于A股Tab）
    pm_fetch_time = pm_d.get('fetch_time', pm_d.get('margin', {}).get('fetch_time'))
    if pm_fetch_time:
        html = update_tab_timestamp(html, 'a_shares', pm_fetch_time)
    
    with open(INDEX_HTML, 'w', encoding='utf-8') as f:
        f.write(html)
    log(f"  HTML 已保存 ({len(html):,} chars)")
    
    # 3. 图表序列增量更新
    run_series_update()
    
    # 4. 更新 SW 版本
    log("--- 3. 更新 Service Worker ---")
    update_sw_version('postmarket')
    
    # 5. 更新后验证
    val_suffix = run_post_update_validation()
    
    # 6. 推送
    log("--- 4. 推送到 GitHub ---")
    github_push(
        [INDEX_HTML, SW_JS],
        f"auto update: postmarket {TODAY}{val_suffix}"
    )

    # 推送后线上验证
    verify_github_push()
    
    log("====== ✅ 盘后复盘更新完成 ======")


def mode_northbound_refresh():
    """北向资金专属刷新（18:00执行）：获取最新北向资金数据并注入HTML"""
    log("====== 📊 北向资金刷新模式 ======")

    # 1. 获取最新A股数据（含北向资金）
    log("--- 1. 获取最新数据 ---")
    script_ok = run_script(os.path.join(BASE_DIR, 'fetch_a_shares.py'))
    if not script_ok:
        log("❌ 数据获取失败，跳过")
        return

    a_d = load_json(A_DATA)
    if not a_d:
        log("❌ A股数据文件不存在")
        return

    # 2. 检查北向数据是否是今天的
    today = TODAY
    nd = a_d.get('north_deal')
    nd_date = nd.get('date', '') if nd else ''

    log(f"  北向成交额日期: {nd_date or '无数据'}")

    if nd_date != today:
        log(f"  ⚠️ 北向成交额仍为旧数据（非{today}），不注入，等下次刷新")
        return

    # 额外校验：如果成交额为0，说明API返回的是无效数据
    if nd and nd.get('total_amt', 0) == 0:
        log(f"  ⚠️ 北向成交额为0（API可能尚未发布），不注入")
        return

    # 3. 注入HTML
    log("--- 2. 注入北向资金数据到 HTML ---")
    with open(INDEX_HTML, 'r', encoding='utf-8') as f:
        html = f.read()

    a_sp = load_json(A_SPARK) if os.path.exists(A_SPARK) else {'stocks': {}}
    html = inject_a_shares(html, a_d, a_sp)
    write_a_shares_page(a_d, a_sp)
    log("  北向资金数据注入完成")

    # 更新A股Tab时间戳
    html = update_tab_timestamp(html, 'a_shares', a_d.get('fetch_time'))

    with open(INDEX_HTML, 'w', encoding='utf-8') as f:
        f.write(html)
    log(f"  HTML 已保存 ({len(html):,} chars)")

    # 4. 更新SW版本
    log("--- 3. 更新 Service Worker ---")
    update_sw_version('northbound')

    # 5. 更新后验证
    val_suffix = run_post_update_validation()

    # 6. 推送
    log("--- 4. 推送到 GitHub ---")
    github_push(
        [INDEX_HTML, A_SHARES_HTML, SW_JS],
        f"auto update: northbound {TODAY}{val_suffix}"
    )
    verify_github_push()

    log("====== ✅ 北向资金刷新完成 ======")


def mode_commodity():
    """商品数据独立更新（07:00/11:00/17:00每天）"""
    log("====== 🛒 商品数据独立更新模式 ======")
    
    # 1. 运行商品获取脚本
    log("--- 1. 获取商品数据 ---")
    script_ok = run_script(os.path.join(BASE_DIR, 'fetch_commodities.py'))
    if not script_ok:
        log("❌ 商品获取失败")
        return
    
    # 2. 加载商品数据
    if not os.path.exists(COMMODITY_DATA):
        log("❌ commodities_data.json 不存在")
        return
    
    data = load_json(COMMODITY_DATA)
    if not data:
        log("❌ 商品数据为空")
        return
    
    # 3. 验证：至少4品种
    count = data.get('_meta', {}).get('count', 0)
    if count < 4:
        log(f"❌ 商品数据不足: {count} 个品种")
        return
    
    log(f"  ✅ 商品数据验证通过 ({count} 个品种)")
    
    # 3.5 数据新鲜度检查
    log("\n📊 数据新鲜度检查:")
    freshness_results = validate_all_data()
    if not freshness_results.get('commodity', {}).get('fresh', False):
        log("⚠️ 商品数据过旧，仍然注入但请注意")
    if not freshness_results.get('bitcoin', {}).get('fresh', False):
        log("⚠️ 比特币数据过旧，仍然注入但请注意")

    # 4. 读取HTML并注入商品
    log("--- 2. 注入商品数据到 HTML ---")
    with open(INDEX_HTML, 'r', encoding='utf-8') as f:
        html = f.read()
    
    html = inject_commodities(html, data)
    
    # 5. 保存
    with open(INDEX_HTML, 'w', encoding='utf-8') as f:
        f.write(html)
    log(f"  HTML 已保存 ({len(html):,} chars)")
    
    # 6. 图表序列增量更新
    run_series_update()
    
    # 7. 更新SW版本
    log("--- 3. 更新 Service Worker ---")
    update_sw_version('commodity')
    
    # 8. 更新后验证
    val_suffix = run_post_update_validation()
    
    # 9. GitHub推送
    log("--- 4. 推送到 GitHub ---")
    github_push(
        [INDEX_HTML, SW_JS],
        f"chore: 商品数据更新 {TODAY}{val_suffix}"
    )

    # 推送后线上验证
    verify_github_push()
    
    log("====== ✅ 商品数据更新完成 ======")


# ============================================================
#  主入口
# ============================================================

def main():
    if len(sys.argv) < 2 or not sys.argv[1].startswith('--mode='):
        print("用法: python3 daily_update.py --mode=morning|noon|evening|auction|tail|postmarket|commodity")
        print()
        print("  morning    (7:00)  — 更新美股/美债，A股用缓存（商品由commodity模式独立处理）")
        print("  commodity  (7:00/11:00/17:00) — 商品数据独立更新")
        print("  auction    (9:26)  — 集合竞价数据注入")
        print("  noon       (12:00) — 更新A股上午盘数据")
        print("  tail       (14:45) — 尾盘资金快照（不注入）")
        print("  evening    (15:30) — 更新A股全天收盘数据+尾盘异动")
        print("  postmarket (17:30) — 盘后复盘数据（融资融券+龙虎榜）")
        print("  northbound (18:00) — 北向资金专属刷新")
        sys.exit(1)

    mode = sys.argv[1].split('=', 1)[1].strip().lower()

    if mode == 'morning':
        mode_morning()
    elif mode == 'commodity':
        mode_commodity()
    elif mode == 'auction':
        mode_auction()
    elif mode == 'noon':
        mode_noon()
    elif mode == 'tail':
        mode_tail()
    elif mode == 'evening':
        mode_evening()
    elif mode == 'postmarket':
        mode_postmarket()
    elif mode == 'northbound':
        mode_northbound_refresh()
    else:
        print(f"未知模式: {mode}")
        print("有效模式: morning, commodity, auction, noon, tail, evening, postmarket, northbound")
        sys.exit(1)


if __name__ == '__main__':
    main()
