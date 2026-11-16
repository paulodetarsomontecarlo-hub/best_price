#!/usr/bin/env python3
"""Preenche lat/lon dos postos sem coordenadas usando o Nominatim (OpenStreetMap).

Uso: python3 geocode.py        (precisa de internet; ~1 consulta por segundo)

Tenta endereço completo, depois "rua, cidade, UF" e por fim só a cidade (neste caso
a posição é aproximada e o posto fica marcado em `approx` no log: confira no /admin.html).
"""
import json
import re
import time
import urllib.parse
import urllib.request

import server

UA = "best_price-geocoder/1.0"


def q(text):
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": text, "format": "json", "limit": 1, "countrycodes": "br"})
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r:
        data = json.load(r)
    time.sleep(1.1)
    return (float(data[0]["lat"]), float(data[0]["lon"])) if data else None


def main():
    server.init_db()
    with server.db() as con:
        rows = con.execute("SELECT * FROM stations WHERE active=1 AND lat IS NULL").fetchall()
        print(f"{len(rows)} posto(s) sem coordenadas")
        for r in rows:
            street = re.split(r",\s*(?:N[ºo°]|CEP)", r["address"], flags=re.I)[0]
            num = re.search(r"N[ºo°]:?\s*(\d+)", r["address"], flags=re.I)
            street_n = f"{street} {num.group(1)}" if num else street
            tries = [(f"{street_n}, {r['city']}, {r['uf']}", "ok"), (f"{street}, {r['city']}, {r['uf']}", "ok"),
                     (f"{r['city']}, {r['uf']}", "approx")]
            for text, kind in tries:
                try:
                    pos = q(text)
                except Exception as e:  # rede/limite: segue para o próximo posto
                    print("erro:", r["name"], e)
                    break
                if pos:
                    con.execute("UPDATE stations SET lat=?, lon=? WHERE id=?", (*pos, r["id"]))
                    con.commit()
                    print(f"[{kind}] {r['name']} -> {pos}")
                    break
            else:
                print("[não achou]", r["name"])


if __name__ == "__main__":
    main()
