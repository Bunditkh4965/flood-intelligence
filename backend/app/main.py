from fastapi import FastAPI

from app.api.branches import router as branches_router

app = FastAPI(title="Flood Intelligence Platform", version="0.1.0")
app.include_router(branches_router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
