# Pin Verde — contexto para o Claude

> Nome do produto: **Pin Verde**. O repositório e o arquivo de banco ainda se chamam est_price / est_price.db (nomes técnicos, não visíveis ao cliente).

Web app responsivo (mobile first) que mostra preços de **DIESEL S-10, DIESEL S-500 e ARLA** nos postos da rede
Monte Carlo para um **grupo piloto de clientes**. Idioma do produto e do usuário: português do Brasil.
Repositório: `paulodetarsomontecarlo-hub/best_price` (não usar o `fuel-prices/` nem o repo scraper-kit).

## Stack e execução
- Python 3 **só stdlib** (`http.server`, `sqlite3`, `hashlib.scrypt`, `urllib`); front vanilla JS + Leaflet 1.9.4 (unpkg), **sem build**.
- Rodar: `$env:ADMIN_TOKEN="bestprice-admin"; $env:PORT="8000"; python server.py` → http://localhost:8000
- Env: `PORT`, `DB_PATH`, `ADMIN_TOKEN`, `COOKIE_SECURE=1`, `UPLOAD_DIR`, `WHATSAPP_NUMBER` (DDI+DDD, só dígitos; sem ele o front usa o mock 5511999999999), `NOMINATIM_URL`, `OSRM_URL`.
- Ambiente do dono: Windows 11 + PowerShell, Python 3.14, Edge (sem node). Checar sintaxe do JS: `new Function(...)` numa página aberta com `msedge --headless --dump-dom`.
- Cuidado ao editar com PowerShell: arquivos podem ser CRLF; use caminhos absolutos em `[IO.File]`; `Get-Content/Set-Content` sem `-Encoding utf8` corrompe acentos.

## Arquivos
- `server.py` — API + estáticos + schema SQLite (stations, prices, price_history, routes, route_stations). `load_seed()` carrega `data/seed.json` em banco vazio.
- `auth.py` — CPF/CNPJ + senha (scrypt), sessões no banco, cookie `bp_session` HttpOnly, bloqueio 5 falhas/15 min.
- `claims.py` — "Preço melhor?": cliente informa preço + anexa nota fiscal; admin analisa (pendente/analise/coberto/recusado) e pode aplicar o preço no posto.
- `planner.py` — roteirizador: Nominatim (geocode, 1 req/s) + OSRM público; postos a ≤ N km da rota.
- `static/` — `index.html`, `app.js`, `style.css`, `login.html`, `admin.html`.
- olc.py — decodificador Open Location Code (usado pelo importador genérico).
- Documentação: README.md (visão geral), docs/API.md, docs/OPERACAO.md, docs/ARQUITETURA.md, docs/POSTOS.md (lista dos 36 postos), CHANGELOG.md. **Atualize-os junto com qualquer mudança de comportamento.**
- Importadores/scripts: `rebuild_from_pluscodes.py` (**fonte da verdade dos postos**), `check_pluscodes.py` (decoder de Plus Code), `import_clients.py` (clientes via CSV), `import_kml.py`, `import_stations.py`, `geocode.py` (legados).

## Dados dos postos
- **Base oficial = `pluscode unidades.csv`** (Unidade;Bandeira;Plus Code; cp1252). `python rebuild_from_pluscodes.py "<csv>"` apaga postos/preços/rotas e recria tudo, regrava `data/seed.json`, gera preços mock e recria rotas por rodovia (a rodovia é herdada do posto antigo equivalente; novos ficam sem rodovia).
- Hoje: 36 postos, todos `geo_quality='ok'`. Preços são **MOCK** (S-10 6,39–6,79; S-500 6,09–6,29; ARLA 3,20–3,90 assumido) — trocar antes do piloto.

## API
Todas as GET `/api/*` exigem sessão (ou header `X-Admin-Token`), senão 401 → front redireciona a `/login.html`.
GET `/api/stations` `/api/routes` `/api/config` `/api/me` `/api/geocode?q=` `/api/plan?from=lat,lon&to=lat,lon&radius=` `/api/claims`; PUT `/api/claims/<id>/file` (binário cru); POST `/api/login` `/api/logout`; admin em `/api/admin/{stations,prices,routes,clients,claims}`.

