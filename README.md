# Pin Verde

Aplicação web responsiva (mobile first) que mostra, num mapa, os **preços de Diesel S-10, Diesel S-500 e Arla**
nos postos da rede Monte Carlo. Feita para um **grupo piloto de clientes**: acesso por CPF/CNPJ + senha,
roteirizador, melhor preço por trecho e um canal para o cliente enviar uma nota fiscal de um preço melhor
encontrado ("a gente tenta cobrir").

> Stack enxuta de propósito: **Python 3 (só biblioteca padrão) + SQLite + Leaflet**, sem build e sem dependências para instalar.

## Sumário
- [Funcionalidades](#funcionalidades) · [Início rápido](#início-rápido) · [Configuração](#configuração)
- [Dados dos postos](#dados-dos-postos) · [Clientes e login](#clientes-e-login) · [Preços](#preços)
- [Preço melhor? (nota fiscal)](#preço-melhor-nota-fiscal) · [Roteirizador](#roteirizador) · [Ajuda via WhatsApp](#ajuda-via-whatsapp)
- [Estrutura do repositório](#estrutura-do-repositório) · [Modelo de dados](#modelo-de-dados)
- [Segurança e LGPD](#segurança-e-lgpd) · [Publicação](#publicação) · [Limitações e roadmap](#limitações-e-roadmap)
- Documentação detalhada: [docs/API.md](docs/API.md) · [docs/OPERACAO.md](docs/OPERACAO.md) · [docs/ARQUITETURA.md](docs/ARQUITETURA.md) · [docs/POSTOS.md](docs/POSTOS.md) · [CHANGELOG.md](CHANGELOG.md) · [CLAUDE.md](CLAUDE.md)

## Funcionalidades

| Para o cliente | Para a equipe (admin) |
|---|---|
| Login com CPF/CNPJ + senha | Cadastro de clientes (ou importação por CSV) |
| Mapa com rodovias; pins → preço → nome do posto conforme o zoom | Cadastro/edição de postos, preços e rotas |
| Cores por faixa: verde (mais barato), laranja, vermelho (mais caro), cinza (sem preço) | Fila de pedidos "Preço melhor?" com visualização da nota fiscal |
| Filtro por produto (S-10, S-500, Arla) | Responder o cliente, marcar *coberto* e já aplicar o preço no posto |
| Cartões "Melhor Diesel S-10 / S-500" (rede toda ou só o trajeto) | Histórico de preços (`price_history`) |
| Preço médio e melhor preço por rodovia | |
| Roteirizador: cidade de origem → destino, mostra os postos no caminho | |
| Toque no posto → **Abrir no Waze** | |
| Botões **Ajuda** (WhatsApp) e **Anexar nota** | |

## Início rápido

Requisitos: Python 3.9+ (testado no 3.14). Nada a instalar.

```powershell
# Windows (PowerShell)
$env:ADMIN_TOKEN = "troque-isto"
python server.py            # http://localhost:8000
```
```bash
# Linux/macOS
ADMIN_TOKEN=troque-isto python3 server.py
```

1. O primeiro start cria o banco (`best_price.db`) e carrega os postos de `data/seed.json`.
2. Abra `http://localhost:8000/admin.html`, informe o `ADMIN_TOKEN` e **crie um cliente** (CPF/CNPJ válido + senha).
3. Entre em `http://localhost:8000` com esse CPF/CNPJ e senha.

> Os preços que acompanham o repositório são **fictícios (mock)**, só para demonstração. Veja [Preços](#preços).

## Configuração

Tudo por variáveis de ambiente (nenhuma é obrigatória, exceto `ADMIN_TOKEN` em produção):

| Variável | Padrão | Função |
|---|---|---|
| `PORT` | `8000` | Porta HTTP |
| `DB_PATH` | `best_price.db` | Arquivo SQLite |
| `ADMIN_TOKEN` | *(vazio = admin desabilitado)* | Senha do painel `/admin.html` e do header `X-Admin-Token` |
| `COOKIE_SECURE` | `0` | `1` marca o cookie de sessão como `Secure` (use atrás de HTTPS) |
| `UPLOAD_DIR` | `uploads/` | Onde ficam as notas fiscais anexadas |
| `WHATSAPP_NUMBER` | mock `5511999999999` no front | Telefone do botão Ajuda (DDI+DDD+número, só dígitos) |
| `NOMINATIM_URL` | `https://nominatim.openstreetmap.org` | Geocodificador do roteirizador |
| `OSRM_URL` | `https://router.project-osrm.org` | Motor de rotas do roteirizador |

## Dados dos postos

A **fonte oficial** dos postos é a planilha `pluscode unidades.csv` (colunas `Unidade;Bandeira;Plus Code`, codificação Windows-1252).
Cada Plus Code (Open Location Code) é decodificado em latitude/longitude; códigos curtos (ex.: `6P55+W5 São José do Rio Preto`) são completados usando a localização de referência da cidade.

```powershell
python rebuild_from_pluscodes.py "pluscode unidades.csv"
```
O script **apaga** postos, preços e rotas atuais e recria: um posto por linha, `data/seed.json` atualizado, preços mock e rotas por rodovia (a rodovia é herdada do posto antigo equivalente quando o nome/cidade casam; postos novos ficam sem rodovia e portanto fora das rotas até alguém informá-la no admin).
Para só **conferir** o casamento/coordenadas sem gravar: `python check_pluscodes.py "pluscode unidades.csv"` (acrescente `--apply` para gravar).

Alternativa genérica (arquivo de texto, sem planilha): `python import_pluscodes.py postos.txt [--replace]`, uma linha por posto: `33R4+XR Margem Esquerda, Gaspar - Santa Catarina ; Nome ; Bandeira ; Rodovia`. Códigos curtos usam a cidade como referência (Nominatim); completos funcionam offline (`olc.py`). `--replace` desativa os postos que não estão no arquivo. Esse importador **atualiza/cria** postos; já o `rebuild_from_pluscodes.py` **recria a base inteira**.

Situação atual: **36 postos**, todos com `geo_quality = ok`.

Scripts legados (úteis se surgir outra fonte): `import_kml.py` (KMZ do Google Maps), `import_stations.py` (CSV de scraper), `geocode.py` (Nominatim). Postos também podem ser criados/editados em `/admin.html`.

## Clientes e login

- Login = **CPF (11) ou CNPJ (14)** com dígito verificador validado + senha (mín. 6 caracteres).
- Senhas só como hash **scrypt** com salt; sessão com token aleatório (o banco guarda só o hash), cookie `bp_session` HttpOnly, SameSite=Lax, 30 dias.
- 5 erros por documento em 15 min (e 20 por IP) bloqueiam novas tentativas. Desativar um cliente derruba as sessões dele.
- Cadastro em massa:

```powershell
python import_clients.py clientes.csv
```
Colunas aceitas (qualquer ordem, sem distinguir acento/caixa): `documento|cpf|cnpj|cpf_cnpj`, `nome|razao social|cliente`, `senha` (vazia = gera uma senha de 8 caracteres). Separador `,` ou `;`; UTF-8 ou Excel (cp1252). Documentos inválidos são listados e ignorados. As **senhas geradas** dos clientes novos vão para `clientes_senhas_AAAAMMDD-HHMMSS.csv` (ignorado pelo git): envie e **apague o arquivo**.

## Preços

- Tabela `prices`: um preço atual por posto × produto; cada alteração também grava em `price_history`.
- Edição manual em `/admin.html` ou pela API (`PUT /api/admin/prices`, ver [docs/API.md](docs/API.md)). Valor vazio remove o preço.
- Os dados de demonstração foram gerados aleatoriamente (S-10 R$ 6,39–6,79; S-500 R$ 6,09–6,29; Arla R$ 3,20–3,90). **Substitua antes do piloto.**
- Cores: os postos são divididos em tercis do produto selecionado (verde = terço mais barato).

## Preço melhor? (nota fiscal)

No menu, aba **Preço melhor?** (ou botão **📎 Anexar nota** no mapa):
1. O cliente escolhe o posto da rede que quer que cubra o preço, produto, preço encontrado, onde achou, cidade, data da nota, litros (opcional), observação e **anexa a nota** (JPG/PNG/WEBP/PDF até 8 MB; fotos são reduzidas no celular).
2. Regras: nota dos últimos 30 dias, até 10 envios por dia; o tipo do arquivo é checado pelos primeiros bytes (não pelo que o navegador diz).
3. A equipe vê em `/admin.html`: abre a nota, responde, muda o status (`pendente` → `analise` → `coberto`/`recusado`) e, se *coberto*, pode **aplicar o preço no posto** automaticamente.
4. O cliente acompanha o status em "Meus envios".

Os anexos ficam em `uploads/` (fora do git, nomes aleatórios, só o dono ou o admin acessa). **Faça backup** e restrinja o acesso ao disco: notas fiscais contêm dados pessoais.

## Roteirizador

Menu → **Roteirizador**: digite a cidade de origem e a de destino (autocomplete), escolha a distância máxima da rota (2–10 km) e **Traçar rota**. Mostra o trajeto, os postos no caminho em ordem, preço médio e melhor preço do trecho. Geocodificação via Nominatim (1 req/s, cache) e rota via OSRM; ambos públicos e de uso leve — troque por instâncias próprias (`NOMINATIM_URL`, `OSRM_URL`) em produção. Links diretos: `/?de=Campinas&para=Ribeirão Preto`.

## Ajuda via WhatsApp

Botão verde **💬 Ajuda** abre `https://wa.me/<número>?text=...` com a mensagem "Olá! Preciso de ajuda com o Pin Verde. (nome do cliente)". O número vem de `WHATSAPP_NUMBER`; enquanto não for definido, o front usa um **telefone fictício**.

## Estrutura do repositório

```
server.py              API + arquivos estáticos + schema SQLite + painel admin (endpoints)
auth.py                CPF/CNPJ, senhas (scrypt), sessões, bloqueio por tentativas
claims.py              "Preço melhor?": validação, anexos, fila e aplicação do preço
planner.py             roteirizador: geocode (Nominatim), rota (OSRM), postos ao longo da rota
rebuild_from_pluscodes.py   refaz a base de postos a partir da planilha de Plus Codes  (fonte oficial)
check_pluscodes.py     decodificador de Plus Code + conferência/ajuste de coordenadas
import_clients.py      cadastro de clientes por CSV
import_kml.py / import_stations.py / geocode.py   importadores legados
import_pluscodes.py    importador genérico de Plus Codes em texto (usa olc.py)
data/seed.json         postos e rotas carregados em banco vazio
static/                index.html, app.js, osmtint.js (mapa recolorido), style.css, login.html, admin.html
docs/                  API, operação do piloto, arquitetura, lista de postos
olc.py                 decodificador Open Location Code (usado por import_pluscodes.py)
CHANGELOG.md          histórico do projeto
CLAUDE.md              contexto para assistentes de código
```

## Modelo de dados

`clients` · `sessions` · `stations` (lat/lon, bandeira, cidade/UF, rodovia, `geo_quality`, `active`) · `prices` (atual) · `price_history` · `routes` · `route_stations` (ordem do percurso) · `price_claims`. Detalhes em [docs/ARQUITETURA.md](docs/ARQUITETURA.md).

## Segurança e LGPD

- Toda a API `GET /api/*` exige sessão de cliente (ou `X-Admin-Token`); sem login o front redireciona para `/login.html`.
- Senhas com scrypt; tokens de sessão armazenados como hash; resposta de login não revela se o documento existe.
- Painel admin protegido por `ADMIN_TOKEN` — use um valor longo e aleatório e **HTTPS**.
- Dados pessoais armazenados: CPF/CNPJ, nome e notas fiscais. Defina prazo de retenção, backup criptografado e quem acessa `uploads/` e o `.db`.
- Nunca commitar: `*.db`, `uploads/`, `.env`, `clientes*.csv`, `clientes_senhas_*.csv` (já no `.gitignore`).

## Publicação

Qualquer VPS/contêiner com Python 3 serve: rode `python server.py` atrás de um proxy reverso com HTTPS (Caddy/Nginx), defina `ADMIN_TOKEN`, `COOKIE_SECURE=1`, `DB_PATH` e `UPLOAD_DIR` em disco persistente e agende backup. Passo a passo e checklist do piloto em [docs/OPERACAO.md](docs/OPERACAO.md).

## Limitações e roadmap

- Mapa base: tiles públicos do OpenStreetMap (uso leve; para volume/comercial, usar provedor com chave).
- Nominatim/OSRM públicos têm limite de uso.
- Não há "esqueci a senha"/troca de senha pelo próprio cliente (hoje o admin redefine).
- A autenticidade da nota fiscal não é verificada (ideia: pedir a **chave da NF-e** e consultar).
- Ideias: agrupamento de pins (clusters), notificações de mudança de preço, importação de preços por planilha, deploy automatizado.
