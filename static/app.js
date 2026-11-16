const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const brl = v => 'R$ ' + Number(v).toFixed(2).replace('.', ',');
const CODE = new URLSearchParams(location.search).get('code') || sessionStorage.getItem('code') || '';
if (CODE) sessionStorage.setItem('code', CODE);

const PRICE_ZOOM = 8;      // a partir daqui aparecem os quadrados de preço e os nomes das cidades
let products = [], product = null, stations = [], routes = [], selRoute = null, routeLine = null;
let markers = new Map();

const map = L.map('map', {zoomControl: false, center: [-21.23, -56.94], zoom: 6, minZoom: 4});
L.control.zoom({position: 'bottomright'}).addTo(map);
const attr = 'Tiles &copy; Esri &mdash; Esri, HERE, Garmin, OpenStreetMap contributors';
// base só com vias; nomes de cidades entram em camada separada, só com zoom
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', {attribution: attr, maxNativeZoom: 16, maxZoom: 19}).addTo(map);
const labels = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}', {maxNativeZoom: 16, maxZoom: 19, pane: 'shadowPane'});

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

function icon(st, zoomed, best) {
  const p = st.prices[product];
  if (!zoomed) return L.divIcon({className: '', html: '<div class="dot"></div>', iconSize: [0, 0]});
  const cls = 'pin' + (p ? (best ? ' best' : '') : ' none');
  return L.divIcon({className: '', html: `<div class="${cls}">${p ? brl(p.price).replace('R$ ', '') : '—'}</div>`, iconSize: [0, 0]});
}

function popup(st) {
  const rows = products.map(pr => {
    const p = st.prices[pr];
    return `<tr><td>${esc(pr)}</td><td>${p ? brl(p.price) : '—'}</td></tr>`;
  }).join('');
  const upd = Object.values(st.prices).map(p => p.updated_at).sort().pop();
  const when = upd ? 'Atualizado ' + new Date(upd).toLocaleDateString('pt-BR') : '';
  return `<div class="popup"><h3>${esc(st.name)}</h3>
    <div class="sub">${esc([st.city, st.uf, st.highway].filter(Boolean).join(' · '))}</div>
    <table>${rows}</table><div class="sub">${when}</div>
    <a class="waze" href="https://waze.com/ul?ll=${st.lat},${st.lon}&navigate=yes" target="_blank" rel="noopener">Abrir no Waze</a></div>`;
}

function render() {
  const zoomed = map.getZoom() >= PRICE_ZOOM;
  if (zoomed) labels.addTo(map); else map.removeLayer(labels);
  const best = bestIds();
  for (const st of stations) {
    let m = markers.get(st.id);
    if (!m) {
      m = L.marker([st.lat, st.lon]).addTo(map).bindPopup(() => popup(st), {minWidth: 220});
      markers.set(st.id, m);
    }
    m.setIcon(icon(st, zoomed, best.has(st.id)));
  }
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
})();