## Front (static/app.js)
- Marcadores Leaflet em 3 modos por zoom: pin (`dot`), chip de preço (zoom ≥ 8), cartão nome+preço (zoom ≥ 10), com anti-colisão; cor por tercil (verde barato / laranja / vermelho / cinza sem preço).
- Base de mapa em camadas (Leaflet panes): fundo **Esri World Light Gray Base** (cinza, sem nomes) < pane `rota` (z 350: linha do roteirizador em roxo `#711CD4` com contorno branco) < pane `nomes` (z 450: **Esri Light Gray Reference**, nomes de cidades/rodovias, por cima da rota) < pins. Tiles OSM têm o nome embutido (não dá para pôr o nome acima da rota) e o CARTO exige chave ("API KEY REQUIRED"). Rodovias ficam finas nesse fundo; um provedor com chave (Stadia/MapTiler) as destaca melhor.
- Canto inferior direito: cartões "Melhor Diesel S-10 / S-500" (rede toda, ou só a rota traçada) + botões **💬 Ajuda** (wa.me) e **📎 Anexar nota** (abre aba "Preço melhor?"). Clique no posto abre Waze.
- Menu lateral: Roteirizador, Rotas (preço médio / melhor por rota), Preço melhor?.

## Conta de teste e pendências antes do piloto
- Admin token local: `bestprice-admin`. Cliente teste CPF 529.982.247-25 / `teste123` → **desativar**.
- Falta: telefone real do WhatsApp; base de clientes (`python import_clients.py clientes.csv`, senhas geradas vão para `clientes_senhas_*.csv`, ignorado pelo git); trocar preços mock; rodovia dos 4 postos novos (Corumbataí, Uberlândia, Várzea Grande, Mirassol KM 446); sem "esqueci a senha"; autenticidade da nota não é verificada (ideia: chave NF-e).

## Convenções
- Commits terminam com `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Branch de trabalho: `claude/trusting-bardeen-5gmp50`.
- Não commitar: `*.db`, `uploads/`, `.env`, `clientes*.csv`.

## Painel admin (`/admin.html`, pede ADMIN_TOKEN)
Seções: Preço melhor? (pedidos, ver nota, responder, coberto + aplicar preço) · Clientes (criar, redefinir senha, desativar) · Preços por posto · Novo posto · Rotas (nome, rodovia, ordem dos postos).

## Armadilhas já encontradas (não repetir)
- **Tiles**: CARTO deu "API KEY REQUIRED"; Esri/cinza ficou feio. Usar OSM padrão (mostra rodovias).
- **Chave `}` faltando** em `icon()` deixa o mapa em branco → sempre validar o JS (`new Function` via Edge headless) e tirar screenshot depois de editar `app.js`.
- **PowerShell**: `Set-Content`/`Get-Content` sem `-Encoding utf8` corrompe acentos (mojibake); `\n` em string de aspas simples é literal — use here-string ou a ferramenta Edit. Normalizar CRLF/LF antes de `.Replace`.
- **Duas sessões do Claude** já trabalharam na mesma branch (conflito em `import_pluscodes.py`). Faça `git fetch` e confira `origin` antes de dar push.
- Casamento automático posto-antigo→planilha pode herdar rodovia errada (ex.: Santópolis → SP-425); revisar no admin.
- CSV da planilha de unidades está em **cp1252**; leia com fallback.
- Mirassol KM 446 cai em São José do Rio Preto pelo Plus Code (cidade exibida = Rio Preto).

## Como verificar mudanças
1. Reiniciar: parar o `python server.py` antigo e subir de novo (env acima).
2. `Invoke-WebRequest http://localhost:8000/login.html` → 200; `/api/stations` sem login → 401.
3. Visual: `msedge --headless --screenshot=...` na página (login necessário para o mapa; usar o cliente de teste).
4. Sem testes automatizados no repo.

## Decisões do dono (preferências)
- Português do Brasil em tudo; produto chamado **Pin Verde**.
- Preferência por pins "chamativos, interativos e comerciais"; mapa colorido com rodovias.
- Cadastros de clientes feitos pela própria equipe (sem auto-cadastro); depois chega uma base com todos.
- "Preço melhor?": cliente anexa nota fiscal e a equipe tenta cobrir.
- Planilha de Plus Codes é a única fonte dos postos; tudo que existia antes foi descartado.
- Quer tudo documentado no GitHub e neste arquivo.