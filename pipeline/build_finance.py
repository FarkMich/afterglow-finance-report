#!/usr/bin/env python3
"""Build the Afterglow finance dashboard.
Tabs: Main (KPIs, revenue/orders/AOV trends, pack mix, Europe heatmap) + KPIs (monthly target gauges).
Self-contained: brand fonts + logo embedded, data embedded. Chart.js + chartjs-chart-geo via CDN.
Reads finance_data.json (parse_finance.py).
"""
import base64, os, pathlib

HERE = pathlib.Path(__file__).resolve().parent          # .../Afterglow/Finance
BRAND = str(HERE.parent / "Brand identity")
OUT_DIR = str(HERE)
DATA_JSON = str(HERE / "finance_data.json")
os.makedirs(OUT_DIR, exist_ok=True)

def b64(p): return base64.b64encode(pathlib.Path(p).read_bytes()).decode()
helv = b64(f"{BRAND}/fonts/HelveticaNowText.ttf")
helvblack = b64(f"{BRAND}/Visual identity/Fonts/Helvetica/helvetica-now-text-black.ttf")
tang = b64(f"{BRAND}/fonts/Tangerine.otf")
logo = b64(f"{BRAND}/Visual identity/Logos/drive-download-20260206T062443Z-1-001/Afterglow-Logo_Black_transparent.svg")
DATA = pathlib.Path(DATA_JSON).read_text()

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Afterglow - Revenue Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  @font-face{font-family:'HelveticaNow';src:url(data:font/ttf;base64,__HELV__) format('truetype');}
  @font-face{font-family:'HNBlack';src:url(data:font/ttf;base64,__HELVBLACK__) format('truetype');}
  @font-face{font-family:'Tangerine';src:url(data:font/otf;base64,__TANG__) format('opentype');}
  :root{--pink:#CE0071;--bg:#DCDEE2;--surface:#FFFFFF;--surface2:#F5F6F7;--mid:#C4C6CB;--text:#121212;--text2:#6C6E72;--light:#2A2A2C;--line:rgba(18,18,18,.08);}
  *{box-sizing:border-box;margin:0;padding:0;}
  body{font-family:'HelveticaNow',-apple-system,Helvetica,Arial,sans-serif;background:var(--bg);color:var(--text);-webkit-font-smoothing:antialiased;}
  .script{font-family:'Tangerine',cursive;font-style:italic;color:var(--pink);}
  .cover{padding:54px 40px 0;text-align:center;}
  .cover img.logo{height:30px;margin-bottom:30px;opacity:.97;}
  .cover h1{font-family:'HNBlack';font-size:56px;letter-spacing:-1px;line-height:1;}
  .cover .sub{font-size:15px;color:var(--text2);margin-top:12px;}
  .cover .period{display:inline-block;border:1px solid var(--mid);border-radius:20px;padding:6px 20px;font-size:12px;color:var(--text2);margin-top:22px;letter-spacing:1px;}
  .strip{height:4px;background:var(--pink);border-radius:4px;max-width:900px;margin:34px auto 0;}
  .container{max-width:960px;margin:0 auto;padding:0 22px 70px;}

  .maintabs{display:flex;gap:8px;justify-content:center;margin:30px 0 4px;}
  .mt-btn{background:var(--surface);color:var(--text2);border:1px solid var(--mid);border-radius:24px;padding:11px 34px;font-family:inherit;font-size:13px;letter-spacing:1.5px;text-transform:uppercase;cursor:pointer;transition:.18s;}
  .mt-btn:hover{color:var(--text);border-color:#555;}
  .mt-btn.active{background:var(--pink);color:#fff;border-color:var(--pink);}
  .panel{display:none;} .panel.active{display:block;animation:fade .35s ease;}
  @keyframes fade{from{opacity:0;transform:translateY(6px);}to{opacity:1;transform:none;}}

  .toggle{display:flex;gap:8px;justify-content:center;margin:24px 0 4px;}
  .tg-btn{background:var(--surface);color:var(--text2);border:1px solid var(--mid);border-radius:24px;padding:9px 28px;font-family:inherit;font-size:12px;letter-spacing:1px;text-transform:uppercase;cursor:pointer;}
  .tg-btn.active{background:var(--pink);color:#fff;border-color:var(--pink);}

  .section-title{font-size:11px;letter-spacing:2.5px;text-transform:uppercase;color:var(--text2);margin:38px 0 16px;padding-bottom:9px;border-bottom:1px solid var(--mid);display:flex;align-items:center;gap:12px;}
  .section-title .num{font-family:'Tangerine',cursive;font-style:italic;font-size:30px;color:var(--pink);line-height:.7;}
  .section-title .ctx{margin-left:auto;text-transform:none;letter-spacing:0;font-size:12px;color:var(--mid);}

  .kpi-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;}
  .kpi-grid.four{grid-template-columns:repeat(4,1fr);}
  .kpi-grid.four .kpi-value{font-size:33px;}
  .kpi-card{background:var(--surface);border-radius:14px;padding:22px 20px;border:1px solid var(--line);border-top:3px solid var(--pink);}
  .kpi-label{font-size:10.5px;letter-spacing:1.2px;text-transform:uppercase;color:var(--text2);margin-bottom:9px;}
  .kpi-value{font-family:'HNBlack';font-size:44px;line-height:1;letter-spacing:-.5px;}
  .kpi-sub{font-size:12px;color:var(--text2);margin-top:7px;}
  .badge{display:inline-block;font-size:11px;padding:3px 9px;border-radius:10px;margin-top:10px;}
  .badge.up{background:rgba(206,0,113,.16);color:var(--pink);}
  .badge.down{background:rgba(178,180,183,.12);color:var(--text2);}
  .badge.flat{background:rgba(178,180,183,.12);color:var(--text2);}

  .card{background:var(--surface);border-radius:14px;padding:22px 24px;margin-bottom:14px;border:1px solid var(--line);}
  .card h3{font-size:13px;font-weight:normal;letter-spacing:.5px;color:var(--light);margin-bottom:16px;}
  .chart-wrap{position:relative;height:300px;}
  .grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px;}
  .grid2 .chart-wrap{height:260px;}

  .totals{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;}
  .tot{background:var(--surface);border-radius:14px;padding:20px;text-align:center;border:1px solid var(--line);}
  .tot .v{font-family:'HNBlack';font-size:34px;color:var(--text);letter-spacing:-.5px;} .tot .l{font-size:10.5px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;margin-top:6px;}
  .packmix{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:14px;}
  .pm{background:var(--surface);border-radius:14px;padding:20px;text-align:center;border:1px solid var(--line);border-top:3px solid var(--pink);}
  .pm .v{font-family:'HNBlack';font-size:34px;color:var(--pink);letter-spacing:-.5px;}
  .pm .l{font-size:10.5px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;margin-top:6px;}
  .pm .s{font-size:11px;color:var(--mid);margin-top:3px;}
  .rowlbl{font-size:10.5px;letter-spacing:1.5px;text-transform:uppercase;color:var(--text2);margin:0 0 8px;}
  .rowlbl.gap{margin-top:16px;}

  /* country pies */
  .leg{display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:14px;}
  .leg .li{display:flex;align-items:center;gap:6px;font-size:11.5px;color:var(--text2);}
  .leg .sw{width:10px;height:10px;border-radius:2px;flex-shrink:0;}
  .leg .li b{color:var(--text);font-weight:normal;}

  /* KPI gauges */
  .gauge-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:14px;}
  .gcard{background:var(--surface);border-radius:14px;padding:22px;border:1px solid var(--line);}
  .gcard h4{font-size:14px;font-weight:normal;color:var(--light);margin-bottom:4px;}
  .gcard .mlbl{font-size:11px;color:var(--mid);text-transform:uppercase;letter-spacing:1px;margin-bottom:16px;}
  .rings{display:flex;gap:18px;justify-content:space-around;}
  .ring{text-align:center;}
  .ring svg{transform:rotate(-90deg);}
  .ring .pctt{font-family:'HNBlack';font-size:17px;fill:var(--text);}
  .ring .rlbl{font-size:10.5px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;margin-top:8px;}
  .ring .rsub{font-size:11px;color:var(--text2);margin-top:3px;}

  /* unit econ table */
  .uetbl{width:100%;border-collapse:collapse;font-size:13px;}
  .uetbl th{text-align:right;font-weight:normal;color:var(--text2);font-size:10.5px;letter-spacing:1px;text-transform:uppercase;padding:10px 12px;border-bottom:1px solid var(--mid);}
  .uetbl th:first-child,.uetbl td:first-child{text-align:left;}
  .uetbl td{text-align:right;padding:10px 12px;border-bottom:1px solid var(--line);color:var(--text);}
  .uetbl tbody tr:last-child td{border-bottom:none;}
  .uetbl .totrow td{font-family:'HNBlack';color:var(--text);border-top:2px solid var(--mid);border-bottom:none;}

  .note{background:rgba(206,0,113,.06);border:1px solid rgba(206,0,113,.22);border-radius:12px;padding:14px 18px;font-size:12px;color:var(--text2);line-height:1.6;margin-top:18px;}
  .footer{text-align:center;padding:34px 20px;font-size:11px;color:var(--mid);}
  .footer .strip{margin-bottom:20px;}
  @media(max-width:680px){.kpi-grid,.kpi-grid.four,.totals,.packmix{grid-template-columns:1fr 1fr;}.grid2,.mapgrid,.gauge-grid{grid-template-columns:1fr;}.cover h1{font-size:40px;}}
</style>
</head>
<body>
<div class="cover">
  <img class="logo" src="data:image/svg+xml;base64,__LOGO__" alt="afterglow">
  <h1>Revenue <span class="script">performance</span></h1>
  <div class="sub">Orders &middot; AOV &middot; revenue &middot; coupons</div>
  <div class="period" id="period">loading...</div>
  <div class="strip"></div>
</div>
<div class="container">
  <div class="maintabs">
    <button class="mt-btn active" data-p="main">Main</button>
    <button class="mt-btn" data-p="unit">CAC</button>
    <button class="mt-btn" data-p="kpis">KPIs</button>
  </div>

  <!-- ===== MAIN ===== -->
  <div class="panel active" id="panel-main">
    <div class="toggle">
      <button class="tg-btn active" data-g="monthly">Monthly</button>
      <button class="tg-btn" data-g="weekly">Weekly</button>
    </div>

    <div class="section-title"><span class="num">01</span> Latest <span id="periodKind">month</span><span class="ctx" id="latestCtx"></span></div>
    <div class="kpi-grid four">
      <div class="kpi-card"><div class="kpi-label">Revenue</div><div class="kpi-value" id="kRev">-</div><div class="kpi-sub" id="kRevSub"></div><span class="badge" id="kRevB"></span></div>
      <div class="kpi-card"><div class="kpi-label">Orders</div><div class="kpi-value" id="kOrd">-</div><div class="kpi-sub" id="kOrdSub"></div><span class="badge" id="kOrdB"></span></div>
      <div class="kpi-card"><div class="kpi-label">Packs sold</div><div class="kpi-value" id="kUnit">-</div><div class="kpi-sub" id="kUnitSub"></div><span class="badge" id="kUnitB"></span></div>
      <div class="kpi-card"><div class="kpi-label">AOV</div><div class="kpi-value" id="kAov">-</div><div class="kpi-sub" id="kAovSub"></div><span class="badge" id="kAovB"></span></div>
    </div>

    <div class="section-title"><span class="num">02</span> Trends</div>
    <div class="card"><h3>Revenue (EUR)</h3><div class="chart-wrap"><canvas id="chRev"></canvas></div></div>
    <div class="grid2">
      <div class="card"><h3>Orders</h3><div class="chart-wrap"><canvas id="chOrd"></canvas></div></div>
      <div class="card"><h3>Average order value (EUR)</h3><div class="chart-wrap"><canvas id="chAov"></canvas></div></div>
    </div>

    <div class="section-title"><span class="num">03</span> Where orders come from<span class="ctx">all time</span></div>
    <div class="grid2">
      <div class="card"><h3>Orders by country</h3><div class="chart-wrap" style="height:250px"><canvas id="chOrdPie" role="img" aria-label="Orders by country"></canvas></div><div class="leg" id="legOrd"></div></div>
      <div class="card"><h3>Revenue by country</h3><div class="chart-wrap" style="height:250px"><canvas id="chRevPie" role="img" aria-label="Revenue by country"></canvas></div><div class="leg" id="legRev"></div></div>
    </div>

    <div class="section-title"><span class="num">04</span> Totals<span class="ctx" id="allCtx"></span></div>
    <div class="rowlbl">All time</div>
    <div class="totals">
      <div class="tot"><div class="v" id="tRev">-</div><div class="l">Revenue</div></div>
      <div class="tot"><div class="v" id="tOrd">-</div><div class="l">Orders</div></div>
      <div class="tot"><div class="v" id="tAov">-</div><div class="l">AOV</div></div>
      <div class="tot"><div class="v" id="tUnit">-</div><div class="l">Units sold</div></div>
    </div>
    <div class="rowlbl gap" id="ytdLblTot">Year to date</div>
    <div class="totals">
      <div class="tot"><div class="v" id="tRevY">-</div><div class="l">Revenue</div></div>
      <div class="tot"><div class="v" id="tOrdY">-</div><div class="l">Orders</div></div>
      <div class="tot"><div class="v" id="tAovY">-</div><div class="l">AOV</div></div>
      <div class="tot"><div class="v" id="tUnitY">-</div><div class="l">Units sold</div></div>
    </div>
    <div class="section-title" style="border:none;margin:22px 0 12px"><span class="num">&middot;</span> Pack mix<span class="ctx">pack-equivalents</span></div>
    <div class="rowlbl">All time</div>
    <div class="packmix" style="margin-top:0">
      <div class="pm"><div class="v" id="p1">-</div><div class="l">1-pack</div><div class="s" id="p1s"></div></div>
      <div class="pm"><div class="v" id="p3">-</div><div class="l">3-pack</div><div class="s" id="p3s"></div></div>
      <div class="pm"><div class="v" id="p10">-</div><div class="l">10-pack</div><div class="s" id="p10s"></div></div>
      <div class="pm"><div class="v" id="pT">-</div><div class="l">Total packs</div><div class="s" id="pTs"></div></div>
    </div>
    <div class="rowlbl gap" id="ytdLblPm">Year to date</div>
    <div class="packmix" style="margin-top:0">
      <div class="pm"><div class="v" id="p1y">-</div><div class="l">1-pack</div><div class="s" id="p1ys"></div></div>
      <div class="pm"><div class="v" id="p3y">-</div><div class="l">3-pack</div><div class="s" id="p3ys"></div></div>
      <div class="pm"><div class="v" id="p10y">-</div><div class="l">10-pack</div><div class="s" id="p10ys"></div></div>
      <div class="pm"><div class="v" id="pTy">-</div><div class="l">Total packs</div><div class="s" id="pTys"></div></div>
    </div>
    <div class="note" id="note"></div>

    <div class="section-title"><span class="num">05</span> Coupons<span class="ctx" id="cpnCtx">all time · from WooCommerce</span></div>
    <div class="packmix" style="margin-top:0">
      <div class="pm"><div class="v" id="cOrd">-</div><div class="l">Coupon orders</div><div class="s" id="cOrdSub"></div></div>
      <div class="pm"><div class="v" id="cApp">-</div><div class="l">Coupons applied</div><div class="s">redemptions</div></div>
      <div class="pm"><div class="v" id="cDisc">-</div><div class="l">Discount given</div><div class="s" id="cDiscSub"></div></div>
      <div class="pm"><div class="v" id="cRev">-</div><div class="l">Coupon revenue</div><div class="s" id="cRevSub"></div></div>
    </div>
    <div class="grid2" style="margin-top:14px">
      <div class="card"><h3>Coupon vs other revenue (monthly)</h3><div class="chart-wrap"><canvas id="chCpn"></canvas></div></div>
      <div class="card"><h3>Top coupons<span style="color:var(--mid);font-size:11px"> · code · uses · discount · revenue</span></h3><div class="leg" id="topCpn" style="flex-direction:column;gap:9px"></div></div>
    </div>
    <div class="note" id="cpnNote"></div>
  </div>

  <!-- ===== UNIT ECON ===== -->
  <div class="panel" id="panel-unit">
    <div class="section-title"><span class="num">€</span> Customer acquisition cost &amp; discounts<span class="ctx" id="ueCtx">since Jan 2026</span></div>
    <div class="kpi-grid">
      <div class="kpi-card"><div class="kpi-label">CAC / customer (incl. influencer)</div><div class="kpi-value" id="uePpp">-</div><div class="kpi-sub" id="uePppSub"></div></div>
      <div class="kpi-card"><div class="kpi-label">Avg discount / order</div><div class="kpi-value" id="ueDisc">-</div><div class="kpi-sub" id="ueDiscSub"></div></div>
      <div class="kpi-card"><div class="kpi-label">Avg discount / discounted order</div><div class="kpi-value" id="ueDiscC">-</div><div class="kpi-sub" id="ueDiscCSub"></div></div>
    </div>
    <div class="section-title"><span class="num">&middot;</span> Customer acquisition cost by month</div>
    <div class="card"><h3>CAC - cost per customer (EUR)</h3><div class="chart-wrap"><canvas id="chPpp"></canvas></div></div>
    <div class="card"><h3>Monthly detail</h3><div id="ueTable"></div></div>
    <div class="note" id="ueNote"></div>
  </div>

  <!-- ===== KPIS ===== -->
  <div class="panel" id="panel-kpis">
    <div class="section-title"><span class="num">★</span> Monthly targets<span class="ctx">% completion vs goal</span></div>
    <div class="gauge-grid" id="gauges"></div>
    <div class="note" id="kpiNote"></div>
  </div>
</div>
<div class="footer"><div class="strip"></div><span id="foot"></span><br><span style="color:#BFC2C7">Your return matters.</span></div>

<script>
const DATA = __DATA__;
const PINK="#CE0071", GRID="rgba(0,0,0,0.07)", TXT="#6C6E72";
const fmt = n => Math.round(n).toLocaleString('en-US');
const eur = n => "€" + Number(n).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
const pct2 = n => n.toFixed(2)+"%";
let state="monthly", charts={};

function delta(cur,prev){
  if(prev==null||prev===0) return {cls:'flat',txt:'–'};
  const d=(cur-prev)/prev*100;
  const a=d>0.5?'▲':d<-0.5?'▼':'–';
  return {cls:d>0.5?'up':d<-0.5?'down':'flat', txt:`${a} ${Math.abs(d).toFixed(2)}% vs prev`};
}
function setBadge(id,cur,prev){const d=delta(cur,prev);const e=document.getElementById(id);e.className='badge '+d.cls;e.textContent=d.txt;}
function baseOpts(yFmt){
  return {responsive:true,maintainAspectRatio:false,
    plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>yFmt(c.parsed.y)}}},
    scales:{x:{grid:{color:GRID},ticks:{color:TXT,maxRotation:0,autoSkip:true,maxTicksLimit:12,font:{size:10}}},
            y:{grid:{color:GRID},ticks:{color:TXT,font:{size:10},callback:v=>yFmt(v)},beginAtZero:true}}};
}
function mkBar(id,l,v,y){return new Chart(document.getElementById(id),{type:'bar',data:{labels:l,datasets:[{data:v,backgroundColor:PINK,borderRadius:4,maxBarThickness:34}]},options:baseOpts(y)});}
function mkLine(id,l,v,y){return new Chart(document.getElementById(id),{type:'line',data:{labels:l,datasets:[{data:v,borderColor:PINK,backgroundColor:'rgba(206,0,113,0.12)',fill:true,tension:.3,pointRadius:2,pointBackgroundColor:PINK,borderWidth:2}]},options:baseOpts(y)});}

