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
- **Login dos clientes:** CPF/CNPJ + senha. Cadastre em `/admin.html` (seção Clientes) ou importe um CSV: `python import_clients.py clientes.csv` (colunas: documento, nome, senha; senha vazia = gerada, e vai para `clientes_senhas_*.csv`). Documentos são validados (dígito verificador). Senhas ficam só como hash (scrypt); 5 erros bloqueiam 15 min; desativar um cliente derruba as sessões dele. Use `COOKIE_SECURE=1` atrás de HTTPS.
- `PORT` e `DB_PATH` também são configuráveis.
- Importar postos de um KML/KMZ do Google Maps: `python3 import_kml.py Mapa_Postos.kmz`. Postos sem coordenadas no arquivo entram sem lat/lon (não aparecem no mapa); complete com `python3 geocode.py` (Nominatim/OSM, precisa de internet) ou pelo `/admin.html` (marcados com ⚠).
- Importar postos de um CSV (ex.: do google-maps-scraper-kit): `python3 import_stations.py postos.csv --highway BR-163`.

## Melhores preços e Ajuda

Dois cartões no canto do mapa mostram o melhor preço de Diesel S-10 e S-500 (da rede toda, ou só do trajeto quando há rota traçada); tocar leva ao posto. O botão verde **Ajuda** abre o WhatsApp (wa.me) no telefone definido em WHATSAPP_NUMBER (DDI+DDD, só dígitos, ex.: 5517999999999); sem a variável o botão não aparece.

## Preço melhor? (nota fiscal)

No menu, aba **Preço melhor?**: o cliente informa produto, preço, onde achou, data e anexa a nota fiscal (foto/PDF, até 8 MB; fotos são reduzidas no celular). Notas só dos últimos 30 dias, até 10 envios por dia. A equipe analisa em /admin.html (ver nota, responder, marcar Coberto e, opcionalmente, já atualizar o preço do posto). Os anexos ficam em uploads/ (UPLOAD_DIR), fora do git: faça backup e restrinja o acesso, pois notas fiscais trazem dados pessoais (LGPD).

## Dados iniciais

`data/seed.json` traz os 63 postos da rede (do `Mapa_Postos.kmz`, com coordenadas corrigidas via OSM) e 7 rotas por rodovia; é carregado sozinho quando o banco está vazio. `geo_quality`: `ok` (confiável), `kml`, `approx` (só a cidade; confira no admin). Preços não vêm cadastrados.

## Tabelas

`clients`, `sessions`, `price_claims`, `stations`, `prices` (um preço atual por posto/produto), `price_history`, `routes`, `route_stations` (ordem do percurso).

## Notas

- Use HTTPS na frente do servidor (proxy reverso) ao publicar; o token e o código trafegam em header.
- Tiles: OpenStreetMap (tile.openstreetmap.org, gratuito, exige atribuição e uso leve). Para tráfego alto/comercial, troque a URL em `static/app.js` por um provedor com chave (MapTiler, Stadia, Mapbox) ou tiles próprios.
