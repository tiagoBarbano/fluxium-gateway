"""Worker process that runs plugin code in a separate process.

Protocol (JSON lines on stdin/stdout):
- init: {"cmd":"init","code": "...python...", "config": {...}}
  responds: {"ok": true} or {"ok": false, "error": "..."}
- call: {"cmd":"call","hook":"before_request"|"after_response","context": {...}}
  responds: {"ok": true} or {"ok": false, "error": "..."}

This worker is intentionally minimal. It executes the plugin code in the
worker process and invokes methods synchronously (async functions are run
via `asyncio.run`).
"""
import sys
import json
import traceback
import asyncio


def send(resp):
    sys.stdout.write(json.dumps(resp) + "\n")
    sys.stdout.flush()


def safe_call(meth, context):
    try:
        if asyncio.iscoroutinefunction(meth):
            # run coroutine
            return {"ok": True, "result": asyncio.run(meth(context))}
        else:
            res = meth(context)
            return {"ok": True, "result": res}
    except Exception:
        return {"ok": False, "error": traceback.format_exc()}


def main():
    plugin_instance = None

    for raw in sys.stdin.buffer:
        try:
            line = raw.decode("utf-8").strip()
            if not line:
                continue
            msg = json.loads(line)
        except Exception:
            send({"ok": False, "error": "invalid json"})
            continue

        cmd = msg.get("cmd")
        if cmd == "init":
            code = msg.get("code", "")
            config = msg.get("config", {}) or {}
            try:
                ns = {}
                exec(code, ns)
                if "create_plugin" in ns and callable(ns["create_plugin"]):
                    plugin_instance = ns["create_plugin"](config)
                elif "Plugin" in ns and isinstance(ns["Plugin"], type):
                    plugin_instance = ns["Plugin"](config)
                else:
                    # fallback to first class
                    cls = None
                    for v in ns.values():
                        if isinstance(v, type):
                            cls = v
                            break
                    if cls is None:
                        send({"ok": False, "error": "no plugin class or factory found"})
                        continue
                    plugin_instance = cls(config)
                send({"ok": True})
            except Exception:
                send({"ok": False, "error": traceback.format_exc()})
            continue

        if cmd == "call":
            hook = msg.get("hook")
            context = msg.get("context", {})
            if not plugin_instance:
                send({"ok": False, "error": "plugin not initialized"})
                continue

            meth = getattr(plugin_instance, hook, None)
            if not callable(meth):
                send({"ok": False, "error": f"hook {hook} not found"})
                continue

            resp = safe_call(meth, context)
            send(resp)
            continue

        send({"ok": False, "error": "unknown command"})


if __name__ == "__main__":
    main()
