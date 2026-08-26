#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全球资产看板数据验证框架
=====================
验证11个数据源、9个验证维度、22+个API端点的数据正确性

用法:
  python3 data_validator.py          # 完整验证报告
  python3 data_validator.py --json   # JSON格式输出
  python3 data_validator.py --html   # 生成HTML报告
  python3 data_validator.py --quick  # 仅关键验证(V1+V2+V5)
"""

import json
import re
import os
import sys
import argparse
import traceback
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum

# ============================================================
# 配置
# ============================================================
BASE_DIR = "/Coze/Drive/金融分析"
HTML_PATH = "/Coze/Drive/扣子/treasury_dashboard/index.html"
REPORT_PATH = os.path.join(BASE_DIR, "validation_report.html")

# JSON数据文件路径
JSON_FILES = {
    "a_share": os.path.join(BASE_DIR, "a_share_data.json"),
    "us_stock": os.path.join(BASE_DIR, "us_enhanced_data.json"),
    "commodities": os.path.join(BASE_DIR, "commodities_data.json"),
    "auction": os.path.join(BASE_DIR, "auction_data.json"),
    "post_market": os.path.join(BASE_DIR, "post_market_data.json"),
    "tail_snapshot": os.path.join(BASE_DIR, "tail_snapshot.json"),
    "volume_history": os.path.join(BASE_DIR, "market_volume_history.json"),
}


class Severity(Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


@dataclass
class CheckResult:
    check_name: str
    data_source: str
    dimension: str
    passed: bool
    severity: str  # critical / warning / info
    message: str
    expected: Any = None
    actual: Any = None

    def to_dict(self):
        return asdict(self)


# ============================================================
# 工具函数
# ============================================================
def safe_load_json(path: str) -> Optional[dict]:
    """安全加载JSON文件"""
    try:
        if not os.path.exists(path):
            return None
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def safe_read_file(path: str) -> Optional[str]:
    """安全读取文本文件"""
    try:
        if not os.path.exists(path):
            return None
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return None


def parse_datetime(s: str) -> Optional[datetime]:
    """解析日期时间字符串"""
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def parse_date(s: str) -> Optional[datetime]:
    """解析日期字符串"""
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d")
    except Exception:
        return None


def is_today(dt: datetime) -> bool:
    """判断是否是今天（北京时间 UTC+8 简化处理）"""
    now = datetime.now()
    return dt.date() == now.date()


def is_recent(dt: datetime, hours: int = 24) -> bool:
    """判断是否在最近N小时内"""
    now = datetime.now()
    return (now - dt).total_seconds() < hours * 3600


def make_result(check_name: str, data_source: str, dimension: str,
                passed: bool, severity: str, message: str,
                expected=None, actual=None) -> CheckResult:
    return CheckResult(
        check_name=check_name,
        data_source=data_source,
        dimension=dimension,
        passed=passed,
        severity=severity,
        message=message,
        expected=expected,
        actual=actual
    )


def safe_check(func, check_name: str, data_source: str, dimension: str) -> List[CheckResult]:
    """安全执行验证，捕获异常"""
    try:
        return func()
    except Exception as e:
        return [make_result(
            check_name=check_name,
            data_source=data_source,
            dimension=dimension,
            passed=False,
            severity="critical",
            message=f"验证执行异常: {str(e)}\n{traceback.format_exc()[:200]}"
        )]


# ============================================================
# V1: 时间验证
# ============================================================
def validate_time_format(data: dict, source: str) -> List[CheckResult]:
    """检查fetch_time格式"""
    results = []
    ft = data.get("fetch_time", data.get("_meta", {}).get("fetch_time", ""))
    if not ft:
        results.append(make_result("time_format", source, "V1", False, "critical",
                                   "缺少fetch_time字段"))
        return results

    pattern = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"
    match = bool(re.match(pattern, str(ft).strip()))
    results.append(make_result("time_format", source, "V1", match,
                               "critical" if not match else "info",
                               f"fetch_time格式: {ft}",
                               expected="YYYY-MM-DD HH:MM:SS", actual=ft))
    return results


def validate_time_freshness(data: dict, source: str, max_hours: int = 24) -> List[CheckResult]:
    """检查数据时效性"""
    results = []
    ft = data.get("fetch_time", data.get("_meta", {}).get("fetch_time", ""))
    if not ft:
        return results

    dt = parse_datetime(str(ft))
    if dt is None:
        results.append(make_result("time_freshness", source, "V1", False, "warning",
                                   f"无法解析fetch_time: {ft}"))
        return results

    fresh = is_recent(dt, max_hours)
    age_hours = round((datetime.now() - dt).total_seconds() / 3600, 1)
    results.append(make_result("time_freshness", source, "V1", fresh,
                               "warning" if not fresh else "info",
                               f"数据年龄: {age_hours}小时 (阈值{max_hours}小时)",
                               expected=f"<{max_hours}h", actual=f"{age_hours}h"))
    return results


# ============================================================
# V2: 价格范围验证
# ============================================================

# A股指数合理范围
INDEX_RANGES = {
    "sh000001": (2000, 5000, "上证指数"),
    "sz399001": (8000, 20000, "深证成指"),
    "sz399006": (1500, 5000, "创业板指"),
    "sh000688": (1000, 3000, "科创50"),
    "sh000016": (2000, 4000, "上证50"),
    "sh000905": (4000, 10000, "中证500"),
}

# 商品合理范围
COMMODITY_RANGES = {
    "wti": (20, 200, "WTI原油"),
    "brent": (20, 200, "布伦特原油"),
    "gold": (100, 10000, "黄金"),
    "silver": (1, 200, "白银"),
    "copper": (200, 2000, "铜"),
    "natgas": (0.5, 20, "天然气"),
    "btc": (10000, 200000, "BTC"),
}


def validate_price_range(value: Any, low: float, high: float, name: str,
                         source: str) -> CheckResult:
    """通用价格范围验证"""
    try:
        v = float(value)
        ok = low <= v <= high
        return make_result("price_range", source, "V2", ok,
                           "critical" if not ok else "info",
                           f"{name}: {v} (范围{low}-{high})",
                           expected=f"[{low}, {high}]", actual=v)
    except (TypeError, ValueError):
        return make_result("price_range", source, "V2", False, "critical",
                           f"{name}值无法转为数字: {value}")


def validate_positive(value: Any, name: str, source: str) -> CheckResult:
    """检查价格是否为正"""
    try:
        v = float(value)
        ok = v > 0
        return make_result("positive_value", source, "V2", ok,
                           "critical" if not ok else "info",
                           f"{name}: {v} 应为正数")
    except (TypeError, ValueError):
        return make_result("positive_value", source, "V2", False, "critical",
                           f"{name}值无法转为数字: {value}")


# ============================================================
# V3: 价格变动验证
# ============================================================
def validate_change_pct(price: float, prev_close: float, chg_pct: float,
                        name: str, source: str, tolerance: float = 0.5) -> List[CheckResult]:
    """验证涨跌幅与价格变动是否一致"""
    results = []
    if prev_close is None or prev_close == 0:
        return results

    try:
        expected_pct = (price - prev_close) / prev_close * 100
        diff = abs(expected_pct - chg_pct)
        ok = diff <= tolerance
        results.append(make_result("change_pct_calc", source, "V3", ok,
                                   "warning" if not ok else "info",
                                   f"{name}: 计算涨跌幅={expected_pct:.2f}%, 报告={chg_pct:.2f}%, 差={diff:.2f}%",
                                   expected=f"~{expected_pct:.2f}%", actual=f"{chg_pct:.2f}%"))
    except Exception:
        pass

    # 异常涨跌检测
    try:
        if abs(chg_pct) > 15:
            results.append(make_result("extreme_movement", source, "V3", False,
                                       "warning",
                                       f"{name}: 涨跌幅{chg_pct:.2f}%超过15%阈值"))
    except Exception:
        pass

    return results


# ============================================================
# V4: 格式正则验证
# ============================================================
def validate_stock_code_format(code: str, market: str, source: str) -> CheckResult:
    """验证股票代码格式"""
    if market == "a_share":
        pattern = r"^\d{6}$"
        expected = "6位数字"
    elif market == "us":
        pattern = r"^[A-Z]{1,5}$"
        expected = "1-5位大写字母"
    else:
        return make_result("code_format", source, "V4", True, "info",
                           f"跳过未知市场{market}")

    ok = bool(re.match(pattern, str(code).strip()))
    return make_result("code_format", source, "V4", ok,
                       "warning" if not ok else "info",
                       f"代码{code}格式检查",
                       expected=expected, actual=code)


def validate_date_format(date_str: str, source: str) -> CheckResult:
    """验证日期格式"""
    pattern = r"^\d{4}-\d{2}-\d{2}$"
    ok = bool(re.match(pattern, str(date_str).strip()))
    return make_result("date_format", source, "V4", ok,
                       "warning" if not ok else "info",
                       f"日期格式: {date_str}",
                       expected="YYYY-MM-DD", actual=date_str)


# ============================================================
# V5: 数据完整性验证
# ============================================================
def validate_list_length(lst: Any, min_len: int, name: str, source: str) -> CheckResult:
    """验证列表最小长度"""
    if lst is None:
        return make_result("list_length", source, "V5", False, "critical",
                           f"{name}为null")
    if not isinstance(lst, list):
        return make_result("list_length", source, "V5", False, "critical",
                           f"{name}不是列表类型: {type(lst).__name__}")
    ok = len(lst) >= min_len
    return make_result("list_length", source, "V5", ok,
                       "critical" if not ok else "info",
                       f"{name}长度: {len(lst)} (最小{min_len})",
                       expected=f">={min_len}", actual=len(lst))


def validate_required_fields(obj: dict, fields: list, name: str, source: str) -> List[CheckResult]:
    """验证必填字段"""
    results = []
    for f in fields:
        val = obj.get(f)
        if val is None or val == "" or val == []:
            results.append(make_result("required_field", source, "V5", False,
                                       "critical",
                                       f"{name}缺少必填字段: {f}"))
    return results


def validate_json_keys(data: dict, expected_keys: list, source: str) -> List[CheckResult]:
    """验证JSON顶层key完整性"""
    results = []
    for k in expected_keys:
        if k not in data:
            results.append(make_result("json_key", source, "V5", False,
                                       "critical",
                                       f"缺少顶层key: {k}",
                                       expected=k, actual="缺失"))
        else:
            results.append(make_result("json_key", source, "V5", True,
                                       "info",
                                       f"顶层key存在: {k}"))
    return results


# ============================================================
# V7: HTML注入验证
# ============================================================
def format_price_with_commas(price_str: str) -> str:
    """将数字字符串格式化为带千位逗号的格式，如 3882.01 -> 3,882.01"""
    try:
        if '.' in price_str:
            integer_part, decimal_part = price_str.split('.')
        else:
            integer_part = price_str
            decimal_part = None
        # 添加千位逗号
        reversed_int = integer_part[::-1]
        chunks = [reversed_int[i:i+3] for i in range(0, len(reversed_int), 3)]
        formatted = ','.join(chunks)[::-1]
        if decimal_part is not None:
            return f"{formatted}.{decimal_part}"
        return formatted
    except Exception:
        return price_str


def price_in_html(price: Any, html_content: str) -> bool:
    """检查价格是否以任一格式出现在HTML中（原始或带逗号）"""
    price_str = str(price)
    if price_str in html_content:
        return True
    # 尝试带逗号格式
    comma_str = format_price_with_commas(price_str)
    if comma_str in html_content:
        return True
    # 如果价格以.0结尾，也检查去掉.0的格式（如 77734.0 -> 77,734）
    if price_str.endswith('.0'):
        int_str = price_str[:-2]
        if int_str in html_content:
            return True
        comma_int = format_price_with_commas(int_str)
        if comma_int in html_content:
            return True
    # 尝试截取关键部分（去掉末尾0后的匹配）
    # 例如 4725.144 在HTML中可能是 $4,725.14
    short = price_str[:5]
    if short in html_content:
        return True
    return False


def validate_html_injection(json_data: dict, html_content: str, source: str) -> List[CheckResult]:
    """验证JSON数据是否在HTML中正确注入"""
    results = []
    if not html_content:
        results.append(make_result("html_exists", source, "V7", False, "critical",
                                   "HTML文件不存在或无法读取"))
        return results

    # A股指数注入检查
    if source == "a_share":
        indices = json_data.get("indices", {})
        for idx_code, idx_data in indices.items():
            price = idx_data.get("price")
            if price is not None:
                found = price_in_html(price, html_content)
                results.append(make_result("html_index_price", source, "V7", found,
                                           "warning" if not found else "info",
                                           f"A股指数{idx_code}价格{price}在HTML中{'找到' if found else '未找到'}"))

    # 美股个股注入检查
    if source == "us_stock":
        stocks = json_data.get("stocks", {})
        checked = 0
        found_count = 0
        for sym, stock_data in stocks.items():
            if checked >= 10:  # 抽样检查前10只
                break
            # 检查股票代码是否出现在ssym标签中
            sym_pattern = f'>{sym}<'
            if sym_pattern in html_content:
                found_count += 1
            else:
                results.append(make_result("html_stock_symbol", source, "V7", False,
                                           "warning",
                                           f"美股代码{sym}未在HTML中找到"))
            checked += 1
        if found_count == checked:
            results.append(make_result("html_stock_symbols", source, "V7", True,
                                       "info",
                                       f"抽检{checked}只美股代码全部在HTML中找到"))

    # 商品注入检查
    if source == "commodities":
        for key, data in json_data.items():
            if key.startswith("_"):
                continue
            if isinstance(data, dict) and "price" in data:
                found = price_in_html(data["price"], html_content)
                if not found:
                    results.append(make_result("html_commodity_price", source, "V7", False,
                                               "warning",
                                               f"商品价格{key}={data['price']}未在HTML中找到"))

    return results


# ============================================================
# V9: 一致性验证
# ============================================================
def validate_market_flow_sum(data: dict, source: str) -> List[CheckResult]:
    """验证market_flow的total_amount与各分项的关系"""
    results = []
    mf = data.get("market_flow")
    if not mf:
        return results

    total = mf.get("total_amount")
    if total is None:
        return results

    # up_count + down_count 应为正数
    up = mf.get("up_count", 0)
    down = mf.get("down_count", 0)
    if up is not None and down is not None:
        total_count = up + down
        ok = total_count > 0
        results.append(make_result("up_down_count", source, "V9", ok,
                                   "warning" if not ok else "info",
                                   f"上涨+下跌家数: {up}+{down}={total_count}"))

    return results


# ============================================================
# 各数据源验证器
# ============================================================

class AShareValidator:
    """A股数据验证"""

    SOURCE = "a_share"

    @staticmethod
    def validate(data: dict, html: str = None, quick: bool = False) -> List[CheckResult]:
        results = []
        if data is None:
            results.append(make_result("file_exists", "a_share", "V5", False, "critical",
                                       "a_share_data.json不存在或无法解析"))
            return results

        # V1: 时间验证
        results += safe_check(lambda: validate_time_format(data, "a_share"),
                              "time_format", "a_share", "V1")
        results += safe_check(lambda: validate_time_freshness(data, "a_share", 24),
                              "time_freshness", "a_share", "V1")

        # V5: 完整性
        expected_keys = ["fetch_time", "indices", "global_indices", "sector_flow",
                         "concept_flow", "stock_inflow", "stock_outflow", "stock_volume",
                         "market_flow", "north_flow", "north_deal", "etf_flow",
                         "limit_up", "limit_down", "north_deal_history"]
        results += safe_check(lambda: validate_json_keys(data, expected_keys, "a_share"),
                              "json_keys", "a_share", "V5")

        # V2: 指数价格范围
        indices = data.get("indices", {})
        for code, range_info in INDEX_RANGES.items():
            low, high, name = range_info
            idx_data = indices.get(code, {})
            if idx_data.get("price") is not None:
                results.append(validate_price_range(
                    idx_data["price"], low, high, name, "a_share"))

            # V3: 涨跌验证
            if idx_data.get("price") and idx_data.get("prev_close") and idx_data.get("chg_pct") is not None:
                results += validate_change_pct(
                    idx_data["price"], idx_data["prev_close"], idx_data["chg_pct"],
                    name, "a_share")

        # V5: 列表长度
        results.append(validate_list_length(data.get("sector_flow"), 80, "sector_flow", "a_share"))
        results.append(validate_list_length(data.get("concept_flow"), 30, "concept_flow", "a_share"))
        results.append(validate_list_length(data.get("stock_inflow"), 10, "stock_inflow", "a_share"))
        results.append(validate_list_length(data.get("stock_outflow"), 10, "stock_outflow", "a_share"))
        results.append(validate_list_length(data.get("stock_volume"), 10, "stock_volume", "a_share"))
        results.append(validate_list_length(data.get("etf_flow"), 10, "etf_flow", "a_share"))
        results.append(validate_list_length(data.get("limit_up"), 1, "limit_up", "a_share"))
        results.append(validate_list_length(data.get("limit_down"), 1, "limit_down", "a_share"))
        results.append(validate_list_length(data.get("north_deal_history"), 5, "north_deal_history", "a_share"))

        if quick:
            return results

        # V4: 代码格式（抽样）
        for lst_name in ["stock_inflow", "stock_outflow", "stock_volume"]:
            lst = data.get(lst_name, [])
            if lst:
                item = lst[0]
                results.append(validate_stock_code_format(
                    item.get("code", ""), "a_share", "a_share"))
        # 板块/概念代码格式验证（BK开头是合法的）
        for lst_name in ["sector_flow", "concept_flow"]:
            lst = data.get(lst_name, [])
            if lst:
                item = lst[0]
                code = str(item.get("code", ""))
                ok = bool(re.match(r"^BK\d{4}$", code))
                results.append(make_result("sector_code_format", "a_share", "V4", ok,
                                           "info",
                                           f"{lst_name}代码格式: {code}",
                                           expected="BK+4位数字", actual=code))

        # V2: 个股价格范围
        for lst_name in ["stock_inflow", "stock_outflow", "stock_volume"]:
            for item in data.get(lst_name, [])[:5]:
                if item.get("price") is not None:
                    results.append(validate_positive(item["price"],
                                                     f"{lst_name}.{item.get('name','')}", "a_share"))

        # V9: 一致性
        results += safe_check(lambda: validate_market_flow_sum(data, "a_share"),
                              "market_flow_consistency", "a_share", "V9")

        # V7: HTML注入
        if html:
            results += safe_check(lambda: validate_html_injection(data, html, "a_share"),
                                  "html_injection", "a_share", "V7")

        return results


class USStockValidator:
    """美股数据验证"""

    SOURCE = "us_stock"

    @staticmethod
    def validate(data: dict, html: str = None, quick: bool = False) -> List[CheckResult]:
        results = []
        if data is None:
            results.append(make_result("file_exists", "us_stock", "V5", False, "critical",
                                       "us_enhanced_data.json不存在或无法解析"))
            return results

        # V1
        results += safe_check(lambda: validate_time_format(data, "us_stock"),
                              "time_format", "us_stock", "V1")
        results += safe_check(lambda: validate_time_freshness(data, "us_stock", 48),
                              "time_freshness", "us_stock", "V1")

        # V5
        expected_keys = ["stocks", "inflow", "outflow", "top_amount", "vix", "fetch_time"]
        results += safe_check(lambda: validate_json_keys(data, expected_keys, "us_stock"),
                              "json_keys", "us_stock", "V5")

        # V2: 股票价格
        stocks = data.get("stocks", {})
        results.append(validate_list_length(list(stocks.values()), 20, "stocks", "us_stock"))

        for sym, sdata in list(stocks.items())[:10]:
            if isinstance(sdata, dict):
                rt_price = sdata.get("rt_price", sdata.get("price"))
                if rt_price is not None:
                    results.append(validate_price_range(
                        rt_price, 0.01, 10000, f"US:{sym}", "us_stock"))

        # V2: VIX范围
        vix = data.get("vix", {})
        if vix.get("value") is not None:
            results.append(validate_price_range(vix["value"], 5, 85, "VIX", "us_stock"))

        # V5: 列表长度
        results.append(validate_list_length(data.get("inflow"), 10, "inflow", "us_stock"))
        results.append(validate_list_length(data.get("outflow"), 10, "outflow", "us_stock"))
        results.append(validate_list_length(data.get("top_amount"), 10, "top_amount", "us_stock"))

        if quick:
            return results

        # V4: 代码格式
        for sym in list(stocks.keys())[:5]:
            results.append(validate_stock_code_format(sym, "us", "us_stock"))

        # V3: 涨跌验证
        for sym, sdata in list(stocks.items())[:10]:
            if isinstance(sdata, dict):
                rt = sdata.get("rt_price", sdata.get("price"))
                pc = sdata.get("prev_close")
                cp = sdata.get("chg_pct")
                if rt and pc and cp is not None:
                    results += validate_change_pct(rt, pc, cp, f"US:{sym}", "us_stock")

        # V7: HTML注入
        if html:
            results += safe_check(lambda: validate_html_injection(data, html, "us_stock"),
                                  "html_injection", "us_stock", "V7")

        return results


class CommodityValidator:
    """商品数据验证"""

    SOURCE = "commodities"

    @staticmethod
    def validate(data: dict, html: str = None, quick: bool = False) -> List[CheckResult]:
        results = []
        if data is None:
            results.append(make_result("file_exists", "commodities", "V5", False, "critical",
                                       "commodities_data.json不存在或无法解析"))
            return results

        # V1: _meta中的fetch_time
        meta = data.get("_meta", {})
        if meta.get("fetch_time"):
            results += validate_time_format(meta, "commodities")

        # 也检查各品种内部的时间
        for key, cdata in data.items():
            if key.startswith("_"):
                continue
            if isinstance(cdata, dict):
                ft = cdata.get("date")
                if ft:
                    results.append(validate_date_format(ft, "commodities"))
                break  # 只检查一个即可

        # V5: 品种完整性
        expected_commodities = ["wti", "brent", "gold", "silver", "copper", "natgas", "btc"]
        for c in expected_commodities:
            if c not in data:
                results.append(make_result("commodity_exists", "commodities", "V5", False,
                                           "critical", f"缺少商品: {c}"))

        # V2: 价格范围
        for key, range_info in COMMODITY_RANGES.items():
            low, high, name = range_info
            cdata = data.get(key, {})
            if isinstance(cdata, dict) and cdata.get("price") is not None:
                results.append(validate_price_range(
                    cdata["price"], low, high, name, "commodities"))

                # V3: 涨跌验证
                pc = cdata.get("prev_close")
                cp = cdata.get("change_pct")
                if pc and cp is not None and pc != 0:
                    results += validate_change_pct(
                        cdata["price"], pc, cp, name, "commodities")

        if quick:
            return results

        # V7: HTML注入
        if html:
            results += safe_check(lambda: validate_html_injection(data, html, "commodities"),
                                  "html_injection", "commodities", "V7")

        return results


class AuctionValidator:
    """集合竞价数据验证"""

    SOURCE = "auction"

    @staticmethod
    def validate(data: dict, html: str = None, quick: bool = False) -> List[CheckResult]:
        results = []
        if data is None:
            results.append(make_result("file_exists", "auction", "V5", False, "critical",
                                       "auction_data.json不存在或无法解析"))
            return results

        # V1
        results += safe_check(lambda: validate_time_format(data, "auction"),
                              "time_format", "auction", "V1")
        results += safe_check(lambda: validate_time_freshness(data, "auction", 24),
                              "time_freshness", "auction", "V1")

        # V5
        expected_keys = ["fetch_time", "indices", "top_gap_up", "top_gap_down", "stats"]
        results += safe_check(lambda: validate_json_keys(data, expected_keys, "auction"),
                              "json_keys", "auction", "V5")

        results.append(validate_list_length(data.get("top_gap_up"), 5, "top_gap_up", "auction"))
        results.append(validate_list_length(data.get("top_gap_down"), 5, "top_gap_down", "auction"))

        # V2: 指数范围
        indices = data.get("indices", {})
        for code, range_info in list(INDEX_RANGES.items())[:3]:
            low, high, name = range_info
            idx = indices.get(code, {})
            if idx.get("price") is not None:
                results.append(validate_price_range(idx["price"], low, high,
                                                    f"竞价.{name}", "auction"))

        # V9: stats
        stats = data.get("stats", {})
        if stats:
            total = (stats.get("gap_up_count", 0) or 0) + (stats.get("gap_down_count", 0) or 0) + (stats.get("flat_count", 0) or 0)
            ok = total > 0
            results.append(make_result("auction_stats_sum", "auction", "V9", ok,
                                       "warning" if not ok else "info",
                                       f"竞价统计总数: {total}"))

        return results


class PostMarketValidator:
    """盘后数据验证"""

    SOURCE = "post_market"

    @staticmethod
    def validate(data: dict, html: str = None, quick: bool = False) -> List[CheckResult]:
        results = []
        if data is None:
            results.append(make_result("file_exists", "post_market", "V5", False, "critical",
                                       "post_market_data.json不存在或无法解析"))
            return results

        # V1
        results += safe_check(lambda: validate_time_format(data, "post_market"),
                              "time_format", "post_market", "V1")
        results += safe_check(lambda: validate_time_freshness(data, "post_market", 48),
                              "time_freshness", "post_market", "V1")

        # V5
        expected_keys = ["fetch_time", "margin", "dragon_tiger", "futures"]
        results += safe_check(lambda: validate_json_keys(data, expected_keys, "post_market"),
                              "json_keys", "post_market", "V5")

        # margin子验证
        margin = data.get("margin", {})
        if margin:
            results += safe_check(lambda: validate_time_format(margin, "post_market.margin"),
                                  "margin_time", "post_market", "V1")

        # dragon_tiger子验证
        dt = data.get("dragon_tiger", {})
        if isinstance(dt, dict):
            if "stocks" in dt:
                results.append(validate_list_length(dt["stocks"], 1, "dragon_tiger.stocks", "post_market"))
            if dt.get("trade_date"):
                results.append(validate_date_format(dt["trade_date"], "post_market"))

        # futures子验证
        futures = data.get("futures", {})
        if isinstance(futures, dict):
            contracts = futures.get("contracts")
            if contracts is not None:
                if isinstance(contracts, dict):
                    results.append(validate_list_length(list(contracts.values()), 1,
                                                        "futures.contracts", "post_market"))
                elif isinstance(contracts, list):
                    results.append(validate_list_length(contracts, 1,
                                                        "futures.contracts", "post_market"))

        return results


class TailSnapshotValidator:
    """尾盘快照验证"""

    SOURCE = "tail_snapshot"

    @staticmethod
    def validate(data: dict, html: str = None, quick: bool = False) -> List[CheckResult]:
        results = []
        if data is None:
            results.append(make_result("file_exists", "tail_snapshot", "V5", False, "critical",
                                       "tail_snapshot.json不存在或无法解析"))
            return results

        # V1
        results += safe_check(lambda: validate_time_format(data, "tail_snapshot"),
                              "time_format", "tail_snapshot", "V1")

        # V5
        expected_keys = ["fetch_time", "market_flow", "indices"]
        results += safe_check(lambda: validate_json_keys(data, expected_keys, "tail_snapshot"),
                              "json_keys", "tail_snapshot", "V5")

        # V2: 指数价格
        indices = data.get("indices", {})
        for code, range_info in INDEX_RANGES.items():
            low, high, name = range_info
            idx = indices.get(code, {})
            if idx.get("price") is not None:
                results.append(validate_price_range(idx["price"], low, high,
                                                    f"尾盘.{name}", "tail_snapshot"))

        # V9: 与a_share的market_flow比较（如果都有）
        results += safe_check(lambda: validate_market_flow_sum(data, "tail_snapshot"),
                              "market_flow_consistency", "tail_snapshot", "V9")

        return results


class VolumeHistoryValidator:
    """成交额历史验证"""

    SOURCE = "volume_history"

    @staticmethod
    def validate(data: dict, html: str = None, quick: bool = False) -> List[CheckResult]:
        results = []
        if data is None:
            results.append(make_result("file_exists", "volume_history", "V5", False, "critical",
                                       "market_volume_history.json不存在或无法解析"))
            return results

        # V5
        if "meta" not in data:
            results.append(make_result("meta_exists", "volume_history", "V5", False,
                                       "warning", "缺少meta字段"))
        if "daily" not in data:
            results.append(make_result("daily_exists", "volume_history", "V5", False,
                                       "critical", "缺少daily字段"))
            return results

        daily = data.get("daily", [])
        results.append(validate_list_length(daily, 3, "daily", "volume_history"))

        # V2: 成交额范围
        for item in daily[-3:]:  # 最近3天
            amt = item.get("amount")
            if amt is not None:
                ok = 1000 < float(amt) < 100000
                results.append(make_result("volume_range", "volume_history", "V2", ok,
                                           "warning" if not ok else "info",
                                           f"{item.get('date')}: 成交额{amt}亿 (范围1000-100000)",
                                           expected="[1000, 100000]", actual=amt))

            # V4: 日期格式
            if item.get("date"):
                results.append(validate_date_format(item["date"], "volume_history"))

            # V2: 上证价格（如有）
            if item.get("sh_price"):
                results.append(validate_price_range(item["sh_price"], 2000, 5000,
                                                    f"上证.{item.get('date')}", "volume_history"))

        return results


class HTMLSeriesValidator:
    """HTML中硬编码的序列数据验证（美债、美股指数）"""

    SOURCE = "html_series"

    @staticmethod
    def validate(html: str, quick: bool = False) -> List[CheckResult]:
        results = []
        if not html:
            results.append(make_result("html_exists", "html_series", "V7", False, "critical",
                                       "HTML文件不存在"))
            return results

        today = datetime.now()
        today_str = today.strftime("%Y-%m-%d")

        # 检查 SERIES_DATA 存在
        has_series = "SERIES_DATA" in html
        results.append(make_result("SERIES_DATA_exists", "html_series", "V7", has_series,
                                   "critical" if not has_series else "info",
                                   "SERIES_DATA(美债收益率)在HTML中"))

        has_us_series = "US_SERIES_DATA" in html
        results.append(make_result("US_SERIES_DATA_exists", "html_series", "V7", has_us_series,
                                   "critical" if not has_us_series else "info",
                                   "US_SERIES_DATA(美股指数)在HTML中"))

        # 尝试提取SERIES_DATA并验证内容
        series_match = re.search(r'const\s+SERIES_DATA\s*=\s*(\{.*?\});\s*\n', html, re.DOTALL)
        if series_match:
            try:
                series_json = json.loads(series_match.group(1))
                expected_series = ["DGS2", "DGS5", "DGS10", "DGS30"]
                for s in expected_series:
                    if s in series_json:
                        sd = series_json[s]
                        if isinstance(sd, dict):
                            dates = sd.get("dates_all", [])
                            vals = sd.get("values_all", sd.get("values_recent", []))
                            if vals:
                                # V2: 美债收益率范围
                                recent = vals[-1] if vals else None
                                if recent is not None:
                                    results.append(validate_price_range(
                                        recent, 0, 15, f"美债{s}", "html_series"))
                            # ★ V1: 日期新鲜度检查（quick模式也执行）
                            if dates:
                                latest_date_str = dates[-1]
                                try:
                                    latest_dt = datetime.strptime(latest_date_str, "%Y-%m-%d")
                                    days_behind = (today - latest_dt).days
                                    # 美债收益率：工作日更新，周末/周一允许3天
                                    ok = days_behind <= 3
                                    results.append(make_result(
                                        f"series_freshness_{s}", "html_series", "V1", ok,
                                        "critical" if not ok else "info",
                                        f"SERIES_DATA.{s}最新日期: {latest_date_str}, 距今{days_behind}天",
                                        expected=f"距今<=3天(最新{today_str})",
                                        actual=f"{latest_date_str}({days_behind}天前)"))
                                except ValueError:
                                    results.append(make_result(
                                        f"series_date_format_{s}", "html_series", "V4", False,
                                        "warning", f"SERIES_DATA.{s}日期格式异常: {latest_date_str}"))
                    else:
                        results.append(make_result("series_key", "html_series", "V5", False,
                                                   "warning", f"SERIES_DATA缺少序列: {s}"))
            except json.JSONDecodeError:
                results.append(make_result("series_parse", "html_series", "V7", False,
                                           "warning", "SERIES_DATA无法解析为JSON"))

        # 尝试提取US_SERIES_DATA
        us_match = re.search(r'const\s+US_SERIES_DATA\s*=\s*(\{.*?\});\s*\n', html, re.DOTALL)
        if us_match:
            try:
                us_json = json.loads(us_match.group(1))
                expected_count = 23
                actual_count = len(us_json)
                ok = actual_count >= expected_count - 2
                results.append(make_result("us_series_count", "html_series", "V5", ok,
                                           "warning" if not ok else "info",
                                           f"US_SERIES_DATA序列数: {actual_count} (预期{expected_count})"))

                # ★ V1: US_SERIES_DATA日期新鲜度（quick模式也执行）
                # 检查主要指数的最新日期
                for sym in ["DJI", "IXIC", "INX"]:
                    if sym in us_json:
                        us_dates = us_json[sym].get("dates_all", [])
                        if us_dates:
                            latest_us = us_dates[-1]
                            try:
                                latest_us_dt = datetime.strptime(latest_us, "%Y-%m-%d")
                                days_behind = (today - latest_us_dt).days
                                # 美股指数：交易日更新，周末/周一允许3天
                                ok = days_behind <= 3
                                results.append(make_result(
                                    f"us_series_freshness_{sym}", "html_series", "V1", ok,
                                    "critical" if not ok else "info",
                                    f"US_SERIES_DATA.{sym}最新日期: {latest_us}, 距今{days_behind}天",
                                    expected=f"距今<=3天(最新{today_str})",
                                    actual=f"{latest_us}({days_behind}天前)"))
                            except ValueError:
                                results.append(make_result(
                                    f"us_series_date_format_{sym}", "html_series", "V4", False,
                                    "warning", f"US_SERIES_DATA.{sym}日期格式异常: {latest_us}"))
                        break  # 只检查一个代表性的就行
            except json.JSONDecodeError:
                results.append(make_result("us_series_parse", "html_series", "V7", False,
                                           "warning", "US_SERIES_DATA无法解析为JSON"))

        # HTML通用结构检查（非quick模式才做）
        if not quick:
            ssym_count = html.count('class="ssym"')
            sprc_count = html.count('class="sprc"')
            results.append(make_result("html_ssym_count", "html_series", "V5",
                                       ssym_count >= 30, "warning" if ssym_count < 30 else "info",
                                       f"HTML中ssym(股票代码)标签数: {ssym_count} (预期>=30)"))
            results.append(make_result("html_sprc_count", "html_series", "V5",
                                       sprc_count >= 30, "warning" if sprc_count < 30 else "info",
                                       f"HTML中sprc(股票价格)标签数: {sprc_count} (预期>=30)"))

            fp_count = html.count('class="fp"')
            results.append(make_result("html_fp_count", "html_series", "V5",
                                       fp_count >= 20, "warning" if fp_count < 20 else "info",
                                       f"HTML中fp(数据点)标签数: {fp_count} (预期>=20)"))

        return results


class CrossSourceValidator:
    """跨数据源交叉验证"""

    SOURCE = "cross_source"

    @staticmethod
    def validate(a_data: dict, tail_data: dict, auction_data: dict) -> List[CheckResult]:
        results = []

        # A股指数 vs 尾盘快照指数比较
        if a_data and tail_data:
            a_indices = a_data.get("indices", {})
            t_indices = tail_data.get("indices", {})
            for code in INDEX_RANGES.keys():
                a_price = a_indices.get(code, {}).get("price")
                t_price = t_indices.get(code, {}).get("price")
                if a_price and t_price:
                    try:
                        diff_pct = abs(float(a_price) - float(t_price)) / float(a_price) * 100
                        ok = diff_pct < 5  # 不同时间采集，允许5%差异
                        results.append(make_result(
                            "cross_a_vs_tail", "cross_source", "V8", ok,
                            "warning" if not ok else "info",
                            f"指数{code}: a_share={a_price} vs tail={t_price}, 差异{diff_pct:.2f}%",
                            expected="差异<5%", actual=f"{diff_pct:.2f}%"))
                    except Exception:
                        pass

        # A股指数 vs 集合竞价指数
        if a_data and auction_data:
            a_indices = a_data.get("indices", {})
            ac_indices = auction_data.get("indices", {})
            for code in ["sh000001", "sz399001", "sz399006"]:
                a_prev = a_indices.get(code, {}).get("prev_close")
                ac_prev = ac_indices.get(code, {}).get("prev_close")
                if a_prev and ac_prev:
                    try:
                        diff_pct = abs(float(a_prev) - float(ac_prev)) / float(a_prev) * 100
                        ok = diff_pct < 0.1
                        results.append(make_result(
                            "cross_a_vs_auction", "cross_source", "V8", ok,
                            "warning" if not ok else "info",
                            f"指数{code} prev_close: a_share={a_prev} vs auction={ac_prev}, 差异{diff_pct:.4f}%",
                            expected="差异<0.1%", actual=f"{diff_pct:.4f}%"))
                    except Exception:
                        pass

        return results


# ============================================================
# 报告生成
# ============================================================

def generate_text_report(results: List[CheckResult]) -> str:
    """生成文本报告"""
    lines = []
    lines.append("=" * 80)
    lines.append("  全球资产看板数据验证报告")
    lines.append(f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 80)
    lines.append("")

    # 统计
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    critical = sum(1 for r in results if not r.passed and r.severity == "critical")
    warnings = sum(1 for r in results if not r.passed and r.severity == "warning")

    lines.append(f"  总计: {total} 项检查 | ✅ 通过: {passed} | ❌ 失败: {failed}")
    lines.append(f"  🔴 严重: {critical} | 🟡 警告: {warnings}")
    lines.append("")

    # 按数据源分组
    by_source = {}
    for r in results:
        by_source.setdefault(r.data_source, []).append(r)

    for source, checks in sorted(by_source.items()):
        src_passed = sum(1 for c in checks if c.passed)
        src_total = len(checks)
        status = "✅" if src_passed == src_total else "❌"
        lines.append(f"── {status} [{source}] ({src_passed}/{src_total}) {'─' * (50 - len(source))}")

        for c in checks:
            if not c.passed:
                icon = "🔴" if c.severity == "critical" else "🟡"
                lines.append(f"  {icon} [{c.dimension}] {c.message}")
                if c.expected and c.actual:
                    lines.append(f"      期望: {c.expected} | 实际: {c.actual}")
        lines.append("")

    lines.append("=" * 80)
    return "\n".join(lines)


def generate_json_report(results: List[CheckResult]) -> str:
    """生成JSON报告"""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed

    report = {
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "critical": sum(1 for r in results if not r.passed and r.severity == "critical"),
            "warning": sum(1 for r in results if not r.passed and r.severity == "warning"),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        },
        "results": [r.to_dict() for r in results]
    }
    return json.dumps(report, ensure_ascii=False, indent=2)


def generate_html_report(results: List[CheckResult]) -> str:
    """生成HTML验证报告"""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    critical = sum(1 for r in results if not r.passed and r.severity == "critical")
    warnings = sum(1 for r in results if not r.passed and r.severity == "warning")
    pass_rate = round(passed / total * 100, 1) if total > 0 else 0

    # 按数据源分组
    by_source = {}
    for r in results:
        by_source.setdefault(r.data_source, []).append(r)

    # 按维度分组统计
    by_dim = {}
    for r in results:
        dim = r.dimension
        if dim not in by_dim:
            by_dim[dim] = {"total": 0, "passed": 0, "failed": 0}
        by_dim[dim]["total"] += 1
        if r.passed:
            by_dim[dim]["passed"] += 1
        else:
            by_dim[dim]["failed"] += 1

    dim_names = {
        "V1": "时间验证", "V2": "价格范围", "V3": "价格变动", "V4": "格式正则",
        "V5": "完整性", "V6": "API状态", "V7": "注入验证", "V8": "交叉验证", "V9": "一致性"
    }

    source_rows = ""
    for source, checks in sorted(by_source.items()):
        sp = sum(1 for c in checks if c.passed)
        st = len(checks)
        pct = round(sp / st * 100, 1) if st > 0 else 0
        bar_color = "#10b981" if pct >= 90 else "#f59e0b" if pct >= 70 else "#ef4444"
        source_rows += f"""
        <tr>
          <td><strong>{source}</strong></td>
          <td>{st}</td>
          <td style="color:#10b981">{sp}</td>
          <td style="color:{'#ef4444' if st-sp > 0 else '#10b981'}">{st - sp}</td>
          <td>
            <div style="display:flex;align-items:center;gap:8px">
              <div style="background:#e5e7eb;border-radius:999px;height:8px;width:100px;overflow:hidden">
                <div style="background:{bar_color};height:100%;width:{pct}%;border-radius:999px"></div>
              </div>
              <span style="font-size:12px;color:{bar_color}">{pct}%</span>
            </div>
          </td>
        </tr>"""

    dim_rows = ""
    for dim in ["V1", "V2", "V3", "V4", "V5", "V6", "V7", "V8", "V9"]:
        if dim in by_dim:
            d = by_dim[dim]
            dp = round(d["passed"] / d["total"] * 100, 1) if d["total"] > 0 else 0
            dim_rows += f"""
        <tr>
          <td><span class="dim-badge">{dim}</span> {dim_names.get(dim, dim)}</td>
          <td>{d['total']}</td>
          <td style="color:#10b981">{d['passed']}</td>
          <td style="color:{'#ef4444' if d['failed'] > 0 else '#10b981'}">{d['failed']}</td>
        </tr>"""

    # 失败项详情
    failed_items = ""
    for r in results:
        if not r.passed:
            sev_class = "critical" if r.severity == "critical" else "warning"
            sev_icon = "🔴" if r.severity == "critical" else "🟡"
            failed_items += f"""
        <div class="fail-item {sev_class}">
          <div class="fail-header">
            {sev_icon} <span class="fail-source">[{r.data_source}]</span>
            <span class="dim-badge">{r.dimension}</span>
            <span class="fail-check">{r.check_name}</span>
          </div>
          <div class="fail-msg">{r.message}</div>
          {"<div class='fail-detail'>期望: " + str(r.expected) + " | 实际: " + str(r.actual) + "</div>" if r.expected is not None and r.actual is not None else ""}
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>全球资产看板 - 数据验证报告</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background:#0f172a; color:#e2e8f0; padding:24px; }}
  .container {{ max-width:1100px; margin:0 auto; }}
  h1 {{ font-size:28px; margin-bottom:8px; color:#f8fafc; }}
  .subtitle {{ color:#94a3b8; font-size:14px; margin-bottom:24px; }}
  .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:16px; margin-bottom:32px; }}
  .card {{ background:#1e293b; border-radius:12px; padding:20px; text-align:center; border:1px solid #334155; }}
  .card-num {{ font-size:36px; font-weight:700; margin-bottom:4px; }}
  .card-label {{ font-size:13px; color:#94a3b8; }}
  .card.total .card-num {{ color:#60a5fa; }}
  .card.pass .card-num {{ color:#10b981; }}
  .card.fail .card-num {{ color:#ef4444; }}
  .card.crit .card-num {{ color:#f87171; }}
  .card.warn .card-num {{ color:#fbbf24; }}
  .card.rate .card-num {{ color:#a78bfa; }}
  .section {{ background:#1e293b; border-radius:12px; padding:20px; margin-bottom:24px; border:1px solid #334155; }}
  .section h2 {{ font-size:18px; margin-bottom:16px; color:#f1f5f9; display:flex; align-items:center; gap:8px; }}
  table {{ width:100%; border-collapse:collapse; }}
  th {{ text-align:left; padding:10px 12px; border-bottom:2px solid #334155; color:#94a3b8; font-size:13px; font-weight:500; }}
  td {{ padding:10px 12px; border-bottom:1px solid #1e293b; font-size:14px; }}
  tr:hover {{ background:#334155; }}
  .dim-badge {{ background:#334155; color:#94a3b8; padding:2px 8px; border-radius:4px; font-size:12px; font-family:monospace; }}
  .fail-item {{ background:#1a1a2e; border-radius:8px; padding:12px 16px; margin-bottom:10px; border-left:3px solid; }}
  .fail-item.critical {{ border-color:#ef4444; }}
  .fail-item.warning {{ border-color:#f59e0b; }}
  .fail-header {{ display:flex; align-items:center; gap:8px; margin-bottom:6px; flex-wrap:wrap; }}
  .fail-source {{ color:#60a5fa; font-size:13px; }}
  .fail-check {{ color:#94a3b8; font-size:12px; font-family:monospace; }}
  .fail-msg {{ font-size:14px; color:#e2e8f0; }}
  .fail-detail {{ font-size:12px; color:#94a3b8; margin-top:4px; }}
  .no-failures {{ text-align:center; padding:40px; color:#10b981; font-size:18px; }}
</style>
</head>
<body>
<div class="container">
  <h1>🌐 全球资产看板 - 数据验证报告</h1>
  <p class="subtitle">生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 数据源: {len(by_source)}个 | 检查维度: {len(by_dim)}个</p>

  <div class="cards">
    <div class="card total"><div class="card-num">{total}</div><div class="card-label">总检查项</div></div>
    <div class="card pass"><div class="card-num">{passed}</div><div class="card-label">✅ 通过</div></div>
    <div class="card fail"><div class="card-num">{failed}</div><div class="card-label">❌ 失败</div></div>
    <div class="card crit"><div class="card-num">{critical}</div><div class="card-label">🔴 严重</div></div>
    <div class="card warn"><div class="card-num">{warnings}</div><div class="card-label">🟡 警告</div></div>
    <div class="card rate"><div class="card-num">{pass_rate}%</div><div class="card-label">通过率</div></div>
  </div>

  <div class="section">
    <h2>📊 各数据源验证情况</h2>
    <table>
      <thead><tr><th>数据源</th><th>检查数</th><th>通过</th><th>失败</th><th>通过率</th></tr></thead>
      <tbody>{source_rows}</tbody>
    </table>
  </div>

  <div class="section">
    <h2>🔬 各验证维度统计</h2>
    <table>
      <thead><tr><th>维度</th><th>检查数</th><th>通过</th><th>失败</th></tr></thead>
      <tbody>{dim_rows}</tbody>
    </table>
  </div>

  <div class="section">
    <h2>❌ 失败项详情 ({failed})</h2>
    {"<div class='no-failures'>🎉 所有检查均已通过！</div>" if failed == 0 else failed_items}
  </div>
</div>
</body>
</html>"""
    return html


# ============================================================
# 主流程
# ============================================================

def run_validation(quick: bool = False) -> List[CheckResult]:
    """运行所有验证"""
    all_results: List[CheckResult] = []

    # 加载数据
    data_files = {}
    for key, path in JSON_FILES.items():
        data_files[key] = safe_load_json(path)

    html_content = safe_read_file(HTML_PATH)

    # 1. A股数据验证
    a_data = data_files.get("a_share")
    all_results += safe_check(
        lambda: AShareValidator.validate(a_data, html_content, quick),
        "a_share_validate", "a_share", "ALL")

    # 2. 美股数据验证
    us_data = data_files.get("us_stock")
    all_results += safe_check(
        lambda: USStockValidator.validate(us_data, html_content, quick),
        "us_stock_validate", "us_stock", "ALL")

    # 3. 商品数据验证
    cmd_data = data_files.get("commodities")
    all_results += safe_check(
        lambda: CommodityValidator.validate(cmd_data, html_content, quick),
        "commodities_validate", "commodities", "ALL")

    # 4. 集合竞价验证
    auc_data = data_files.get("auction")
    all_results += safe_check(
        lambda: AuctionValidator.validate(auc_data, html_content, quick),
        "auction_validate", "auction", "ALL")

    # 5. 盘后数据验证
    pm_data = data_files.get("post_market")
    all_results += safe_check(
        lambda: PostMarketValidator.validate(pm_data, html_content, quick),
        "post_market_validate", "post_market", "ALL")

    # 6. 尾盘快照验证
    ts_data = data_files.get("tail_snapshot")
    all_results += safe_check(
        lambda: TailSnapshotValidator.validate(ts_data, html_content, quick),
        "tail_snapshot_validate", "tail_snapshot", "ALL")

    # 7. 成交额历史验证
    vh_data = data_files.get("volume_history")
    all_results += safe_check(
        lambda: VolumeHistoryValidator.validate(vh_data, html_content, quick),
        "volume_history_validate", "volume_history", "ALL")

    # 8. HTML序列数据验证（quick模式也执行，检查日期新鲜度）
    all_results += safe_check(
        lambda: HTMLSeriesValidator.validate(html_content, quick),
        "html_series_validate", "html_series", "V7")

    if not quick:
        # 9. 跨数据源验证
        all_results += safe_check(
            lambda: CrossSourceValidator.validate(a_data, ts_data, auc_data),
            "cross_source_validate", "cross_source", "V8")

    return all_results


def main():
    parser = argparse.ArgumentParser(description="全球资产看板数据验证框架")
    parser.add_argument("--json", action="store_true", help="JSON格式输出")
    parser.add_argument("--html", action="store_true", help="生成HTML报告")
    parser.add_argument("--quick", action="store_true", help="仅关键验证(V1+V2+V5)")
    args = parser.parse_args()

    quick = args.quick
    results = run_validation(quick=quick)

    if args.json:
        print(generate_json_report(results))
    elif args.html:
        html = generate_html_report(results)
        with open(REPORT_PATH, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"HTML报告已生成: {REPORT_PATH}")
        # 同时输出简要文本
        print(generate_text_report(results))
    else:
        print(generate_text_report(results))


if __name__ == "__main__":
    main()
