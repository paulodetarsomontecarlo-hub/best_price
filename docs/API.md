# API

Base: o próprio servidor (`http://localhost:8000`). Corpo e respostas em JSON, exceto o upload de anexos.
Erros: `{"error": "mensagem em português"}` com HTTP 400 (validação), 401 (sem login), 403, 404.

## Autenticação
- **Cliente:** cookie `bp_session` (HttpOnly) obtido em `POST /api/login`.
- **Admin:** header `X-Admin-Token: <ADMIN_TOKEN>` em qualquer chamada. Sem `ADMIN_TOKEN` configurado o admin fica desabilitado.
- Todas as `GET /api/*` exigem uma das duas. Sem credencial → `401 {"error":"login necessário"}`.

## Sessão
| Método | Rota | Corpo / resposta |
|---|---|---|
| POST | `/api/login` | `{"doc":"52998224725","password":"..."}` → define cookie; `{"name": "..."}` |
| POST | `/api/logout` | encerra a sessão |
| GET | `/api/me` | `{"name","doc"}` do cliente logado |
| GET | `/api/config` | `{"products":[...],"whatsapp":"<digits>"}` |

## Dados do mapa
| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/stations` | Postos ativos com coordenadas e `prices` `{produto:{price,updated_at}}`. `?all=1` (admin) inclui os sem coordenada |
| GET | `/api/routes` | Rotas por rodovia com postos em ordem e média/melhor preço por produto |
| GET | `/api/geocode?q=Campinas` | Até 5 sugestões `{label,lat,lon}` (Nominatim, com cache) |
| GET | `/api/plan?from=lat,lon&to=lat,lon&radius=3` | Rota (OSRM) + postos a ≤ `radius` km, em ordem ao longo do trajeto |

## Preço melhor? (cliente)
| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/claims` | Envios do cliente logado |
| POST | `/api/claims` | `{station_id?,product,price,place_name,place_city?,purchased_on(YYYY-MM-DD),liters?,comment?}` → `{id}` (status *rascunho*) |
| PUT | `/api/claims/<id>/file` | Corpo = **bytes do arquivo** (JPG/PNG/WEBP/PDF ≤ 8 MB); `Content-Type` opcional. Passa para *pendente* |
| GET | `/api/claims/<id>/file` | Baixa o anexo (dono ou admin) |

Limites: nota de até 30 dias, 10 envios/24 h por cliente.

## Admin (`X-Admin-Token`)
| Método | Rota | Corpo |
|---|---|---|
| POST / PUT / DELETE | `/api/admin/stations[/<id>]` | `{name,brand,city,uf,highway,lat,lon,address,category}` (DELETE = desativa) |
| PUT | `/api/admin/prices` | `{"station_id":1,"prices":{"DIESEL S-10":6.45,"ARLA":null}}` (`null`/vazio remove) |
| POST / PUT / DELETE | `/api/admin/routes[/<id>]` | `{name,highway,station_ids:[...]}` (ordem = percurso) |
| GET | `/api/admin/clients` | Lista clientes |
| POST | `/api/admin/clients` | `{doc,name,password}` |
| PUT | `/api/admin/clients/<id>` | `{name?,password?,active?}` (senha/desativar derrubam sessões) |
| DELETE | `/api/admin/clients/<id>` | Desativa e derruba sessões |
| GET | `/api/admin/claims` | Todos os pedidos (com cliente e posto) |
| PUT | `/api/admin/claims/<id>` | `{status,admin_reply,covered_price,apply_price}` — status: `pendente`,`analise`,`coberto`,`recusado`; `apply_price:true` com *coberto* grava o preço no posto e no histórico |

Produtos válidos: `DIESEL S-10`, `DIESEL S-500`, `ARLA`.
