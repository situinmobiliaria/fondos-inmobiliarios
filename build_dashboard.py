"""
Genera dashboard_fondos.html (Tarea 3 de INSTRUCCIONES_VSCODE.txt): un solo
archivo HTML, con los datos de registro_rentabilidad.xlsx + diagnostico_fondos.xlsx
incrustados como JSON dentro del propio archivo, para que funcione offline
con doble clic (sin servidor, sin fetch a fondos_data.json).

Uso:
    python build_dashboard.py
"""
import json
import re
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent
REGISTRO = BASE / "registro_rentabilidad.xlsx"
DIAGNOSTICO = BASE / "diagnostico_fondos.xlsx"
OUT = BASE / "dashboard_fondos.html"
DOCS_DIR = BASE / "docs"
CHARTJS_VENDOR = BASE / "vendor" / "chart.umd.min.js"

# Arreglo cosmetico de nombres con mojibake heredado del listado maestro
# original (encoding roto en "20260507 Fondos Inmobiliarios.xlsx").
FIX_NOMBRES = {
    "Capital Ra�ces": "Capital Raíces",
    "Fundamenta Plaza Ega�a": "Fundamenta Plaza Egaña",
    "Rentas Inmobiliarias Pt Fondo de Inversi�n": "Rentas Inmobiliarias Pt Fondo de Inversión",
    "Plaza Ega�a": "Plaza Egaña",
    "Renta Reisdencial": "Renta Residencial",  # typo del listado maestro
}

TIPO_KEYWORDS = [
    ("residencial", "Residencial"),
    ("industrial", "Industrial"),
    ("bodega", "Industrial"),
    ("comercial", "Comercial"),
    ("stripcenter", "Comercial"),
    ("mall", "Comercial"),
    ("oficina", "Oficinas"),
    ("desarrollo", "Desarrollo"),
]


def fix_nombre(s):
    if not isinstance(s, str):
        return s
    return FIX_NOMBRES.get(s, s).replace("�", "")


def inferir_tipo(fondo: str) -> str:
    f = fondo.lower()
    for kw, tipo in TIPO_KEYWORDS:
        if kw in f:
            return tipo
    return "Renta"