function renderMain(){
  const rows=DATA[state], labels=rows.map(r=>r.label);
  ['rev','ord','aov'].forEach(k=>{if(charts[k])charts[k].destroy();});
  charts.rev=mkBar('chRev',labels,rows.map(r=>r.revenue),eur);
  charts.ord=mkBar('chOrd',labels,rows.map(r=>r.orders),fmt);
  charts.aov=mkLine('chAov',labels,rows.map(r=>r.aov),eur);
  const last=rows[rows.length-1], prev=rows[rows.length-2]||{};
  document.getElementById('periodKind').textContent=state==='monthly'?'month':'week';
  document.getElementById('latestCtx').textContent=last.label+(state==='monthly'?' (in progress)':'');
  document.getElementById('kRev').textContent=eur(last.revenue);
  document.getElementById('kRevSub').textContent=`prev ${eur(prev.revenue||0)}`; setBadge('kRevB',last.revenue,prev.revenue);
  document.getElementById('kOrd').textContent=fmt(last.orders);
  document.getElementById('kOrdSub').textContent=`prev ${fmt(prev.orders||0)}`; setBadge('kOrdB',last.orders,prev.orders);
  document.getElementById('kUnit').textContent=fmt(last.units);
  document.getElementById('kUnitSub').textContent=`prev ${fmt(prev.units||0)}`; setBadge('kUnitB',last.units,prev.units);
  document.getElementById('kAov').textContent=eur(last.aov);
  document.getElementById('kAovSub').textContent=`prev ${eur(prev.aov||0)}`; setBadge('kAovB',last.aov,prev.aov);
}

