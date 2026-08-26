#!/usr/bin/env python3
"""看板HTML注入单元测试

验证 inject_commodities / inject_us_data / inject_a_shares 等函数的
HTML注入逻辑不会导致标签损坏、重复class、span嵌套错误等问题。

运行: python3 test_injection.py
"""

import re
import sys
import json
import importlib.util

sys.path.insert(0, '/Coze/Drive/金融分析')

# 加载 daily_update 模块
spec = importlib.util.spec_from_file_location('daily_update', '/Coze/Drive/金融分析/daily_update.py')
du = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(du)
except SystemExit:
    pass

PASS = 0
FAIL = 0

def assert_test(name, condition, detail=''):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f'  ✅ {name}')
    else:
        FAIL += 1
        print(f'  ❌ {name} {detail}')


# ============================================================
# Test 1: inject_commodities 不产生重复class
# ============================================================
print('\n=== Test 1: yield-chg 注入不产生重复class ===')

html_path = '/Coze/Drive/扣子/treasury_dashboard/index.html'
with open(html_path, 'r', encoding='utf-8') as f:
    html = f.read()

# 构造测试数据
test_data = {
    '_meta': {'fetch_time': '2026-08-24 09:00:00'},
    'btc': {
        'price': 80000, 'change': 100, 'change_pct': 0.13,
        'decimals': 0, 'prev_close': 79900
    },
    'gold': {
        'price': 4700.5, 'change': -20, 'change_pct': -0.42,
        'decimals': 2, 'prev_close': 4720.5
    },
    'wti': {
        'price': 86.0, 'change': 0, 'change_pct': 0.0,
        'decimals': 3, 'prev_close': 86.0
    },
    'brent': {
        'price': 91.5, 'change': -1.14, 'change_pct': -1.23,
        'decimals': 3, 'prev_close': 92.64
    },
}

# 连续注入3次，验证不会产生重复class
html_v1 = du.inject_commodities(html, test_data)
html_v2 = du.inject_commodities(html_v1, test_data)
html_v3 = du.inject_commodities(html_v2, test_data)

bad_spans = re.findall(r'class="yield-chg[^"]*(?:\s+\w+){2,}"', html_v3)
assert_test('连续3次注入后无重复class yield-chg', len(bad_spans) == 0,
            f'发现 {len(bad_spans)} 个: {bad_spans[:3]}')

bad_ov = re.findall(r'class="ov-chg[^"]*(?:\s+\w+){2,}"', html_v3)
assert_test('连续3次注入后无重复class ov-chg', len(bad_ov) == 0,
            f'发现 {len(bad_ov)} 个: {bad_ov[:3]}')


# ============================================================
# Test 2: 注入后每个商品区块有且只有一个 yield-chg span
# ============================================================
print('\n=== Test 2: 每个区块 yield-chg span 结构正确 ===')

for key, hint in [('btc', '比特币'), ('gold', '黄金'), ('wti', 'WTI'), ('brent', '布伦特')]:
    # 只在商品Tab内查找（page-commodities之后）
    comm_tab_start = html_v3.find('page-commodities')
    if comm_tab_start < 0:
        assert_test(f'{key} 商品Tab存在', False)
        continue
    
    title_pos = html_v3.find(hint, comm_tab_start)
    if title_pos < 0:
        assert_test(f'{key} ({hint}) 在商品Tab中', False)
        continue

    # commodity-block 中查找
    block_start = html_v3.rfind('commodity-block', comm_tab_start, title_pos)
    if block_start < 0 or title_pos - block_start > 500:
        assert_test(f'{key} ({hint}) 在 commodity-block 中', False)
        continue

    block_end = html_v3.find('</section>', title_pos)
    if block_end < 0:
        block_end = title_pos + 1000
    block = html_v3[block_start:block_end]

    yc_count = len(re.findall(r'class="yield-chg', block))
    assert_test(f'{key} 区块恰好1个yield-chg', yc_count == 1,
                f'实际有 {yc_count} 个')

    # 检查 span 结构: <span class="yield-chg ..."><span class="chg-icon">...</span></span>
    # 精确匹配：外层yield-chg包裹内层chg-icon
    yc_match = re.search(
        r'<span\s+class="yield-chg[^"]*"[^>]*><span\s+class="chg-icon"[^>]*>.*?</span></span>',
        block, re.DOTALL
    )
    if yc_match:
        span_html = yc_match.group()
        open_count = len(re.findall(r'<span\s', span_html))
        close_count = span_html.count('</span>')
        assert_test(f'{key} span结构正确(2 open, 2 close)',
                    open_count == 2 and close_count == 2,
                    f'open={open_count}, close={close_count}')
        assert_test(f'{key} 包含chg-icon', 'chg-icon' in span_html)
    else:
        assert_test(f'{key} yield-chg+chg-icon嵌套结构存在', False)


# ============================================================
# Test 3: validate_html_integrity 函数存在且可用
# ============================================================
print('\n=== Test 3: validate_html_integrity ===')

assert_test('validate_html_integrity 函数存在', hasattr(du, 'validate_html_integrity'))

if hasattr(du, 'validate_html_integrity'):
    valid, issues = du.validate_html_integrity(html_v3, 'test')
    yield_ok = not any('yield-chg' in i for i in issues)
    ov_ok = not any('ov-chg' in i for i in issues)
    assert_test('验证无yield-chg问题', yield_ok, f'issues: {issues}')
    assert_test('验证无ov-chg问题', ov_ok, f'issues: {issues}')


# ============================================================
# Test 4: 注入后价格数值正确
# ============================================================
print('\n=== Test 4: 价格数值正确 ===')

# BTC 价格应该是 $80,000
btc_val = re.search(r'yield-num[^>]*>(\$[\d,]+)', html_v3)
if btc_val:
    assert_test('BTC价格已更新为$80,000', btc_val.group(1) == '$80,000',
                f'实际: {btc_val.group(1)}')
else:
    assert_test('BTC yield-num 存在', False)


# ============================================================
# Test 5: 注入后涨跌幅文字正确
# ============================================================
print('\n=== Test 5: 涨跌幅文字正确 ===')

# 查找所有 yield-chg span，检查至少有一个包含▲
all_yc_contents = re.findall(r'yield-chg[^>]*>(.*?)</span>', html_v3, re.DOTALL)
has_up = any('▲' in c for c in all_yc_contents)
has_down = any('▼' in c for c in all_yc_contents)
has_flat = any('—' in c for c in all_yc_contents)
assert_test('存在上涨(▲)的yield-chg', has_up, f'contents: {[c[:30] for c in all_yc_contents[:5]]}')
assert_test('存在下跌(▼)的yield-chg', has_down)
assert_test('存在平盘(—)的yield-chg', has_flat)


# ============================================================
# 汇总
# ============================================================
print(f'\n{"=" * 50}')
print(f'测试结果: {PASS} 通过, {FAIL} 失败')
if FAIL > 0:
    sys.exit(1)
else:
    print('✅ 全部通过')
