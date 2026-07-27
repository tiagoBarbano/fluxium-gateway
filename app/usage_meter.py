from datetime import datetime, timezone

from app.config_store import client


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _day_key(dt: datetime | None = None) -> str:
    now = dt or _utcnow()
    return now.strftime("%Y-%m-%d")


usage_collection = client.core.tenant_usage_metrics


async def record_gateway_request(tenant_id: str, amount: int = 1):
    normalized_tenant_id = str(tenant_id or "").strip()
    if not normalized_tenant_id:
        return

    await usage_collection.update_one(
        {"tenant_id": normalized_tenant_id, "day": _day_key()},
        {
            "$inc": {"metrics.gateway_requests": int(amount)},
            "$set": {"updated_at": _utcnow(), "last_source": "gateway"},
            "$setOnInsert": {
                "tenant_id": normalized_tenant_id,
                "day": _day_key(),
                "created_at": _utcnow(),
            },
        },
        upsert=True,
    )