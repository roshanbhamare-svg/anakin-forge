from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import os, logging
from dotenv import load_dotenv

load_dotenv()

from agent import process_chat_request, compare_products_ai
from memory import memory

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="ShopAgent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PromptRequest(BaseModel):
    prompt: str

class CompareRequest(BaseModel):
    productIds: list[str]

class TrackRequest(BaseModel):
    productId: str
    targetPrice: int
    productData: dict  # full product object from frontend state


@app.get("/api/health")
async def health():
    """Check configuration without exposing keys."""
    return {
        "status": "ok",
        "data_mode": os.getenv("DATA_MODE", "live"),
        "serpapi_configured": bool(os.getenv("SERPAPI_API_KEY")),
        "groq_configured": bool(os.getenv("GROQ_API_KEY")),
        "llm_model": os.getenv("LLM_MODEL", "openai/gpt-oss-120b"),
    }


@app.post("/api/find-laptops")
async def find_laptops(request: PromptRequest):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="LLM API key missing. Add GROQ_API_KEY to .env")

    return StreamingResponse(
        process_chat_request(request.prompt, api_key),
        media_type="application/x-ndjson",
    )


@app.post("/api/compare")
async def compare_products(request: CompareRequest):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="LLM API key missing. Add GROQ_API_KEY to .env")

    result = await compare_products_ai(request.productIds, api_key)
    return result


@app.post("/api/track")
async def track_product(request: TrackRequest):
    """
    Track a product for price drops.
    productData comes directly from the frontend's in-memory product object
    (which was retrieved from a real search), so we trust it as-is.
    """
    from models import Product, PriceTrack
    from datetime import datetime, timezone

    try:
        # Build a Product from the passed productData
        product = Product(**request.productData)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid product data: {e}")

    track = memory.add_to_watchlist(product, request.targetPrice, ["Amazon", "Flipkart"])
    return {"status": "success", "track": track.dict()}


@app.get("/api/watchlist")
async def get_watchlist():
    return {"watchlist": [t.dict() for t in memory.get_watchlist()]}


@app.get("/api/profile")
async def get_profile():
    return {"profile": memory.get_profile().dict()}


@app.get("/api/debug/last-search")
async def debug_last_search():
    """Developer endpoint: inspect the last search pipeline execution."""
    return memory.get_debug_info()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
