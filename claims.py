"""\"Preço melhor?\": o cliente informa um preço mais barato que achou, anexa a nota fiscal
como evidência e a equipe tenta cobrir. Aqui ficam a validação, o armazenamento do anexo
(em disco, fora do banco) e as consultas."""
import os
import secrets
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", ROOT / "uploads"))
MAX_FILE = 8 * 1024 * 1024
MAX_PER_DAY = 10
MAX_AGE_DAYS = 30
STATUSES = ("pendente", "analise", "coberto", "recusado")
EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "application/pdf": ".pdf"}

CLAIMS_SCHEMA = """
CREATE TABLE IF NOT EXISTS price_claims (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  client_id INTEGER NOT NULL REFERENCES clients(id),
  station_id INTEGER REFERENCES stations(id),      -- posto da rede que o cliente quer que cubra
  product TEXT NOT NULL,
  price REAL NOT NULL,                             -- preço encontrado (R$/L)
  place_name TEXT NOT NULL,                        -- onde encontrou
  place_city TEXT DEFAULT '',
  purchased_on TEXT NOT NULL,                      -- data da nota fiscal
  liters REAL,
  comment TEXT DEFAULT '',
  file_name TEXT DEFAULT '',
  file_type TEXT DEFAULT '',
  status TEXT NOT NULL DEFAULT 'rascunho',         -- rascunho (sem anexo ainda) | pendente | analise | coberto | recusado
  admin_reply TEXT DEFAULT '',
  covered_price REAL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _num(v, field, lo, hi):
    try:
        x = float(str(v).replace(",", "."))
    except ValueError:
        raise ValueError(f"{field} inválido")
    if not lo <= x <= hi:
        raise ValueError(f"{field} fora do esperado")
    return x


def sniff(data):
    """Tipo real do arquivo pelos primeiros bytes (não confia no que o navegador diz)."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:5] == b"%PDF-":
        return "application/pdf"
    return ""


