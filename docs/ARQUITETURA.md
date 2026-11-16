# Arquitetura

```
Navegador (Leaflet, JS puro)  ──HTTP──►  server.py (http.server, threads)
   static/*.html|js|css                    ├─ auth.py     sessões / senhas
                                           ├─ claims.py   notas fiscais (uploads/)
                                           ├─ planner.py ─► Nominatim + OSRM (HTTP externo)
                                           └─ SQLite (best_price.db)
```
Sem framework, sem build, sem dependências além do Python. O servidor serve os estáticos e a API.

## Modelo de dados (SQLite)
| Tabela | Conteúdo |
|---|---|
| `stations` | id, name, brand, city, uf, highway, lat, lon, address, category, `geo_quality` (`ok`/`approx`/`manual`/`kml`), active |
| `prices` | PK (station_id, product): preço atual, `updated_at`. `product` ∈ DIESEL S-10 / DIESEL S-500 / ARLA |
| `price_history` | Toda mudança de preço (station_id, product, price, changed_at) |
| `routes`, `route_stations` | Rotas por rodovia e a ordem dos postos no percurso |
| `clients` | doc (CPF/CNPJ só dígitos, único), name, `pwd_hash` (scrypt), active, last_login |
| `sessions` | `token_hash` (SHA-256 do token do cookie), client_id, expires_at |
| `price_claims` | Pedido "Preço melhor?": cliente, posto, produto, preço, local, data da nota, arquivo, status, resposta, preço coberto |

`data/seed.json` (postos + rotas) popula um banco vazio no primeiro start.

## Frontend (`static/app.js`)
- **Marcadores**: `L.divIcon` em três modos conforme o zoom — pin (padrão), chip de preço (≥ 8), cartão com nome do posto + preço (≥ 10) — com anti-colisão por caixas em pixels.
- **Cor**: tercis do produto selecionado (`t0` verde, `t1` laranja, `t2` vermelho, `tn` sem preço).
- **Cartões de melhor preço** (`renderBest`): rede toda, ou só os postos do trajeto quando há rota traçada. Botões Ajuda/Anexar nota ficam no mesmo bloco (canto inferior direito).
- **Menu lateral**: Roteirizador, Rotas (média/melhor por rodovia), Preço melhor?.
- Parâmetros de URL: `?view=lat,lon,zoom`, `?de=<cidade>&para=<cidade>`.
- `api()` redireciona a `/login.html` quando recebe 401.

## Roteirizador (`planner.py`)
1. `geocode(texto)` → Nominatim, lock de 1 req/s, cache em memória.
2. `route(a, b)` → OSRM (geometria simplificada).
3. `stations_along(line, radius)` → distância ponto-a-polilinha; ordena por posição ao longo do trajeto.

## Plus Code (`check_pluscodes.py`)
`decode()` converte Open Location Code completo em lat/lon (grade 20×20, refinamento 4×5). `recover()` completa códigos curtos escolhendo a célula mais próxima de uma referência (posto antigo, cidade conhecida ou geocodificação da cidade).

## Decisões
- **SQLite + stdlib**: piloto pequeno, implantação trivial, backup = copiar arquivo.
- **Sessão no banco com hash do token**: vazamento do banco não entrega sessões válidas.
- **Anexos em disco, nome aleatório**: banco leve; acesso sempre via API autenticada (dono/admin).
- **Tiles OSM**: já mostram rodovias e cidades sem chave; limitar a uso leve.
