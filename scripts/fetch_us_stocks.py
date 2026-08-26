#!/usr/bin/env python3
"""
美股数据获取 + 看板HTML生成
数据源：
  - 历史K线：新浪财经美股日K（JSONP，免费，数据完整）
  - 实时报价：腾讯财经（GBK编码，含涨跌幅）
  - VIX实时：腾讯财经
  - VIX历史趋势：VIXY ETF（新浪K线）
"""

import urllib.request
import json
import re
import datetime
import os
import sys

# ============ 配置 ============
DASHBOARD_DIR = "/Coze/Drive/扣子/treasury_dashboard"
OUTPUT_HTML = os.path.join(DASHBOARD_DIR, "index.html")
TODAY = datetime.date.today().strftime("%Y-%m-%d")

# 指数定义
INDICES = [
    {"sina": ".DJI",  "tencent": "usDJI",  "label": "道琼斯",   "en": "Dow Jones",     "color": "#3b82f6", "decimals": 0},
    {"sina": ".IXIC", "tencent": "usIXIC", "label": "纳斯达克", "en": "NASDAQ",        "color": "#10b981", "decimals": 0},
    {"sina": ".INX",  "tencent": "usINX",  "label": "标普500",  "en": "S&P 500",       "color": "#f59e0b", "decimals": 0},
    {"sina": ".SOX",  "tencent": "usSOX",  "label": "费城半导体", "en": "PHLX Semicon", "color": "#ef4444", "decimals": 0},
]

# VIX
VIX_TENCENT = "usVIX"
VIXY_SINA = "VIXY"  # VIX短期期货ETF，作为历史趋势代理

# 11大板块ETF
SECTOR_ETFS = [
    {"sina": "XLK",  "label": "科技",       "en": "Technology",       "color": "#3b82f6"},
    {"sina": "XLF",  "label": "金融",       "en": "Financials",       "color": "#10b981"},
    {"sina": "XLE",  "label": "能源",       "en": "Energy",           "color": "#f59e0b"},
    {"sina": "XLV",  "label": "医疗",       "en": "Health Care",      "color": "#ef4444"},
    {"sina": "XLI",  "label": "工业",       "en": "Industrials",      "color": "#8b5cf6"},
    {"sina": "XLY",  "label": "可选消费",   "en": "Cons. Disc.",      "color": "#ec4899"},
    {"sina": "XLP",  "label": "必需消费",   "en": "Cons. Staples",    "color": "#06b6d4"},
    {"sina": "XLU",  "label": "公用事业",   "en": "Utilities",        "color": "#84cc16"},
    {"sina": "XLB",  "label": "材料",       "en": "Materials",        "color": "#f97316"},
    {"sina": "XLRE", "label": "房地产",     "en": "Real Estate",      "color": "#a855f7"},
    {"sina": "XLC",  "label": "通讯服务",   "en": "Comm. Services",   "color": "#14b8a6"},
]

# 行业/主题ETF
THEME_ETFS = [
    {"sina": "SMH",  "label": "半导体ETF",   "en": "VanEck Semicon",   "color": "#ef4444"},
    {"sina": "SOXX", "label": "半导体iShares","en": "iShares Semicon", "color": "#f97316"},
    {"sina": "GLD",  "label": "黄金ETF",     "en": "SPDR Gold",        "color": "#ffd700"},
    {"sina": "SLV",  "label": "白银ETF",     "en": "iShares Silver",   "color": "#c0c0c0"},
    {"sina": "GDX",  "label": "金矿ETF",     "en": "Gold Miners",      "color": "#d4a017"},
    {"sina": "USO",  "label": "原油ETF",     "en": "US Oil Fund",      "color": "#8b5cf6"},
    {"sina": "TLT",  "label": "长债ETF",     "en": "20+ Yr Treasury",  "color": "#06b6d4"},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
    "Referer": "https://finance.sina.com.cn/",
}


# ============ 数据获取 ============

