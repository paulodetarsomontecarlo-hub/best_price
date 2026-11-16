"""Roteirizador: busca de cidades (Nominatim/OSM), rota (OSRM) e postos ao longo do percurso.

Serviços públicos e gratuitos, pensados para uso leve. Para tráfego alto, aponte
NOMINATIM_URL e OSRM_URL (variáveis de ambiente) para instâncias próprias ou de um provedor.
"""
import json
import math
import os
import threading
import time
import urllib.parse
import urllib.request

NOMINATIM_URL = os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org")
OSRM_URL = os.environ.get("OSRM_URL", "https://router.project-osrm.org")
UA = "PinVerde/1.0 (roteirizador)"

_lock = threading.Lock()
_last_call = 0.0
_cache = {}


def _get(url, spaced=False):
    global _last_call
    if spaced:  # política do Nominatim: no máximo 1 consulta por segundo
        with _lock:
            wait = 1.1 - (time.time() - _last_call)
            if wait > 0:
                time.sleep(wait)
            _last_call = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


def _cached(key, ttl, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    val = fn()
    if len(_cache) > 500:
        _cache.clear()
    _cache[key] = (time.time(), val)
    return val


def geocode(text):
    text = " ".join(text.split())[:80]
    if len(text) < 3:
        return []

    def run():
        url = NOMINATIM_URL + "/search?" + urllib.parse.urlencode(
            {"q": text, "format": "jsonv2", "limit": 8, "countrycodes": "br", "addressdetails": 1})
        out, seen = [], set()
        for it in _get(url, spaced=True):
            a = it.get("address", {})
            name = (a.get("city") or a.get("town") or a.get("village") or a.get("municipality")
                    or it.get("name") or "")
            if not name or it.get("category") not in ("place", "boundary"):
                continue
            label = f"{name} - {a.get('state', '')}".strip(" -")
            if label in seen:
                continue
            seen.add(label)
            out.append({"label": label, "lat": float(it["lat"]), "lon": float(it["lon"])})
        return out[:5]

    return _cached(("g", text.lower()), 3600, run)


def route(a, b):
    """a, b = (lat, lon). Devolve (pontos [(lat, lon)], distância km, duração min)."""
    def run():
        url = (f"{OSRM_URL}/route/v1/driving/{a[1]},{a[0]};{b[1]},{b[0]}"
               "?overview=full&geometries=geojson&steps=false")
        d = _get(url)
        if d.get("code") != "Ok" or not d.get("routes"):
            raise ValueError("não foi possível traçar uma rota entre essas cidades")
        r = d["routes"][0]
        pts = [(lat, lon) for lon, lat in r["geometry"]["coordinates"]]
        return pts, r["distance"] / 1000, r["duration"] / 60

    return _cached(("r", round(a[0], 3), round(a[1], 3), round(b[0], 3), round(b[1], 3)), 900, run)


def stations_along(points, stations, radius_km):
    """Postos a até radius_km do percurso, em ordem de passagem.
    Acrescenta km_along (km desde a origem até o ponto mais próximo) e offset_km (desvio)."""
    lat0 = sum(p[0] for p in points) / len(points)
    kx = 111.32 * math.cos(math.radians(lat0))
    xy = [(p[1] * kx, p[0] * 110.57) for p in points]
    cum = [0.0]
    for i in range(1, len(xy)):
        cum.append(cum[-1] + math.hypot(xy[i][0] - xy[i - 1][0], xy[i][1] - xy[i - 1][1]))
    out = []
    for s in stations:
        sx, sy = s["lon"] * kx, s["lat"] * 110.57
        best = (1e9, 0.0)
        for i in range(len(xy) - 1):
            (x1, y1), (x2, y2) = xy[i], xy[i + 1]
            if (sx < min(x1, x2) - radius_km or sx > max(x1, x2) + radius_km
                    or sy < min(y1, y2) - radius_km or sy > max(y1, y2) + radius_km):
                continue
            dx, dy = x2 - x1, y2 - y1
            seg = dx * dx + dy * dy
            t = 0 if seg == 0 else max(0, min(1, ((sx - x1) * dx + (sy - y1) * dy) / seg))
            d = math.hypot(sx - (x1 + t * dx), sy - (y1 + t * dy))
            if d < best[0]:
                best = (d, cum[i] + t * math.sqrt(seg))
        if best[0] <= radius_km:
            out.append({**s, "offset_km": round(best[0], 1), "km_along": round(best[1], 1)})
    out.sort(key=lambda s: s["km_along"])
    return out


def simplify(points, limit=1500):
    if len(points) <= limit:
        return points
    step = len(points) / limit
    pts = [points[int(i * step)] for i in range(limit)]
    pts.append(points[-1])
    return pts