// ---- country pies (orders + revenue) ----
const CPAL=['#5E0033','#8A0048','#B0005C','#CE0071','#DA3B8E','#E768A6','#F08FBE','#F6B6D5','#C7C9CE','#DDE0E4'];
function renderCountryPies(){
  const rows=Object.entries(DATA.countryOrders).map(([k,v])=>({code:k,orders:v.orders,rev:v.revenue})).sort((a,b)=>b.orders-a.orders);
  const colors={}; rows.forEach((r,i)=>colors[r.code]=CPAL[Math.min(i,CPAL.length-1)]);
  const labels=rows.map(r=>r.code);
  const cols=rows.map(r=>colors[r.code]);
  const totO=rows.reduce((a,r)=>a+r.orders,0), totR=rows.reduce((a,r)=>a+r.rev,0);
  const pie=(id,vals,fmtv,tot)=>new Chart(document.getElementById(id),{type:'doughnut',
    data:{labels,datasets:[{data:vals,backgroundColor:cols,borderColor:'#fff',borderWidth:1.5}]},
    options:{maintainAspectRatio:false,cutout:'58%',plugins:{legend:{display:false},
      tooltip:{callbacks:{label:c=>`${c.label}: ${fmtv(c.parsed)} (${(c.parsed/tot*100).toFixed(1)}%)`}}}}});
  pie('chOrdPie',rows.map(r=>r.orders),v=>v+' orders',totO);
  pie('chRevPie',rows.map(r=>r.rev),eur,totR);
  document.getElementById('legOrd').innerHTML=rows.map(r=>`<span class="li"><span class="sw" style="background:${colors[r.code]}"></span>${r.code} <b>${r.orders}</b> · ${(r.orders/totO*100).toFixed(1)}%</span>`).join('');
  document.getElementById('legRev').innerHTML=rows.map(r=>`<span class="li"><span class="sw" style="background:${colors[r.code]}"></span>${r.code} <b>${eur(r.rev)}</b> · ${(r.rev/totR*100).toFixed(1)}%</span>`).join('');
}

