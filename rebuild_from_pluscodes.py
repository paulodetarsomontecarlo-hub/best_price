#!/usr/bin/env python3
"""Refaz a base de postos usando SOMENTE a planilha de Plus Codes (Unidade;Bandeira;Plus Code).

Uso: python rebuild_from_pluscodes.py "pluscode unidades.csv"

- Apaga todos os postos/preços/rotas atuais e cria um posto por linha da planilha.
- Gera data/seed.json (usado por bancos novos) e recria as rotas por rodovia.
- Preços de teste (mock) nos faixas combinadas: S-10 6,39–6,79 / S-500 6,09–6,29 / ARLA 3,20–3,90.
- Rodovia: herdada do posto antigo equivalente quando o nome/cidade casam; senão, vazia.
"""
import json
import random
import re
import sys
from datetime import datetime, timezone

import import_kml
import check_pluscodes as ip
import planner
import server

UF = {"acre": "AC", "alagoas": "AL", "amapa": "AP", "amazonas": "AM", "bahia": "BA", "ceara": "CE",
      "distrito federal": "DF", "espirito santo": "ES", "goias": "GO", "maranhao": "MA", "mato grosso": "MT",
      "mato grosso do sul": "MS", "minas gerais": "MG", "para": "PA", "paraiba": "PB", "parana": "PR",
      "pernambuco": "PE", "piaui": "PI", "rio de janeiro": "RJ", "rio grande do norte": "RN",
      "rio grande do sul": "RS", "rondonia": "RO", "roraima": "RR", "santa catarina": "SC", "sao paulo": "SP",
      "sergipe": "SE", "tocantins": "TO"}
# referência aproximada para completar códigos curtos de postos que ainda não existiam no banco
REF = {"corumbata": (-22.22, -47.62), "uberlandia": (-18.92, -48.28), "varzea grande": (-15.65, -56.13),
       "mirassol": (-20.81, -49.46), "candido mota": (-22.75, -50.39)}


def parse_place(text):
    t = re.sub(r",?\s*\d{5}-\d{3}\s*$", "", text.strip().lstrip(","))
    t = t.strip(" ,")
    if " - " in t:
        left, state = t.rsplit(" - ", 1)
        city = left.split(",")[-1].strip()
    elif "," in t:
        city, state = [x.strip() for x in t.rsplit(",", 1)]
        city = city.split(",")[-1].strip()
    else:
        city, state = t, ""
    st = state.strip()
    uf = st.upper() if len(st) == 2 else UF.get(ip.norm(st).strip(), "")
    return city, uf


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    rows = ip.read_rows(sys.argv[1])
    server.init_db()
    with server.db() as con:
        old = [dict(r) for r in con.execute("SELECT * FROM stations")]
    used, stations = set(), []
    for r in rows:
        unit, brand, pc = r["Unidade"].strip(), r["Bandeira"].strip(), r["Plus Code"].strip()
        m = re.match(r"([23456789CFGHJMPQRVWX]{2,8}\+[23456789CFGHJMPQRVWX]{2,3})\b", pc, re.I)
        code, rest = m.group(1).upper(), pc[m.end():]
        city, uf = parse_place(rest)
        place = ip.norm(rest)
        utoks = {t for t in ip.norm(unit).split() if t not in ip.STOP}
        best, score = None, 0
        for s in old:
            if s["id"] in used or not s["lat"]:
                continue
            c = ip.norm(s["city"]).strip()
            sc = 3 if c and re.search(r"\b" + re.escape(c) + r"\b", place) else 0
            if c and re.search(r"\b" + re.escape(c) + r"\b", ip.norm(unit)):
                sc += 1
            toks = set(ip.norm(s["name"]).split())
            sc += sum(1 for a in utoks if a in toks)
            if sc > score:
                best, score = s, sc
        if best and score >= 4:
            used.add(best["id"])
        else:
            best = None
        if len(code.split("+")[0]) >= 8:
            lat, lon = ip.decode(code)
        else:
            ref = (best["lat"], best["lon"]) if best else next(
                (v for k, v in REF.items() if k in ip.norm(city) or k in place), None)
            if not ref:
                try:
                    g = planner.geocode(f"{city}, {uf}, Brasil")
                    ref = (g[0]["lat"], g[0]["lon"]) if g else None
                except Exception:
                    ref = None
            if not ref:
                print(f"!! sem referência para {unit} [{code}] — ignorado")
                continue
            lat, lon = ip.recover(code, *ref)
        stations.append({"name": unit, "brand": brand.upper(), "city": city, "uf": uf,
                         "highway": best["highway"] if best else "", "lat": round(lat, 6), "lon": round(lon, 6),
                         "address": pc, "category": best["category"] if best else "", "geo_quality": "ok"})
        print(f"{unit[:40]:40} {city}/{uf}  {lat:.5f},{lon:.5f}  {'(herdou ' + best['highway'] + ')' if best and best['highway'] else ''}")

    # ---- grava
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    random.seed(42)
    with server.db() as con:
        for t in ("price_claims", "price_history", "prices", "route_stations", "routes", "stations"):
            con.execute(f"DELETE FROM {t}")
        con.execute("DELETE FROM sqlite_sequence WHERE name IN ('stations','routes','price_claims','price_history')")
        for s in stations:
            sid = con.execute(
                "INSERT INTO stations (name,brand,city,uf,highway,lat,lon,address,category,geo_quality) "
                "VALUES (:name,:brand,:city,:uf,:highway,:lat,:lon,:address,:category,:geo_quality)", s).lastrowid
            for prod, lo, hi in (("DIESEL S-10", 6.39, 6.79), ("DIESEL S-500", 6.09, 6.29), ("ARLA", 3.20, 3.90)):
                con.execute("INSERT INTO prices (station_id,product,price,updated_at) VALUES (?,?,?,?)",
                            (sid, prod, round(random.uniform(lo, hi), 2), ts))
        n = import_kml.build_routes(con)
        routes = []
        ids = {r["id"]: i for i, r in enumerate(con.execute("SELECT id FROM stations ORDER BY id"))}
        for r in con.execute("SELECT * FROM routes ORDER BY id").fetchall():
            st = [ids[x["station_id"]] for x in con.execute(
                "SELECT station_id FROM route_stations WHERE route_id=? ORDER BY position", (r["id"],))]
            routes.append({"name": r["name"], "highway": r["highway"], "stations": st})
    with open(server.ROOT / "data" / "seed.json", "w", encoding="utf-8") as f:
        json.dump({"stations": stations, "routes": routes}, f, ensure_ascii=False, indent=1)
    print(f"\n{len(stations)} postos, {n} rotas. seed.json atualizado.")


if __name__ == "__main__":
    main()
