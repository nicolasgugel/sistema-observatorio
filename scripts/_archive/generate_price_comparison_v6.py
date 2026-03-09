from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "output" / "prices.csv"
OUTPUT_PATH = ROOT / "price_comparison_v6_premium.html"
VALID_OFFERS = {
    "renting_no_insurance",
    "renting_with_insurance",
    "financing_max_term",
    "cash",
}


def _to_int(raw: str) -> int | None:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _to_float(raw: str) -> float | None:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _to_bool(raw: str) -> bool | None:
    value = (raw or "").strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def load_rows(path: Path) -> tuple[list[dict], str]:
    rows: list[dict] = []
    extracted: list[str] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            brand = (row.get("brand") or "").strip()
            offer_type = (row.get("offer_type") or "").strip()
            if brand.lower() != "samsung" or offer_type not in VALID_OFFERS:
                continue
            price_value = _to_float(row.get("price_value") or "")
            if price_value is None:
                continue
            ts = (row.get("extracted_at") or "").strip()
            if ts:
                extracted.append(ts)
            rows.append(
                {
                    "retailer": (row.get("retailer") or "").strip(),
                    "model": (row.get("model") or "").strip(),
                    "capacity_gb": _to_int(row.get("capacity_gb") or ""),
                    "offer_type": offer_type,
                    "price_value": price_value,
                    "price_unit": (row.get("price_unit") or "").strip(),
                    "term_months": _to_int(row.get("term_months") or ""),
                    "in_stock": _to_bool(row.get("in_stock") or ""),
                    "brand": "Samsung",
                }
            )
    rows.sort(key=lambda r: (r["model"], str(r["capacity_gb"]), r["retailer"], r["offer_type"], r["price_value"]))
    return rows, (max(extracted) if extracted else "")