// ---- coupons ----
function renderCoupons(){
  const C=DATA.coupons; if(!C) return;
  document.getElementById('cOrd').textContent=fmt(C.orders);
  document.getElementById('cOrdSub').textContent=pct2(C.pctOrders)+' of orders';
  document.getElementById('cApp').textContent=fmt(C.applications);
  document.getElementById('cDisc').textContent=eur(C.discountGiven);
  document.getElementById('cDiscSub').textContent=pct2(C.savingsRate)+' off gross';
  document.getElementById('cRev').textContent=eur(C.revenue);
  document.getElementById('cRevSub').textContent=pct2(C.pctRevenue)+' of revenue';
  document.getElementById('topCpn').innerHTML=(C.topCoupons||[]).map(c=>
    `<span class="li" style="justify-content:space-between;width:100%;border-bottom:1px solid var(--line);padding-bottom:7px">
       <b style="color:var(--pink)">${c.code}</b>
       <span>${c.uses}× &middot; ${eur(c.discount)} off &middot; <b>${eur(c.revenue)}</b></span></span>`).join('');
  const rows=DATA.monthly;
  if(charts.cpn)charts.cpn.destroy();
  charts.cpn=new Chart(document.getElementById('chCpn'),{type:'bar',
    data:{labels:rows.map(r=>r.label),datasets:[
      {label:'Coupon revenue',data:rows.map(r=>r.couponRevenue),backgroundColor:PINK,borderRadius:4,maxBarThickness:34},
      {label:'Other revenue',data:rows.map(r=>Math.max(0,+(r.revenue-r.couponRevenue).toFixed(2))),backgroundColor:'#C7C9CE',borderRadius:4,maxBarThickness:34}
    ]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:true,position:'bottom',labels:{color:TXT,font:{size:10},boxWidth:12}},
        tooltip:{callbacks:{label:c=>c.dataset.label+': '+eur(c.parsed.y)}}},
      scales:{x:{stacked:true,grid:{color:GRID},ticks:{color:TXT,font:{size:10},maxRotation:0,autoSkip:true,maxTicksLimit:12}},
              y:{stacked:true,grid:{color:GRID},ticks:{color:TXT,font:{size:10},callback:v=>eur(v)},beginAtZero:true}}}});
  document.getElementById('cpnNote').textContent=`Coupon orders are completed orders carrying at least one coupon code; "coupons applied" counts every redemption (orders can stack more than one). Discount given is the total markdown on those orders; coupon revenue is what they still brought in. Across all completed orders, total discount given was ${eur(C.totalDiscountAllOrders)}.`;
}

