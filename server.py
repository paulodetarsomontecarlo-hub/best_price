#!/usr/bin/env python3
"""best_price: API + servidor estático (somente biblioteca padrão + SQLite).

Variáveis de ambiente:
  PORT          porta (padrão 8000)
  DB_PATH       arquivo SQLite (padrão best_price.db)
  ADMIN_TOKEN   token para /admin e escrita na API (obrigatório para cadastrar)
  COOKIE_SECURE 1 para marcar o cookie de sessão como Secure (use com HTTPS)

Clientes entram com CPF/CNPJ + senha (cadastrados no /admin.html ou por import_clients.py).
"""
import hmac
import json
import mimetypes
import os
import sqlite3
import sys
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import auth
import planner

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DB_PATH = os.environ.get("DB_PATH", str(ROOT / "best_price.db"))
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
COOKIE_SECURE = os.environ.get("COOKIE_SECURE") == "1"
PRODUCTS = ["DIESEL S-10", "DIESEL S-500", "ARLA"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS stations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  brand TEXT DEFAULT '',
  city TEXT DEFAULT '',
  uf TEXT DEFAULT '',
  highway TEXT DEFAULT '',
  lat REAL,
  lon REAL,
  address TEXT DEFAULT '',
  category TEXT DEFAULT '',
  geo_quality TEXT DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS prices (
  station_id INTEGER NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
  product TEXT NOT NULL CHECK (product IN ('DIESEL S-10','DIESEL S-500','ARLA')),
  price REAL NOT NULL CHECK (price > 0),
  updated_at TEXT NOT NULL,
  PRIMARY KEY (station_id, product)
);
CREATE TABLE IF NOT EXISTS price_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  station_id INTEGER NOT NULL,
  product TEXT NOT NULL,
  price REAL NOT NULL,
  changed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS routes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  highway TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS route_stations (
  route_id INTEGER NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
  station_id INTEGER NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
  position INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (route_id, station_id)
);
"""


def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db():
    with db() as con:
        con.executescript(SCHEMA)
        con.executescript(auth.AUTH_SCHEMA)
        cols = {r["name"] for r in con.execute("PRAGMA table_info(stations)")}
        for c in ("address", "category", "geo_quality"):  # migração de bancos criados antes
            if c not in cols:
                con.execute(f"ALTER TABLE stations ADD COLUMN {c} TEXT DEFAULT ''")


def load_seed():
    """Banco vazio: carrega data/seed.json (postos da rede e rotas por rodovia, sem preços)."""
    seed = ROOT / "data" / "seed.json"
    with db() as con:
        if not seed.exists() or con.execute("SELECT 1 FROM stations LIMIT 1").fetchone():
            return
        data = json.loads(seed.read_text(encoding="utf-8"))
        ids = []
        for s in data["stations"]:
            ids.append(con.execute(
                "INSERT INTO stations (name,brand,city,uf,highway,lat,lon,address,category,geo_quality) "
                "VALUES (:name,:brand,:city,:uf,:highway,:lat,:lon,:address,:category,:geo_quality)", s).lastrowid)
        for r in data["routes"]:
            rid = con.execute("INSERT INTO routes (name,highway) VALUES (?,?)", (r["name"], r["highway"])).lastrowid
            for pos, i in enumerate(r["stations"]):
                con.execute("INSERT INTO route_stations (route_id,station_id,position) VALUES (?,?,?)", (rid, ids[i], pos))


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def stations_with_prices(con, mapped_only=True):
    where = "active = 1" + (" AND lat IS NOT NULL AND lon IS NOT NULL" if mapped_only else "")
    rows = con.execute(f"SELECT * FROM stations WHERE {where} ORDER BY name").fetchall()
    prices = {}
    for p in con.execute("SELECT * FROM prices"):
        prices.setdefault(p["station_id"], {})[p["product"]] = {
            "price": p["price"], "updated_at": p["updated_at"]}
    return [{**dict(r), "prices": prices.get(r["id"], {})} for r in rows]


def routes_with_stats(con):
    stations = {s["id"]: s for s in stations_with_prices(con)}
    out = []
    for r in con.execute("SELECT * FROM routes ORDER BY name"):
        ids = [x["station_id"] for x in con.execute(
            "SELECT station_id FROM route_stations WHERE route_id = ? ORDER BY position",
            (r["id"],))]
        members = [stations[i] for i in ids if i in stations]
        stats = {}
        for prod in PRODUCTS:
            vals = [(s["prices"][prod]["price"], s) for s in members if prod in s["prices"]]
            if vals:
                best_price, best = min(vals, key=lambda v: v[0])
                stats[prod] = {
                    "avg": round(sum(v[0] for v in vals) / len(vals), 3),
                    "best": best_price,
                    "best_station_id": best["id"],
                    "best_station": best["name"],
                    "best_city": best["city"],
                    "count": len(vals),
                }
        out.append({"id": r["id"], "name": r["name"], "highway": r["highway"],
                    "station_ids": ids, "stats": stats})
    return out


def need(body, *keys):
    for k in keys:
        if body.get(k) in (None, ""):
            raise ValueError(f"campo obrigatório: {k}")


def num(v, field):
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        raise ValueError(f"{field} inválido")


class Handler(BaseHTTPRequestHandler):
    server_version = "best_price"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    # ---- helpers
    def send_json(self, data, status=200):
        raw = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def is_admin(self):
        tok = self.headers.get("X-Admin-Token", "")
        return bool(ADMIN_TOKEN) and hmac.compare_digest(tok, ADMIN_TOKEN)

    def session_token(self):
        c = SimpleCookie(self.headers.get("Cookie", ""))
        return c["bp_session"].value if "bp_session" in c else ""

    def client_ok(self, query=None):
        if self.is_admin():
            return True
        with db() as con:
            return auth.session_client(con, self.session_token()) is not None

    def set_cookie(self, token, max_age):
        flags = f"bp_session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}"
        return flags + ("; Secure" if COOKIE_SECURE else "")

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 1_000_000:
            raise ValueError("corpo grande demais")
        return json.loads(self.rfile.read(n) or b"{}")

    # ---- routing
    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path.startswith("/api/"):
            if not self.client_ok(q):
                return self.send_json({"error": "login necessário"}, 401)
            if u.path == "/api/me":
                with db() as con:
                    c = auth.session_client(con, self.session_token())
                return self.send_json({"name": (c["name"] or auth.fmt_doc(c["doc"])) if c else "Administrador"})
            if u.path == "/api/admin/clients":
                if not self.is_admin():
                    return self.send_json({"error": "token de admin inválido"}, 401)
                with db() as con:
                    rows = con.execute("SELECT id,doc,name,active,created_at,last_login FROM clients ORDER BY name,doc")
                    return self.send_json([{**dict(r), "doc_fmt": auth.fmt_doc(r["doc"])} for r in rows])
            if u.path in ("/api/geocode", "/api/plan"):
                return self.planner(u.path, q)
            with db() as con:
                if u.path == "/api/stations":
                    everything = self.is_admin() and q.get("all") == ["1"]
                    return self.send_json(stations_with_prices(con, mapped_only=not everything))
                if u.path == "/api/routes":
                    return self.send_json(routes_with_stats(con))
                if u.path == "/api/config":
                    return self.send_json({"products": PRODUCTS})
            return self.send_json({"error": "não encontrado"}, 404)
        self.serve_static(u.path)

    def planner(self, path, q):
        def latlon(key):
            lat, lon = (float(x) for x in (q.get(key) or [""])[0].split(","))
            if not (-35 <= lat <= 6 and -75 <= lon <= -33):
                raise ValueError("coordenadas fora do Brasil")
            return lat, lon
        try:
            if path == "/api/geocode":
                return self.send_json(planner.geocode((q.get("q") or [""])[0]))
            a, b = latlon("from"), latlon("to")
            radius = max(1.0, min(25.0, float((q.get("radius") or ["5"])[0])))
            pts, km, minutes = planner.route(a, b)
            with db() as con:
                found = planner.stations_along(pts, stations_with_prices(con), radius)
            return self.send_json({
                "distance_km": round(km), "duration_min": round(minutes), "radius_km": radius,
                "geometry": [[round(la, 5), round(lo, 5)] for la, lo in planner.simplify(pts)],
                "stations": found})
        except ValueError as e:
            return self.send_json({"error": str(e) if "rota" in str(e) or "Brasil" in str(e) else "parâmetros inválidos"}, 400)
        except OSError as e:  # sem internet / serviço fora do ar
            return self.send_json({"error": "serviço de mapas indisponível no momento, tente novamente"}, 502)

    def serve_static(self, path):
        if path in ("", "/"):
            path = "/index.html"
        f = (STATIC / path.lstrip("/")).resolve()
        if STATIC not in f.parents or not f.is_file():
            self.send_response(404)
            self.end_headers()
            return
        data = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(f.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        path = urlparse(self.path).path
        if path in ("/api/login", "/api/logout"):
            return self.auth_endpoint(path)
        self.write("POST")

    def auth_endpoint(self, path):
        def reply(data, status=200, cookie=None):
            raw = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            if cookie:
                self.send_header("Set-Cookie", cookie)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)
        if path == "/api/logout":
            with db() as con:
                auth.logout(con, self.session_token())
            return reply({"ok": True}, cookie=self.set_cookie("", 0))
        try:
            b = self.body()
            ip = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()
            with db() as con:
                token, name = auth.login(con, b.get("doc"), str(b.get("password") or ""), ip)
        except json.JSONDecodeError:
            return reply({"error": "Requisição inválida."}, 400)
        except ValueError as e:
            return reply({"error": str(e)}, 429 if "tentativas" in str(e) else 401)
        reply({"name": name}, cookie=self.set_cookie(token, auth.SESSION_DAYS * 86400))

    def do_PUT(self):
        self.write("PUT")

    def do_DELETE(self):
        self.write("DELETE")

    def write(self, method):
        u = urlparse(self.path)
        if not self.is_admin():
            return self.send_json({"error": "token de admin inválido"}, 401)
        parts = u.path.strip("/").split("/")  # api admin <res> [id]
        if parts[:2] != ["api", "admin"] or len(parts) < 3:
            return self.send_json({"error": "não encontrado"}, 404)
        res = parts[2]
        rid = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else None
        try:
            b = self.body() if method != "DELETE" else {}
            with db() as con:
                return self.send_json(self.handle_admin(con, method, res, rid, b))
        except (ValueError, sqlite3.Error, json.JSONDecodeError) as e:
            return self.send_json({"error": str(e)}, 400)

    def handle_admin(self, con, method, res, rid, b):
        if res == "stations":
            if method == "DELETE" and rid:
                con.execute("UPDATE stations SET active = 0 WHERE id = ?", (rid,))
                return {"ok": True}
            need(b, "name")
            lat = num(b["lat"], "lat") if b.get("lat") not in (None, "") else None
            lon = num(b["lon"], "lon") if b.get("lon") not in (None, "") else None
            if (lat is None) != (lon is None):
                raise ValueError("informe latitude e longitude juntas")
            vals = (b["name"], b.get("brand", ""), b.get("city", ""), b.get("uf", ""),
                    b.get("highway", ""), lat, lon, b.get("address", ""), b.get("category", ""))
            if method == "POST":
                cur = con.execute(
                    "INSERT INTO stations (name,brand,city,uf,highway,lat,lon,address,category,geo_quality) "
                    "VALUES (?,?,?,?,?,?,?,?,?,'manual')", vals)
                return {"id": cur.lastrowid}
            if method == "PUT" and rid:
                con.execute("UPDATE stations SET name=?,brand=?,city=?,uf=?,highway=?,lat=?,lon=?,"
                            "address=?,category=?,geo_quality=CASE WHEN lat IS ? AND lon IS ? THEN geo_quality ELSE 'manual' END "
                            "WHERE id=?", vals + (lat, lon, rid))
                return {"ok": True}
        if res == "prices" and method == "PUT":
            # {"station_id": 1, "prices": {"DIESEL S-10": 6.12, "ARLA": 3.4}}  (vazio/null = remove)
            need(b, "station_id")
            sid = int(b["station_id"])
            for prod, val in (b.get("prices") or {}).items():
                if prod not in PRODUCTS:
                    raise ValueError(f"produto inválido: {prod}")
                if val in (None, ""):
                    con.execute("DELETE FROM prices WHERE station_id=? AND product=?", (sid, prod))
                    continue
                p = num(val, prod)
                if p <= 0:
                    raise ValueError(f"preço inválido para {prod}")
                ts = now()
                con.execute(
                    "INSERT INTO prices (station_id,product,price,updated_at) VALUES (?,?,?,?) "
                    "ON CONFLICT(station_id,product) DO UPDATE SET price=excluded.price, updated_at=excluded.updated_at",
                    (sid, prod, p, ts))
                con.execute("INSERT INTO price_history (station_id,product,price,changed_at) VALUES (?,?,?,?)",
                            (sid, prod, p, ts))
            return {"ok": True}
        if res == "clients":
            if method == "DELETE" and rid:  # desativa e derruba as sessões
                con.execute("UPDATE clients SET active=0 WHERE id=?", (rid,))
                con.execute("DELETE FROM sessions WHERE client_id=?", (rid,))
                return {"ok": True}
            if method == "POST":
                need(b, "doc", "password")
                if not auth.valid_doc(b["doc"]):
                    raise ValueError("CPF/CNPJ inválido")
                if len(str(b["password"])) < auth.MIN_PASSWORD:
                    raise ValueError(f"senha com pelo menos {auth.MIN_PASSWORD} caracteres")
                if con.execute("SELECT 1 FROM clients WHERE doc=?", (auth.digits(b["doc"]),)).fetchone():
                    raise ValueError("já existe cliente com esse CPF/CNPJ")
                return {"id": auth.upsert_client(con, b["doc"], b.get("name", ""), str(b["password"]))[0]}
            if method == "PUT" and rid:
                if b.get("password"):
                    if len(str(b["password"])) < auth.MIN_PASSWORD:
                        raise ValueError(f"senha com pelo menos {auth.MIN_PASSWORD} caracteres")
                    con.execute("UPDATE clients SET pwd_hash=? WHERE id=?", (auth.hash_password(str(b["password"])), rid))
                    con.execute("DELETE FROM sessions WHERE client_id=?", (rid,))
                if "name" in b:
                    con.execute("UPDATE clients SET name=? WHERE id=?", (b["name"], rid))
                if "active" in b:
                    con.execute("UPDATE clients SET active=? WHERE id=?", (1 if b["active"] else 0, rid))
                    if not b["active"]:
                        con.execute("DELETE FROM sessions WHERE client_id=?", (rid,))
                return {"ok": True}
        if res == "routes":
            if method == "DELETE" and rid:
                con.execute("DELETE FROM routes WHERE id = ?", (rid,))
                return {"ok": True}
            if method in ("POST", "PUT"):
                need(b, "name")
                if method == "POST":
                    rid = con.execute("INSERT INTO routes (name,highway) VALUES (?,?)",
                                      (b["name"], b.get("highway", ""))).lastrowid
                elif rid:
                    con.execute("UPDATE routes SET name=?, highway=? WHERE id=?",
                                (b["name"], b.get("highway", ""), rid))
                else:
                    raise ValueError("id da rota ausente")
                con.execute("DELETE FROM route_stations WHERE route_id = ?", (rid,))
                for pos, sid in enumerate(b.get("station_ids", [])):
                    con.execute("INSERT OR IGNORE INTO route_stations (route_id,station_id,position) VALUES (?,?,?)",
                                (rid, int(sid), pos))
                return {"id": rid}
        raise ValueError("operação não suportada")


def main():
    init_db()
    load_seed()
    port = int(os.environ.get("PORT", 8000))
    if not ADMIN_TOKEN:
        print("AVISO: defina ADMIN_TOKEN para poder cadastrar postos/preços.", file=sys.stderr)
    print(f"best_price em http://localhost:{port}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
