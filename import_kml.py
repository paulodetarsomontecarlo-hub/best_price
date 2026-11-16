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
            row = (d.get("BANDEIRA", ""), city(d.get("CIDADE", "")), d.get("ESTADO", ""),
                   lat, lon, addr, d.get("CATEGORIA", "").title())
            ex = con.execute("SELECT id FROM stations WHERE name=? AND address=?", (name, addr)).fetchone()
            if ex:
                updated += 1  # não sobrescreve coordenadas já corrigidas
            else:
                con.execute("INSERT INTO stations (name,brand,city,uf,lat,lon,address,category,highway,geo_quality) "
                            "VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (name,) + row + (rodovia(addr), 'kml' if lat is not None else ''))
                added += 1
        routes = build_routes(con)
    print(f"{routes} rota(s) por rodovia criada(s)/atualizada(s)")
    print(f"{added} novo(s), {updated} já existente(s); {nocoord} sem coordenadas (use geocode.py).")


import unicodedata

CITIES = {  # nome sem acento/maiúsculo -> grafia correta
    "S J RIO PRETO": "São José do Rio Preto", "SAO JOSE DO RIO PRETO": "São José do Rio Preto",
    "MARILIA": "Marília", "ORLANDIA": "Orlândia", "OLIMPIA": "Olímpia", "URANIA": "Urânia",
    "GALIA": "Gália", "GUARA": "Guará", "JUNDIAI": "Jundiaí", "PARANAGUA": "Paranaguá",
    "CANDIDO MOTA": "Cândido Mota", "RUBINEIA": "Rubinéia", "SANTA FE DO SUL": "Santa Fé do Sul",
    "BALSAMO": "Bálsamo", "SANTOPOLIS DO AGUAPEI": "Santópolis do Aguapeí",
    "CAMPINA GRANDE DO SUL": "Campina Grande do Sul", "RIBEIRAO PRETO": "Ribeirão Preto",
    "ARACARIGUAMA": "Araçariguama", "PARIQUERA-ACU": "Pariquera-Açu", "SAO CARLOS": "São Carlos",
}
SMALL = {"Do", "Da", "De", "Dos", "Das"}


def city(name):
    key = "".join(c for c in unicodedata.normalize("NFD", name.upper()) if unicodedata.category(c) != "Mn").strip()
    if key in CITIES:
        return CITIES[key]
    return " ".join(w if w not in SMALL else w.lower() for w in name.title().split())


# palavra no endereço -> nome da rodovia
HIGHWAYS = [
    (r"EUCLIDES DA CUNHA", "SP-320 Euclides da Cunha"), (r"BR[ -]?153", "BR-153"),
    (r"ANHANGUERA", "SP-330 Anhanguera"), (r"BANDEIRANTES", "SP-348 Bandeirantes"),
    (r"CASTELO BRANCO", "SP-280 Castelo Branco"), (r"FERNAO DIAS", "BR-381 Fernão Dias"),
    (r"DUTRA", "BR-116 Dutra"), (r"REGIS BIT+ENCOURT", "BR-116 Régis Bittencourt"),
    (r"RAPOSO TAVARES", "SP-270 Raposo Tavares"), (r"ASSIS CHATE", "SP-425 Assis Chateaubriand"),
    (r"WASHINGTON LUIZ", "SP-310 Washington Luís"), (r"BR[ -]?376", "BR-376"),
    (r"BR[ -]?116", "BR-116 Sul (PR)"), (r"BR[ -]?470", "BR-470"),
]


def rodovia(addr):
    a = unicodedata.normalize("NFD", addr.upper())
    a = "".join(c for c in a if unicodedata.category(c) != "Mn")
    for pat, name in HIGHWAYS:
        if re.search(pat, a):
            return name
    return ""


def build_routes(con):
    """Uma rota por rodovia com 2+ postos mapeados, ordenados ao longo do percurso."""
    rows = con.execute("SELECT id,highway,lat,lon FROM stations WHERE active=1 AND highway!='' "
                       "AND lat IS NOT NULL").fetchall()
    groups = {}
    for r in rows:
        groups.setdefault(r["highway"], []).append(r)
    n = 0
    for hw, g in sorted(groups.items()):
        if len(g) < 2:
            continue
        lons, lats = [x["lon"] for x in g], [x["lat"] for x in g]
        key = (lambda x: x["lon"]) if max(lons) - min(lons) >= max(lats) - min(lats) else (lambda x: x["lat"])
        g.sort(key=key)
        name = f"Rodovia {hw}"
        ex = con.execute("SELECT id FROM routes WHERE name=?", (name,)).fetchone()
        rid = ex["id"] if ex else con.execute("INSERT INTO routes (name,highway) VALUES (?,?)", (name, hw)).lastrowid
        con.execute("DELETE FROM route_stations WHERE route_id=?", (rid,))
        for i, x in enumerate(g):
            con.execute("INSERT INTO route_stations (route_id,station_id,position) VALUES (?,?,?)", (rid, x["id"], i))
        n += 1
    return n


if __name__ == "__main__":
    main()