// ---- unit economics ----
function renderUnitEcon(){
  const U=DATA.unitEcon; if(!U) return;
  const naE = v => (v==null ? 'n/a' : eur(v));
  document.getElementById('ueCtx').textContent='since '+U.sinceLabel;
  document.getElementById('uePpp').textContent=naE(U.overall.cacInclInfluencer);
  document.getElementById('uePppSub').textContent=`${naE(U.overall.cacExInfluencer)} excl. influencer · ${fmt(U.overall.customers)} customers`;
  document.getElementById('ueDisc').textContent=eur(U.avgDiscountPerOrder);
  document.getElementById('ueDiscSub').textContent=`${pct2(U.discountPctPerOrder)} off gross · ${fmt(U.wcOrders)} WooCommerce orders`;
  document.getElementById('ueDiscC').textContent=eur(U.avgDiscountPerCouponOrder);
  document.getElementById('ueDiscCSub').textContent=`${pct2(U.discountPctPerCouponOrder)} off gross · ${fmt(U.couponOrders)} coupon orders`;
  const rows=U.cac, labels=rows.map(r=>r.label.split(' ')[0]);
  if(charts.ppp)charts.ppp.destroy();
  charts.ppp=new Chart(document.getElementById('chPpp'),{type:'bar',
    data:{labels,datasets:[
      {label:'CAC excl. influencer',data:rows.map(r=>r.cacExInfluencer),backgroundColor:'#C7C9CE',borderRadius:4,maxBarThickness:30},
      {label:'CAC incl. influencer',data:rows.map(r=>r.cacInclInfluencer),backgroundColor:PINK,borderRadius:4,maxBarThickness:30}
    ]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:true,position:'bottom',labels:{color:TXT,font:{size:10},boxWidth:12}},
        tooltip:{callbacks:{label:c=>c.dataset.label+': '+eur(c.parsed.y)}}},
      scales:{x:{grid:{color:GRID},ticks:{color:TXT,font:{size:10},maxRotation:0,autoSkip:true}},
              y:{grid:{color:GRID},ticks:{color:TXT,font:{size:10},callback:v=>eur(v)},beginAtZero:true}}}});
  let t=`<table class="uetbl"><thead><tr><th>Month</th><th>Customers</th><th>Meta</th><th>Influencer</th><th>CAC excl. infl.</th><th>CAC incl. infl.</th></tr></thead><tbody>`;
  rows.forEach(r=>{t+=`<tr><td>${r.label}</td><td>${fmt(r.customers)}</td><td>${eur(r.metaSpend)}</td><td>${eur(r.influencer)}</td><td>${naE(r.cacExInfluencer)}</td><td>${naE(r.cacInclInfluencer)}</td></tr>`;});
  const o=U.overall;
  t+=`<tr class="totrow"><td>Overall</td><td>${fmt(o.customers)}</td><td>${eur(o.metaSpend)}</td><td>${eur(o.influencer)}</td><td>${naE(o.cacExInfluencer)}</td><td>${naE(o.cacInclInfluencer)}</td></tr>`;
  t+=`</tbody></table>`;
  document.getElementById('ueTable').innerHTML=t;
  const metaNote = U.metaSpendAvailable
    ? `Meta ad spend is pulled from Windsor.`
    : `Meta Ads currently returns €0 spend from Windsor for this period.`;
  document.getElementById('ueNote').textContent=`CAC (customer acquisition cost) = marketing spend ÷ unique customers, since ${U.sinceLabel}. Customers are distinct billing emails on completed WooCommerce orders (deduped, internal/test addresses excluded), so a repeat buyer counts once per month. The two CAC columns split out the €500/month influencer cost (Mar, Apr, May, Jun 2026): "excl. influencer" is Meta spend only ÷ customers; "incl. influencer" adds it back. ${metaNote} CAC counts active purchasing customers (a buyer returning in a later month is counted again that month); it is blended across channels and ignores attribution lag. Average discount per order = total discount ÷ all ${fmt(U.wcOrders)} completed WooCommerce orders (${eur(U.totalDiscount)} total, ${pct2(U.discountPctPerOrder)} off gross); the third card narrows to the ${fmt(U.couponOrders)} coupon orders (${eur(U.avgDiscountPerCouponOrder)} / ${pct2(U.discountPctPerCouponOrder)} each). Figures use 2 decimals.`;
}