def build_html(rows: list[dict], extracted_at: str) -> str:
    data_json = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    html = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Comparador de Precios Samsung</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@700;800&family=Inter:wght@400;600;700&display=swap" rel="stylesheet" />
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    :root { --red:#EC0000; --red2:#CC0000; --ink:#1A1A2E; --muted:#646c80; --bg:#F7F8FA; --line:#EAEDF1; --shadow:0 1px 3px rgba(0,0,0,.04),0 10px 30px rgba(0,0,0,.06); }
    * { box-sizing:border-box; margin:0; padding:0; }
    body { font-family:Inter,sans-serif; background:radial-gradient(1100px 380px at 12% -12%, rgba(236,0,0,.16), transparent 60%), linear-gradient(180deg,#f6f7fa,#f7f8fa); color:var(--ink); padding:20px; }
    .dash { max-width:1360px; margin:0 auto; background:#fff; border-radius:28px; box-shadow:0 22px 54px rgba(30,35,60,.14); overflow:hidden; }
    .hero { padding:30px 34px; display:flex; justify-content:space-between; gap:18px; align-items:center; color:#fff; background:linear-gradient(135deg,var(--red2),var(--red)); position:relative; overflow:hidden; }
    .hero:before { content:""; position:absolute; inset:-30% -10%; background:radial-gradient(circle at 15% 18%, rgba(255,255,255,.28), transparent 20%), linear-gradient(120deg, transparent 30%, rgba(255,255,255,.16) 45%, transparent 60%); }
    .hero h1,.hero p,.hero .brand { position:relative; z-index:1; }
    h1 { font-family:Outfit,sans-serif; font-size:clamp(1.6rem,3vw,2.3rem); letter-spacing:-.02em; line-height:1.1; margin-bottom:6px; }
    .hero p { font-size:.98rem; opacity:.95; font-weight:600; }
    .brand { border:1px solid rgba(255,255,255,.45); border-radius:16px; background:rgba(255,255,255,.1); padding:10px 14px; min-width:232px; text-align:right; }
    .brand strong { font-family:Outfit,sans-serif; font-weight:800; font-size:1.05rem; display:block; }
    .brand span { opacity:.92; font-size:.84rem; }
    .content { padding:20px 24px 0; background:linear-gradient(180deg, rgba(247,248,250,.75), #fff); }
    .kpis { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin-bottom:14px; }
    .kpi { border:1px solid rgba(236,0,0,.14); border-left:4px solid var(--red); border-radius:14px; padding:12px; background:linear-gradient(140deg,#fff,rgba(255,255,255,.86)); box-shadow:var(--shadow); min-height:102px; animation:up .45s ease both; }
    .kpi:nth-child(2){animation-delay:.05s;} .kpi:nth-child(3){animation-delay:.1s;} .kpi:nth-child(4){animation-delay:.15s;}
    .kpi .h { display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:8px; }
    .kpi .t { font-size:.73rem; text-transform:uppercase; letter-spacing:.08em; color:#737a8d; font-weight:700; }
    .ki { width:24px; height:24px; border-radius:8px; border:1px solid rgba(236,0,0,.22); background:rgba(236,0,0,.1); color:var(--red); display:inline-flex; align-items:center; justify-content:center; flex:0 0 auto; }
    .ki svg { width:14px; height:14px; stroke:currentColor; fill:none; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; }
    .kpi .v { font-family:Outfit,sans-serif; font-size:clamp(1.15rem,2.2vw,1.55rem); font-weight:800; line-height:1.15; }
    .kpi .m { margin-top:5px; font-size:.79rem; color:var(--muted); min-height:16px; }
    .panel { border:1px solid var(--line); border-radius:22px; background:#fff; box-shadow:var(--shadow); padding:14px; margin-bottom:14px; }
    .filters { display:grid; grid-template-columns:repeat(6,minmax(0,1fr)); gap:10px; align-items:end; }
    .f { display:flex; flex-direction:column; gap:7px; min-width:0; }
    .f label { font-size:.71rem; text-transform:uppercase; letter-spacing:.07em; color:#727b8f; font-weight:700; }
    .pill, .multi-toggle { height:44px; border-radius:999px; border:1px solid #d9dde6; background:#fff; padding:0 14px; font:600 .94rem Inter,sans-serif; color:var(--ink); width:100%; outline:none; transition:.2s; }
    .pill:focus, .multi-toggle:focus-visible { border-color:rgba(236,0,0,.65); box-shadow:0 0 0 3px rgba(236,0,0,.14); }
    .multi { position:relative; grid-column:span 2; }
    .multi-toggle { text-align:left; cursor:pointer; display:flex; align-items:center; justify-content:space-between; }
    .menu { display:none; position:absolute; left:0; right:0; top:calc(100% + 8px); z-index:30; background:#fff; border:1px solid #e4e8ef; border-radius:14px; box-shadow:0 16px 34px rgba(16,20,31,.14); overflow:hidden; }
    .menu.open { display:block; }
    .menu-head { display:flex; justify-content:space-between; padding:10px 12px; background:#f8fafc; border-bottom:1px solid #edf0f5; }
    .menu-head button { border:none; background:none; font-size:.78rem; font-weight:700; color:#53617e; cursor:pointer; }
    .opts { max-height:270px; overflow:auto; padding:7px; display:grid; gap:4px; }
    .opt { display:grid; grid-template-columns:auto auto 1fr; align-items:center; gap:10px; padding:8px 10px; border-radius:10px; cursor:pointer; }
    .opt:hover { background:rgba(236,0,0,.06); }
    .opt input { width:16px; height:16px; accent-color:var(--red); }
    .opt img { width:18px; height:18px; object-fit:contain; border:1px solid #e7eaf0; border-radius:4px; padding:1px; background:#fff; }
    .opt span { font-size:.9rem; font-weight:600; color:#2b3042; }
    .btn { height:46px; border:none; border-radius:999px; padding:0 24px; font:800 .98rem Outfit,sans-serif; color:#fff; background:linear-gradient(140deg,var(--red),var(--red2)); cursor:pointer; box-shadow:0 10px 24px rgba(236,0,0,.3); transition:.2s; }
    .btn:hover { transform:translateY(-1px) scale(1.01); box-shadow:0 14px 28px rgba(236,0,0,.35); }
    .title { font:700 1.05rem Outfit,sans-serif; color:#20243a; margin-bottom:10px; }
    .placeholder { min-height:430px; border:1px dashed #d7dce6; border-radius:15px; background:linear-gradient(180deg,#fbfcff,#f7f8fb); display:grid; place-items:center; text-align:center; color:#80879a; font-weight:600; padding:20px; }
    .chart-wrap { height:430px; border:1px solid #edf0f5; border-radius:15px; background:linear-gradient(180deg,#fdfefe,#f7f9fc); padding:8px 12px; display:none; position:relative; overflow:hidden; }
    .chart-wrap.on { display:block; }
    .chart-canvas-box { height:calc(100% - 72px); position:relative; }
    .chart-canvas-box canvas { width:100% !important; height:100% !important; display:block; }
    .logo-strip { display:none; position:absolute; left:12px; right:12px; bottom:6px; height:64px; }
    .logo-strip.on { display:block; }
    .logo-pill { position:absolute; left:0; top:0; width:94px; transform:translateX(-50%); display:flex; flex-direction:column; align-items:center; gap:4px; }
    .logo-pill img { width:44px; height:22px; object-fit:contain; background:#fff; border:1px solid #e7eaf0; border-radius:6px; padding:2px; }
    .logo-pill span { text-align:center; font-size:.67rem; color:#727b8f; font-weight:600; line-height:1.2; }
    .empty { display:none; border:1px dashed #d6dce7; border-radius:14px; background:#f8fafe; color:#7b8398; padding:24px; text-align:center; font-weight:600; margin-bottom:10px; }
    .table-wrap { border:1px solid #e5e8ef; border-radius:14px; overflow:auto; max-height:460px; }
    table { width:100%; border-collapse:collapse; min-width:920px; font-size:.91rem; }
    thead th { position:sticky; top:0; z-index:1; background:#1A1A2E; color:#fff; text-transform:uppercase; letter-spacing:.06em; font-size:.76rem; text-align:left; padding:11px 12px; white-space:nowrap; }
    tbody td { border-bottom:1px solid #edf0f5; padding:10px 12px; color:#22293e; white-space:nowrap; }
    tbody tr:hover { background:#f7fafe; }
    tbody tr.santander { background:rgba(236,0,0,.04); box-shadow:inset 3px 0 0 var(--red); }
    .price { font-weight:700; }
    .badge { display:inline-flex; border-radius:999px; padding:4px 10px; font-size:.75rem; font-weight:700; border:1px solid transparent; }
    .b-rn { background:rgba(236,0,0,.09); color:#b30000; border-color:rgba(179,0,0,.18); }
    .b-rw { background:rgba(230,0,126,.09); color:#a60062; border-color:rgba(166,0,98,.22); }
    .b-fin { background:rgba(3,78,162,.10); color:#034ea2; border-color:rgba(3,78,162,.24); }
    .b-cash { background:rgba(0,103,57,.11); color:#005832; border-color:rgba(0,88,50,.24); }
    .yes { color:#0d7a46; font-weight:700; } .no { color:#b02a37; font-weight:700; }
    footer { border-top:1px solid #edf1f6; background:#fafbfd; color:#6f7890; font-size:.8rem; display:flex; justify-content:space-between; gap:8px; padding:12px 22px 14px; flex-wrap:wrap; }
    @keyframes up { from { opacity:0; transform:translateY(8px); } to { opacity:1; transform:translateY(0); } }
    @media (max-width:1200px){ .kpis{grid-template-columns:repeat(2,minmax(0,1fr));} .filters{grid-template-columns:repeat(2,minmax(0,1fr));} .multi{grid-column:span 2;} .btn{width:100%;} }
    @media (max-width:760px){ body{padding:12px 8px;} .hero{padding:22px 16px; flex-direction:column; align-items:flex-start;} .brand{width:100%; text-align:left; min-width:0;} .content{padding:14px 10px 0;} .kpis,.filters{grid-template-columns:1fr;} .multi{grid-column:span 1;} }
  </style>
</head>
<body>
  <main class="dash">
    <header class="hero">
      <div>
        <h1>Comparador de Precios Samsung</h1>
        <p>Santander Boutique &middot; Inteligencia de Mercado</p>
      </div>
      <div class="brand"><strong>Santander Boutique</strong><span>Dashboard de monitorizacion competitiva</span></div>
    </header>
    <section class="content">
      <section class="kpis">
        <article class="kpi">
          <div class="h"><div class="t">Modelo seleccionado</div><span class="ki"><svg viewBox="0 0 24 24"><rect x="7" y="2.8" width="10" height="18.4" rx="2.2"></rect><path d="M11 18.2h2"></path></svg></span></div>
          <div class="v" id="kModel">-</div><div class="m" id="kModelMeta"></div>
        </article>
        <article class="kpi">
          <div class="h"><div class="t">Mejor precio renting</div><span class="ki"><svg viewBox="0 0 24 24"><path d="M4 7h12"></path><path d="M13 3l3.8 4L13 11"></path><path d="M20 17H8"></path><path d="M11 13l-3.8 4L11 21"></path></svg></span></div>
          <div class="v" id="kRenting">-</div><div class="m" id="kRentingMeta"></div>
        </article>
        <article class="kpi">
          <div class="h"><div class="t">Mejor precio contado</div><span class="ki"><svg viewBox="0 0 24 24"><rect x="3" y="7" width="18" height="12" rx="2"></rect><path d="M3 11h18"></path><path d="M7 15h3"></path></svg></span></div>
          <div class="v" id="kCash">-</div><div class="m" id="kCashMeta"></div>
        </article>
        <article class="kpi">
          <div class="h"><div class="t">Retailers activos</div><span class="ki"><svg viewBox="0 0 24 24"><path d="M3 21h18"></path><path d="M5 21V8h5v13"></path><path d="M14 21V3h5v18"></path></svg></span></div>
          <div class="v" id="kRetailers">0</div><div class="m" id="kRetailersMeta"></div>
        </article>
      </section>
      <section class="panel">
        <div class="filters">
          <div class="f">
            <label for="fModality">Modalidad</label>
            <select id="fModality" class="pill">
              <option value="renting_no_insurance">Renting SIN seguro</option>
              <option value="renting_with_insurance" selected>Renting CON seguro</option>
              <option value="financing_max_term">Financiacion</option>
              <option value="cash">Compra al contado</option>
            </select>
          </div>
          <div class="f"><label for="fModel">Modelo</label><select id="fModel" class="pill"></select></div>
          <div class="f"><label for="fCapacity">Capacidad</label><select id="fCapacity" class="pill"></select></div>
          <div class="f" id="termField" style="display:none;"><label for="fTerm">Plazo</label><select id="fTerm" class="pill"></select></div>
          <div class="f multi">
            <label for="retailerToggle">Retailers</label>
            <button id="retailerToggle" class="multi-toggle" type="button" aria-expanded="false"><span id="retailerText">Todos los retailers</span><span>v</span></button>
            <div class="menu" id="retailerMenu">
              <div class="menu-head"><button type="button" id="retailerAll">Seleccionar todos</button><button type="button" id="retailerNone">Limpiar</button></div>
              <div class="opts" id="retailerOpts"></div>
            </div>
          </div>
          <div class="f"><label>&nbsp;</label><button type="button" id="btnGenerate" class="btn">Generar Comparativa</button></div>
        </div>
      </section>
      <section class="panel">
        <h2 class="title">Comparativa de precios por retailer</h2>
        <div id="placeholder" class="placeholder">Selecciona filtros y pulsa <strong>Generar Comparativa</strong>.</div>
        <div id="chartWrap" class="chart-wrap"><div class="chart-canvas-box"><canvas id="chart" height="365"></canvas></div><div id="logoStrip" class="logo-strip"></div></div>
      </section>
      <section class="panel">
        <h2 class="title">Ofertas filtradas (ordenadas por precio)</h2>
        <div id="empty" class="empty">No hay ofertas para los filtros seleccionados.</div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Retailer</th><th>Modelo</th><th>Capacidad</th><th>Modalidad</th><th>Plazo</th><th>Precio</th><th>Unidad</th><th>Stock</th></tr></thead>
            <tbody id="rows"></tbody>
          </table>
        </div>
      </section>
    </section>
    <footer><span id="footerTs">Extraccion: --</span><span>Santander Boutique &middot; Dashboard v6.0 Premium</span></footer>
  </main>
  <script>
    const DATA = __DATA__;
    const EXTRACTED_AT = "__EXTRACTED__";
    const OFFER_LABELS = { renting_no_insurance:"Renting SIN seguro", renting_with_insurance:"Renting CON seguro", financing_max_term:"Financiacion", cash:"Compra al contado" };
    const BADGES = { renting_no_insurance:"b-rn", renting_with_insurance:"b-rw", financing_max_term:"b-fin", cash:"b-cash" };
    const COLORS = { "Santander Boutique":"#EC0000", "Movistar":"#019DF4", "Rentik":"#E6007E", "Grover":"#FF245B", "Media Markt":"#DF0000", "El Corte Inglés":"#006739", "El Corte Ingles":"#006739", "Samsung Oficial":"#034EA2", "Qonexa":"#333333", "Amazon":"#FF9900" };
    const LOGOS = {
      "Santander Boutique":[
        "https://upload.wikimedia.org/wikipedia/commons/b/b8/Santander_Logotipo.svg",
        "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b8/Santander_Logotipo.svg/512px-Santander_Logotipo.svg.png"
      ],
      "Movistar":[
        "https://upload.wikimedia.org/wikipedia/commons/1/1c/Movistar_logo.svg",
        "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1c/Movistar_logo.svg/512px-Movistar_logo.svg.png"
      ],
      "Rentik":[
        "https://www.rentik.com/img/footer/logo_rentik.svg",
        "https://www.rentik.com/favicon.ico"
      ],
      "Grover":[
        "https://upload.wikimedia.org/wikipedia/commons/c/c5/Grover_Logo.svg",
        "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c5/Grover_Logo.svg/512px-Grover_Logo.svg.png"
      ],
      "Media Markt":[
        "https://upload.wikimedia.org/wikipedia/commons/b/b3/MediaMarkt_logo.svg",
        "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b3/MediaMarkt_logo.svg/512px-MediaMarkt_logo.svg.png"
      ],
      "El Corte Inglés":[
        "https://upload.wikimedia.org/wikipedia/en/c/ca/El_Corte_Ingles_Logo.svg",
        "https://upload.wikimedia.org/wikipedia/en/thumb/c/ca/El_Corte_Ingles_Logo.svg/512px-El_Corte_Ingles_Logo.svg.png"
      ],
      "El Corte Ingles":[
        "https://upload.wikimedia.org/wikipedia/en/c/ca/El_Corte_Ingles_Logo.svg",
        "https://upload.wikimedia.org/wikipedia/en/thumb/c/ca/El_Corte_Ingles_Logo.svg/512px-El_Corte_Ingles_Logo.svg.png"
      ],
      "Samsung Oficial":[
        "https://upload.wikimedia.org/wikipedia/commons/thumb/2/24/Samsung_Logo.svg/1200px-Samsung_Logo.svg.png"
      ],
      "Qonexa":[
        "https://qonexa.com/wp-content/uploads/2021/04/logo-qonexa.png",
        "https://qonexa.com/favicon.ico"
      ],
      "Amazon":[
        "https://upload.wikimedia.org/wikipedia/commons/a/a9/Amazon_logo.svg",
        "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a9/Amazon_logo.svg/512px-Amazon_logo.svg.png"
      ]
    };
    const FALLBACK_DOMAINS = {
      "Santander Boutique":"bancosantander.es",
      "Movistar":"movistar.es",
      "Rentik":"rentik.com",
      "Grover":"grover.com",
      "Media Markt":"mediamarkt.es",
      "El Corte Inglés":"elcorteingles.es",
      "El Corte Ingles":"elcorteingles.es",
      "Samsung Oficial":"samsung.com",
      "Qonexa":"qonexa.com",
      "Amazon":"amazon.es"
    };
    const ORDER = ["Santander Boutique","Amazon","Movistar","Rentik","Samsung Oficial","Media Markt","El Corte Inglés","Grover","Qonexa"];
    const TRANSPARENT_PNG = "https://upload.wikimedia.org/wikipedia/commons/8/89/HD_transparent_picture.png";
    const nf = new Intl.NumberFormat("es-ES", { style:"currency", currency:"EUR", maximumFractionDigits:2, minimumFractionDigits:2 });
    const s = { chart:null, generated:false, selected:new Set() };
    const d = {
      modality:document.getElementById("fModality"), model:document.getElementById("fModel"), capacity:document.getElementById("fCapacity"), term:document.getElementById("fTerm"), termField:document.getElementById("termField"),
      toggle:document.getElementById("retailerToggle"), toggleText:document.getElementById("retailerText"), menu:document.getElementById("retailerMenu"), opts:document.getElementById("retailerOpts"),
      all:document.getElementById("retailerAll"), none:document.getElementById("retailerNone"), btn:document.getElementById("btnGenerate"),
      placeholder:document.getElementById("placeholder"), chartWrap:document.getElementById("chartWrap"), chart:document.getElementById("chart"), logoStrip:document.getElementById("logoStrip"),
      rows:document.getElementById("rows"), empty:document.getElementById("empty"), footerTs:document.getElementById("footerTs"),
      kModel:document.getElementById("kModel"), kModelMeta:document.getElementById("kModelMeta"), kRenting:document.getElementById("kRenting"), kRentingMeta:document.getElementById("kRentingMeta"),
      kCash:document.getElementById("kCash"), kCashMeta:document.getElementById("kCashMeta"), kRetailers:document.getElementById("kRetailers"), kRetailersMeta:document.getElementById("kRetailersMeta")
    };
    const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (m) => ({ "&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;" }[m]));
    const euro = (v, compact=false) => (typeof v === "number" && Number.isFinite(v)) ? (compact ? new Intl.NumberFormat("es-ES",{style:"currency",currency:"EUR",maximumFractionDigits:0}).format(v) : nf.format(v)) : "-";
    const cap = (v) => (typeof v === "number" && Number.isFinite(v)) ? (v >= 1024 ? `${(v / 1024).toFixed(v % 1024 ? 1 : 0)} TB` : `${v} GB`) : "-";
    const rSort = (a,b) => ((ORDER.indexOf(a) === -1 ? 999 : ORDER.indexOf(a)) - (ORDER.indexOf(b) === -1 ? 999 : ORDER.indexOf(b))) || a.localeCompare(b, "es");
    const uniq = (arr) => [...new Set(arr)];
    const fill = (sel, vals, allV, allL) => { const prev = sel.value; sel.innerHTML = ""; const o = document.createElement("option"); o.value = allV; o.textContent = allL; sel.appendChild(o); vals.forEach((x) => { const n = document.createElement("option"); n.value = String(x.value); n.textContent = x.label; sel.appendChild(n); }); sel.value = [...sel.options].some((x) => x.value === prev) ? prev : allV; };
    function logoCandidates(ret) {
      const base = Array.isArray(LOGOS[ret]) ? LOGOS[ret] : (LOGOS[ret] ? [LOGOS[ret]] : []);
      const domain = FALLBACK_DOMAINS[ret];
      const fallback = domain ? `https://www.google.com/s2/favicons?sz=64&domain_url=${encodeURIComponent(domain)}` : TRANSPARENT_PNG;
      return [...base, fallback, TRANSPARENT_PNG];
    }
    function buildLogoImg(ret) {
      const img = document.createElement("img");
      img.alt = `${ret} logo`;
      const candidates = logoCandidates(ret);
      let idx = 0;
      img.src = candidates[idx];
      img.addEventListener("error", () => {
        idx += 1;
        if (idx < candidates.length) img.src = candidates[idx];
      });
      return img;
    }
    function buildRetailers() {
      const retailers = uniq(DATA.map((r) => r.retailer).filter(Boolean)).sort(rSort);
      s.selected = new Set(retailers);
      d.opts.innerHTML = "";
      retailers.forEach((ret) => {
        const label = document.createElement("label"); label.className = "opt";
        const c = document.createElement("input"); c.type = "checkbox"; c.value = ret; c.checked = true;
        c.addEventListener("change", () => { c.checked ? s.selected.add(ret) : s.selected.delete(ret); syncRetailers(); updateKpis(); if (s.generated) render(); });
        const img = buildLogoImg(ret);
        const span = document.createElement("span"); span.textContent = ret;
        label.appendChild(c); label.appendChild(img); label.appendChild(span); d.opts.appendChild(label);
      });
      syncRetailers();
    }
    function syncRetailers() {
      const total = d.opts.querySelectorAll("input[type='checkbox']").length;
      const selected = s.selected.size;
      d.toggleText.textContent = selected === 0 ? "Sin retailers" : (selected === total ? "Todos los retailers" : `${selected} de ${total} retailers`);
    }
    function selectRetailers(checked) {
      s.selected.clear();
      d.opts.querySelectorAll("input[type='checkbox']").forEach((i) => { i.checked = checked; if (checked) s.selected.add(i.value); });
      syncRetailers(); updateKpis(); if (s.generated) render();
    }
    function updateModels() { fill(d.model, uniq(DATA.map((r) => r.model).filter(Boolean)).sort((a,b) => a.localeCompare(b,"es")).map((v) => ({ value:v, label:v })), "all", "Todos los modelos"); }
    function updateCapacities() {
      const m = d.model.value; const o = d.modality.value;
      const caps = uniq(DATA.filter((r) => (m === "all" || r.model === m) && (!o || r.offer_type === o) && typeof r.capacity_gb === "number").map((r) => r.capacity_gb)).sort((a,b) => a-b);
      fill(d.capacity, caps.map((v) => ({ value:v, label:cap(v) })), "all", "Todas las capacidades");
    }
    function updateTerms() {
      if (d.modality.value !== "financing_max_term") { d.termField.style.display = "none"; d.term.value = "all"; return; }
      d.termField.style.display = "flex";
      const m = d.model.value; const c = d.capacity.value;
      const terms = uniq(DATA.filter((r) => r.offer_type === "financing_max_term" && (m === "all" || r.model === m) && (c === "all" || String(r.capacity_gb) === c) && typeof r.term_months === "number").map((r) => r.term_months)).sort((a,b) => a-b);
      fill(d.term, terms.map((v) => ({ value:v, label:`${v} meses` })), "all", "Todos los plazos");
    }
    function updateKpis() {
      const m = d.model.value;
      const rows = DATA.filter((r) => (m === "all" || r.model === m) && s.selected.has(r.retailer) && typeof r.price_value === "number" && r.price_value >= 0);
      d.kModel.textContent = m === "all" ? "Todos los modelos" : m;
      d.kModelMeta.textContent = `${new Set(rows.map((r) => r.model)).size} modelo(s) visibles`;
      const renting = rows.filter((r) => r.offer_type === "renting_no_insurance" || r.offer_type === "renting_with_insurance");
      if (renting.length) { const best = renting.reduce((a,b) => b.price_value < a.price_value ? b : a); d.kRenting.textContent = euro(best.price_value, best.price_value >= 1000); d.kRentingMeta.textContent = `${best.retailer} · ${cap(best.capacity_gb)}`; }
      else { d.kRenting.textContent = "-"; d.kRentingMeta.textContent = "Sin oferta de renting"; }
      const cash = rows.filter((r) => r.offer_type === "cash");
      if (cash.length) { const best = cash.reduce((a,b) => b.price_value < a.price_value ? b : a); d.kCash.textContent = euro(best.price_value, best.price_value >= 1000); d.kCashMeta.textContent = `${best.retailer} · ${cap(best.capacity_gb)}`; }
      else { d.kCash.textContent = "-"; d.kCashMeta.textContent = "Sin oferta al contado"; }
      d.kRetailers.textContent = String(new Set(rows.map((r) => r.retailer)).size);
      d.kRetailersMeta.textContent = `${rows.length} oferta(s) detectadas`;
    }
    function filtered() {
      const m = d.model.value, c = d.capacity.value, o = d.modality.value, t = d.term.value;
      return DATA.filter((r) => (o ? r.offer_type === o : true) && (m === "all" || r.model === m) && (c === "all" || String(r.capacity_gb) === c) && (o !== "financing_max_term" || t === "all" || String(r.term_months) === t) && s.selected.has(r.retailer) && typeof r.price_value === "number" && Number.isFinite(r.price_value) && r.price_value >= 0);
    }
    function renderLogoStrip(labels) {
      d.logoStrip.innerHTML = "";
      if (!labels.length) {
        d.logoStrip.classList.remove("on");
        return;
      }
      labels.forEach((ret) => {
        const item = document.createElement("div");
        item.className = "logo-pill";
        item.appendChild(buildLogoImg(ret));
        const txt = document.createElement("span");
        txt.textContent = ret;
        item.appendChild(txt);
        d.logoStrip.appendChild(item);
      });
      d.logoStrip.classList.add("on");
    }
    function alignLogoStrip(chart, labels) {
      if (!chart || !labels.length) return;
      const x = chart.scales.x;
      if (!x) return;
      const pills = [...d.logoStrip.children];
      pills.forEach((pill, i) => {
        pill.style.left = `${x.getPixelForValue(i)}px`;
      });
    }
    const pricePlugin = { id:"pricePlugin", afterDatasetsDraw(chart){ const ds = chart.data.datasets[0]; if (!ds) return; const ctx = chart.ctx; const bars = chart.getDatasetMeta(0).data; ctx.save(); ctx.textAlign = "center"; ctx.textBaseline = "bottom"; ctx.font = "700 12px Inter"; ctx.fillStyle = "#1A1A2E"; bars.forEach((b,i) => { const v = Number(ds.data[i]); if (Number.isFinite(v)) ctx.fillText(euro(v, v >= 1000), b.x, b.y - 8); }); ctx.restore(); } };
    const htmlLogoAlignPlugin = { id:"htmlLogoAlignPlugin", afterRender(chart){ alignLogoStrip(chart, chart.data.labels || []); } };
    function drawChart(rows) {
      const map = new Map(); rows.forEach((r) => { const cur = map.get(r.retailer); if (!cur || r.price_value < cur.price_value) map.set(r.retailer, r); });
      const labels = [...map.keys()].sort(rSort); const values = labels.map((k) => map.get(k).price_value); const colors = labels.map((k) => COLORS[k] || "#7A8193");
      renderLogoStrip(labels);
      if (s.chart) s.chart.destroy();
      s.chart = new Chart(d.chart.getContext("2d"), { type:"bar", data:{ labels, datasets:[{ data:values, backgroundColor:colors, borderColor:colors, borderWidth:1, borderRadius:16, borderSkipped:false, maxBarThickness:72 }] }, options:{ responsive:true, maintainAspectRatio:false, onResize:(chart) => alignLogoStrip(chart, labels), layout:{ padding:{ top:22, left:8, right:8, bottom:20 } }, plugins:{ legend:{display:false}, tooltip:{ backgroundColor:"#1A1A2E", callbacks:{ label:(ctx) => ` ${euro(ctx.parsed.y, ctx.parsed.y >= 1000)}` } } }, scales:{ x:{ ticks:{display:false}, grid:{display:false, drawBorder:false} }, y:{ beginAtZero:true, grid:{ color:"rgba(26,26,46,.07)", drawBorder:false }, ticks:{ color:"#646B80", callback:(v) => euro(Number(v), Number(v) >= 1000) } } } }, plugins:[pricePlugin, htmlLogoAlignPlugin] });
      alignLogoStrip(s.chart, labels);
    }
    const stock = (v) => v === true ? '<span class="yes">Disponible</span>' : (v === false ? '<span class="no">No disponible</span>' : "-");
    function drawTable(rows) {
      const sorted = [...rows].sort((a,b) => a.price_value - b.price_value);
      d.rows.innerHTML = sorted.map((r) => {
        const cls = r.retailer === "Santander Boutique" ? "santander" : "";
        const term = (r.offer_type === "financing_max_term" && typeof r.term_months === "number") ? `${r.term_months} meses` : "-";
        return `<tr class="${cls}"><td>${esc(r.retailer)}</td><td>${esc(r.model)}</td><td>${esc(cap(r.capacity_gb))}</td><td><span class="badge ${BADGES[r.offer_type] || "b-fin"}">${esc(OFFER_LABELS[r.offer_type] || r.offer_type)}</span></td><td>${esc(term)}</td><td class="price">${esc(euro(r.price_value, r.price_value >= 1000))}</td><td>${esc(r.price_unit || "EUR")}</td><td>${stock(r.in_stock)}</td></tr>`;
      }).join("");
      d.empty.style.display = sorted.length ? "none" : "block";
    }
    function render() {
      const rows = filtered();
      if (!rows.length) {
        d.placeholder.style.display = "grid";
        d.chartWrap.classList.remove("on");
        renderLogoStrip([]);
        if (s.chart) { s.chart.destroy(); s.chart = null; }
        drawTable(rows);
        return;
      }
      d.placeholder.style.display = "none";
      d.chartWrap.classList.add("on");
      drawChart(rows);
      drawTable(rows);
    }
    function fmtTs(raw) { if (!raw) return "--"; const dt = new Date(raw); if (Number.isNaN(dt.getTime())) return raw; return new Intl.DateTimeFormat("es-ES", { dateStyle:"long", timeStyle:"short" }).format(dt); }
    function init() {
      updateModels(); buildRetailers(); updateCapacities(); updateTerms(); updateKpis();
      d.footerTs.textContent = `Extraccion: ${fmtTs(EXTRACTED_AT)}`;
      d.modality.addEventListener("change", () => { updateCapacities(); updateTerms(); updateKpis(); if (s.generated) render(); });
      d.model.addEventListener("change", () => { updateCapacities(); updateTerms(); updateKpis(); if (s.generated) render(); });
      d.capacity.addEventListener("change", () => { updateTerms(); if (s.generated) render(); });
      d.term.addEventListener("change", () => { if (s.generated) render(); });
      d.btn.addEventListener("click", () => { s.generated = true; render(); });
      d.toggle.addEventListener("click", () => { const o = d.menu.classList.toggle("open"); d.toggle.setAttribute("aria-expanded", o ? "true" : "false"); });
      d.all.addEventListener("click", () => selectRetailers(true));
      d.none.addEventListener("click", () => selectRetailers(false));
      document.addEventListener("click", (ev) => { if (!d.menu.classList.contains("open")) return; const t = ev.target; if (t instanceof Node && !d.menu.contains(t) && !d.toggle.contains(t)) { d.menu.classList.remove("open"); d.toggle.setAttribute("aria-expanded", "false"); } });
    }
    init();
  </script>
</body>
</html>
"""
    return html.replace("__DATA__", data_json).replace("__EXTRACTED__", extracted_at)


def main() -> None:
    rows, extracted_at = load_rows(CSV_PATH)
    OUTPUT_PATH.write_text(build_html(rows, extracted_at), encoding="utf-8")
    print(f"Generated {OUTPUT_PATH.name} from {CSV_PATH.name} with {len(rows)} rows")


if __name__ == "__main__":
    main()
