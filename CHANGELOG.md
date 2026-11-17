# Changelog

Histórico do projeto (mais recente primeiro). Branch de trabalho: `claude/trusting-bardeen-5gmp50`.

## Pin Verde (renomeação)
- Produto passa a se chamar **Pin Verde** (telas, mensagem do WhatsApp, docs). Repositório e `best_price.db` mantêm o nome técnico.

## Base de postos por Plus Code
- `pluscode unidades.csv` vira a **única fonte** dos postos: `rebuild_from_pluscodes.py` recria postos, preços mock, rotas e `data/seed.json` (36 postos).
- `check_pluscodes.py`: decodificador de Plus Code + conferência/ajuste de coordenadas. Importador genérico `import_pluscodes.py` + `olc.py` (outra sessão, mesclado).
- Documentação ampliada: README, `docs/` (API, Operação, Arquitetura, Postos), CLAUDE.md.

## Botões Ajuda e Anexar nota
- Os dois cartões do canto inferior direito ganharam **💬 Ajuda** (wa.me, telefone mock `5511999999999` até definir `WHATSAPP_NUMBER`) e **📎 Anexar nota** (abre a aba "Preço melhor?").

## Cartões de melhor preço
- "Melhor Diesel S-10 / S-500" (rede toda ou só a rota traçada); tocar leva ao posto.

## "Preço melhor?" (nota fiscal)
- Cliente informa preço + anexa nota (JPG/PNG/WEBP/PDF ≤ 8 MB); admin analisa, responde, marca *coberto* e pode aplicar o preço no posto. Anexos em `uploads/`.

## Login do piloto
- CPF/CNPJ + senha (scrypt), sessões no banco, bloqueio por tentativas, admin de clientes e `import_clients.py`.

## Visual do mapa
- Pins de bomba de combustível, chips de preço e cartões com nome do posto conforme o zoom; base OSM com rodovias (CARTO/Esri descartados por exigir chave / ficarem cinza).

## Roteirizador
- Cidade de origem → destino (Nominatim + OSRM), postos a ≤ N km da rota, preço médio/melhor do trecho.

## Preços mock
- Faixas: S-10 6,39–6,79; S-500 6,09–6,29; ARLA 3,20–3,90 (assumida).

## Início
- App web + backend (Python stdlib + SQLite + Leaflet), importação do `Mapa_Postos.kmz` (63 postos, geocodificação via Nominatim), menu com preço médio/melhor por rota, abrir no Waze.