// ---- KPI gauges ----
function ring(pct,label,sub){
  const r=42,c=2*Math.PI*r,off=c*(1-Math.min(1,pct/100));
  return `<div class="ring">
    <svg width="104" height="104" viewBox="0 0 104 104">
      <circle cx="52" cy="52" r="${r}" stroke="#E2E4E8" stroke-width="9" fill="none"/>
      <circle cx="52" cy="52" r="${r}" stroke="${PINK}" stroke-width="9" fill="none" stroke-linecap="round"
        stroke-dasharray="${c.toFixed(1)}" stroke-dashoffset="${off.toFixed(1)}"/>
      <text x="52" y="56" text-anchor="middle" class="pctt" transform="rotate(90 52 52)">${pct2(pct)}</text>
    </svg>
    <div class="rlbl">${label}</div><div class="rsub">${sub}</div></div>`;
}
function renderKpis(){
  document.getElementById('gauges').innerHTML=DATA.kpis.map(k=>{
    const po=k.tPieces?k.aPieces/k.tPieces*100:0, pr=k.tRev?k.aRev/k.tRev*100:0;
    return `<div class="gcard"><h4>${k.month}</h4><div class="mlbl">target ${fmt(k.tPieces)} pieces · ${eur(k.tRev)}</div>
      <div class="rings">
        ${ring(po,'Pieces',`${fmt(k.aPieces)} / ${fmt(k.tPieces)}`)}
        ${ring(pr,'Revenue',`${eur(k.aRev)} / ${eur(k.tRev)}`)}
      </div></div>`;
  }).join('');
  document.getElementById('kpiNote').textContent="Pieces = products sold (sum of pack quantities); Revenue in EUR. Targets are monthly goals for 2026; % completion = actual ÷ target. The current month is still in progress, so its rings fill as orders land. Figures use 2 decimals.";
}

