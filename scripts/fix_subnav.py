#!/usr/bin/env python3
"""
修复子导航栏固定：
1. 美股/A股子导航改为 fixed 定位，始终可见
2. 确保刷新按钮正常工作
"""

HTML = '/Coze/Drive/扣子/treasury_dashboard/index.html'

with open(HTML, 'r', encoding='utf-8') as f:
    html = f.read()

# ─── 1. 替换子导航CSS为fixed定位 ───
old_css = """    .us-subnav {
      position: sticky; top: 0; z-index: 50;
      display: flex; gap: 4px; padding: 8px 6px;
      background: rgba(17, 24, 39, 0.92); backdrop-filter: blur(10px);
      border-bottom: 1px solid rgba(255,255,255,.08);
      margin: -12px -12px 12px -12px; padding-left: 12px; padding-right: 12px;
      overflow-x: auto; -webkit-overflow-scrolling: touch;
      scrollbar-width: none;
    }"""

new_css = """    .us-subnav {
      position: fixed; left: 0; right: 0; z-index: 90;
      display: flex; gap: 4px; padding: 8px 6px;
      background: rgba(17, 24, 39, 0.95); backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      border-bottom: 1px solid rgba(255,255,255,.08);
      padding-left: max(12px, env(safe-area-inset-left));
      padding-right: max(12px, env(safe-area-inset-right));
      overflow-x: auto; -webkit-overflow-scrolling: touch;
      scrollbar-width: none;
      transition: top .2s ease;
    }
    .subnav-spacer { display: block; height: 40px; }"""

html = html.replace(old_css, new_css)

# ─── 2. 在每个subnav前面插入spacer，防止内容被遮挡 ───
# 美股subnav
html = html.replace(
    '    <div class="us-subnav" id="usSubnav">',
    '    <div class="subnav-spacer"></div>\n    <div class="us-subnav" id="usSubnav">'
)
# A股subnav
html = html.replace(
    '    <div class="us-subnav" id="aSubnav">',
    '    <div class="subnav-spacer"></div>\n    <div class="us-subnav" id="aSubnav">'
)

# ─── 3. 添加JS：动态计算subnav位置（跟随header高度）───
subnav_js = """
/* ── 子导航固定定位 ── */
(function(){
  function updateSubnavPos(){
    var header = document.querySelector('.app-header');
    var headerH = header ? header.offsetHeight : 0;
    var subnavs = document.querySelectorAll('.us-subnav');
    subnavs.forEach(function(sn){
      sn.style.top = headerH + 'px';
    });
  }
  // 初始设置 + 窗口变化时重算
  updateSubnavPos();
  window.addEventListener('resize', updateSubnavPos);
  // 监听Tab切换，确保切换后也正确定位
  document.querySelectorAll('.tab-btn, .top-tab-btn').forEach(function(btn){
    btn.addEventListener('click', function(){ setTimeout(updateSubnavPos, 100); });
  });
  // Header高度可能因top-tabs展开而变化，用ResizeObserver监听
  if(window.ResizeObserver){
    var header = document.querySelector('.app-header');
    if(header) new ResizeObserver(updateSubnavPos).observe(header);
  }
})();
"""

# 插入到已有的</script>前（或body前）
# 找到最后一个 </script> 标签之前
last_script_end = html.rfind('</script>')
if last_script_end > 0:
    # 在最后一个</script>后插入新的script块
    insert_pos = last_script_end + len('</script>')
    html = html[:insert_pos] + '\n<script>' + subnav_js + '</script>' + html[insert_pos:]
else:
    html = html.replace('</body>', '<script>' + subnav_js + '</script>\n</body>')

with open(HTML, 'w', encoding='utf-8') as f:
    f.write(html)

print(f"Subnav CSS → fixed positioning")
print(f"Added spacer divs for both subnavs")
print(f"Added JS for dynamic position calculation")
print(f"File size: {len(html):,} bytes")
