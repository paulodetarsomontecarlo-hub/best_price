#!/usr/bin/env python3
"""Corrige/preenche lat/lon dos postos usando o Nominatim (OpenStreetMap).

Uso: python3 geocode.py          só postos sem coordenadas
     python3 geocode.py --all    reavalia todos (as coordenadas do KMZ costumam vir erradas)

Precisa de internet; ~1 consulta por segundo. Resultado por posto (coluna geo_quality):
  ok      endereço (ou rua + cidade) encontrado: coordenada confiável
  kml     coordenada do arquivo, mantida porque fica perto da cidade
  approx  só a cidade foi encontrada: posição aproximada (com pequeno deslocamento
          para os pinos não se sobreporem). Confira no /admin.html.
"""
import hashlib
import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request

import import_kml
import server

UA = "best_price-geocoder/1.0"


def q(text):
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": text, "format": "json", "limit": 1, "countrycodes": "br"})
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r:
        data = json.load(r)
    time.sleep(1.1)
    return (float(data[0]["lat"]), float(data[0]["lon"])) if data else None


def km(a, b):
    dy = (a[0] - b[0]) * 111
    dx = (a[1] - b[1]) * 111 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


def jitter(sid, pos):
    h = hashlib.md5(str(sid).encode()).digest()
    return (pos[0] + (h[0] / 255 - .5) * .05, pos[1] + (h[1] / 255 - .5) * .05)  # ~±2,7 km


def main():
    everything = "--all" in sys.argv
    server.init_db()
    centroids = {}
    with server.db() as con:
        where = "active=1" + ("" if everything else " AND lat IS NULL")
        rows = con.execute(f"SELECT * FROM stations WHERE {where}").fetchall()
        print(f"{len(rows)} posto(s) para processar")
        for r in rows:
            street = re.split(r",\s*(?:N[ºo°]|CEP)", r["address"], flags=re.I)[0].replace("\n", " ")
            num = re.search(r"N[ºo°]:?\s*(\d+)", r["address"], flags=re.I)
            street_n = f"{street} {num.group(1)}" if num else street
            place = f"{r['city']}, {r['uf']}"
            pos, kind = None, ""
            try:
                for text in (f"{street_n}, {place}", f"{street}, {place}"):
                    pos = q(text)
                    if pos:
                        kind = "ok"
                        break
                if not pos:
                    if place not in centroids:
                        centroids[place] = q(place)
                    c = centroids[place]
                    if c and r["lat"] is not None and km((r["lat"], r["lon"]), c) <= 25:
                        pos, kind = (r["lat"], r["lon"]), "kml"
                    elif c:
                        pos, kind = jitter(r["id"], c), "approx"
            except Exception as e:
                print("erro:", r["name"], e)
                continue
            if pos:
                con.execute("UPDATE stations SET lat=?, lon=?, geo_quality=? WHERE id=?", (*pos, kind, r["id"]))
                con.commit()
            print(f"[{kind or 'não achou'}] {r['name']} ({r['city']}) -> {pos}")
        print(import_kml.build_routes(con), "rota(s) por rodovia atualizada(s)")


if __name__ == "__main__":
    main()
