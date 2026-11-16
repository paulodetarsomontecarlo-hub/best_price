"""Plus Codes (Open Location Code), só biblioteca padrão.

decode("849VCWC8+R9")                       -> (lat, lon) do centro
recover("CWC8+R9", ref_lat, ref_lon)        -> código curto + posição de referência -> (lat, lon)
"""
ALPHABET = "23456789CFGHJMPQRVWX"
SEP, SEP_POS = "+", 8
_PAIR_RES = [20.0, 1.0, 0.05, 0.0025, 0.000125]


def is_valid(code):
    code = code.upper()
    if code.count(SEP) != 1 or code.index(SEP) % 2 or code.index(SEP) > SEP_POS:
        return False
    digits = code.replace(SEP, "").rstrip("0")
    return len(digits) >= 2 and all(c in ALPHABET for c in digits) and len(code) - code.index(SEP) - 1 != 1


def is_short(code):
    return is_valid(code) and code.index(SEP) < SEP_POS


def _decode_full(code):
    digits = code.upper().replace(SEP, "").rstrip("0")
    lat, lon = -90.0, -180.0
    res = _PAIR_RES[0]
    for i, ch in enumerate(digits[:10]):
        v = ALPHABET.index(ch)
        res = _PAIR_RES[i // 2]
        if i % 2 == 0:
            lat += v * res
        else:
            lon += v * res
    lat_res = lon_res = res
    for ch in digits[10:15]:  # refinamento em grade (5x4)
        v = ALPHABET.index(ch)
        lat_res /= 5
        lon_res /= 4
        lat += (v // 4) * lat_res
        lon += (v % 4) * lon_res
    return lat + lat_res / 2, lon + lon_res / 2


def encode_prefix(lat, lon, n=10):
    lat = min(max(lat, -90), 90 - 1e-9) + 90
    lon = (lon + 180) % 360
    out = ""
    for res in _PAIR_RES[: n // 2]:
        d = int(lat // res)
        lat -= d * res
        out += ALPHABET[d]
        d = int(lon // res)
        lon -= d * res
        out += ALPHABET[d]
    return out


def decode(code):
    if not is_valid(code) or is_short(code):
        raise ValueError(f"Plus Code completo inválido: {code}")
    return _decode_full(code)


def recover(code, ref_lat, ref_lon):
    """Completa um código curto usando a posição de referência (a mais próxima)."""
    code = code.upper()
    if not is_valid(code):
        raise ValueError(f"Plus Code inválido: {code}")
    if not is_short(code):
        return decode(code)
    pad = SEP_POS - code.index(SEP)
    res = 20 ** (2 - pad / 2)
    prefix = encode_prefix(ref_lat, ref_lon)[:pad]
    full = prefix + code
    lat, lon = _decode_full(full[:SEP_POS] + SEP + full[SEP_POS + 1:])
    if ref_lat + res / 2 < lat and lat - res >= -90:
        lat -= res
    elif ref_lat - res / 2 > lat and lat + res <= 90:
        lat += res
    if ref_lon + res / 2 < lon:
        lon -= res
    elif ref_lon - res / 2 > lon:
        lon += res
    return lat, lon
