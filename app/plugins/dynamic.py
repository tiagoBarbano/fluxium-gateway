"""Dynamic plugin loader from Mongo plugin documents.

This module supports two loading modes:
- For `phase == 'forward'` plugins we instantiate in-process (same as
  previous behaviour) because `around_request` requires calling `call_next`.
- For `phase == 'before_after'` plugins we spawn a worker subprocess that
  executes the plugin code; the main process communicates via stdin/stdout
  JSON lines. This isolates execution and reduces blast radius.

Plugin documents should contain keys: `type`, `code`, `enabled` (optional),
`config` (optional), and may include `phase`.
"""

from typing import List, Dict, Any
import traceback
import asyncio
import json
import sys
from app.logging_fast import log_json


class SubprocessProxyPlugin:
    """Proxy that talks to a plugin worker process over stdin/stdout.

    The worker runs the plugin code and executes hooks on request. Only
    `before_request` and `after_response` are proxied here.
    """

    def __init__(self, ptype: str, code: str, config: Dict[str, Any]):
        self.type = ptype
        self._code = code
        self._config = config or {}
        self.name = ptype
        self.phase = "before_after"
        self._proc = None
        self._lock = asyncio.Lock()

    async def _ensure_proc(self):
        if self._proc and self._proc.returncode is None:
            return
        # spawn worker module in unbuffered mode
        self._proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-u",
            "-m",
            "app.plugins.plugin_worker",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # send init message
        init_msg = {"cmd": "init", "code": self._code, "config": self._config}
        await self._send(init_msg)

    async def _send(self, msg: Dict[str, Any]):
        data = (json.dumps(msg) + "\n").encode("utf-8")
        self._proc.stdin.write(data)
        await self._proc.stdin.drain()
        # read response line
        line = await self._proc.stdout.readline()
        if not line:
            raise RuntimeError("plugin worker closed")
        try:
            return json.loads(line.decode("utf-8"))
        except Exception as e:
            raise RuntimeError(f"invalid response from plugin worker: {e}")

    async def before_request(self, context):
        async with self._lock:
            await self._ensure_proc()
            payload = {
                "cmd": "call",
                "hook": "before_request",
                "context": {
                    "route": getattr(context, "route", {}) or {},
                    "tenant": getattr(context, "tenant", None),
                },
            }
            resp = await self._send(payload)
            if not resp.get("ok"):
                raise RuntimeError(resp.get("error") or "plugin error")

    async def after_response(self, context):
        async with self._lock:
            await self._ensure_proc()
            payload = {
                "cmd": "call",
                "hook": "after_response",
                "context": {
                    "route": getattr(context, "route", {}) or {},
                    "tenant": getattr(context, "tenant", None),
                },
            }
            resp = await self._send(payload)
            if not resp.get("ok"):
                raise RuntimeError(resp.get("error") or "plugin error")


async def build_plugin_instances(plugin_docs: List[Dict]) -> Dict[str, object]:
    """Compile and instantiate plugin documents asynchronously.

    Returns mapping of plugin_type -> plugin_instance for enabled plugins.
    """
    instances: Dict[str, object] = {}

    for doc in plugin_docs:
        try:
            if not doc.get("enabled", True):
                continue

            ptype = doc.get("type")
            src = doc.get("code", "")
            config = doc.get("config", {}) or {}
            phase = doc.get("phase", "before_after")

            if not ptype or not src:
                log_json("WARN", "plugin_doc_invalid", type=ptype)
                continue

            if phase == "forward":
                # instantiate in-process to support around_request semantics
                namespace: Dict[str, Any] = {}
                exec(src, namespace)
                if "create_plugin" in namespace and callable(namespace["create_plugin"]):
                    inst = namespace["create_plugin"](config)
                elif "Plugin" in namespace and isinstance(namespace.get("Plugin"), type):
                    inst = namespace["Plugin"](config)
                else:
                    # fallback to first class
                    cls = None
                    for v in namespace.values():
                        if isinstance(v, type):
                            cls = v
                            break
                    if cls is None:
                        log_json("WARN", "no_plugin_class_found", type=ptype)
                        continue
                    inst = cls(config)
                instances[ptype] = inst
                log_json("INFO", "loaded_plugin_from_db", type=ptype, name=doc.get("name"))
                continue

            # For before_after plugins, spawn a subprocess to sandbox execution
            proxy = SubprocessProxyPlugin(ptype, src, config)
            instances[ptype] = proxy
            log_json("INFO", "loaded_plugin_from_db_sandboxed", type=ptype, name=doc.get("name"))

        except Exception:
            log_json("ERROR", "plugin_load_failed", type=doc.get("type"), error=traceback.format_exc())

    return instances
