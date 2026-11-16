# Operação do piloto

## Checklist antes de liberar para clientes
- [ ] Definir `ADMIN_TOKEN` forte (≥ 24 caracteres aleatórios) — não usar o valor de desenvolvimento.
- [ ] Publicar atrás de **HTTPS** e iniciar com `COOKIE_SECURE=1`.
- [ ] Definir `WHATSAPP_NUMBER` com o telefone real de suporte.
- [ ] Substituir os **preços mock** pelos reais (admin ou `PUT /api/admin/prices`).
- [ ] Importar a base de clientes (`python import_clients.py clientes.csv`), enviar as senhas geradas e **apagar** `clientes_senhas_*.csv`.
- [ ] **Desativar o cliente de teste** (CPF 529.982.247-25) criado em desenvolvimento.
- [ ] Informar a rodovia dos postos sem rota (Corumbataí, Uberlândia, Várzea Grande, Mirassol KM 446) para entrarem nas rotas.
- [ ] Apontar `DB_PATH` e `UPLOAD_DIR` para disco persistente e agendar backup.

## Rotinas
| Tarefa | Como |
|---|---|
| Atualizar preços | `/admin.html` → Preços (ou API) |
| Novo posto | `/admin.html` → Novo posto, ou acrescentar linha na planilha de Plus Codes e rodar `rebuild_from_pluscodes.py` (**apaga e recria** postos/preços/rotas — use só na carga inicial) |
| Novo cliente / redefinir senha | `/admin.html` → Clientes, ou `import_clients.py` (senha só muda se a coluna `senha` vier preenchida) |
| Cliente bloqueado (5 erros) | Aguardar 15 min ou reiniciar o servidor (bloqueio é em memória) |
| Analisar "Preço melhor?" | `/admin.html` → Pedidos: abrir nota → responder → *coberto* (+ aplicar preço) ou *recusado* |

## Backup e restauração
- Banco: copie `best_price.db` com o servidor parado ou use `sqlite3 best_price.db ".backup copia.db"`.
- Anexos: copie a pasta `UPLOAD_DIR` inteira. Restaurar = recolocar arquivo e pasta nos mesmos caminhos.
- O banco e a pasta de anexos contêm dados pessoais (CPF/CNPJ, notas fiscais): backup criptografado, acesso restrito, prazo de retenção definido (LGPD).

## Publicação (exemplo)
```
python server.py            # escuta em PORT (padrão 8000)
```
Proxy reverso (Caddy):
```
bestprice.exemplo.com.br {
    reverse_proxy 127.0.0.1:8000
}
```
Variáveis de produção: `ADMIN_TOKEN`, `COOKIE_SECURE=1`, `DB_PATH=/dados/best_price.db`, `UPLOAD_DIR=/dados/uploads`, `WHATSAPP_NUMBER`.
Para volume maior, use instâncias próprias de Nominatim/OSRM (`NOMINATIM_URL`, `OSRM_URL`) e um provedor de tiles com chave.

## Problemas comuns
| Sintoma | Causa provável |
|---|---|
| Mapa em branco | Erro de JavaScript (abrir o console) ou sem internet para carregar Leaflet/tiles |
| Tiles "API KEY REQUIRED" | Provedor de tiles exige chave; o padrão é o OSM (sem chave) |
| Redireciona sempre para o login | Sessão expirada ou cookie `Secure` sem HTTPS (`COOKIE_SECURE=1` só em HTTPS) |
| Roteirizador não acha cidade / lento | Limite do Nominatim/OSRM público (1 req/s) |
| Acentos quebrados em CSV | CSV do Excel é cp1252; os importadores detectam sozinhos (UTF-8 ou cp1252) |