def fetch_sina_daily(symbol):
    """从新浪获取美股日K历史数据"""
    url = f"https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var=/US_MinKService.getDailyK?symbol={symbol}&___qn=3"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        text = resp.read().decode("utf-8")
        m = re.search(r"var=\((\[.*?\])\)", text, re.DOTALL)
        if not m:
            print(f"  [WARN] {symbol}: no JSONP match")
            return []
        data = json.loads(m.group(1))
        if not data:
            print(f"  [WARN] {symbol}: empty data")
            return []
        # 统一格式: [{date, open, high, low, close, volume}]
        result = []
        for item in data:
            try:
                result.append({
                    "date": item["d"],
                    "open": float(item["o"]),
                    "high": float(item["h"]),
                    "low": float(item["l"]),
                    "close": float(item["c"]),
                    "volume": int(float(item.get("v", 0))),
                })
            except (ValueError, KeyError):
                continue
        return result
    except Exception as e:
        print(f"  [ERROR] {symbol}: {e}")
        return []


def fetch_tencent_realtime(codes):
    """从腾讯获取实时行情，codes如 ['usDJI','usXLK']"""
    url = f"http://qt.gtimg.cn/q={','.join(codes)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        raw = resp.read().decode("gbk", errors="replace")
    except Exception as e:
        print(f"  [ERROR] tencent realtime: {e}")
        return {}

    result = {}
    for line in raw.strip().split(";"):
        line = line.strip()
        if not line or "=" not in line:
            continue
        eq_pos = line.index("=")
        key = line[:eq_pos].replace("v_", "")
        val = line[eq_pos + 2:-1]  # remove surrounding quotes
        parts = val.split("~")
        if len(parts) < 35:
            continue
        try:
            result[key] = {
                "name": parts[1],
                "price": float(parts[3]) if parts[3] else 0,
                "prev_close": float(parts[4]) if parts[4] else 0,
                "open": float(parts[5]) if parts[5] else 0,
                "change": float(parts[31]) if parts[31] else 0,
                "change_pct": float(parts[32]) if parts[32] else 0,
                "high": float(parts[33]) if parts[33] else 0,
                "low": float(parts[34]) if parts[34] else 0,
                "time": parts[30] if len(parts) > 30 else "",
            }
        except (ValueError, IndexError):
            continue
    return result


def compute_stats(bars, decimals=2):
    """计算52周统计数据"""
    if not bars:
        return None
    closes = [b["close"] for b in bars]
    latest = closes[-1]
    prev = closes[-2] if len(closes) >= 2 else latest

    # 52周 ≈ 252个交易日
    lookback = min(252, len(bars))
    recent_bars = bars[-lookback:]
    high_52w = max(b["high"] for b in recent_bars)
    low_52w = min(b["low"] for b in recent_bars)

    # 找最高最低日期
    high_bar = max(recent_bars, key=lambda b: b["high"])
    low_bar = min(recent_bars, key=lambda b: b["low"])

    avg_52w = sum(c for c in closes[-lookback:]) / lookback

    return {
        "latest": round(latest, decimals),
        "prev": round(prev, decimals),
        "change": round(latest - prev, decimals),
        "change_pct": round((latest - prev) / prev * 100, 2) if prev else 0,
        "high_52w": round(high_52w, decimals),
        "low_52w": round(low_52w, decimals),
        "high_date": high_bar["date"],
        "low_date": low_bar["date"],
        "avg_52w": round(avg_52w, decimals),
        "data_points": len(bars),
    }


def build_series(bars, decimals=2):
    """构建JS图表数据结构"""
    if not bars:
        return None
    dates_all = [b["date"] for b in bars]
    values_all = [round(b["close"], decimals) for b in bars]

    # 近30天
    recent = bars[-30:]
    dates_recent = [b["date"] for b in recent]
    values_recent = [round(b["close"], decimals) for b in recent]

    stats = compute_stats(bars, decimals)

    return {
        "dates_all": dates_all,
        "values_all": values_all,
        "dates_recent": dates_recent,
        "values_recent": values_recent,
        "stats": stats,
    }


