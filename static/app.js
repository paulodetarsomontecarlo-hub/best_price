const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const brl = v => 'R$ ' + Number(v).toFixed(2).replace('.', ',');
const CODE = new URLSearchParams(location.search).get('code') || sessionStorage.getItem('code') || '';
if (CODE) sessionStorage.setItem('code', CODE);


const CARD_ZOOM = 10;      // com zoom: nome do posto + preço (cartão), sem sobrepor
const CHIP_ZOOM = 8;       // zoom intermediário: só o preço; abaixo disso: pontos
let products = [], product = null, stations = [], routes = [], selRoute = null, routeLine = null;
let markers = new Map(), tiers = new Map();

const map = L.map('map', {zoomControl: false, center: [-21.23, -56.94], zoom: 6, minZoom: 4});
L.control.zoom({position: 'bottomright'}).addTo(map);
const attr = 'Tiles &copy; Esri &mdash; Esri, HERE, Garmin, OpenStreetMap contributors';
// base só com vias; nomes de cidades entram em camada separada, só com zoom
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', {attribution: attr, maxNativeZoom: 16, maxZoom: 19}).addTo(map);
const labels = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}', {maxNativeZoom: 16, maxZoom: 19, pane: 'shadowPane'});

const legend = L.control({position: 'bottomleft'});
legend.onAdd = () => {
  const d = L.DomUtil.create('div', 'legend');
  d.innerHTML = '<i class="t0"></i>mais barato <i class="t1"></i>médio <i class="t2"></i>mais caro <i class="tn"></i>sem preço';
  return d;
};
legend.addTo(map);

const BRANDS = {IPIRANGA: '#1d4ed8', SHELL: '#eab308', BR: '#16a34a', BRANCA: '#64748b', PETRONAS: '#0d9488'};
const SHORT = {'DIESEL S-10': 'S-10', 'DIESEL S-500': 'S-500', 'ARLA': 'ARLA'};
const ACRONYMS = new Set(['mc', 'br', 'jk', 'sp', 'km', 'axr']);
const LOWER = new Set(['de', 'da', 'do', 'das', 'dos', 'e']);
const prettyName = n => String(n).toLowerCase().replace(/[\p{L}\d]+/gu, w =>
  ACRONYMS.has(w) || /\d/.test(w) ? w.toUpperCase() : LOWER.has(w) ? w : w[0].toUpperCase() + w.slice(1));

async function api(path) {
  const r = await fetch(path, {headers: CODE ? {'X-Client-Code': CODE} : {}});
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.status);
  return r.json();
}

function bestIds() {
  const ids = new Set();
  if (selRoute) { const s = selRoute.stats[product]; if (s) ids.add(s.best_station_id); }
  return ids;
}

// faixa de preço do produto atual: terço mais barato / médio / mais caro
function computeTiers() {
  tiers = new Map();
  const vals = stations.map(s => s.prices[product]?.price).filter(v => v != null).sort((a, b) => a - b);
  const lo = vals[Math.floor((vals.length - 1) / 3)], hi = vals[Math.floor((vals.length - 1) * 2 / 3)];
  for (const s of stations) {
    const p = s.prices[product]?.price;
    tiers.set(s.id, p == null ? 'n' : p <= lo ? 0 : p <= hi ? 1 : 2);
  }
}

const num = p => p.toFixed(2).replace('.', ',');

function icon(st, mode, best) {
  const p = st.prices[product], t = 't' + tiers.get(st.id), star = best ? '<span class="star">★</span>' : '';
  if (mode === 'dot') return L.divIcon({className: '', iconSize: [0, 0], html: `<div class="dot ${t}"></div>`});
  if (mode === 'chip') {
    return L.divIcon({className: '', iconSize: [0, 0], html: `<div class="chip ${t}${best ? ' best' : ''}">${star}${p ? num(p.price) : '—'}</div>`});
  }
  const brand = BRANDS[String(st.brand).toUpperCase()] || '#94a3b8';
  return L.divIcon({className: '', iconSize: [0, 0], html:
    `<div class="card ${t}${best ? ' best' : ''}"><div class="nm"><i style="background:${brand}"></i><span>${esc(prettyName(st.name))}</span></div>
     <div class="pr">${star}${p ? `<b>${num(p.price)}</b><small>R$ · ${esc(SHORT[product] || product)}</small>` : '<small>sem preço</small>'}</div></div>`});
}

function popup(st) {
  const rows = products.map(pr => {
    const p = st.prices[pr];
    return `<tr class="${pr === product ? 'cur' : ''}"><td>${esc(pr)}</td><td>${p ? brl(p.price) : '—'}</td></tr>`;
  }).join('');
  const upd = Object.values(st.prices).map(p => p.updated_at).sort().pop();
  const when = upd ? 'Atualizado em ' + new Date(upd).toLocaleDateString('pt-BR') : 'Preços ainda não cadastrados';
  const color = BRANDS[String(st.brand).toUpperCase()] || '#94a3b8';
  return `<div class="popup"><div class="brand"><i style="background:${color}"></i>${esc(st.brand || 'Posto')}${st.category ? ' · ' + esc(st.category) : ''}</div>
    <h3>${esc(prettyName(st.name))}</h3>
    <div class="sub">${esc([st.city, st.uf].filter(Boolean).join(' - '))}${st.highway ? ' · ' + esc(st.highway) : ''}</div>
    <table>${rows}</table><div class="sub when">${when}</div>
    <a class="waze" href="https://waze.com/ul?ll=${st.lat},${st.lon}&navigate=yes" target="_blank" rel="noopener">Abrir no Waze</a></div>`;
}

