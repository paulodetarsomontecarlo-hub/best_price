# best_price

Aplicação web (responsiva) com mapa de postos e preços de **DIESEL S-10**, **DIESEL S-500** e **ARLA**.

- Mapa enxuto: só vias no zoom aberto; com zoom (≥ 8) aparecem nomes de cidades e os quadrados de preço.
- Menu lateral: **preço médio** e **melhor preço** por rota, para o produto selecionado.
- Toque no posto → popup com os preços e botão **Abrir no Waze**.
- Backend: Python (biblioteca padrão) + SQLite. Frontend: Leaflet, sem build.

## Rodar

```bash
ADMIN_TOKEN=troque-isto python3 server.py        # http://localhost:8000
```

- Cadastro de postos, preços e rotas: `/admin.html` (pede o `ADMIN_TOKEN`).
- `CLIENT_CODE=abc123` (opcional): restringe a leitura ao grupo de clientes; compartilhe `http://host:8000/?code=abc123`.
- `PORT` e `DB_PATH` também são configuráveis.
- Importar postos de um KML/KMZ do Google Maps: `python3 import_kml.py Mapa_Postos.kmz`. Postos sem coordenadas no arquivo entram sem lat/lon (não aparecem no mapa); complete com `python3 geocode.py` (Nominatim/OSM, precisa de internet) ou pelo `/admin.html` (marcados com ⚠).
- Importar postos de um CSV (ex.: do google-maps-scraper-kit): `python3 import_stations.py postos.csv --highway BR-163`.

## Dados iniciais

`data/seed.json` traz os 63 postos da rede (do `Mapa_Postos.kmz`, com coordenadas corrigidas via OSM) e 7 rotas por rodovia; é carregado sozinho quando o banco está vazio. `geo_quality`: `ok` (confiável), `kml`, `approx` (só a cidade; confira no admin). Preços não vêm cadastrados.

## Tabelas

`stations`, `prices` (um preço atual por posto/produto), `price_history`, `routes`, `route_stations` (ordem do percurso).

## Notas

- Use HTTPS na frente do servidor (proxy reverso) ao publicar; o token e o código trafegam em header.
- Tiles: Esri Light Gray Canvas (sem chave, com atribuição). Para uso comercial intenso, confira os termos da Esri ou troque por um provedor com chave (MapTiler, Stadia) em static/app.js.