# ============ HTML 生成 ============

def fmt_num(val, decimals=0):
    if decimals == 0:
        return f"{val:,.0f}"
    return f"{val:,.{decimals}f}"


def chg_class(val):
    if val > 0:
        return "up"
    elif val < 0:
        return "down"
    return "flat"


def chg_icon(val):
    if val > 0:
        return "▲"
    elif val < 0:
        return "▼"
    return "—"


def generate_html(us_data):
    """生成完整HTML，将美股Tab嵌入现有看板"""

    # 读取现有HTML以提取SERIES_DATA等核心JS
    # 我们采用全新生成的方式，确保完整性

    indices_js = {}
    for idx in INDICES:
        key = idx["sina"].replace(".", "")
        if key in us_data and us_data[key]:
            s = us_data[key]
            indices_js[key] = {
                "label": idx["label"],
                "en": idx["en"],
                "color": idx["color"],
                "decimals": idx["decimals"],
                **s,
            }

    # 板块ETF
    sector_js = {}
    for etf in SECTOR_ETFS:
        sym = etf["sina"]
        if sym in us_data and us_data[sym]:
            s = us_data[sym]
            sector_js[sym] = {
                "label": etf["label"],
                "en": etf["en"],
                "color": etf["color"],
                **s,
            }

    # 主题ETF
    theme_js = {}
    for etf in THEME_ETFS:
        sym = etf["sina"]
        if sym in us_data and us_data[sym]:
            s = us_data[sym]
            theme_js[sym] = {
                "label": etf["label"],
                "en": etf["en"],
                "color": etf["color"],
                **s,
            }

    # VIXY
    vixy_js = us_data.get("VIXY")

    # 实时行情
    rt = us_data.get("_realtime", {})
    vix_rt = rt.get("usVIX", {})

    # 生成指数概览卡片
    overview_cards = ""
    for idx in INDICES:
        key = idx["sina"].replace(".", "")
        if key not in indices_js:
            continue
        s = indices_js[key]
        st = s["stats"]
        tcode = idx["tencent"]
        rt_info = rt.get(tcode, {})
        # 优先用实时涨跌幅
        chg_pct = rt_info.get("change_pct", st["change_pct"])
        chg_val = rt_info.get("change", st["change"])
        price = rt_info.get("price", st["latest"])
        c = chg_class(chg_pct)
        icon = chg_icon(chg_pct)
        dec = idx["decimals"]
        if dec == 0:
            price_str = fmt_num(price, 0)
            chg_str = f"{icon}{fmt_num(abs(chg_val),0)} ({chg_pct:+.2f}%)"
        else:
            price_str = fmt_num(price, dec)
            chg_str = f"{icon}{fmt_num(abs(chg_val),dec)} ({chg_pct:+.2f}%)"

        overview_cards += f'''
            <div class="ov-card" style="border-top: 3px solid {idx['color']};">
              <div class="ov-label">{idx['label']}</div>
              <div class="ov-value">{price_str}</div>
              <div class="ov-chg {c}">{chg_str}</div>
            </div>'''

    # VIX卡片
    vix_price = vix_rt.get("price", 0)
    vix_chg_pct = vix_rt.get("change_pct", 0)
    vix_c = chg_class(vix_chg_pct) if vix_chg_pct != 0 else "flat"
    vix_icon = chg_icon(vix_chg_pct)
    vix_time = vix_rt.get("time", "")
    # VIX > 20 恐慌, < 15 贪婪
    vix_level = "恐慌区间" if vix_price >= 25 else ("偏高" if vix_price >= 20 else ("中性" if vix_price >= 15 else "低波/贪婪"))
    vix_level_color = "#ef4444" if vix_price >= 25 else ("#f59e0b" if vix_price >= 20 else ("#10b981" if vix_price < 15 else "#9ca3af"))

    # 生成指数详情区块
    index_blocks = ""
    for idx in INDICES:
        key = idx["sina"].replace(".", "")
        if key not in indices_js:
            continue
        s = indices_js[key]
        st = s["stats"]
        tcode = idx["tencent"]
        rt_info = rt.get(tcode, {})
        price = rt_info.get("price", st["latest"])
        chg_pct = rt_info.get("change_pct", st["change_pct"])
        chg_val = rt_info.get("change", st["change"])
        c = chg_class(chg_pct)
        icon = chg_icon(chg_pct)
        dec = idx["decimals"]

        index_blocks += f'''
        <section class="us-block" style="border-left: 4px solid {idx['color']};">
          <div class="tenor-header">
            <div class="tenor-title" style="color: {idx['color']};">{idx['label']}（{idx['en']}）</div>
            <div class="tenor-yield">
              <span class="yield-num">{fmt_num(price, dec)}</span>
              <span class="yield-chg {c}">
                <span class="chg-icon">{icon}</span>{fmt_num(abs(chg_val), dec)} ({chg_pct:+.2f}%)
              </span>
            </div>
          </div>
          <div class="tenor-meta">
            <div class="meta-item">
              <span class="meta-label">52周最高</span>
              <span class="meta-val high">{fmt_num(st['high_52w'], dec)}</span>
              <span class="meta-date">{st['high_date']}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">52周最低</span>
              <span class="meta-val low">{fmt_num(st['low_52w'], dec)}</span>
              <span class="meta-date">{st['low_date']}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">52周均值</span>
              <span class="meta-val">{fmt_num(st['avg_52w'], dec)}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">数据点</span>
              <span class="meta-val">{st['data_points']} 个交易日</span>
            </div>
          </div>
          <div class="tenor-charts">
            <div class="chart-half">
              <div class="chart-subtitle">近1年走势</div>
              <div id="chart_{key}_1y" class="chart-tall"></div>
            </div>
            <div class="chart-half">
              <div class="chart-subtitle">近30天放大</div>
              <div id="chart_{key}_30d" class="chart-tall"></div>
            </div>
          </div>
        </section>'''

    # 生成板块ETF涨跌条形图数据
    sector_bar_data = []
    for etf in SECTOR_ETFS:
        sym = etf["sina"]
        if sym not in sector_js:
            continue
        s = sector_js[sym]
        st = s["stats"]
        rt_info = rt.get(f"us{sym}", {})
        chg_pct = rt_info.get("change_pct", st["change_pct"])
        price = rt_info.get("price", st["latest"])
        sector_bar_data.append({
            "name": etf["label"],
            "en": etf["en"],
            "symbol": sym,
            "price": price,
            "change_pct": chg_pct,
            "color": etf["color"],
        })

    # 按涨跌幅排序
    sector_bar_data.sort(key=lambda x: x["change_pct"], reverse=True)

    # 板块表格行
    sector_table_rows = ""
    for i, d in enumerate(sector_bar_data):
        c = chg_class(d["change_pct"])
        sector_table_rows += f'''
            <tr>
              <td class="rank-cell">{i+1}</td>
              <td class="name-cell">
                <span class="sector-dot" style="background:{d['color']}"></span>
                {d['name']}
                <span class="sector-en">{d['en']}</span>
              </td>
              <td class="price-cell">${d['price']:.2f}</td>
              <td class="chg-cell {c}">{d['change_pct']:+.2f}%</td>
            </tr>'''

    # 主题ETF表格
    theme_table_rows = ""
    for etf in THEME_ETFS:
        sym = etf["sina"]
        if sym not in theme_js:
            continue
        s = theme_js[sym]
        st = s["stats"]
        rt_info = rt.get(f"us{sym}", {})
        chg_pct = rt_info.get("change_pct", st["change_pct"])
        price = rt_info.get("price", st["latest"])
        c = chg_class(chg_pct)
        theme_table_rows += f'''
            <tr>
              <td class="name-cell">
                <span class="sector-dot" style="background:{etf['color']}"></span>
                {etf['label']}
                <span class="sector-en">{sym}</span>
              </td>
              <td class="price-cell">${price:.2f}</td>
              <td class="chg-cell {c}">{chg_pct:+.2f}%</td>
              <td class="chg-cell">{fmt_num(st['high_52w'],2)}</td>
              <td class="chg-cell">{fmt_num(st['low_52w'],2)}</td>
            </tr>'''

    # VIXY图表
    vixy_chart = ""
    if vixy_js:
        vst = vixy_js["stats"]
        vixy_rt = rt.get("usVIXY", {})
        vixy_price = vixy_rt.get("price", vst["latest"])
        vixy_chg = vixy_rt.get("change_pct", vst["change_pct"])
        vc = chg_class(vixy_chg)
        vicon = chg_icon(vixy_chg)
        vixy_chart = f'''
        <section class="us-block" style="border-left: 4px solid #f97316;">
          <div class="tenor-header">
            <div>
              <div class="tenor-title" style="color: #f97316;">VIX 恐慌指数趋势（VIXY 代理）</div>
              <div style="font-size:11px;color:#6b7280;margin-top:4px;">VIXY为VIX短期期货ETF，用于观察波动率趋势方向</div>
            </div>
            <div class="tenor-yield">
              <div style="text-align:right;">
                <div class="yield-num" style="font-size:24px;">${vixy_price:.2f}</div>
                <div class="yield-chg {vc}" style="font-size:12px;">{vicon}{vixy_chg:+.2f}%</div>
              </div>
            </div>
          </div>
          <div class="tenor-charts">
            <div class="chart-half">
              <div class="chart-subtitle">近1年走势</div>
              <div id="chart_VIXY_1y" class="chart-tall"></div>
            </div>
            <div class="chart-half">
              <div class="chart-subtitle">近30天放大</div>
              <div id="chart_VIXY_30d" class="chart-tall"></div>
            </div>
          </div>
        </section>'''

    # JS数据序列化
    all_us_series = {}
    for idx in INDICES:
        key = idx["sina"].replace(".", "")
        if key in indices_js:
            s = indices_js[key]
            all_us_series[key] = {
                "label": s["label"], "color": s["color"], "decimals": s["decimals"],
                "dates_all": s["dates_all"], "values_all": s["values_all"],
                "dates_recent": s["dates_recent"], "values_recent": s["values_recent"],
                "stats": s["stats"],
            }

    for sym, s in sector_js.items():
        all_us_series[sym] = {
            "label": s["label"], "color": s["color"], "decimals": 2,
            "dates_all": s["dates_all"], "values_all": s["values_all"],
            "dates_recent": s["dates_recent"], "values_recent": s["values_recent"],
            "stats": s["stats"],
        }

    for sym, s in theme_js.items():
        all_us_series[sym] = {
            "label": s["label"], "color": s["color"], "decimals": 2,
            "dates_all": s["dates_all"], "values_all": s["values_all"],
            "dates_recent": s["dates_recent"], "values_recent": s["values_recent"],
            "stats": s["stats"],
        }

    if vixy_js:
        all_us_series["VIXY"] = {
            "label": "VIXY", "color": "#f97316", "decimals": 2,
            "dates_all": vixy_js["dates_all"], "values_all": vixy_js["values_all"],
            "dates_recent": vixy_js["dates_recent"], "values_recent": vixy_js["values_recent"],
            "stats": vixy_js["stats"],
        }

    # 板块ETF图表 - 当日涨跌幅横向条形图
    sector_chart_names = json.dumps([d["name"] for d in sector_bar_data], ensure_ascii=False)
    sector_chart_values = json.dumps([d["change_pct"] for d in sector_bar_data])
    sector_chart_colors = json.dumps([("#ef4444" if d["change_pct"] < 0 else "#10b981") for d in sector_bar_data])

    rt_time = ""
    for k, v in rt.items():
        if v.get("time"):
            rt_time = v["time"]
            break

    return all_us_series, {
        "overview_cards": overview_cards,
        "index_blocks": index_blocks,
        "vix_card": {
            "price": vix_price,
            "chg_pct": vix_chg_pct,
            "level": vix_level,
            "level_color": vix_level_color,
            "time": vix_time,
        },
        "sector_table_rows": sector_table_rows,
        "theme_table_rows": theme_table_rows,
        "vixy_chart": vixy_chart,
        "sector_chart": {
            "names": sector_chart_names,
            "values": sector_chart_values,
            "colors": sector_chart_colors,
        },
        "rt_time": rt_time,
    }