def parse_num(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    if not s or s.lower() == "nan":
        return None
    s = s.replace(".", "").replace(",", ".") if s.count(",") == 1 and s.count(".") <= 1 else s.replace(",", ".")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def clean_str(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v)


def calidad(categoria: str) -> str:
    if categoria == "OK":
        return "OK"
    if categoria == "F":
        return "Parcial"
    return "Sin dato"


def main():
    reg = pd.read_excel(REGISTRO)
    reg.columns = [c.replace("�", "a") if "actualiza" in c.lower() else c for c in reg.columns]
    diag = pd.read_excel(DIAGNOSTICO, sheet_name="Diagnostico")

    fondos = []
    for _, row in reg.iterrows():
        adm = row["Administradora"]
        fondo_raw = row["Fondo"]
        fondo = fix_nombre(fondo_raw)

        drow = diag[(diag["Administradora"] == adm) & (diag["Fondo"] == fondo_raw)]
        categoria = drow.iloc[0]["Categoria"] if len(drow) else ""
        link = drow.iloc[0]["Link"] if len(drow) else ""

        campos_num = {}
        for col in ["Rent. 1M", "Rent. 3M", "Rent. 6M", "Rent. YTD", "Rent. 12M (1A)",
                    "Rent. 24M (2A)", "Rent. 36M (3A)", "Rent. Desde Inicio",
                    "Dividend Yield", "TIR", "Cap Rate", "LTV",
                    "Rentabilidad Directa", "Leverage"]:
            campos_num[col] = parse_num(row.get(col))

        fondos.append({
            "administradora": fix_nombre(adm),
            "fondo": fondo,
            "tipo": inferir_tipo(fondo),
            "archivo": clean_str(row.get("Archivo")),
            "link": clean_str(link),
            "categoria": clean_str(categoria),
            "calidad": calidad(categoria),
            "estado": clean_str(row.get("Estado")),
            "notas": clean_str(row.get("Notas")),
            "moneda": clean_str(row.get("Moneda")) or None,
            "plazo": clean_str(row.get("Plazo/Duracion")) or None,
            "n_activos": (None if pd.isna(row.get("N Activos")) else int(row.get("N Activos"))),
            **{k: v for k, v in campos_num.items()},
        })

    n_fondos = len(fondos)
    n_admin = len({f["administradora"] for f in fondos})
    n_ok = sum(1 for f in fondos if f["categoria"] == "OK")
    pct_ok = round(100 * n_ok / n_fondos, 1) if n_fondos else 0

    r12 = [f["Rent. 12M (1A)"] for f in fondos if f["Rent. 12M (1A)"] is not None]
    dy = [f["Dividend Yield"] for f in fondos if f["Dividend Yield"] is not None]

    def prom(xs):
        return round(sum(xs) / len(xs), 1) if xs else None

    def mediana(xs):
        if not xs:
            return None
        s = sorted(xs)
        n = len(s)
        m = n // 2
        return round(s[m] if n % 2 else (s[m - 1] + s[m]) / 2, 1)

    n_act = [f["n_activos"] for f in fondos if f["n_activos"] is not None]

    kpis = {
        "n_fondos": n_fondos,
        "n_admin": n_admin,
        "pct_ok": pct_ok,
        "rent12_prom": prom(r12),
        "rent12_mediana": mediana(r12),
        "dy_prom": prom(dy),
        "n_activos_total": sum(n_act) if n_act else None,
        "n_activos_fondos": len(n_act),
    }

    data = {
        "generado": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "kpis": kpis,
        "fondos": fondos,
    }

    if not CHARTJS_VENDOR.exists():
        raise SystemExit(
            f"Falta {CHARTJS_VENDOR}. Descargar una vez con:\n"
            f'  curl -L "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.5.1/chart.umd.min.js" '
            f'-o "{CHARTJS_VENDOR}"'
        )
    chartjs_code = CHARTJS_VENDOR.read_text(encoding="utf-8")

    html = TEMPLATE.replace("__DATA_JSON__", json.dumps(data, ensure_ascii=False, allow_nan=False))
    html = html.replace("__CHARTJS_INLINE__", chartjs_code)
    OUT.write_text(html, encoding="utf-8")

    # Copia identica en docs/index.html -- es la carpeta que se configura como
    # fuente de GitHub Pages para publicar el dashboard con URL publica
    # (repo.situinmobiliaria.github.io/fondos-inmobiliarios/), igual que Panel-TECSERVICE.
    DOCS_DIR.mkdir(exist_ok=True)
    (DOCS_DIR / "index.html").write_text(html, encoding="utf-8")

    print(f"OK -> {OUT} ({n_fondos} fondos, {n_admin} administradoras, {pct_ok}% OK)")
    print(f"OK -> {DOCS_DIR / 'index.html'} (copia para GitHub Pages)")


TEMPLATE = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fondos de Inversión Inmobiliarios</title>
<!-- Roboto vía Google Fonts: si no hay internet, cae a Helvetica/Arial (ver font-family abajo) -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap" rel="stylesheet">
<!-- Chart.js incrustado (vendor/chart.umd.min.js) para que el dashboard funcione sin internet -->
<script>__CHARTJS_INLINE__</script>
<style>
:root{
  --gris-oscuro:#2D3334;
  --gris-medio:#5B6670;
  --gris-claro:#F2F2F2;
  --gris-claro2:#E6E7E8;
  --burdeo:#96323C;
  --burdeo2:#A26579;
  --burdeo3:#D7A1A7;
  --burdeo4:#51313C;
  --fondo:#FFFFFF;
  --borde:#E0E0E0;
  --ok:#2D3334;
  --neg:#96323C;
}
*{box-sizing:border-box;}
body{
  margin:0;background:var(--fondo);color:var(--gris-oscuro);
  font-family:'Roboto',Helvetica,Arial,sans-serif;
  padding:0 20px 40px;
}
header{
  border-bottom:3px solid var(--burdeo);
  padding:24px 0 16px;margin-bottom:24px;
  display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:12px;
}
header h1{font-size:1.6rem;font-weight:700;margin:0;letter-spacing:.2px;}
header .meta{color:var(--gris-medio);font-size:.85rem;text-align:right;}
.situ-tag{color:var(--burdeo);font-weight:700;letter-spacing:1px;font-size:.75rem;text-transform:uppercase;}

.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-bottom:28px;}
@media (max-width:900px){.kpis{grid-template-columns:repeat(2,1fr);}}
.kpi{background:var(--gris-claro);border-radius:6px;padding:14px 16px;border-left:3px solid var(--burdeo);}
.kpi .val{font-size:1.5rem;font-weight:700;color:var(--gris-oscuro);}
.kpi .lbl{font-size:.72rem;color:var(--gris-medio);text-transform:uppercase;letter-spacing:.4px;margin-top:2px;}