// ---- boot ----
const m=DATA.monthly;
document.getElementById('period').textContent="📅 "+m[0].label+" – "+m[m.length-1].label;
const T=DATA.totals, TY=DATA.totalsYtd||{year:'',orders:0,revenue:0,units:0,aov:0};
document.getElementById('tRev').textContent=eur(T.revenue);
document.getElementById('tOrd').textContent=fmt(T.orders);
document.getElementById('tAov').textContent=eur(T.aov);
document.getElementById('tUnit').textContent=fmt(T.units);
document.getElementById('tRevY').textContent=eur(TY.revenue);
document.getElementById('tOrdY').textContent=fmt(TY.orders);
document.getElementById('tAovY').textContent=eur(TY.aov);
document.getElementById('tUnitY').textContent=fmt(TY.units);
document.getElementById('ytdLblTot').textContent=TY.year+" year to date";
document.getElementById('ytdLblPm').textContent=TY.year+" year to date";
function fillPm(pm,ids){
  const tot=pm.ones+pm.threes+pm.tens, pp=n=>tot?Math.round(n/tot*100)+'%':'';
  document.getElementById(ids[0]).textContent=fmt(pm.ones); document.getElementById(ids[0]+'s').textContent=pp(pm.ones);
  document.getElementById(ids[1]).textContent=fmt(pm.threes); document.getElementById(ids[1]+'s').textContent=pp(pm.threes);
  document.getElementById(ids[2]).textContent=fmt(pm.tens); document.getElementById(ids[2]+'s').textContent=pp(pm.tens);
  document.getElementById(ids[3]).textContent=fmt(tot); document.getElementById(ids[3]+'s').textContent='pack-equivalents';
}
fillPm(DATA.packMix,['p1','p3','p10','pT']);
fillPm(DATA.packMixYtd||{ones:0,threes:0,tens:0},['p1y','p3y','p10y','pTy']);
document.getElementById('note').textContent=`Orders, revenue and AOV come from the order log (incl. offline/wholesale orders not in WooCommerce). Pack mix counts pack-equivalents (Afterglow sells 1/3/10-packs): multiples of 10 (20, 30, 50, 100…) count as that many 10-packs, other multiples of 3 (6, 9, 24…) as that many 3-packs, and any other size splits into 10s + 3s + singles (13 = 10+3, 76 = 7×10 + 2×3, 5 = 3+1+1, 2 = 1+1). This attribution now also covers the pre-Oct 2025 non-standard sizes that used to show as "Other orders". AOV is revenue ÷ orders, lifted by occasional large wholesale orders. ${DATA.blanksExcluded} value-less rows were excluded; the current month/week and YTD are in progress.`;
document.getElementById('foot').textContent="Afterglow · revenue dashboard · generated "+new Date().toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric'});

renderMain(); renderCountryPies(); renderCoupons(); renderUnitEcon(); renderKpis();
document.querySelectorAll('.tg-btn').forEach(b=>b.addEventListener('click',()=>{
  document.querySelectorAll('.tg-btn').forEach(x=>x.classList.remove('active'));b.classList.add('active');state=b.dataset.g;renderMain();}));
document.querySelectorAll('.mt-btn').forEach(b=>b.addEventListener('click',()=>{
  document.querySelectorAll('.mt-btn').forEach(x=>x.classList.remove('active'));b.classList.add('active');
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  document.getElementById('panel-'+b.dataset.p).classList.add('active');
  if(b.dataset.p==='unit') renderUnitEcon();  // (re)build chart while panel is visible so it sizes correctly
  window.scrollTo({top:0,behavior:'smooth'});}));
</script>
</body>
</html>
"""

html = (TEMPLATE.replace("__HELV__",helv).replace("__HELVBLACK__",helvblack)
        .replace("__TANG__",tang).replace("__LOGO__",logo).replace("__DATA__",DATA))
out=f"{OUT_DIR}/afterglow-finance-dashboard.html"
pathlib.Path(out).write_text(html,encoding="utf-8")
print("WROTE",out,len(html),"bytes")
