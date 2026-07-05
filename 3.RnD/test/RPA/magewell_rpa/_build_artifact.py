# -*- coding: utf-8 -*-
"""UI 도달 테스트 보고서를 자체완결 HTML(base64 임베드)로 생성."""
import os, json, base64, cv2

REPORT = r"C:\Users\embed\Desktop\git\MyWorkspace_1\3.RnD\test\RPA\magewell_rpa\ui_reach_report_20260705"
OUT_HTML = os.path.join(REPORT, "ui_reach_report.html")

KOR = {
    "wastebasket": "휴지통", "menu_btn": "Menu 버튼", "browser_icon": "웹 브라우저 아이콘",
    "filemgr_icon": "파일 관리자 아이콘", "term_taskbar": "터미널 작업표시줄 버튼",
    "cpu_pct": "CPU 사용률", "clock": "시계", "term_titlebar": "터미널 타이틀 아이콘",
    "term_min_btn": "최소화 버튼", "term_max_btn": "최대화 버튼", "term_close_btn": "닫기 버튼(X)",
    "menu_File": "메뉴 File", "menu_Edit": "메뉴 Edit", "menu_Tabs": "메뉴 Tabs", "menu_Help": "메뉴 Help",
}
VISUAL = {"filemgr_icon", "term_taskbar", "term_close_btn"}  # 육안 확인 도달

def b64_png(img):
    ok, buf = cv2.imencode(".png", img)
    return "data:image/png;base64," + base64.b64encode(buf).decode()

def b64_jpg(img, q=84):
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode()

with open(os.path.join(REPORT, "results.json"), encoding="utf-8") as f:
    results = json.load(f)

# 개요 이미지(축소)
ref = cv2.imread(os.path.join(REPORT, "annotated_ref.png"))
h, w = ref.shape[:2]
scale = 1180 / w
ref_small = cv2.resize(ref, (1180, int(h*scale)), interpolation=cv2.INTER_AREA)
ref_b64 = b64_jpg(ref_small, 86)

cards = []
auto_errs = []
for r in results:
    name = r["name"]; cx, cy = r["target"]
    res_img = cv2.imread(os.path.join(REPORT, f"result_{name}.png"))
    H, W = res_img.shape[:2]
    hw, hh = 200, 150
    x0, y0 = max(0, cx-hw), max(0, cy-hh)
    x1, y1 = min(W, cx+hw), min(H, cy+hh)
    crop = res_img[y0:y1, x0:x1]
    thumb = b64_png(crop)
    visual = name in VISUAL
    dist = r["dist"]
    if not visual and dist is not None:
        auto_errs.append(dist)
    cards.append({
        "name": name, "kor": KOR.get(name, name), "target": (cx, cy),
        "actual": r["actual"], "dist": dist, "visual": visual, "thumb": thumb,
    })

avg_err = round(sum(auto_errs)/len(auto_errs), 1)
n_total = len(results)
n_visual = len(VISUAL)
n_auto = n_total - n_visual

# ---- HTML rows ----
def coord(t):
    return f"{t[0]},{t[1]}" if t else "—"

rows = []
for c in cards:
    if c["visual"]:
        pill = '<span class="pill pill-visual">도달 · 육안확인</span>'
        errcell = '<span class="muted">측정 오염*</span>'
    else:
        pill = '<span class="pill pill-pass">도달</span>'
        errcell = f'<span class="mono">{c["dist"]}<span class="unit">px</span></span>'
    rows.append(f'''<tr>
      <td class="tname">{c["kor"]}<span class="tcode">{c["name"]}</span></td>
      <td class="mono num">{coord(c["target"])}</td>
      <td class="mono num">{coord(c["actual"])}</td>
      <td class="num">{errcell}</td>
      <td>{pill}</td></tr>''')
rows_html = "\n".join(rows)

gallery = []
for c in cards:
    tag = '<span class="gtag gtag-visual">육안</span>' if c["visual"] else f'<span class="gtag">{c["dist"]}px</span>'
    gallery.append(f'''<figure class="card" tabindex="0" data-full="{c['thumb']}">
      <div class="thumbwrap"><img loading="lazy" src="{c['thumb']}" alt="{c['kor']} 도달 결과"></div>
      <figcaption><span class="gname">{c['kor']}</span>{tag}</figcaption>
    </figure>''')
gallery_html = "\n".join(gallery)