.filtros{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px;}
.filtros select, .filtros input{
  border:1px solid var(--borde);border-radius:5px;padding:7px 10px;font-family:inherit;
  font-size:.85rem;color:var(--gris-oscuro);background:#fff;
}
.filtros input{flex:1;min-width:160px;}

section{margin-bottom:36px;}
h2{font-size:1.05rem;font-weight:700;border-bottom:1px solid var(--borde);padding-bottom:8px;margin-bottom:14px;color:var(--gris-oscuro);}

.charts-grid{display:grid;grid-template-columns:1.3fr 1fr;gap:20px;margin-bottom:10px;}
@media (max-width:900px){.charts-grid{grid-template-columns:1fr;}}
.chart-box{background:var(--gris-claro);border-radius:6px;padding:14px;overflow-x:auto;}
.chart-box canvas{max-width:100%;}
.chart-tall{height:420px;}

table{width:100%;border-collapse:collapse;font-size:.82rem;}
thead th{
  position:sticky;top:0;background:var(--gris-oscuro);color:#fff;
  text-align:left;padding:9px 10px;cursor:pointer;user-select:none;font-weight:500;
}
thead th:hover{background:var(--burdeo4);}
tbody td{padding:8px 10px;border-bottom:1px solid var(--gris-claro2);}
tbody tr:hover{background:var(--gris-claro);cursor:pointer;}
.tabla-wrap{max-height:560px;overflow:auto;border:1px solid var(--borde);border-radius:6px;}
.num{text-align:right;font-variant-numeric:tabular-nums;}
.neg{color:var(--neg);}
.pill{display:inline-block;padding:2px 9px;border-radius:10px;font-size:.72rem;font-weight:500;}
.pill-ok{background:#E4E7E7;color:var(--gris-oscuro);}
.pill-parcial{background:var(--burdeo3);color:var(--burdeo4);}
.pill-sindato{background:var(--gris-claro2);color:var(--gris-medio);}

.modal-overlay{
  position:fixed;inset:0;background:rgba(45,51,52,.55);display:none;
  align-items:center;justify-content:center;padding:20px;z-index:50;
}
.modal-overlay.open{display:flex;}
.modal{
  background:#fff;border-radius:8px;max-width:560px;width:100%;max-height:85vh;overflow:auto;
  padding:24px 26px;border-top:4px solid var(--burdeo);
}
.modal h3{margin:0 0 4px;font-size:1.15rem;}
.modal .sub{color:var(--gris-medio);font-size:.85rem;margin-bottom:16px;}
.modal-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px;}
.modal-grid .item{background:var(--gris-claro);border-radius:5px;padding:8px 10px;}
.modal-grid .item .l{font-size:.68rem;color:var(--gris-medio);text-transform:uppercase;}
.modal-grid .item .v{font-size:1rem;font-weight:700;}
.modal .estado{background:var(--gris-claro);border-radius:5px;padding:10px 12px;font-size:.82rem;color:var(--gris-medio);margin-bottom:14px;}
.modal .links a{color:var(--burdeo);text-decoration:none;font-size:.85rem;margin-right:16px;}
.modal .links a:hover{text-decoration:underline;}
.modal-close{position:sticky;top:0;float:right;background:none;border:none;font-size:1.3rem;color:var(--gris-medio);cursor:pointer;}
footer{color:var(--gris-medio);font-size:.75rem;text-align:center;padding-top:20px;border-top:1px solid var(--borde);margin-top:10px;}
</style>
</head>
<body>

<header>
  <div>
    <div class="situ-tag">SITU</div>
    <h1>Fondos de Inversión Inmobiliarios</h1>
  </div>
  <div class="meta">Actualizado: <span id="fecha-actualizacion"></span></div>
</header>

<section class="kpis" id="kpis"></section>

