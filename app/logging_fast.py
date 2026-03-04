import sys
import orjson
from datetime import datetime

def log_json(level, message, **extra):
    record = {
        "level": level,
        "message": message,
        "time": datetime.utcnow().isoformat(),
        **extra,
    }
    sys.stdout.buffer.write(orjson.dumps(record) + b"\n")