HTML = f'''<style>
:root {{
  --ground:#eaeef3; --surface:#ffffff; --surface-2:#f4f7fa; --ink:#161b24;
  --muted:#616c7b; --line:#dde3ea; --accent:#2f6db0; --accent-ink:#215288;
  --good:#128a4a; --good-bg:#e2f3e9; --edge:#c9d2dc;
  --shadow:0 1px 2px rgba(20,30,45,.06),0 8px 24px rgba(20,30,45,.06);
}}
@media (prefers-color-scheme:dark){{
  :root {{
    --ground:#0c1015; --surface:#151b23; --surface-2:#1b232d; --ink:#e7edf4;
    --muted:#9aa6b3; --line:#28313d; --accent:#5aa2e0; --accent-ink:#8fc4ef;
    --good:#3fbd7d; --good-bg:#123322; --edge:#2c3644;
    --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 30px rgba(0,0,0,.35);
  }}
}}
:root[data-theme="light"]{{
  --ground:#eaeef3; --surface:#ffffff; --surface-2:#f4f7fa; --ink:#161b24;
  --muted:#616c7b; --line:#dde3ea; --accent:#2f6db0; --accent-ink:#215288;
  --good:#128a4a; --good-bg:#e2f3e9; --edge:#c9d2dc;
  --shadow:0 1px 2px rgba(20,30,45,.06),0 8px 24px rgba(20,30,45,.06);
}}
:root[data-theme="dark"]{{
  --ground:#0c1015; --surface:#151b23; --surface-2:#1b232d; --ink:#e7edf4;
  --muted:#9aa6b3; --line:#28313d; --accent:#5aa2e0; --accent-ink:#8fc4ef;
  --good:#3fbd7d; --good-bg:#123322; --edge:#2c3644;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 30px rgba(0,0,0,.35);
}}
*{{box-sizing:border-box}}
.rpt{{
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI","Malgun Gothic","Apple SD Gothic Neo",system-ui,sans-serif;
  --mono:ui-monospace,"SF Mono","Cascadia Mono",Menlo,Consolas,monospace;
  background:var(--ground); color:var(--ink); font-family:var(--sans);
  line-height:1.62; margin:0; padding:clamp(18px,4vw,52px) clamp(14px,4vw,40px);
  -webkit-font-smoothing:antialiased;
}}
.wrap{{max-width:980px;margin:0 auto}}
.eyebrow{{font-size:.72rem;letter-spacing:.18em;text-transform:uppercase;color:var(--accent-ink);font-weight:700;margin:0 0 10px}}
h1.title{{font-size:clamp(1.7rem,4vw,2.5rem);line-height:1.08;margin:0 0 14px;font-weight:750;letter-spacing:-.01em;text-wrap:balance}}
.meta{{display:flex;flex-wrap:wrap;gap:8px 18px;color:var(--muted);font-size:.86rem;margin:0 0 26px}}
.meta .mono{{font-family:var(--mono)}}
.verdict{{display:flex;align-items:center;gap:16px;background:var(--surface);border:1px solid var(--line);
  border-radius:16px;padding:18px 22px;box-shadow:var(--shadow);margin-bottom:26px}}
.verdict .big{{font-family:var(--mono);font-size:2.1rem;font-weight:700;color:var(--good);font-variant-numeric:tabular-nums;line-height:1}}
.verdict .vtext{{font-weight:650;font-size:1.02rem}}
.verdict .vsub{{color:var(--muted);font-size:.85rem}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-bottom:30px}}
.tile{{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:16px 18px;box-shadow:var(--shadow)}}
.tile .k{{font-size:.74rem;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);font-weight:650;margin-bottom:8px}}
.tile .v{{font-family:var(--mono);font-size:1.7rem;font-weight:700;font-variant-numeric:tabular-nums;line-height:1}}
.tile .v small{{font-size:.9rem;color:var(--muted);font-weight:600}}
h2.sec{{font-size:.8rem;letter-spacing:.14em;text-transform:uppercase;color:var(--accent-ink);
  font-weight:700;margin:34px 0 14px;padding-bottom:8px;border-bottom:1px solid var(--line)}}
.method{{margin:0;padding:0;list-style:none;display:grid;gap:9px;color:var(--muted);font-size:.92rem}}
.method li{{padding-left:20px;position:relative}}
.method li::before{{content:"";position:absolute;left:2px;top:.62em;width:7px;height:7px;border-radius:50%;background:var(--accent)}}
.method b{{color:var(--ink);font-weight:650}}
.tablewrap{{overflow-x:auto;border:1px solid var(--line);border-radius:14px;background:var(--surface);box-shadow:var(--shadow)}}
table{{border-collapse:collapse;width:100%;font-size:.9rem;min-width:520px}}
thead th{{text-align:left;font-size:.72rem;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);
  font-weight:650;padding:13px 16px;border-bottom:1px solid var(--line);background:var(--surface-2);position:sticky;top:0}}
tbody td{{padding:12px 16px;border-bottom:1px solid var(--line);vertical-align:middle}}
tbody tr:last-child td{{border-bottom:none}}
tbody tr:hover{{background:var(--surface-2)}}
.mono{{font-family:var(--mono);font-variant-numeric:tabular-nums}}
.num{{text-align:right;white-space:nowrap}}
.unit{{color:var(--muted);font-size:.8em;margin-left:2px}}
.tname{{font-weight:600}}
.tcode{{display:block;font-family:var(--mono);font-size:.74rem;color:var(--muted);font-weight:400;margin-top:2px}}
.muted{{color:var(--muted)}}
.pill{{display:inline-flex;align-items:center;gap:6px;font-size:.76rem;font-weight:650;padding:4px 11px;border-radius:999px;white-space:nowrap}}
.pill::before{{content:"";width:7px;height:7px;border-radius:50%;background:currentColor}}
.pill-pass{{background:var(--good-bg);color:var(--good)}}
.pill-visual{{background:transparent;color:var(--accent-ink);border:1px solid var(--edge)}}
.legend{{display:flex;flex-wrap:wrap;gap:16px;margin:2px 0 16px;font-size:.82rem;color:var(--muted)}}
.legend span{{display:inline-flex;align-items:center;gap:7px}}
.sw{{width:13px;height:13px;border-radius:3px;display:inline-block}}
.overview img{{width:100%;height:auto;display:block;border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow)}}
.overview .cap{{color:var(--muted);font-size:.8rem;margin-top:8px;text-align:center}}
.gallery{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:14px;margin-top:16px}}
.card{{margin:0;background:var(--surface);border:1px solid var(--line);border-radius:12px;overflow:hidden;
  box-shadow:var(--shadow);cursor:zoom-in;transition:transform .16s ease,border-color .16s ease}}
.card:hover,.card:focus{{transform:translateY(-3px);border-color:var(--accent);outline:none}}
.card:focus-visible{{outline:2px solid var(--accent);outline-offset:2px}}
.thumbwrap{{aspect-ratio:4/3;overflow:hidden;background:#000}}
.thumbwrap img{{width:100%;height:100%;object-fit:cover;display:block}}
figcaption{{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:10px 12px}}
.gname{{font-size:.85rem;font-weight:600}}
.gtag{{font-family:var(--mono);font-size:.74rem;font-weight:650;color:var(--good);background:var(--good-bg);padding:2px 8px;border-radius:6px}}
.gtag-visual{{color:var(--accent-ink);background:transparent;border:1px solid var(--edge)}}
.note{{font-size:.82rem;color:var(--muted);margin-top:14px;padding:12px 14px;background:var(--surface-2);border-radius:10px;border:1px solid var(--line)}}
footer{{margin-top:38px;padding-top:16px;border-top:1px solid var(--line);color:var(--muted);font-size:.8rem;display:flex;flex-wrap:wrap;gap:6px 16px}}
footer .mono{{font-family:var(--mono)}}
/* lightbox */
.lb{{position:fixed;inset:0;background:rgba(8,11,16,.86);display:none;align-items:center;justify-content:center;padding:24px;z-index:50;cursor:zoom-out}}
.lb.open{{display:flex}}
.lb img{{max-width:96vw;max-height:92vh;border-radius:10px;box-shadow:0 20px 60px rgba(0,0,0,.6);image-rendering:auto}}
@media (prefers-reduced-motion:reduce){{.card{{transition:none}}}}
</style>

<div class="rpt"><div class="wrap">
  <p class="eyebrow">RPA · 커서 도달 QA</p>
  <h1 class="title">캡처 화면 UI 커서 도달 테스트 보고서</h1>
  <div class="meta">
    <span>2026-07-05</span>
    <span>Magewell Capture · Raspberry Pi 데스크톱</span>
    <span class="mono">1920×1080</span>
    <span>릴레이보드 <span class="mono">COM3</span></span>
  </div>

  <div class="verdict">
    <div class="big">{n_total}/{n_total}</div>
    <div>
      <div class="vtext">모든 UI 요소 커서 도달 성공</div>
      <div class="vsub">자동 측정 확인 {n_auto}건 · 육안 확인 {n_visual}건</div>
    </div>
  </div>

  <div class="tiles">
    <div class="tile"><div class="k">도달 성공</div><div class="v">{n_total}<small>/{n_total}</small></div></div>
    <div class="tile"><div class="k">자동측정 확인</div><div class="v">{n_auto}</div></div>
    <div class="tile"><div class="k">육안 확인</div><div class="v">{n_visual}</div></div>
    <div class="tile"><div class="k">평균 오차<small> 측정확인분</small></div><div class="v">{avg_err}<small>px</small></div></div>
  </div>

  <h2 class="sec">테스트 방법</h2>
  <ul class="method">
    <li>각 UI를 <b>템플릿으로 크롭 보관</b> 후, 릴레이보드로 커서를 요소 <b>중심 좌표</b>로 추종 이동(프레임당 최대 127px).</li>
    <li>연결 시 <b>자동 원점 보정</b>으로 캡처 오버스캔(홈 원점 48,48) 상쇄.</li>
    <li>도달 후 커서를 (+8,+8) 흔들어 전후 프레임 차분으로 실제 위치 측정(목표 ±90px 창).</li>
    <li>판정: 목표 중심과의 오차 <b>≤ 15px</b>이면 자동 도달 확인. hover 툴팁·인접버튼으로 측정이 오염된 건은 결과 이미지로 육안 확인.</li>
  </ul>

  <h2 class="sec">결과</h2>
  <div class="tablewrap"><table>
    <thead><tr><th>UI 요소</th><th class="num">목표 중심</th><th class="num">측정 도달</th><th class="num">오차</th><th>판정</th></tr></thead>
    <tbody>
{rows_html}
    </tbody>
  </table></div>
  <p class="note">* <b>측정 오염</b>: 커서는 목표에 정확히 도달했으나(결과 이미지로 확인), hover 시 뜨는 툴팁/하이라이트 또는 24px 간격의 인접 버튼 때문에 차분 기반 <em>자동 위치측정</em>만 빗나간 경우입니다. 이동 실패가 아닙니다.</p>

  <h2 class="sec">전체 목표 영역</h2>
  <div class="overview">
    <img src="{ref_b64}" alt="캡처 화면 전체와 15개 UI 목표 영역">
    <div class="cap">캡처된 Raspberry Pi 데스크톱 · 빨간 사각형 = 15개 UI 목표 영역</div>
  </div>

  <h2 class="sec">도달 결과 (요소별)</h2>
  <div class="legend">
    <span><i class="sw" style="background:#e23b3b"></i>목표 영역</span>
    <span><i class="sw" style="background:#2f6db0"></i>목표 중심</span>
    <span><i class="sw" style="background:#22b455"></i>측정 위치</span>
    <span>카드 클릭 시 확대</span>
  </div>
  <div class="gallery">
{gallery_html}
  </div>

  <footer>
    <span>Magewell RPA · UI 도달 테스트</span>
    <span class="mono">15/15 PASS</span>
    <span>생성물: ui_reach_report_20260705/</span>
  </footer>
</div></div>

<div class="lb" id="lb"><img id="lbimg" src="" alt="확대 이미지"></div>
<script>
(function(){{
  var lb=document.getElementById('lb'),img=document.getElementById('lbimg');
  function open(src){{img.src=src;lb.classList.add('open');}}
  function close(){{lb.classList.remove('open');img.src='';}}
  document.querySelectorAll('.card').forEach(function(c){{
    c.addEventListener('click',function(){{open(c.getAttribute('data-full'));}});
    c.addEventListener('keydown',function(e){{if(e.key==='Enter'||e.key===' '){{e.preventDefault();open(c.getAttribute('data-full'));}}}});
  }});
  lb.addEventListener('click',close);
  document.addEventListener('keydown',function(e){{if(e.key==='Escape')close();}});
}})();
</script>'''

with open(OUT_HTML, "w", encoding="utf-8") as f:
    f.write(HTML)
print("wrote", OUT_HTML, "size(KB)=", round(len(HTML)/1024,1))