def create_claim(con, client_id, b, products):
    if b.get("product") not in products:
        raise ValueError("escolha o produto")
    price = _num(b.get("price"), "preço", 1, 30)
    place = " ".join(str(b.get("place_name") or "").split())[:80]
    if len(place) < 2:
        raise ValueError("informe onde você encontrou o preço")
    try:
        d = date.fromisoformat(str(b.get("purchased_on") or ""))
    except ValueError:
        raise ValueError("informe a data da nota fiscal")
    today = date.today()
    if d > today:
        raise ValueError("a data da nota não pode ser futura")
    if d < today - timedelta(days=MAX_AGE_DAYS):
        raise ValueError(f"só aceitamos notas dos últimos {MAX_AGE_DAYS} dias")
    sid = b.get("station_id")
    if sid not in (None, ""):
        sid = int(sid)
        if not con.execute("SELECT 1 FROM stations WHERE id=? AND active=1", (sid,)).fetchone():
            raise ValueError("posto da rede inválido")
    else:
        sid = None
    liters = _num(b["liters"], "litros", 1, 1_000_000) if b.get("liters") not in (None, "") else None
    n = con.execute("SELECT COUNT(*) c FROM price_claims WHERE client_id=? AND created_at >= ?",
                    (client_id, (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds"))).fetchone()["c"]
    if n >= MAX_PER_DAY:
        raise ValueError("limite de envios por dia atingido; tente amanhã")
    ts = _now()
    cur = con.execute(
        "INSERT INTO price_claims (client_id,station_id,product,price,place_name,place_city,purchased_on,liters,comment,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (client_id, sid, b["product"], price, place, " ".join(str(b.get("place_city") or "").split())[:60],
         d.isoformat(), liters, str(b.get("comment") or "").strip()[:500], ts, ts))
    return cur.lastrowid


def save_file(con, client_id, claim_id, data, ctype):
    row = con.execute("SELECT * FROM price_claims WHERE id=? AND client_id=?", (claim_id, client_id)).fetchone()
    if not row:
        raise ValueError("solicitação não encontrada")
    if row["status"] not in ("rascunho", "pendente"):
        raise ValueError("esta solicitação já está em análise")
    if not data or len(data) > MAX_FILE:
        raise ValueError(f"arquivo vazio ou maior que {MAX_FILE // 1024 // 1024} MB")
    real = sniff(data)
    if not real or (ctype and ctype != real):
        raise ValueError("envie uma foto (JPG, PNG, WEBP) ou PDF da nota fiscal")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    name = secrets.token_hex(16) + EXT[real]
    (UPLOAD_DIR / name).write_bytes(data)
    if row["file_name"]:
        (UPLOAD_DIR / row["file_name"]).unlink(missing_ok=True)
    con.execute("UPDATE price_claims SET file_name=?, file_type=?, status='pendente', updated_at=? WHERE id=?",
                (name, real, _now(), claim_id))


def list_claims(con, client_id=None):
    where, args = ("WHERE c.status != 'rascunho'", [])
    if client_id is not None:
        where, args = "WHERE c.client_id = ? AND c.status != 'rascunho'", [client_id]
    rows = con.execute(
        "SELECT c.id,c.product,c.price,c.place_name,c.place_city,c.purchased_on,c.liters,c.comment,c.status,"
        "c.admin_reply,c.covered_price,c.created_at,c.updated_at,c.station_id,"
        "s.name AS station_name,s.city AS station_city, cl.name AS client_name, cl.doc AS client_doc "
        "FROM price_claims c LEFT JOIN stations s ON s.id=c.station_id JOIN clients cl ON cl.id=c.client_id "
        f"{where} ORDER BY CASE c.status WHEN 'pendente' THEN 0 WHEN 'analise' THEN 1 ELSE 2 END, c.id DESC", args)
    return [dict(r) for r in rows]


def file_for(con, claim_id, client_id=None):
    sql, args = "SELECT file_name,file_type FROM price_claims WHERE id=? AND file_name != ''", [claim_id]
    if client_id is not None:
        sql, args = sql + " AND client_id=?", args + [client_id]
    row = con.execute(sql, args).fetchone()
    if not row:
        raise ValueError("anexo não encontrado")
    path = UPLOAD_DIR / row["file_name"]
    if not path.is_file():
        raise ValueError("anexo não encontrado")
    return path, row["file_type"]


def update_claim(con, claim_id, b):
    """Admin: status, resposta ao cliente e (opcional) preço coberto + aplicar no posto."""
    row = con.execute("SELECT * FROM price_claims WHERE id=?", (claim_id,)).fetchone()
    if not row:
        raise ValueError("solicitação não encontrada")
    status = b.get("status", row["status"])
    if status not in STATUSES:
        raise ValueError("status inválido")
    covered = row["covered_price"]
    if "covered_price" in b:
        covered = _num(b["covered_price"], "preço coberto", 1, 30) if b["covered_price"] not in (None, "") else None
    if status == "coberto" and covered is None:
        raise ValueError("informe o preço coberto")
    reply = str(b.get("admin_reply", row["admin_reply"]) or "").strip()[:500]
    con.execute("UPDATE price_claims SET status=?, admin_reply=?, covered_price=?, updated_at=? WHERE id=?",
                (status, reply, covered, _now(), claim_id))
    applied = False
    if b.get("apply_price") and status == "coberto" and row["station_id"]:
        ts = _now()
        con.execute(
            "INSERT INTO prices (station_id,product,price,updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(station_id,product) DO UPDATE SET price=excluded.price, updated_at=excluded.updated_at",
            (row["station_id"], row["product"], covered, ts))
        con.execute("INSERT INTO price_history (station_id,product,price,changed_at) VALUES (?,?,?,?)",
                    (row["station_id"], row["product"], covered, ts))
        applied = True
    return {"ok": True, "applied": applied}