<section>
  <h2>Rentabilidad y calidad de los datos</h2>
  <div class="charts-grid">
    <div class="chart-box chart-tall"><canvas id="chartBarras12m"></canvas></div>
    <div class="chart-box">
      <canvas id="chartPromAdmin" style="margin-bottom:16px;"></canvas>
      <canvas id="chartScatter"></canvas>
    </div>
  </div>
</section>

<section>
  <h2>Composición de la cartera</h2>
  <div class="charts-grid">
    <div class="chart-box"><canvas id="chartMoneda"></canvas></div>
    <div class="chart-box"><canvas id="chartTipo"></canvas></div>
  </div>
</section>

<section>
  <h2>Detalle por fondo</h2>
  <div class="filtros">
    <input type="text" id="f-busca" placeholder="Buscar fondo o administradora…">
    <select id="f-admin"><option value="">Todas las administradoras</option></select>
    <select id="f-tipo"><option value="">Todos los tipos</option></select>
    <select id="f-moneda"><option value="">Todas las monedas</option></select>
    <select id="f-estado">
      <option value="">Todos los estados</option>
      <option value="OK">OK</option>
      <option value="Parcial">Parcial</option>
      <option value="Sin dato">Sin dato</option>
    </select>
  </div>
  <button id="btn-csv" style="margin-bottom:10px;padding:7px 14px;border:1px solid var(--burdeo);background:#fff;color:var(--burdeo);border-radius:5px;font-family:inherit;font-size:.8rem;cursor:pointer;">Exportar CSV</button>
  <div class="tabla-wrap">
    <table id="tabla">
      <thead>
        <tr>
          <th data-k="administradora">Administradora</th>
          <th data-k="fondo">Fondo</th>
          <th data-k="tipo">Tipo</th>
          <th data-k="moneda">Moneda</th>
          <th data-k="n_activos" class="num">N° Activos</th>
          <th data-k="Rent. 1M" class="num">1M</th>
          <th data-k="Rent. 3M" class="num">3M</th>
          <th data-k="Rent. 6M" class="num">6M</th>
          <th data-k="Rent. YTD" class="num">YTD</th>
          <th data-k="Rent. 12M (1A)" class="num">12M</th>
          <th data-k="Rent. 36M (3A)" class="num">36M</th>
          <th data-k="Rent. Desde Inicio" class="num">Desde Inicio</th>
          <th data-k="Dividend Yield" class="num">Div. Yield</th>
          <th data-k="Cap Rate" class="num">Cap Rate</th>
          <th data-k="LTV" class="num">LTV</th>
          <th data-k="calidad">Estado</th>
        </tr>
      </thead>
      <tbody id="tabla-body"></tbody>
    </table>
  </div>
</section>

<footer>Fuente: registro_rentabilidad.xlsx / diagnostico_fondos.xlsx — generado por build_dashboard.py</footer>

<div class="modal-overlay" id="modal-overlay">
  <div class="modal" id="modal-content"></div>
</div>

<script id="fondos-data" type="application/json">__DATA_JSON__</script>
<script>
const DATA = JSON.parse(document.getElementById('fondos-data').textContent);
const fondos = DATA.fondos;

function fmtPct(v){
  if(v===null||v===undefined) return '—';
  const s = v.toFixed(1).replace('.', ',').replace('-,','-');
  return (v>0?'+':'') + s + '%';
}
function pctClass(v){ return (v!==null && v<0) ? 'neg' : ''; }
function pillClass(cal){
  return cal==='OK' ? 'pill-ok' : (cal==='Parcial' ? 'pill-parcial' : 'pill-sindato');
}

document.getElementById('fecha-actualizacion').textContent = DATA.generado;

// KPIs
const k = DATA.kpis;
const kpiDefs = [
  [k.n_fondos, 'Fondos'],
  [k.n_admin, 'Administradoras'],
  [k.pct_ok + '%', 'Fondos con datos OK'],
  [k.rent12_prom!==null ? fmtPct(k.rent12_prom) : '—', 'Rent. 12M promedio'],
  [k.rent12_mediana!==null ? fmtPct(k.rent12_mediana) : '—', 'Rent. 12M mediana'],
  [k.dy_prom!==null ? fmtPct(k.dy_prom) : '—', 'Dividend Yield promedio'],
  [k.n_activos_total!==null ? k.n_activos_total : '—', `N° Activos (suma, ${k.n_activos_fondos} fondos)`],
];
document.getElementById('kpis').innerHTML = kpiDefs.map(([v,l])=>
  `<div class="kpi"><div class="val">${v}</div><div class="lbl">${l}</div></div>`).join('');

