#!/usr/bin/env python3
"""
增强看板UX:
1. 更新SW缓存版本号 → 强制PWA刷新
2. Header添加刷新+分享按钮
3. Header添加紧凑Tab切换条（解决页面太长回不去导航的问题）
"""
import re

HTML = '/Coze/Drive/扣子/treasury_dashboard/index.html'
SW   = '/Coze/Drive/扣子/treasury_dashboard/sw.js'

# ─── 1. 更新SW缓存版本 ───
with open(SW, 'r', encoding='utf-8') as f:
    sw = f.read()
sw_new = sw.replace("treasury-dashboard-v1", "treasury-dashboard-v2-20260823")
with open(SW, 'w', encoding='utf-8') as f:
    f.write(sw_new)
print("[1/3] SW cache version bumped → treasury-dashboard-v2-20260823")

# ─── 2+3. 修改HTML ───
with open(HTML, 'r', encoding='utf-8') as f:
    html = f.read()

# --- A: 在header CSS后添加新样式 ---
header_css_end = ".app-header .date { font-size: 13px; color: #9ca3af; }"
new_css = """

  /* ===== Header 操作按钮 ===== */
  .header-actions { display: flex; gap: 6px; align-items: center; margin-left: 8px; }
  .header-btn {
    width: 32px; height: 32px; border-radius: 8px; border: none;
    background: rgba(255,255,255,.08); color: #9ca3af; font-size: 15px;
    display: flex; align-items: center; justify-content: center; cursor: pointer;
    transition: background .2s, color .2s;
  }
  .header-btn:hover { background: rgba(255,255,255,.15); color: #e5e7eb; }
  .header-btn.spin { animation: hdr-spin .6s linear; }
  @keyframes hdr-spin { from{transform:rotate(0)} to{transform:rotate(360deg)} }

  /* ===== 顶部快捷Tab条 ===== */
  .top-tabs {
    display: flex; gap: 2px; margin-top: 10px; padding-top: 8px;
    border-top: 1px solid rgba(255,255,255,.06);
    overflow-x: auto; -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
  }
  .top-tabs::-webkit-scrollbar { display: none; }
  .top-tab-btn {
    flex-shrink: 0;
    padding: 5px 12px; font-size: 12px; font-weight: 500;
    border-radius: 16px; border: none; cursor: pointer;
    background: transparent; color: #6b7280;
    transition: all .2s;
  }
  .top-tab-btn.active { background: rgba(59,130,246,.2); color: #60a5fa; }
  .top-tab-btn:not(.active):hover { color: #d1d5db; }

  /* ===== Toast 提示 ===== */
  .toast {
    position: fixed; top: 50%; left: 50%; transform: translate(-50%,-50%) scale(.9);
    background: rgba(0,0,0,.85); color: #fff; padding: 14px 24px;
    border-radius: 12px; font-size: 14px; z-index: 9999;
    opacity: 0; pointer-events: none; transition: all .3s;
  }
  .toast.show { opacity: 1; transform: translate(-50%,-50%) scale(1); }"""

html = html.replace(header_css_end, header_css_end + new_css)

# --- B: 替换header HTML，添加按钮和顶部Tab条 ---
old_header = """  <header class="app-header">
    <div class="app-header-inner">
      <h1><span class="accent">🌍</span> 全球资产看板</h1>
      <div class="date">2026-08-23</div>
    </div>
  </header>"""

new_header = """  <header class="app-header">
    <div class="app-header-inner">
      <h1><span class="accent">🌍</span> 全球资产看板</h1>
      <div style="display:flex;align-items:center;">
        <div class="date">2026-08-23</div>
        <div class="header-actions">
          <button class="header-btn" id="btn-refresh" title="刷新数据">🔄</button>
          <button class="header-btn" id="btn-share" title="分享看板">📤</button>
        </div>
      </div>
    </div>
    <div class="top-tabs" id="top-tabs">
      <button class="top-tab-btn active" data-tab="overview">📊 总览</button>
      <button class="top-tab-btn" data-tab="bonds">🇺🇸 美债</button>
      <button class="top-tab-btn" data-tab="commodities">💰 商品</button>
      <button class="top-tab-btn" data-tab="us-stocks">🇺🇸 美股</button>
      <button class="top-tab-btn" data-tab="a-shares">🇨🇳 A股</button>
    </div>
  </header>"""

html = html.replace(old_header, new_header)

# --- C: 在</body>前添加JS逻辑 ---
extra_js = """
<script>
/* ── 顶部Tab快捷切换 ── */
(function(){
  var topTabs = document.querySelectorAll('#top-tabs .top-tab-btn');
  var bottomTabs = document.querySelectorAll('.tab-btn');
  topTabs.forEach(function(btn){
    btn.addEventListener('click', function(){
      var tab = btn.dataset.tab;
      // 触发底部Tab切换逻辑
      bottomTabs.forEach(function(b){ if(b.dataset.tab===tab) b.click(); });
    });
  });
  // 同步高亮
  function syncTopTab(){
    var active = document.querySelector('.tab-btn.active');
    if(!active) return;
    var tab = active.dataset.tab;
    topTabs.forEach(function(b){
      b.classList.toggle('active', b.dataset.tab === tab);
    });
  }
  // 每次Tab切换后同步
  var origClick = HTMLElement.prototype.click;
  bottomTabs.forEach(function(btn){
    btn.addEventListener('click', function(){ setTimeout(syncTopTab, 50); });
  });
})();

/* ── 刷新按钮 ── */
document.getElementById('btn-refresh').addEventListener('click', function(){
  var btn = this;
  btn.classList.add('spin');
  // 清除SW缓存并强制刷新
  if('serviceWorker' in navigator){
    navigator.serviceWorker.getRegistration().then(function(reg){
      if(reg){
        reg.update().then(function(){
          if(reg.waiting){ reg.waiting.postMessage('SKIP_WAITING'); }
        });
      }
      // 清除所有缓存
      caches.keys().then(function(names){
        Promise.all(names.map(function(n){ caches.delete(n); }));
      });
    });
  }
  // Toast
  showToast('正在刷新数据...');
  setTimeout(function(){
    btn.classList.remove('spin');
    location.reload();
  }, 800);
});

/* ── 分享按钮 ── */
document.getElementById('btn-share').addEventListener('click', function(){
  var url = location.href;
  var title = '全球资产看板';
  var text = '美债·商品·美股·A股 一站式看板';
  if(navigator.share){
    navigator.share({title:title, text:text, url:url}).catch(function(){});
  } else {
    // 降级：复制到剪贴板
    if(navigator.clipboard){
      navigator.clipboard.writeText(url).then(function(){
        showToast('链接已复制到剪贴板');
      });
    } else {
      prompt('复制以下链接分享：', url);
    }
  }
});

/* ── Toast ── */
function showToast(msg){
  var t = document.querySelector('.toast');
  if(!t){
    t = document.createElement('div');
    t.className = 'toast';
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(function(){ t.classList.remove('show'); }, 2000);
}
</script>
"""

# 插入到 </body> 前
html = html.replace('</body>', extra_js + '</body>')

with open(HTML, 'w', encoding='utf-8') as f:
    f.write(html)

print(f"[2/3] Header enhanced: refresh + share + top tab bar")
print(f"[3/3] File size: {len(html):,} bytes")
print("Done!")
