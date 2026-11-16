const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const brl = v => 'R$ ' + Number(v).toFixed(2).replace('.', ',');
const CODE = new URLSearchParams(location.search).get('code') || sessionStorage.getItem('code') || '';
if (CODE) sessionStorage.setItem('code', CODE);


const CARD_ZOOM = 10;      // com zoom: nome do posto + preço (cartão), sem sobrepor
const CHIP_ZOOM = 8;       // zoom intermediário: só o preço; abaixo disso: pontos
let products = [], product = null, stations = [], routes = [], selRoute = null, routeLine = null;
let markers = new Map(), tiers = new Map();
let plan = null, planLine = null;   // roteirizador: {data, from, to, ids:Set}

const map = L.map('map', {zoomControl: false, center: [-21.23, -56.94], zoom: 6, minZoom: 4});
L.control.zoom({position: 'bottomright'}).addTo(map);
const attr = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
// mapa colorido com rodovias (verde/laranja/rosa), cidades e rótulos já incluídos no tile
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {attribution: attr, maxZoom: 19}).addTo(map);
const labels = L.layerGroup();  // (rótulos vêm no próprio tile; mantido só para a lógica de zoom)

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
  const pb = plan && planStats().best; if (pb) ids.add(pb.id);
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
  if (mode === 'dot') {  // pino de posto (bomba de combustível), cor pela faixa de preço
    const tip = esc(prettyName(st.name)) + (p ? ' · ' + brl(p.price) : '');
    return L.divIcon({className: '', iconSize: [0, 0], html:
      `<div class="mpin ${t}${best ? ' best' : ''}" title="${tip}"><svg viewBox="0 0 30 40" width="30" height="40" aria-hidden="true">
        <path class="bd" d="M15 39C15 39 2 24.5 2 14.5 2 7.1 7.8 1 15 1s13 6.1 13 13.5C28 24.5 15 39 15 39z"/>
        <circle cx="15" cy="14.5" r="8.6" fill="#fff"/>
        <path class="gl" d="M10.6 9.3a1 1 0 0 1 1-1h4.1a1 1 0 0 1 1 1v10.4h-6.1zM17.7 10.7l2 1.9c.3.3.5.7.5 1.1v3.6a.9.9 0 0 0 1.8 0v-4.4l-2.5-2.4z"/>
        <rect x="11.9" y="10" width="3.5" height="3" rx=".5" fill="#fff"/></svg>${best ? '<span class="pstar">★</span>' : ''}</div>`});
  }
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
  const onRoute = id => !plan || plan.ids.has(id);
  const order = [...stations].sort((a, b) =>
    (onRoute(b.id) - onRoute(a.id)) || (best.has(b.id) - best.has(a.id)) || ((a.prices[product]?.price ?? 1e9) - (b.prices[product]?.price ?? 1e9)));
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
    if (!onRoute(st.id)) mode = 'dot';  // fora do trajeto: só um ponto apagado
    else if (z >= CARD_ZOOM && free(pt.x, pt.y, BOX.card)) mode = 'card';
    else if (z >= CHIP_ZOOM && free(pt.x, pt.y, BOX.chip)) mode = 'chip';
    take(pt.x, pt.y, BOX[mode]);
    m.setOpacity(onRoute(st.id) ? 1 : .3);
    m.setIcon(icon(st, mode, best.has(st.id)));
    m.options.icon.options.popupAnchor = [0, mode === 'dot' ? -38 : -30];
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
  clearPlan(false);
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
  product = b.dataset.p; renderProducts(); render(); renderRoutes(); renderPlan();
};
$('#routes').onclick = e => {
  const c = e.target.closest('.route'); if (!c) return;
  const id = +c.dataset.id;
  pickRoute(selRoute?.id === id ? null : id);
};
/* ---------- roteirizador ---------- */
const chosen = {from: null, to: null};
const fmtTime = m => m >= 60 ? `${Math.floor(m / 60)}h${String(m % 60).padStart(2, '0')}` : `${m} min`;
const fmtKm = v => String(v).replace('.', ',');

