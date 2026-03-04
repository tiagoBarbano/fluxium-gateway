# Fluxium Gateway

Gateway ASGI em Python para roteamento dinâmico de requisições HTTP com pipeline de plugins (autenticação JWT, rate limit, cache, retry e circuit breaker), métricas Prometheus e tracing OpenTelemetry.

## Visão Geral

O gateway recebe requisições HTTP, identifica a rota de destino a partir de regras armazenadas no MongoDB e aplica plugins configuráveis por rota antes de encaminhar a chamada para o upstream.

Principais capacidades:

- Roteamento dinâmico via coleção `gateway.routes` no MongoDB.
- Suporte a path template, por exemplo: `/ws/{cep}/json/`.
- Pipeline de plugins por rota com duas fases: `before/after` e `forward`.
- Retorno padronizado de erros de plugin (`code` + `description`).
- Cache de resposta GET com Redis e TTL configurável.
- Rate limiting por tenant e janela de tempo com Redis.
- Métricas Prometheus em `/metrics`.
- Tracing com OpenTelemetry (ASGI, aiohttp client, Redis e PyMongo).

## Arquitetura

Fluxo de alto nível:

1. Requisição chega no ASGI app (`app/main.py`).
2. Gateway carrega a rota correspondente via `match_route` (`app/config_store.py`).
3. Executa plugins `before_request` na ordem declarada em `route.plugins`.
4. Se houver cache hit, responde imediatamente sem chamar upstream.
5. Executa plugins `forward` (por exemplo: `retry`, `circuit_breaker`) envolvendo a chamada upstream.
6. Encaminha para `target_base + path` usando `aiohttp`.
7. Retorna resposta para o cliente.
8. Executa plugins `after_response` em ordem reversa.
9. Registra métricas e logs estruturados.

### Componentes principais

- `app/main.py`: core do gateway e middleware OpenTelemetry.
- `app/config_store.py`: conexão MongoDB e resolução de rota.
- `app/plugins/engine.py`: orquestra execução dos plugins por fase (`before_after` e `forward`).
- `app/plugins/*.py`: plugins de negócio.
- `app/rate_limit.py`: backend de rate limit no Redis.
- `app/metrics.py`: contadores/histogramas Prometheus.
- `app/telemetry.py`: configuração de tracing OTLP.
- `app/lifespan.py`: startup/shutdown e ciclo de recursos.
- `app/handler_http.py`: sessão compartilhada de `aiohttp`.

## Estrutura de pastas

```text
.
├── app/
│   ├── main.py
│   ├── config_store.py
│   ├── context.py
│   ├── handler_http.py
│   ├── lifespan.py
│   ├── logging_fast.py
│   ├── metrics.py
│   ├── rate_limit.py
│   ├── telemetry.py
│   └── plugins/
│       ├── base.py
│       ├── cache.py
│       ├── circuit_breaker.py
│       ├── engine.py
│       ├── errors.py
│       ├── forward_auth.py
│       ├── jwt_auth.py
│       ├── oauth.py
│       ├── rate_limit.py
│       └── retry.py
├── docker-compose.yml
├── Dockerfile
├── mongo-init.js
├── prometheus.yml
├── tempo.yaml
└── overrides.yaml
```

## Modelo de rota no MongoDB

As rotas ficam na coleção `gateway.routes`.

Campos usados pelo gateway:

- `prefix` (string): prefixo/path template da rota.
- `target_base` (string): base URL do upstream.
- `plugins` (array): plugins a executar na rota. Cada item pode ser `string` (nome) ou objeto com `type`, `order` e `config`.
- `cache` (objeto): configuração do plugin de cache.

Exemplo de documento:

```json
{
	"prefix": "/ws/{cep}/json/",
	"target_base": "https://viacep.com.br",
	"plugins": [
		{"type": "jwt_auth", "order": 1},
		{
			"type": "rate_limit",
			"order": 2,
			"config": {"limit": 100, "window_seconds": 60}
		},
		{
			"type": "circuit_breaker",
			"order": 50,
			"config": {"failure_threshold": 5, "recovery_timeout_seconds": 30}
		},
		{
			"type": "retry",
			"order": 60,
			"config": {"attempts": 3, "backoff_ms": 100, "retry_on": [502, 503, 504]}
		},
		{"type": "cache", "order": 100}
	],
	"cache": {
		"ttl_seconds": 30
	}
}
```

