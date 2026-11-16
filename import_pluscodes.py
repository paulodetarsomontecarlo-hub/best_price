#!/usr/bin/env python3
"""Importa postos a partir de Plus Codes do Google Maps.

Uso: python3 import_pluscodes.py postos.txt [--replace]

Uma linha por posto, campos separados por ';' (só o primeiro é obrigatório):

    33R4+XR Margem Esquerda, Gaspar - Santa Catarina ; Posto Exemplo ; Ipiranga ; BR-470

  1. Plus Code como o Google Maps mostra (curto + localidade, ou completo, ex.: 58GR33R4+XR)
  2. nome do posto (padrão: "Posto <bairro>, <cidade>")
  3. bandeira   4. rodovia   (opcionais)

Plus Code curto precisa da cidade para ser completado: ela é localizada pelo Nominatim
(OpenStreetMap, ~1 consulta/s) e o código é resolvido para a posição mais próxima.
Posto com o mesmo nome é atualizado (coordenadas); senão é criado.
--replace desativa (não apaga) os postos que não estão no arquivo. Linhas com # são ignoradas.
"""
import re
import sys

import geocode
import import_kml
import olc
import server

CODE = re.compile(r"^\s*([23456789CFGHJMPQRVWX]{2,8}\+[23456789CFGHJMPQRVWX]*)\s*(.*)$", re.I)
UF = {"acre": "AC", "alagoas": "AL", "amapá": "AP", "amazonas": "AM", "bahia": "BA", "ceará": "CE",
      "distrito federal": "DF", "espírito santo": "ES", "goiás": "GO", "maranhão": "MA",
      "mato grosso": "MT", "mato grosso do sul": "MS", "minas gerais": "MG", "pará": "PA",
      "paraíba": "PB", "paraná": "PR", "pernambuco": "PE", "piauí": "PI", "rio de janeiro": "RJ",
      "rio grande do norte": "RN", "rio grande do sul": "RS", "rondônia": "RO", "roraima": "RR",
      "santa catarina": "SC", "são paulo": "SP", "sergipe": "SE", "tocantins": "TO"}


def parse_locality(text):
    """'Margem Esquerda, Gaspar - Santa Catarina' -> (bairro, cidade, estado)"""
    text = text.strip().strip(",")
    state = ""
    m = re.search(r"\s[-–]\s([^-–,]+)$", text)
    if m:
        state, text = m.group(1).strip(), text[:m.start()].strip()
    parts = [p.strip() for p in text.split(",") if p.strip()]
    city = parts[-1] if parts else ""
    hood = ", ".join(parts[:-1])
    return hood, city, state


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    replace = "--replace" in sys.argv
    server.init_db()
    refs, seen, added, updated, failed = {}, set(), 0, 0, []
    with server.db() as con:
        for n, line in enumerate(open(args[0], encoding="utf-8-sig"), 1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            f = [x.strip() for x in line.split(";")]
            m = CODE.match(f[0])
            if not m:
                failed.append((n, "Plus Code não reconhecido", f[0]))
                continue
            code, locality = m.group(1).upper(), m.group(2)
            hood, city, state = parse_locality(locality)
            try:
                if olc.is_short(code):
                    if not city:
                        raise ValueError("código curto sem cidade")
                    key = (city, state)
                    if key not in refs:
                        refs[key] = geocode.q(f"{city}, {state}, Brasil" if state else f"{city}, Brasil")
                    if not refs[key]:
                        raise ValueError(f"cidade não encontrada: {city}")
                    lat, lon = olc.recover(code, *refs[key])
                else:
                    lat, lon = olc.decode(code)
            except Exception as e:
                failed.append((n, str(e), f[0]))
                continue
            name = f[1] if len(f) > 1 and f[1] else f"Posto {hood + ', ' if hood else ''}{city}"
            brand = f[2] if len(f) > 2 else ""
            hw = f[3] if len(f) > 3 else ""
            uf = UF.get(state.lower(), state[:2].upper())
            ex = con.execute("SELECT id FROM stations WHERE lower(name)=lower(?) AND active=1", (name,)).fetchone()
            if ex:
                con.execute("UPDATE stations SET lat=?,lon=?,geo_quality='pluscode',"
                            "city=COALESCE(NULLIF(?,''),city),uf=COALESCE(NULLIF(?,''),uf),"
                            "brand=COALESCE(NULLIF(?,''),brand),highway=COALESCE(NULLIF(?,''),highway),"
                            "address=? WHERE id=?", (lat, lon, city, uf, brand, hw, f[0], ex["id"]))
                sid = ex["id"]
                updated += 1
            else:
                sid = con.execute("INSERT INTO stations (name,brand,city,uf,highway,lat,lon,address,geo_quality) "
                                  "VALUES (?,?,?,?,?,?,?,?,'pluscode')",
                                  (name, brand, city, uf, hw, lat, lon, f[0])).lastrowid
                added += 1
            seen.add(sid)
            print(f"{name}: {lat:.6f}, {lon:.6f}  https://maps.google.com/?q={lat:.6f},{lon:.6f}")
        removed = 0
        if replace and seen:
            ids = ",".join(str(i) for i in seen)
            removed = con.execute(f"UPDATE stations SET active=0 WHERE active=1 AND id NOT IN ({ids})").rowcount
        import_kml.build_routes(con)
    print(f"\n{added} criado(s), {updated} atualizado(s), {removed} desativado(s), {len(failed)} com erro.")
    for n, why, txt in failed:
        print(f"  linha {n}: {why} -> {txt}")


if __name__ == "__main__":
    main()