function planStats() {
  const priced = plan.data.stations.filter(s => s.prices[product]);
  if (!priced.length) return {n: 0};
  const best = priced.reduce((a, b) => b.prices[product].price < a.prices[product].price ? b : a);
  return {n: priced.length, avg: priced.reduce((t, s) => t + s.prices[product].price, 0) / priced.length, best};
}

function suggest(key, input, ul) {
  let timer;
  input.addEventListener('input', () => {
    chosen[key] = null; clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 3) { ul.innerHTML = ''; return; }
    timer = setTimeout(async () => {
      try {
        const res = await api('/api/geocode?q=' + encodeURIComponent(q));
        if (input.value.trim() !== q) return;
        ul._res = res;
        ul.innerHTML = res.map((c, i) => `<li data-i="${i}">${esc(c.label)}</li>`).join('');
      } catch { ul.innerHTML = ''; }
    }, 450);
  });
  ul.addEventListener('click', e => {
    const li = e.target.closest('li'); if (!li) return;
    chosen[key] = ul._res[+li.dataset.i]; input.value = chosen[key].label; ul.innerHTML = '';
  });
  input.addEventListener('blur', () => setTimeout(() => { ul.innerHTML = ''; }, 250));
}
suggest('from', $('#fromIn'), $('#fromSug'));
suggest('to', $('#toIn'), $('#toSug'));

async function resolveCity(key, input) {
  if (chosen[key]) return chosen[key];
  const text = input.value.trim();
  if (!text) throw new Error('Informe a cidade de ' + (key === 'from' ? 'saída.' : 'chegada.'));
  const res = await api('/api/geocode?q=' + encodeURIComponent(text));
  if (!res.length) throw new Error('Cidade não encontrada: ' + text);
  chosen[key] = res[0]; input.value = res[0].label;
  return res[0];
}

async function runPlan(e) {
  e.preventDefault();
  const out = $('#planOut'), btn = $('#goBtn');
  btn.disabled = true; btn.textContent = 'Traçando…'; clearPlan(); out.innerHTML = '';
  try {
    const from = await resolveCity('from', $('#fromIn')), to = await resolveCity('to', $('#toIn'));
    const d = await api(`/api/plan?from=${from.lat},${from.lon}&to=${to.lat},${to.lon}&radius=${$('#radius').value}`);
    setPlan({data: d, from, to, ids: new Set(d.stations.map(s => s.id))});
  } catch (err) {
    out.innerHTML = `<p class="err">${esc(err.message)}</p>`;
  } finally { btn.disabled = false; btn.textContent = 'Traçar rota'; }
}

function setPlan(p) {
  clearPlan(false);
  selRoute = null; if (routeLine) { map.removeLayer(routeLine); routeLine = null; }
  renderRoutes();
  plan = p;
  const end = (pt, txt) => L.marker(pt, {zIndexOffset: 500000, icon: L.divIcon({className: '', iconSize: [0, 0], html: `<div class="endpin">${txt}</div>`})});
  const g = p.data.geometry;
  planLine = L.featureGroup([
    L.polyline(g, {color: '#fff', weight: 9, opacity: .9}), L.polyline(g, {color: '#0f4c81', weight: 5, opacity: .9}),
    end(g[0], 'A'), end(g[g.length - 1], 'B')]).addTo(map);
  map.fitBounds(planLine.getBounds().pad(.08), {paddingTopLeft: [0, 70]});
  render(); renderPlan();
  toggle(false);
}

function clearPlan(redraw = true) {
  if (planLine) { map.removeLayer(planLine); planLine = null; }
  plan = null; renderPlan();
  if (redraw) render();
}

