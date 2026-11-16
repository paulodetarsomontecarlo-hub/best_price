#!/usr/bin/env python3
"""Importa clientes (login do app) de um CSV.

Uso: python import_clients.py clientes.csv

Colunas aceitas (qualquer ordem, maiúsculas/minúsculas e acentos não importam):
  documento | cpf | cnpj | cpf_cnpj | cnpj_cpf   (obrigatória)
  nome | razao social | cliente                   (opcional)
  senha                                           (opcional: vazia = senha gerada)

- Separador `,` ou `;` e codificação UTF-8 ou Excel (cp1252) são detectados sozinhos.
- Documento inválido (dígito verificador) é listado e ignorado; nada é gravado para ele.
- Cliente já cadastrado: atualiza o nome; a senha só muda se a coluna `senha` vier preenchida.
- Senhas geradas dos clientes NOVOS vão para `clientes_senhas_AAAAMMDD-HHMMSS.csv`
  (arquivo ignorado pelo git). Envie aos clientes e apague o arquivo.
"""
import csv
import io
import sys
import unicodedata
from datetime import datetime

import auth
import server

DOC_COLS = {"documento", "doc", "cpf", "cnpj", "cpf_cnpj", "cnpj_cpf", "cpf/cnpj", "cnpj/cpf", "cpfcnpj"}
NAME_COLS = {"nome", "razao social", "razao_social", "cliente", "nome cliente", "nome/razao social"}
PW_COLS = {"senha", "password"}


def norm(s):
    s = unicodedata.normalize("NFD", str(s or "").strip().lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def read_rows(path):
    raw = open(path, "rb").read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    delim = ";" if text.splitlines()[0].count(";") > text.splitlines()[0].count(",") else ","
    return list(csv.DictReader(io.StringIO(text), delimiter=delim))


def pick(row, names):
    for k, v in row.items():
        if norm(k) in names and str(v or "").strip():
            return str(v).strip()
    return ""


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    rows = read_rows(sys.argv[1])
    server.init_db()
    created, updated, bad, issued = 0, 0, [], []
    with server.db() as con:
        for n, row in enumerate(rows, start=2):  # linha 1 = cabeçalho
            doc, name, pw = pick(row, DOC_COLS), pick(row, NAME_COLS), pick(row, PW_COLS)
            if not auth.valid_doc(doc):
                bad.append((n, doc or "(vazio)", name))
                continue
            if pw and len(pw) < auth.MIN_PASSWORD:
                bad.append((n, doc, f"{name} — senha curta (mín. {auth.MIN_PASSWORD})"))
                continue
            exists = con.execute("SELECT 1 FROM clients WHERE doc=?", (auth.digits(doc),)).fetchone()
            generated = "" if (pw or exists) else auth.generate_password()
            _, is_new = auth.upsert_client(con, doc, name, pw or generated or None)
            if is_new:
                created += 1
                issued.append((auth.fmt_doc(doc), name, pw or generated))
            else:
                updated += 1
    print(f"{created} cliente(s) novo(s), {updated} atualizado(s), {len(bad)} ignorado(s).")
    for n, doc, name in bad:
        print(f"  linha {n}: documento inválido ou dados incorretos: {doc} {name}")
    if issued:
        out = f"clientes_senhas_{datetime.now():%Y%m%d-%H%M%S}.csv"
        with open(out, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["documento", "nome", "senha"])
            w.writerows(issued)
        print(f"Senhas dos novos clientes em {out} (envie aos clientes e apague o arquivo).")


if __name__ == "__main__":
    main()