# ============ 主流程 ============

def main():
    print(f"=== 美股数据获取 {TODAY} ===\n")

    us_data = {}

    # 1. 获取指数历史K线
    print("[1/4] 获取美股指数历史K线...")
    for idx in INDICES:
        sym = idx["sina"]
        print(f"  {idx['label']} ({sym})...", end=" ", flush=True)
        bars = fetch_sina_daily(sym)
        key = sym.replace(".", "")
        if bars:
            us_data[key] = build_series(bars, idx["decimals"])
            print(f"{len(bars)} bars, latest={bars[-1]['date']} close={bars[-1]['close']}")
        else:
            print("FAILED")

    # 2. 获取板块ETF
    print("\n[2/4] 获取11大板块ETF历史K线...")
    for etf in SECTOR_ETFS:
        sym = etf["sina"]
        print(f"  {etf['label']} ({sym})...", end=" ", flush=True)
        bars = fetch_sina_daily(sym)
        if bars:
            us_data[sym] = build_series(bars, 2)
            print(f"{len(bars)} bars, close={bars[-1]['close']}")
        else:
            print("FAILED")

    # 3. 获取主题ETF
    print("\n[3/4] 获取主题/行业ETF历史K线...")
    for etf in THEME_ETFS:
        sym = etf["sina"]
        print(f"  {etf['label']} ({sym})...", end=" ", flush=True)
        bars = fetch_sina_daily(sym)
        if bars:
            us_data[sym] = build_series(bars, 2)
            print(f"{len(bars)} bars, close={bars[-1]['close']}")
        else:
            print("FAILED")

    # VIXY
    print(f"  VIXY (VIX趋势代理)...", end=" ", flush=True)
    bars = fetch_sina_daily("VIXY")
    if bars:
        us_data["VIXY"] = build_series(bars, 2)
        print(f"{len(bars)} bars")
    else:
        print("FAILED")

    # 4. 获取实时行情
    print("\n[4/4] 获取腾讯实时行情...")
    all_codes = [idx["tencent"] for idx in INDICES]
    all_codes += ["usVIX", "usVIXY"]
    all_codes += [f"us{e['sina']}" for e in SECTOR_ETFS]
    all_codes += [f"us{e['sina']}" for e in THEME_ETFS]
    rt = fetch_tencent_realtime(all_codes)
    us_data["_realtime"] = rt
    for k, v in rt.items():
        print(f"  {k}: {v['name']} = {v['price']} ({v['change_pct']:+.2f}%)")

    # 5. 生成HTML片段和JS数据
    print("\n[5/5] 生成HTML...")
    us_series, html_parts = generate_html(us_data)

    # 保存中间数据为JSON供后续嵌入
    output = {
        "date": TODAY,
        "series": us_series,
        "html": html_parts,
    }

    out_path = "/Coze/Drive/金融分析/us_stock_data.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n数据已保存到 {out_path}")
    print(f"指数: {len([k for k in us_series if k in ['DJI','IXIC','INX','SOX']])}")
    print(f"板块ETF: {len(SECTOR_ETFS)}")
    print(f"主题ETF: {len(THEME_ETFS)}")
    print("完成！")


if __name__ == "__main__":
    main()
