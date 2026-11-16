#!/usr/bin/env python3
"""Importa postos de um KML/KMZ do Google Maps / My Maps.

Uso: python3 import_kml.py Mapa_Postos.kmz

Lê as pastas que trazem dados de unidade (BANDEIRA, CATEGORIA, ENDEREÇO, CIDADE,
ESTADO no ExtendedData). Linhas de rota ("Directions...") e camadas vazias são ignoradas.
Postos sem coordenadas no arquivo entram sem lat/lon: rode geocode.py para completá-los.
Só importa o necessário (nome, bandeira, categoria, endereço, cidade, UF, coordenadas):
CNPJ, IE, e-mail e gerente NÃO são gravados.
Reexecutar não duplica: o posto é identificado pelo nome + endereço.
"""
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

import server

K = "{http://www.opengis.net/kml/2.2}"


def load(path):
    if path.lower().endswith(".kmz"):
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.lower().endswith(".kml"))
            return ET.fromstring(z.read(name))
    return ET.parse(path).getroot()


def extended(pm):
    return {d.get("name"): (d.findtext(K + "value") or "").strip() for d in pm.iter(K + "Data")}


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    root = load(sys.argv[1])
    server.init_db()
    added = updated = nocoord = 0
    with server.db() as con:
        for pm in root.iter(K + "Placemark"):
            d = extended(pm)
            if "BANDEIRA" not in d and "ENDEREÇO" not in d:
                continue
            name = (pm.findtext(K + "name") or "").strip()
            if not name:
                continue
            lat = lon = None
            c = pm.findtext(f"{K}Point/{K}coordinates")
            if c:
                x, y = c.strip().split(",")[:2]
                lon, lat = float(x), float(y)
            else:
                nocoord += 1
            addr = d.get("ENDEREÇO", "")
            row = (d.get("BANDEIRA", ""), d.get("CIDADE", "").title(), d.get("ESTADO", ""),
                   lat, lon, addr, d.get("CATEGORIA", "").title())
            ex = con.execute("SELECT id FROM stations WHERE name=? AND address=?", (name, addr)).fetchone()
            if ex:
                if lat is not None:
                    con.execute("UPDATE stations SET lat=?, lon=? WHERE id=?", (lat, lon, ex["id"]))
                updated += 1
            else:
                con.execute("INSERT INTO stations (name,brand,city,uf,lat,lon,address,category,highway) "
                            "VALUES (?,?,?,?,?,?,?,?,?)",
                            (name,) + row + (rodovia(addr),))
                added += 1
    print(f"{added} novo(s), {updated} já existente(s); {nocoord} sem coordenadas (use geocode.py).")


def rodovia(addr):
    m = re.search(r"\b(BR|SP|PR|SC|MS)[ -]?(\d{2,3})\b", addr.upper())
    return f"{m.group(1)}-{m.group(2)}" if m else ""


if __name__ == "__main__":
    main()
