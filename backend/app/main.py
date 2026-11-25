from fastapi import FastAPI

from app.api.v1.anomaly import router as anomaly_router
from app.api.v1.assistant import router as assistant_router
from app.api.v1.network_health import router as health_router
from app.api.v1.simulator import router as simulator_router
from app.incidents.router import router as incidents_router
from app.inventory.router import router as inventory_router
from app.modules.simulator.guard import guard_demo_mutations
from app.webhooks.router import router as webhook_router

app = FastAPI(title="Nexus AI API", version="0.2.0")
app.middleware("http")(guard_demo_mutations)
for router in (inventory_router, webhook_router, incidents_router, anomaly_router, assistant_router, health_router, simulator_router):
    app.include_router(router, prefix="/api/v1")
