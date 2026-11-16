#!/usr/bin/env python3
"""Corrige as coordenadas dos postos a partir de uma planilha com Plus Codes.

Uso: python import_pluscodes.py "pluscode unidades.csv"          (só mostra o casamento)
     python import_pluscodes.py "pluscode unidades.csv" --apply  (grava lat/lon, geo_quality='ok')

Colunas: Unidade;Bandeira;Plus Code. O Plus Code curto (ex.: 6P55+W5 São José do Rio Preto) é
completado usando a posição atual do posto casado como referência (vale quando o erro < ~50 km).
"""
import csv
import difflib
import io
import re
import sys
import unicodedata

import server

ALPHA = "23456789CFGHJMPQRVWX"


def decode(code):
    """Plus Code completo -> (lat, lon) do centro da célula."""
    c = code.replace("+", "").upper()
    lat, lon, res = -90.0, -180.0, 20.0
    for i in range(0, min(len(c), 10), 2):
        lat += ALPHA.index(c[i]) * res
        lon += ALPHA.index(c[i + 1]) * res
        res /= 20
    res *= 20
    if len(c) > 10:  # refinamento em grade 4x5
        la, lo = 0.000125 * 5, 0.000125 * 4
        for ch in c[10:]:
            k = ALPHA.index(ch)
            la /= 5; lo /= 4
            lat += (k // 4) * la; lon += (k % 4) * lo
        res_lat, res_lon = la, lo
    else:
        res_lat = res_lon = res
    return lat + res_lat / 2, lon + res_lon / 2


def recover(short, ref_lat, ref_lon):
    """Completa um código curto (ex.: 6P55+W5) escolhendo a célula mais próxima da referência."""
    pad = 8 - short.index("+")
    area = 20 ** (2 - pad // 2)  # tamanho da célula do prefixo faltante, em graus
    prefix = ""
    # prefixo do código completo da referência
    la, lo = ref_lat + 90, ref_lon + 180
    for r in (20.0, 1.0, 0.05, 0.0025):
        prefix += ALPHA[int(la // r) % 20] + ALPHA[int(lo // r) % 20]
        la %= r; lo %= r
    full = prefix[:pad] + short
    lat, lon = decode(full)
    half = area / 2
    if lat - ref_lat > half: lat -= area
    elif ref_lat - lat > half: lat += area
    if lon - ref_lon > half: lon -= area
    elif ref_lon - lon > half: lon += area
    return lat, lon


def norm(s):
    s = unicodedata.normalize("NFD", str(s or "").lower())
    return re.sub(r"[^a-z0-9 ]+", " ", "".join(c for c in s if unicodedata.category(c) != "Mn"))


STOP = {"posto", "monte", "carlo", "mc", "auto", "de", "do", "da", "ltda", "km", "br", "pista", "conveniencia"}


def read_rows(path):
    raw = open(path, "rb").read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    return list(csv.DictReader(io.StringIO(text), delimiter=";"))


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    apply = "--apply" in sys.argv
    rows = read_rows(sys.argv[1])
    with server.db() as con:
        sts = [dict(r) for r in con.execute("SELECT id,name,city,lat,lon,geo_quality FROM stations")]
        used = set()
        for r in rows:
            unit, pc = r["Unidade"].strip(), r["Plus Code"].strip()
            m = re.match(r"([23456789CFGHJMPQRVWX]{2,8}\+[23456789CFGHJMPQRVWX]{2,3})\b", pc, re.I)
            if not m:
                print(f"?? sem Plus Code: {unit}")
                continue
            code, place = m.group(1).upper(), norm(pc[m.end():])
            utoks = {t for t in norm(unit).split() if t not in STOP}
            best, score = None, 0
            for s in sts:
                if s["id"] in used or not s["lat"]:
                    continue
                city = norm(s["city"]).strip()
                sc = (3 if city and re.search(r"\b" + re.escape(city) + r"\b", place) else 0)
                stoks = set(norm(s["name"]).split())
                sc += sum(1 for a in utoks if any(a == b or (len(a) > 4 and difflib.SequenceMatcher(None, a, b).ratio() > .85) for b in stoks))
                if city and re.search(r"\b" + re.escape(city) + r"\b", norm(unit)):
                    sc += 1
                if sc > score:
                    best, score = s, sc
            if not best or score < 4:
                print(f"?? sem posto casado ({score}): {unit} [{code}]")
                continue
            lat, lon = recover(code, best["lat"], best["lon"]) if len(code.split("+")[0]) < 8 else decode(code)
            km = (((lat - best["lat"]) * 111) ** 2 + ((lon - best["lon"]) * 102) ** 2) ** .5
            flag = "  <-- CONFERIR (longe)" if km > 15 else ""
            print(f"{unit[:38]:38} -> #{best['id']} {best['name'][:34]:34} {lat:.5f},{lon:.5f} (move {km:.1f} km){flag}")
            used.add(best["id"])
            if apply and km <= 60:
                con.execute("UPDATE stations SET lat=?, lon=?, geo_quality='ok' WHERE id=?", (lat, lon, best["id"]))
    if not apply:
        print("\nNada gravado. Confira e rode de novo com --apply.")


if __name__ == "__main__":
    main()
