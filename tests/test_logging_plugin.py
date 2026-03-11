import pytest

from app.plugins.logging import RequestLoggingPlugin


@pytest.mark.asyncio
async def test_logging_plugin_logs_request_and_response_with_masking(make_context, make_response, monkeypatch):
	plugin = RequestLoggingPlugin()
	captured = []

	def fake_log_json(level, message, **extra):
		captured.append({"level": level, "message": message, "extra": extra})

	monkeypatch.setattr("app.plugins.logging.log_json", fake_log_json)

	context = make_context(
		route={
			"prefix": "/orders",
			"plugins": [{"type": "logging", "order": 1}],
		},
		method="POST",
		tenant="tenant-a",
	)
	context.extra["request_body"] = b'{"cpf":"12345678900","name":"Alice"}'

	config = {
		"log_request": True,
		"log_response": True,
		"mask_sensitive_enabled": True,
		"sensitive_fields": ["cpf"],
		"mask_value": "***",
	}

	async def call_next():
		return make_response(status=201, body=b'{"cpf":"98765432100","ok":true}')

	response = await plugin.around_request(context, call_next, config)

	assert response.status == 201
	assert len(captured) == 2

	req_log = captured[0]
	resp_log = captured[1]

	assert req_log["message"] == "gateway_request_input"
	assert '"cpf": "***"' in req_log["extra"]["request_body"]

	assert resp_log["message"] == "gateway_response_output"
	assert '"cpf": "***"' in resp_log["extra"]["response_body"]


@pytest.mark.asyncio
async def test_logging_plugin_can_log_only_response(make_context, make_response, monkeypatch):
	plugin = RequestLoggingPlugin()
	captured = []

	def fake_log_json(level, message, **extra):
		captured.append(message)

	monkeypatch.setattr("app.plugins.logging.log_json", fake_log_json)

	context = make_context(
		route={
			"prefix": "/orders",
			"plugins": [{"type": "logging", "order": 1}],
		},
		method="GET",
		tenant="tenant-b",
	)
	context.extra["request_body"] = b"{}"

	config = {
		"log_request": False,
		"log_response": True,
	}

	async def call_next():
		return make_response(status=200, body=b'{"ok":true}')

	await plugin.around_request(context, call_next, config)

	assert captured == ["gateway_response_output"]