### Fases de plugin

- `before_after`: executa `before_request` e `after_response` (ex.: `jwt_auth`, `rate_limit`, `cache`, `oauth2`).
- `forward`: executa `around_request` durante a chamada upstream (ex.: `retry`, `circuit_breaker`).

## Plugins disponíveis

### 1) `jwt_auth`

Valida header `Authorization: Bearer <token>` e extrai `tenant_id` do JWT.

Observações atuais:

- Algoritmo: `HS256`.
- Secret: fixo no código (`super-secret`).

### 2) `rate_limit`

Aplica limite por tenant + rota + janela usando Redis.

- Chave de contador: `rl:{tenant}:{prefix}:{bucket}`.
- Bucket é calculado por `now // window_seconds`.

### 3) `cache`

Cacheia respostas `GET` com status `200` no Redis.

- Chave de cache: hash SHA-256 de `tenant + method + path + query`.
- Body é armazenado em Base64.
- TTL por rota (`cache.ttl_seconds`) ou fallback global (`CACHE_TTL_SECONDS`).
- Respeita limite máximo de payload (`CACHE_MAX_BODY_BYTES`).

### 4) `retry` (fase `forward`)

Reexecuta chamada upstream conforme configuração por rota.

- `attempts` (default: `3`)
- `backoff_ms` (default: `100`, alias: `delay_ms`)
- `retry_on` (default: `[502, 503, 504]`, alias: `retry_on_status`)

### 5) `circuit_breaker` (fase `forward`)

Interrompe chamadas temporariamente após sequência de falhas.

- `failure_threshold` (default: `5`)
- `recovery_timeout_seconds` (default: `30`)

### 6) `forward_auth` (fase `forward`)

Injeta autenticação na chamada upstream.

Modos suportados:

- `propagate` (default): copia header da requisição de entrada para o upstream.
	- `source_header` (default: `authorization`)
	- `target_header` (default: `authorization`)
- `static`: usa token fixo configurado na rota.
	- `token`
	- `scheme` (default: `Bearer`)
- `oauth2_client_credentials`: gera token chamando endpoint OAuth2 e reutiliza em cache até expirar.
	- `token_url`
	- `client_id`
	- `client_secret`
	- `scope` (opcional)
	- `audience` (opcional)
	- `grant_type` (default: `client_credentials`)
	- `timeout_seconds` (default: `5`)
	- `cache_skew_seconds` (default: `30`)
	- `refresh_on_401` (default: `true`) — ao receber 401 do upstream, força refresh do token e refaz a chamada uma vez.
	- `refresh_retry_methods` (default: `[
		"GET", "HEAD", "OPTIONS"
	]`) — métodos permitidos para retry após refresh em 401.
	- `refresh_retry_all_methods` (default: `false`) — habilita retry em qualquer método (usar com cautela).

Exemplo de configuração:

```json
{
	"type": "forward_auth",
	"order": 40,
	"config": {
		"mode": "oauth2_client_credentials",
		"token_url": "https://idp.exemplo.com/realms/myrealm/protocol/openid-connect/token",
		"client_id": "gateway-upstream-client",
		"client_secret": "<secret>",
		"scope": "pricing.read",
		"target_header": "authorization"
	}
}
```

Exemplo completo no padrão da rota (retry em 401 apenas para métodos seguros):

```json
{
	"tenant": "teste",
	"prefix": "/ws/{cep}/json/",
	"target_base": "https://viacep.com.br",
	"strip_prefix": true,
	"plugins": [
		{
			"type": "oauth22",
			"order": 1,
			"config": {
				"issuer": "https://keycloak.meudominio.com/realms/myrealm",
				"audience": "gateway-api",
				"required_scopes": ["pricing.read"]
			}
		},
		{
			"type": "forward_auth",
			"order": 3,
			"config": {
				"mode": "oauth2_client_credentials",
				"token_url": "https://idp.exemplo.com/realms/myrealm/protocol/openid-connect/token",
				"client_id": "gateway-upstream-client",
				"client_secret": "<secret>",
				"scope": "pricing.read",
				"target_header": "authorization",
				"refresh_on_401": true,
				"refresh_retry_methods": ["GET", "HEAD", "OPTIONS"],
				"refresh_retry_all_methods": false
			}
		},
		{
			"type": "retry",
			"order": 4,
			"config": {
				"attempts": 3,
				"retry_on": [502, 503, 504],
				"backoff_ms": 50
			}
		}
	]
}
```