const BOX = {card: [168, 50], chip: [62, 26], dot: [14, 14]};
function render() {
  const z = map.getZoom();
  if (z >= CHIP_ZOOM) labels.addTo(map); else map.removeLayer(labels);
  computeTiers();
  const best = bestIds();
  // prioridade: melhor da rota > mais barato > sem preço
  const order = [...stations].sort((a, b) =>
    (best.has(b.id) - best.has(a.id)) || ((a.prices[product]?.price ?? 1e9) - (b.prices[product]?.price ?? 1e9)));
  const placed = [];
  const free = (x, y, [w, h]) => !placed.some(r => x - w / 2 < r.x2 && x + w / 2 > r.x1 && y - h < r.y2 && y > r.y1);
  const take = (x, y, [w, h]) => placed.push({x1: x - w / 2, x2: x + w / 2, y1: y - h, y2: y});
  order.forEach((st, rank) => {
    let m = markers.get(st.id);
    if (!m) {
      m = L.marker([st.lat, st.lon]).addTo(map).bindPopup(() => popup(st), {minWidth: 230, maxWidth: 280});
      markers.set(st.id, m);
    }
    const pt = map.latLngToContainerPoint([st.lat, st.lon]);
    let mode = 'dot';
    if (z >= CARD_ZOOM && free(pt.x, pt.y, BOX.card)) mode = 'card';
    else if (z >= CHIP_ZOOM && free(pt.x, pt.y, BOX.chip)) mode = 'chip';
    take(pt.x, pt.y, BOX[mode]);
    m.setIcon(icon(st, mode, best.has(st.id)));
    m.options.icon.options.popupAnchor = [0, mode === 'dot' ? -8 : -30];
    m.setZIndexOffset(100000 - rank * 100);
  });
}

function renderRoutes() {
  $('#routes').innerHTML = routes.map(r => {
    const s = r.stats[product];
    return `<div class="route ${selRoute?.id === r.id ? 'sel' : ''}" data-id="${r.id}">
      <h2>${esc(r.name)}</h2>
      ${s ? `<div class="row"><span>Preço médio</span><b>${brl(s.avg)}</b></div>
      <div class="row best"><span>Melhor preço</span><b>${brl(s.best)}</b></div>
      <small>${esc(s.best_station)}${s.best_city ? ' · ' + esc(s.best_city) : ''} · ${s.count} posto(s)</small>`
      : '<small>Sem preços cadastrados para este produto.</small>'}</div>`;
  }).join('') || '<p class="hint">Nenhuma rota cadastrada.</p>';
}

function pickRoute(id) {
  selRoute = routes.find(r => r.id === id) || null;
  if (routeLine) { map.removeLayer(routeLine); routeLine = null; }
  if (selRoute) {
    const pts = selRoute.station_ids.map(i => stations.find(s => s.id === i)).filter(Boolean).map(s => [s.lat, s.lon]);
    if (pts.length) {
      routeLine = L.polyline(pts, {color: '#0b5fff', weight: 4, opacity: .6, dashArray: '2 8'}).addTo(map);
      map.fitBounds(L.latLngBounds(pts).pad(.2), {maxZoom: 11});
    }
  }
  render(); renderRoutes(); toggle(false);
}

function toggle(open) {
  $('#drawer').classList.toggle('open', open);
  $('#scrim').classList.toggle('on', open);
}

function renderProducts() {
  $('#products').innerHTML = products.map(p => `<button class="${p === product ? 'on' : ''}" data-p="${esc(p)}">${esc(p)}</button>`).join('');
}

$('#products').onclick = e => {
  const b = e.target.closest('button'); if (!b) return;
  product = b.dataset.p; renderProducts(); render(); renderRoutes();
};
$('#routes').onclick = e => {
  const c = e.target.closest('.route'); if (!c) return;
  const id = +c.dataset.id;
  pickRoute(selRoute?.id === id ? null : id);
};
$('#menuBtn').onclick = () => toggle(true);
$('#closeBtn').onclick = $('#scrim').onclick = () => toggle(false);
map.on('zoomend', render);

(async () => {
  try {
    products = (await api('/api/config')).products; product = products[0];
    [stations, routes] = await Promise.all([api('/api/stations'), api('/api/routes')]);
  } catch (e) {
    const c = e.message.includes('código') ? prompt('Código de acesso:') : null;
    if (c) { sessionStorage.setItem('code', c); location.reload(); return; }
    alert('Erro ao carregar: ' + e.message); return;
  }
  renderProducts(); render(); renderRoutes();
  if (stations.length) map.fitBounds(L.latLngBounds(stations.map(s => [s.lat, s.lon])).pad(.1), {maxZoom: 7});
  const v = (new URLSearchParams(location.search).get('view') || '').split(',').map(Number); // ?view=lat,lon,zoom
  if (v.length === 3 && v.every(Number.isFinite)) map.setView([v[0], v[1]], v[2], {animate: false});
})();