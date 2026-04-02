FROM python:3.13-slim

RUN pip install uv
RUN mkdir -p /tmp/prometheus

WORKDIR /app

COPY pyproject.toml ./

RUN uv venv && \
    . .venv/bin/activate && \
    uv pip install --system .

COPY app ./app
COPY openapi.json ./openapi.json

CMD ["granian", "--interface", "asgi", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
