#!/usr/bin/env python3
"""Importa postos de um CSV (ex.: gerado pelo google-maps-scraper-kit).

Uso: python3 import_stations.py postos.csv [--highway BR-163]

Colunas aceitas (nomes em inglês ou português, sem diferenciar maiúsculas):
  name/nome, latitude/lat, longitude/lon/lng, address/endereco, city/cidade,
  uf/state, brand/bandeira. Sem coordenadas, a linha é ignorada.
Postos já existentes (mesmo nome + coordenadas) não são duplicados.
"""
import csv
import sys

import server

ALIASES = {
    "name": ("name", "nome", "title"),
    "lat": ("latitude", "lat"),
    "lon": ("longitude", "lon", "lng", "long"),
    "city": ("city", "cidade"),
    "uf": ("uf", "state", "estado"),
    "brand": ("brand", "bandeira"),
}


def pick(row, key):
    for a in ALIASES[key]:
        for k, v in row.items():
            if k and k.strip().lower() == a and v:
                return v.strip()
    return ""


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    hw = args[args.index("--highway") + 1] if "--highway" in args else ""
    server.init_db()
    added = skipped = 0
    with open(args[0], newline="", encoding="utf-8-sig") as f, server.db() as con:
        for row in csv.DictReader(f):
            name, lat, lon = pick(row, "name"), pick(row, "lat"), pick(row, "lon")
            try:
                lat, lon = float(lat), float(lon)
            except ValueError:
                skipped += 1
                continue
            if not name or con.execute("SELECT 1 FROM stations WHERE name=? AND lat=? AND lon=?",
                                       (name, lat, lon)).fetchone():
                skipped += 1
                continue
            con.execute("INSERT INTO stations (name,brand,city,uf,highway,lat,lon) VALUES (?,?,?,?,?,?,?)",
                        (name, pick(row, "brand"), pick(row, "city"), pick(row, "uf"), hw, lat, lon))
            added += 1
    print(f"{added} posto(s) importado(s), {skipped} ignorado(s).")


if __name__ == "__main__":
    main()
