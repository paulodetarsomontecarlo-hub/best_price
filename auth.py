"""Autenticação de clientes: CPF/CNPJ + senha, sessões no SQLite.

Senhas guardadas só como hash (scrypt com salt). Sessões: o cookie leva um token aleatório
e o banco guarda apenas o hash dele.
"""
import hashlib
import hmac
import re
import secrets
import time
from datetime import datetime, timedelta, timezone

SESSION_DAYS = 30
MAX_FAILS, LOCK_SECONDS = 5, 15 * 60
MIN_PASSWORD = 6

AUTH_SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  doc TEXT NOT NULL UNIQUE,          -- CPF (11) ou CNPJ (14), só dígitos
  name TEXT NOT NULL DEFAULT '',
  pwd_hash TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  last_login TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  expires_at TEXT NOT NULL
);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------- documento
def digits(s):
    return re.sub(r"\D", "", str(s or ""))


def valid_doc(doc):
    d = digits(doc)
    if len(d) == 11:
        if d == d[0] * 11:
            return False
        for n in (9, 10):
            s = sum(int(d[i]) * (n + 1 - i) for i in range(n))
            if int(d[n]) != (s * 10 % 11) % 10:
                return False
        return True
    if len(d) == 14:
        if d == d[0] * 14:
            return False
        for n, w in ((12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]), (13, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])):
            s = sum(int(d[i]) * w[i] for i in range(n))
            r = s % 11
            if int(d[n]) != (0 if r < 2 else 11 - r):
                return False
        return True
    return False


def fmt_doc(d):
    d = digits(d)
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return d


# ---------- senha
def hash_password(pw):
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${h.hex()}"


def verify_password(pw, stored):
    try:
        _, salt, h = stored.split("$")
        calc = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(calc.hex(), h)
    except (ValueError, AttributeError):
        return False


_DUMMY = hash_password("x")  # evita revelar por tempo se o documento existe


def generate_password(n=8):
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"  # sem 0/O/1/l/I
    return "".join(secrets.choice(alphabet) for _ in range(n))


# ---------- clientes
def upsert_client(con, doc, name, password=None):
    """Cria ou atualiza. Devolve (id, criado). Senha só é alterada se informada."""
    doc = digits(doc)
    row = con.execute("SELECT id FROM clients WHERE doc=?", (doc,)).fetchone()
    if row:
        if name:
            con.execute("UPDATE clients SET name=? WHERE id=?", (name, row["id"]))
        if password:
            con.execute("UPDATE clients SET pwd_hash=? WHERE id=?", (hash_password(password), row["id"]))
        return row["id"], False
    if not password:
        raise ValueError("senha obrigatória para novo cliente")
    cur = con.execute("INSERT INTO clients (doc,name,pwd_hash,created_at) VALUES (?,?,?,?)",
                      (doc, name or "", hash_password(password), now()))
    return cur.lastrowid, True


# ---------- tentativas (em memória: limite por documento e por IP)
_fails = {}


def _key_state(key):
    n, first = _fails.get(key, (0, 0))
    if n and time.time() - first > LOCK_SECONDS:
        _fails.pop(key, None)
        return 0
    return n


def locked(doc, ip):
    return _key_state("d" + doc) >= MAX_FAILS or _key_state("i" + ip) >= MAX_FAILS * 4


def _fail(doc, ip):
    for k in ("d" + doc, "i" + ip):
        n, first = _fails.get(k, (0, time.time()))
        _fails[k] = (n + 1, first)


def login(con, doc, password, ip):
    """Devolve (token, nome) ou levanta ValueError com a mensagem para o usuário."""
    doc = digits(doc)
    if locked(doc, ip):
        raise ValueError("Muitas tentativas. Aguarde 15 minutos e tente de novo.")
    row = con.execute("SELECT * FROM clients WHERE doc=?", (doc,)).fetchone()
    ok = verify_password(password or "", row["pwd_hash"] if row else _DUMMY)
    if not (row and ok and row["active"]):
        _fail(doc, ip)
        raise ValueError("CPF/CNPJ ou senha incorretos.")
    _fails.pop("d" + doc, None)
    token = secrets.token_urlsafe(32)
    exp = (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds")
    con.execute("DELETE FROM sessions WHERE expires_at < ?", (now(),))
    con.execute("INSERT INTO sessions (token_hash,client_id,expires_at) VALUES (?,?,?)",
                (hashlib.sha256(token.encode()).hexdigest(), row["id"], exp))
    con.execute("UPDATE clients SET last_login=? WHERE id=?", (now(), row["id"]))
    return token, row["name"] or fmt_doc(doc)


def session_client(con, token):
    if not token:
        return None
    return con.execute(
        "SELECT c.id, c.name, c.doc FROM sessions s JOIN clients c ON c.id = s.client_id "
        "WHERE s.token_hash=? AND s.expires_at > ? AND c.active = 1",
        (hashlib.sha256(token.encode()).hexdigest(), now())).fetchone()


def logout(con, token):
    con.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256((token or "").encode()).hexdigest(),))