// Filtros: poblar selects
const admins = [...new Set(fondos.map(f=>f.administradora))].sort();
const tipos = [...new Set(fondos.map(f=>f.tipo))].sort();
const monedas = [...new Set(fondos.map(f=>f.moneda).filter(Boolean))].sort();
document.getElementById('f-admin').innerHTML += admins.map(a=>`<option value="${a}">${a}</option>`).join('');
document.getElementById('f-tipo').innerHTML += tipos.map(t=>`<option value="${t}">${t}</option>`).join('');
document.getElementById('f-moneda').innerHTML += monedas.map(m=>`<option value="${m}">${m}</option>`).join('');

let sortKey = null, sortDir = 1;

function aplicarFiltros(){
  const busca = document.getElementById('f-busca').value.toLowerCase();
  const admin = document.getElementById('f-admin').value;
  const tipo = document.getElementById('f-tipo').value;
  const moneda = document.getElementById('f-moneda').value;
  const estado = document.getElementById('f-estado').value;
  let rows = fondos.filter(f=>
    (!busca || f.fondo.toLowerCase().includes(busca) || f.administradora.toLowerCase().includes(busca)) &&
    (!admin || f.administradora===admin) &&
    (!tipo || f.tipo===tipo) &&
    (!moneda || f.moneda===moneda) &&
    (!estado || f.calidad===estado)
  );
  if(sortKey){
    rows = rows.slice().sort((a,b)=>{
      const va = a[sortKey], vb = b[sortKey];
      if(va===null||va===undefined) return 1;
      if(vb===null||vb===undefined) return -1;
      if(typeof va === 'string') return va.localeCompare(vb) * sortDir;
      return (va-vb) * sortDir;
    });
  }
  renderTabla(rows);
}

let filasActuales = [];

function renderTabla(rows){
  filasActuales = rows;
  const cols = ['Rent. 1M','Rent. 3M','Rent. 6M','Rent. YTD','Rent. 12M (1A)','Rent. 36M (3A)','Rent. Desde Inicio','Dividend Yield','Cap Rate','LTV'];
  document.getElementById('tabla-body').innerHTML = rows.map((f,i)=>`
    <tr data-idx="${fondos.indexOf(f)}">
      <td>${f.administradora}</td>
      <td>${f.fondo}</td>
      <td>${f.tipo}</td>
      <td>${f.moneda || '—'}</td>
      <td class="num">${f.n_activos ?? '—'}</td>
      ${cols.map(c=>`<td class="num ${pctClass(f[c])}">${fmtPct(f[c])}</td>`).join('')}
      <td><span class="pill ${pillClass(f.calidad)}">${f.calidad}</span></td>
    </tr>
  `).join('');
  [...document.querySelectorAll('#tabla-body tr')].forEach(tr=>{
    tr.addEventListener('click', ()=> abrirDetalle(fondos[+tr.dataset.idx]));
  });
}

document.querySelectorAll('#tabla thead th').forEach(th=>{
  th.addEventListener('click', ()=>{
    const k2 = th.dataset.k;
    if(sortKey===k2) sortDir *= -1; else { sortKey=k2; sortDir=1; }
    aplicarFiltros();
  });
});
['f-busca','f-admin','f-tipo','f-moneda','f-estado'].forEach(id=>
  document.getElementById(id).addEventListener('input', aplicarFiltros));

