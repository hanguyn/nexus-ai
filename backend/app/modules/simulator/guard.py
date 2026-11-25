from os import environ

from fastapi import Request
from fastapi.responses import JSONResponse

INVENTORY = {"sites", "devices", "dependencies"}
READ_METHODS = {"GET", "HEAD", "OPTIONS"}


def demo_read_only() -> bool:
    return environ.get("DEMO_READ_ONLY_MODE", "").strip().lower() in {"1", "true", "yes", "on"}


async def guard_demo_mutations(request: Request, call_next):
    if demo_read_only() and request.method not in READ_METHODS:
        segments = request.url.path.strip("/").split("/")
        if segments[:2] == ["api", "v1"]:
            inventory_write = len(segments) >= 3 and segments[2] in INVENTORY
            public_webhook = (
                segments[2:] == ["webhooks", "alertmanager"]
                and request.headers.get("x-nexus-public-proxy") == "1"
            )
            if inventory_write or public_webhook:
                return JSONResponse(status_code=403, content={"detail": "This operation is blocked in read-only demo mode."})
    return await call_next(request)