function renderPlan() {
  const bar = $('#planBar'), out = $('#planOut');
  if (!plan) { bar.hidden = true; if (!out.querySelector('.err')) out.innerHTML = ''; return; }
  const d = plan.data, st = planStats();
  bar.hidden = false;
  bar.innerHTML = `<b>${d.distance_km} km</b> · ${fmtTime(d.duration_min)} · ${d.stations.length} posto(s)` +
    (st.n ? ` · melhor <b class="g">${brl(st.best.prices[product].price)}</b>` : '') + '<button id="barClear">Limpar</button>';
  const to = plan.to;
  out.innerHTML = `
    <div class="sum"><div><b>${d.distance_km} km</b><span>distância</span></div><div><b>${fmtTime(d.duration_min)}</b><span>tempo</span></div><div><b>${d.stations.length}</b><span>postos</span></div></div>
    <div class="route sel nohover">${st.n
      ? `<div class="row"><span>Preço médio · ${esc(product)}</span><b>${brl(st.avg)}</b></div>
         <div class="row best"><span>Melhor preço</span><b>${brl(st.best.prices[product].price)}</b></div>
         <small>${esc(prettyName(st.best.name))} · ${esc(st.best.city)} · km ${fmtKm(st.best.km_along)}</small>`
      : `<small>${d.stations.length ? 'Nenhum posto do trajeto tem preço de ' + esc(product) + ' cadastrado.' : 'Nenhum posto cadastrado a até ' + d.radius_km + ' km deste trajeto. Aumente a distância e trace de novo.'}</small>`}</div>
    <div class="actions"><a class="waze" href="https://waze.com/ul?ll=${to.lat},${to.lon}&navigate=yes" target="_blank" rel="noopener">Abrir destino no Waze</a>
      <button type="button" id="planClear" class="ghost">Limpar rota</button></div>
    ${d.stations.length ? `<h3 class="stops-h">Postos no trajeto, na ordem</h3><ol class="stops">${d.stations.map(s => {
      const p = s.prices[product], t = 't' + tiers.get(s.id), isBest = st.n && st.best.id === s.id;
      return `<li data-id="${s.id}"><span class="km">${fmtKm(s.km_along)}<small>km</small></span>
        <div class="who"><b>${isBest ? '<span class="star">★</span>' : ''}${esc(prettyName(s.name))}</b>
        <small>${esc(s.city)}${s.offset_km >= 0.3 ? ' · ' + fmtKm(s.offset_km) + ' km fora da rota' : ' · na rota'}</small></div>
        <span class="pp ${t}">${p ? num(p.price) : '—'}</span></li>`;
    }).join('')}</ol>` : ''}`;
}

$('#planForm').onsubmit = runPlan;
$('#planOut').onclick = e => {
  if (e.target.id === 'planClear') return clearPlan();
  const li = e.target.closest('.stops li'); if (!li) return;
  const s = stations.find(x => x.id === +li.dataset.id), m = markers.get(+li.dataset.id);
  if (!s || !m) return;
  toggle(false);
  map.setView([s.lat, s.lon], Math.max(map.getZoom(), 13), {animate: false});
  render(); m.openPopup();
};
document.body.insertAdjacentHTML('beforeend', '<div id="planBar" hidden></div>');
$('#planBar').onclick = e => { if (e.target.id === 'barClear') clearPlan(); };
$('#swapBtn').onclick = () => {
  [$('#fromIn').value, $('#toIn').value] = [$('#toIn').value, $('#fromIn').value];
  [chosen.from, chosen.to] = [chosen.to, chosen.from];
};
$('#tabs').onclick = e => {
  const b = e.target.closest('button'); if (!b) return;
  document.querySelectorAll('#tabs button').forEach(x => x.classList.toggle('on', x === b));
  $('#tab-plan').hidden = b.dataset.tab !== 'plan';
  $('#tab-routes').hidden = b.dataset.tab !== 'routes';
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
  const qs = new URLSearchParams(location.search);  // ?de=Cidade&para=Cidade abre a rota pronta
  if (qs.get('de') && qs.get('para')) {
    $('#fromIn').value = qs.get('de'); $('#toIn').value = qs.get('para');
    $('#planForm').requestSubmit();
  }
})();