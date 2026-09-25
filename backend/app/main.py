from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core import get_settings

from app.api.branches import router as branches_router
from app.api.flood_reports import router as flood_reports_router
from app.api.gistda import router as gistda_router
from app.api.flood_impact import router as flood_impact_router
from app.api.public_flood_impact import router as public_flood_impact_router
from app.api.branch_flood_situation import router as branch_flood_situation_router

app = FastAPI(title="Flood Intelligence Platform", version="0.1.0")
origins = [origin.strip() for origin in get_settings().cors_allowed_origins.split(",") if origin.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
app.include_router(branches_router)
app.include_router(flood_reports_router)
app.include_router(gistda_router)
app.include_router(flood_impact_router)
app.include_router(public_flood_impact_router)
app.include_router(branch_flood_situation_router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
