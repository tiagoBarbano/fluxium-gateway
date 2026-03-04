FROM python:3.13-slim

# Instala uv
RUN pip install uv
RUN mkdir -p /tmp/prometheus

WORKDIR /app

# Copia apenas arquivos de dependência primeiro (melhor cache)
COPY pyproject.toml .

# Cria ambiente e instala deps
RUN uv venv && \
    . .venv/bin/activate && \
    uv pip install --system .

# Copia aplicação
COPY app ./app

CMD ["granian", "--interface", "asgi", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]