document.getElementById('btn-csv').addEventListener('click', ()=>{
  const cols = ['administradora','fondo','tipo','moneda','n_activos','plazo',
    'Rent. 1M','Rent. 3M','Rent. 6M','Rent. YTD','Rent. 12M (1A)','Rent. 24M (2A)','Rent. 36M (3A)',
    'Rent. Desde Inicio','Dividend Yield','TIR','Cap Rate','LTV','Rentabilidad Directa','Leverage','calidad','estado'];
  const encabezados = ['Administradora','Fondo','Tipo','Moneda','N Activos','Plazo',
    '1M','3M','6M','YTD','12M','24M','36M','Desde Inicio','Dividend Yield','TIR','Cap Rate','LTV','Rent Directa','Leverage','Calidad','Estado'];
  const escapa = v => { const s = (v===null||v===undefined) ? '' : String(v); return '"' + s.replace(/"/g,'""') + '"'; };
  const lineas = [encabezados.map(escapa).join(';')]
    .concat(filasActuales.map(f => cols.map(c=>escapa(f[c])).join(';')));
  const blob = new Blob(['﻿' + lineas.join('\r\n')], {type:'text/csv;charset=utf-8;'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'fondos_inmobiliarios.csv';
  a.click();
});

aplicarFiltros();

function abrirDetalle(f){
  const cols = [
    ['Rent. 1M','1M'],['Rent. 3M','3M'],['Rent. 6M','6M'],['Rent. YTD','YTD'],
    ['Rent. 12M (1A)','12M'],['Rent. 24M (2A)','24M'],['Rent. 36M (3A)','36M'],
    ['Rent. Desde Inicio','Desde Inicio'],['Dividend Yield','Dividend Yield'],
    ['TIR','TIR'],['Cap Rate','Cap Rate'],['LTV','LTV'],
    ['Rentabilidad Directa','Rent. Directa'],['Leverage','Leverage'],
  ];
  const items = cols.filter(([k])=>f[k]!==null && f[k]!==undefined).map(([k,l])=>
    `<div class="item"><div class="l">${l}</div><div class="v ${pctClass(f[k])}">${l==='Leverage' ? f[k]+'x' : fmtPct(f[k])}</div></div>`
  ).join('') || '<div class="item"><div class="l">Sin indicadores disponibles</div></div>';

  const ficha = [
    ['Moneda', f.moneda || '—'],
    ['Plazo / Duración', f.plazo || '—'],
    ['N° Activos', f.n_activos ?? '—'],
  ].map(([l,v])=>`<div class="item"><div class="l">${l}</div><div class="v">${v}</div></div>`).join('');

  document.getElementById('modal-content').innerHTML = `
    <button class="modal-close" onclick="cerrarDetalle()">&times;</button>
    <h3>${f.fondo}</h3>
    <div class="sub">${f.administradora} · ${f.tipo}</div>
    <div class="modal-grid">${ficha}</div>
    <div class="modal-grid">${items}</div>
    <div class="estado"><strong>Estado:</strong> ${f.estado || '—'}${f.notas ? '<br><br>' + f.notas : ''}</div>
    <div class="links">
      ${f.link ? `<a href="${f.link}" target="_blank" rel="noopener">Ver página del fondo →</a>` : ''}
      ${f.archivo ? `<a href="Fondos Descargados/${f.administradora}/${f.fondo}/${f.archivo}" target="_blank">Abrir PDF local →</a>` : ''}
    </div>
  `;
  document.getElementById('modal-overlay').classList.add('open');
}
function cerrarDetalle(){ document.getElementById('modal-overlay').classList.remove('open'); }
document.getElementById('modal-overlay').addEventListener('click', e=>{
  if(e.target.id==='modal-overlay') cerrarDetalle();
});

// ---- Charts ----
// Chart.js va incrustado en este mismo archivo (ver build_dashboard.py / vendor/chart.umd.min.js),
// asi que funciona sin internet. El try/catch queda como resguardo defensivo nada mas.
try {
if (typeof Chart === 'undefined') throw new Error('Chart.js no disponible (el bundle incrustado no se cargo correctamente)');

const conRent12 = fondos.filter(f=>f['Rent. 12M (1A)']!==null && f['Rent. 12M (1A)']!==undefined)
  .sort((a,b)=>b['Rent. 12M (1A)']-a['Rent. 12M (1A)']);

new Chart(document.getElementById('chartBarras12m'), {
  type:'bar',
  data:{
    labels: conRent12.map(f=>f.fondo),
    datasets:[{
      label:'Rentabilidad 12M (%)',
      data: conRent12.map(f=>f['Rent. 12M (1A)']),
      backgroundColor: conRent12.map(f=> f['Rent. 12M (1A)']<0 ? '#96323C' : '#2D3334'),
      borderRadius:2,
    }]
  },
  options:{
    indexAxis:'y',
    plugins:{legend:{display:false}, title:{display:true, text:'Rentabilidad 12M por fondo', color:'#2D3334', font:{size:13}}},
    scales:{
      x:{ticks:{callback:v=>v+'%'}, grid:{color:'#E6E7E8'}},
      y:{ticks:{font:{size:10}}, grid:{display:false}}
    }
  }
});

const porAdmin = {};
fondos.forEach(f=>{
  if(f['Rent. 12M (1A)']===null || f['Rent. 12M (1A)']===undefined) return;
  (porAdmin[f.administradora] ??= []).push(f['Rent. 12M (1A)']);
});
const adminLabels = Object.keys(porAdmin);
const adminProm = adminLabels.map(a=> (porAdmin[a].reduce((x,y)=>x+y,0)/porAdmin[a].length));

new Chart(document.getElementById('chartPromAdmin'), {
  type:'bar',
  data:{
    labels: adminLabels,
    datasets:[{label:'Rent. 12M promedio (%)', data: adminProm, backgroundColor:'#96323C', borderRadius:2}]
  },
  options:{
    plugins:{legend:{display:false}, title:{display:true, text:'Rentabilidad 12M promedio por administradora', color:'#2D3334', font:{size:13}}},
    scales:{ x:{ticks:{font:{size:9}}}, y:{ticks:{callback:v=>v+'%'}, grid:{color:'#E6E7E8'}} }
  }
});

const conDyLtv = fondos.filter(f=>f['Dividend Yield']!==null && f['Dividend Yield']!==undefined
  && (f['LTV']!==null && f['LTV']!==undefined));

new Chart(document.getElementById('chartScatter'), {
  type:'scatter',
  data:{
    datasets:[{
      label:'Fondos',
      data: conDyLtv.map(f=>({x:f['LTV'], y:f['Dividend Yield'], f})),
      backgroundColor:'#A26579',
    }]
  },
  options:{
    plugins:{
      legend:{display:false},
      title:{display:true, text:'Dividend Yield vs LTV', color:'#2D3334', font:{size:13}},
      tooltip:{callbacks:{label:ctx=>ctx.raw.f.fondo+': DY '+ctx.raw.y+'%, LTV '+ctx.raw.x+'%'}}
    },
    scales:{
      x:{title:{display:true,text:'LTV (%)'}, grid:{color:'#E6E7E8'}},
      y:{title:{display:true,text:'Dividend Yield (%)'}, grid:{color:'#E6E7E8'}}
    }
  }
});

// Composicion: moneda y tipo de fondo
const PALETA = ['#96323C','#A26579','#D7A1A7','#51313C','#5B6670','#2D3334'];
const porMoneda = {};
fondos.forEach(f=>{ const m = f.moneda || 'Sin dato'; porMoneda[m] = (porMoneda[m]||0)+1; });
new Chart(document.getElementById('chartMoneda'), {
  type:'doughnut',
  data:{
    labels: Object.keys(porMoneda),
    datasets:[{ data: Object.values(porMoneda), backgroundColor: PALETA }]
  },
  options:{
    plugins:{
      legend:{position:'bottom', labels:{color:'#2D3334', font:{size:11}}},
      title:{display:true, text:'Fondos por moneda', color:'#2D3334', font:{size:13}}
    }
  }
});

const porTipo = {};
fondos.forEach(f=>{ porTipo[f.tipo] = (porTipo[f.tipo]||0)+1; });
new Chart(document.getElementById('chartTipo'), {
  type:'bar',
  data:{
    labels: Object.keys(porTipo),
    datasets:[{ label:'N° de fondos', data: Object.values(porTipo), backgroundColor:'#5B6670', borderRadius:2 }]
  },
  options:{
    plugins:{legend:{display:false}, title:{display:true, text:'Fondos por tipo', color:'#2D3334', font:{size:13}}},
    scales:{ y:{ticks:{stepSize:1}, grid:{color:'#E6E7E8'}} }
  }
});

} catch(e) {
  console.warn('Graficos no disponibles:', e.message);
  document.querySelectorAll('.chart-box').forEach(el=>{
    el.innerHTML = '<p style="color:var(--gris-medio);font-size:.8rem;padding:20px;">'
      + 'No se pudieron cargar los gráficos (error inesperado del bundle de Chart.js incrustado). '
      + 'La tabla de abajo funciona igual.</p>';
  });
}
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
