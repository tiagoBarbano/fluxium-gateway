# LGPD/GDPR - Auditoria e remediacao do Fluxium Gateway

Data da revisao: 2026-05-17

## Pontos problematicos encontrados

- Plugin `logging` registrava body de request/response por padrao quando habilitado. Payloads de gateway podem conter CPF, email, tokens, dados financeiros ou qualquer dado pessoal transitando para APIs upstream.
- Mascaramento era restrito a chaves JSON e nao tratava texto livre.
- `/routes` e logs de cache de rotas podiam expor configuracoes de plugins com segredos.
- `config_store.py` imprimia rotas inteiras no stdout durante carga/atualizacao.
- Autenticacao por API key resolvia consumers por `api_keys` em claro.
- Autenticacao por `x-client-id`/`x-secret-id` procurava `secret_id` em claro.
- `forward_auth` podia incluir corpo retornado pelo endpoint de token em erro interno.
- `event_bridge` publicava query/body por padrao no Redis, o que ampliava retencao e replicacao de dados pessoais.
- Fallbacks Redis tinham senha hardcoded.
- `send.http` continha tokens e client secrets com formato real.

## Correcoes aplicadas

- `logging` agora registra apenas metadados e tamanho do body por padrao. O conteudo so aparece com `log_bodies=true`.
- Mascaramento foi ampliado para `client_secret`, `secret_id`, `authorization`, `api_key`, telefone, email, CPF e CNPJ, inclusive em texto livre.
- `/routes` e `/admin/plugins` retornam configuracao sensivel redigida.
- Prints de carga/atualizacao de rotas foram trocados por logs estruturados sem dump de documento.
- API key passa a aceitar `api_key_hashes` com salt/PBKDF2, mantendo lookup legado apenas para compatibilidade.
- Client credentials passam a validar `secret_hash`/`secret_salt`, mantendo `secret_id` legado apenas para compatibilidade.
- `forward_auth` redige `token`, `secret`, `password` e `authorization` em erros de endpoint de token.
- `event_bridge` nao publica query/body por padrao; exige `include_query=true` e/ou `include_body=true`.
- Fallbacks Redis removeram senha hardcoded.
- `send.http` foi substituido por exemplos com placeholders e dados sinteticos.

## Pendencias operacionais

- Migrar registros legados para remover `api_keys` e `secret_id` em claro das collections.
- Habilitar `log_bodies` apenas em troubleshooting controlado, com retencao curta e mascaramento ativo.
- Revisar configuracoes existentes de `event_bridge` que dependiam de body/query e confirmar base legal/finalidade antes de religar.
- Configurar `REDIS_URL` via segredo de ambiente em todos os ambientes.