## Padrão de erros de plugin

Quando um plugin falha em `before_request`, o gateway retorna JSON com:

```json
{
	"code": "ERROR_CODE",
	"description": "Descrição"
}
```

Erros implementados:

- `JWT_MISSING_AUTH_HEADER` → `401`
- `JWT_INVALID_TOKEN` → `401`
- `JWT_MISSING_TENANT` → `403`
- `RATE_LIMIT_EXCEEDED` → `429`
- `CACHE_BACKEND_UNAVAILABLE` → `503`
- `ROUTE_NOT_FOUND` → `404`
- Erro inesperado em plugin → `500` com `PLUGIN_EXECUTION_ERROR`

## Variáveis de ambiente

| Variável | Default | Uso |
|---|---|---|
| `MONGO_URL` | `mongodb://localhost:27017/?directConnection=true` | Leitura de rotas |
| `REDIS_URL` | `redis://localhost:6379` | Rate limit e cache |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | Exportador de tracing |
| `CACHE_TTL_SECONDS` | `30` | TTL padrão do cache |
| `CACHE_MAX_BODY_BYTES` | `1048576` | Tamanho máximo de body cacheável |
| `PROMETHEUS_MULTIPROC_DIR` | `/tmp/prometheus` | Diretório de métricas multiprocess |

## Executando localmente

### Pré-requisitos

- Python 3.13+
- `uv`
- MongoDB e Redis em execução

### 1) Instalar dependências

```bash
uv sync
```

### 2) Subir somente dependências (opcional via Docker)

```bash
docker compose up -d mongo redis prometheus tempo grafana
```

### 3) Executar gateway

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8080
```

## Executando com Docker Compose

Subir stack completa:

```bash
docker compose up -d --build
```

Serviços expostos:

- Gateway: `http://localhost:8080`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000`
- Tempo API: `http://localhost:3200`
- OTLP gRPC: `localhost:4317`
- OTLP HTTP: `localhost:4318`

## Observabilidade

### Métricas

Endpoint do gateway:

- `GET /metrics`

Métricas principais:

- `gateway_requests_total{method,route,status,tenant}`
- `gateway_request_latency_seconds{route,tenant}`

### Tracing

Instrumentações ativas:

- ASGI middleware
- Cliente `aiohttp`
- PyMongo
- Redis

As traces são exportadas via OTLP para o endpoint configurado em `OTEL_EXPORTER_OTLP_ENDPOINT`.

## Exemplo de requisição

```bash
curl -i \
	-H "Authorization: Bearer <seu-jwt>" \
	-H "x-tenant-id: tenant-a" \
	http://localhost:8080/ws/01001000/json/
```

## Troubleshooting

### 1) `ASGI callable returned without starting response`

Ocorre quando algum caminho retorna sem enviar `http.response.start`. O gateway atual responde rota inexistente com status `404` e payload JSON padronizado:

```json
{
	"code": "ROUTE_NOT_FOUND",
	"description": "Route not found"
}
```

### 2) Erro de conexão com Mongo (`ServerSelectionTimeoutError`)

- Em execução local, use `MONGO_URL` apontando para `localhost`.
- Em container, use `MONGO_URL` apontando para `mongo`.

### 3) Falha de mount do Tempo (`not a directory`)

Use o bind correto de overrides:

- Host: `./overrides.yaml`
- Container: `/etc/tempo/tempo-overrides.yaml`

### 4) Cache não está funcionando

Verifique:

- `plugins` da rota contém `"cache"`
- Método é `GET`
- Resposta upstream é `200`
- Redis está acessível pelo `REDIS_URL`

## Limitações atuais e próximos passos sugeridos

- Secret JWT ainda fixo em código (`app/plugins/jwt_auth.py`): ideal mover para env/secret manager.
- Não há suíte de testes automatizados no repositório.

## Licença

Este projeto está licenciado sob a licença MIT. Consulte o arquivo [LICENSE](LICENSE).

