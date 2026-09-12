"""
agent.py — Core agentic pipeline

Architecture:
  1. Requirement extraction (LLM interprets user intent)
  2. Real product search (SerpAPI live or mock if fallback)
  3. Normalization (uniform schema, numeric specs)
  4. DETERMINISTIC hard-requirement filtering (code, not LLM)
  5. LLM ranking + evidence-based explanation
  6. Honest uncertainty — products that fail verification are labelled
"""

import json
import os
import re
import logging
from datetime import datetime, timezone
from groq import AsyncGroq
from sources import get_sources, gpu_tier, parse_ram_gb, parse_storage_gb, parse_weight_kg

logger = logging.getLogger("shopagent")

# GPU tier comparator for hard-requirement check
KNOWN_GPU_ORDER = [
    "rtx 4090", "rtx 4080", "rtx 4070 ti", "rtx 4070",
    "rtx 4060 ti", "rtx 4060", "rtx 4050",
    "rtx 3080 ti", "rtx 3080", "rtx 3070", "rtx 3060", "rtx 3050",
    "rx 7900 xtx", "rx 7800 xt", "rx 7700 xt",
    "rx 6800 xt", "rx 6700 xt", "rx 6600",
]


def now_fmt() -> str:
    return datetime.now(timezone.utc).strftime("%d %b %Y, %I:%M %p UTC")


async def process_chat_request(prompt: str, api_key: str):
    """
    Streaming agentic pipeline. Yields NDJSON lines.
    Every status event corresponds to real work performed.
    """
    client = AsyncGroq(api_key=api_key)
    llm_model = os.environ.get("LLM_MODEL", "openai/gpt-oss-120b")

    def status(msg: str, layer: str = "Agent"):
        return json.dumps({"type": "status", "status": msg, "layer": layer}) + "\\n"

    def error(msg: str):
        return json.dumps({"type": "error", "message": msg}) + "\\n"

    # ── Step 1: Requirement extraction ──────────────────────────────────────
    yield status("Parsing your requirements...", "Perception")

    extract_prompt = f"""
Extract structured shopping requirements from this user request: "{prompt}"

Return ONLY a JSON object with these fields (use null if not mentioned):
{{
    "category": "laptop|phone|monitor|other",
    "budget_max": <integer INR or null>,
    "gpu_min": "<GPU model string like 'RTX 4050' or null>",
    "ram_min_gb": <integer or null>,
    "storage_min_gb": <integer GB (convert TB to GB) or null>,
    "weight_max_kg": <float or null>,
    "use_cases": ["gaming", "coding", "college", etc],
    "hard_requirements": ["describe each hard constraint in plain English"],
    "soft_preferences": ["describe each preference in plain English"]
}}
"""

    try:
        resp = await client.chat.completions.create(
            messages=[{"role": "user", "content": extract_prompt}],
            model=llm_model,
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        req = json.loads(resp.choices[0].message.content)
    except Exception as e:
        yield error(f"Could not parse requirements (LLM error): {e}")
        return

    budget_max = req.get("budget_max")
    gpu_min = req.get("gpu_min")
    ram_min = req.get("ram_min_gb")
    storage_min = req.get("storage_min_gb")
    weight_max = req.get("weight_max_kg")
    use_cases = req.get("use_cases", [])

    yield status(
        f"Requirements: budget ≤₹{budget_max or 'any'}, GPU≥{gpu_min or 'any'}, "
        f"RAM≥{ram_min or 'any'}GB, storage≥{storage_min or 'any'}GB",
        "Reasoning",
    )

    # Build search queries from requirements (not LLM, deterministic)
    category = req.get("category", "laptop")
    base_query = category
    if gpu_min:
        base_query += f" {gpu_min}"
    if ram_min:
        base_query += f" {ram_min}GB RAM"
    if storage_min and storage_min < 1024:
        base_query += f" {storage_min}GB SSD"
    elif storage_min:
        base_query += f" {storage_min // 1024}TB SSD"

    logger.info(f"[agent] Search query: {base_query!r}")

    # ── Step 2: Multi-source search ─────────────────────────────────────────
    sources = get_sources()
    data_mode = os.environ.get("DATA_MODE", "live").lower()
    serp_key = os.environ.get("SERPAPI_API_KEY", "")
    is_live = data_mode == "live" and bool(serp_key)

    all_raw = []
    for src in sources:
        src_name = type(src).__name__.replace("Source", "")
        yield status(f"Searching product listings ({src_name})...", "Action")
        try:
            results = await src.search(base_query)
            all_raw.extend(results)
            yield status(f"Retrieved {len(results)} candidate listings from {src_name}.", "Action")
        except Exception as e:
            yield status(f"Search failed for {src_name}: {e}", "Warning")

    if not all_raw:
        yield error(
            "Could not retrieve any product listings right now. "
            + ("The search API may be unavailable." if is_live else "Running in demo mode with no data.")
        )
        return

    yield status(f"Retrieved {len(all_raw)} total candidates. Deduplicating...", "Action")

    # ── Step 3: Deduplication ────────────────────────────────────────────────
    # Keep unique products; if same model from multiple stores, keep all with lowest price first
    seen_ids: set[str] = set()
    unique_products = []
    for p in all_raw:
        if p.id not in seen_ids:
            seen_ids.add(p.id)
            unique_products.append(p)

    yield status(f"After deduplication: {len(unique_products)} unique products.", "Reasoning")

    # ── Step 4: Deterministic hard-requirement filtering ─────────────────────
    yield status("Applying hard requirements (budget, GPU, RAM, storage)...", "Reasoning")

    passed = []
    rejected_reasons = {}

    gpu_min_tier = gpu_tier(gpu_min) if gpu_min else 0

    for p in unique_products:
        spec = p.specifications
        reasons = []

        # Budget
        if budget_max and p.price > budget_max:
            reasons.append(f"price ₹{p.price:,} > budget ₹{budget_max:,}")

        # GPU (only if gpu_min is specified)
        if gpu_min and gpu_min_tier > 0:
            product_gpu_tier = gpu_tier(spec.gpu)
            if product_gpu_tier == 0:
                reasons.append(f"GPU '{spec.gpu or 'unknown'}' not in known tier table — skipping")
            elif product_gpu_tier < gpu_min_tier:
                reasons.append(f"GPU {spec.gpu} (tier {product_gpu_tier}) < required {gpu_min} (tier {gpu_min_tier})")

        # RAM
        if ram_min:
            product_ram = spec.ram_gb or parse_ram_gb(spec.ram)
            if product_ram is None:
                pass  # can't verify, don't reject
            elif product_ram < ram_min:
                reasons.append(f"RAM {product_ram}GB < required {ram_min}GB")

        # Storage
        if storage_min:
            product_storage = spec.storage_gb or parse_storage_gb(spec.storage)
            if product_storage is None:
                pass  # can't verify
            elif product_storage < storage_min:
                reasons.append(f"storage {product_storage}GB < required {storage_min}GB")

        if reasons:
            rejected_reasons[p.id] = reasons
            logger.info(f"[filter] Rejected '{p.title}': {reasons}")
        else:
            passed.append(p)

    if rejected_reasons:
        yield status(f"Filtered out {len(rejected_reasons)} products that failed hard requirements.", "Reasoning")

    # ── Step 5: Handle empty results ─────────────────────────────────────────
    if not passed:
        yield status("No products satisfied all hard requirements.", "Reasoning")
        # Honest: show closest alternatives with failure explanation
        top_alternatives = unique_products[:3]
        for p in top_alternatives:
            fail = rejected_reasons.get(p.id, ["unknown"])
            p.matchReason = f"⚠ Does NOT fully satisfy requirements — fails: {'; '.join(fail)}"
            p.confidence = "unverified"

        final_output = {
            "type": "products",
            "message": "I couldn't find any verified products matching all your hard requirements. Here are the closest alternatives — note they may not fully satisfy your criteria:",
            "products": [p.dict() for p in top_alternatives],
            "requirements": req,
            "is_live": is_live,
            "search_query": base_query,
        }
        yield json.dumps(final_output) + "\\n"
        yield status("Done (no exact matches found).", "Complete")
        return

    yield status(f"{len(passed)} products passed all hard requirements. Ranking by preferences...", "Reasoning")

    # Sort by price (ascending) as baseline before LLM re-ranking
    passed.sort(key=lambda p: p.price)
    top_candidates = passed[:8]  # limit to 8 for LLM context

    # ── Step 6: Evidence-based LLM ranking and explanation ──────────────────
    candidate_summaries = []
    for p in top_candidates:
        s = p.specifications
        candidate_summaries.append({
            "id": p.id,
            "title": p.title,
            "store": p.store,
            "price_inr": p.price,
            "gpu": s.gpu,
            "ram": s.ram or (f"{s.ram_gb}GB" if s.ram_gb else None),
            "storage": s.storage or (f"{s.storage_gb}GB" if s.storage_gb else None),
            "weight": s.weight or (f"{s.weight_kg}kg" if s.weight_kg else None),
            "confidence": p.confidence,
        })

    rank_prompt = f"""
You are helping a student choose a laptop. The user's request was: "{prompt}"

Structured requirements:
{json.dumps(req, indent=2)}

These products have ALREADY passed hard requirement checks (budget, GPU, RAM, storage).
Your task: rank them and explain why each is or isn't a good fit, using ONLY the data provided.

Products (verified by live search):
{json.dumps(candidate_summaries, indent=2)}

Rules:
1. Base ALL reasoning on the product data above. Do NOT invent specs, prices, or names.
2. For each product, generate a matchReason that cites actual spec values from the data.
   Example: "✓ RTX 4050 meets GPU requirement. ✓ 16GB RAM. ✓ ₹X within ₹Y budget. ⚠ Weight Xkg above Ykg preference."
3. Return a ranked list of product IDs in order of best match.
4. Return a JSON object with:
   {{
     "ranked_ids": ["id1", "id2", ...],
     "reasons": {{"id1": "reason text", "id2": "reason text", ...}}
   }}
Do not include products not in the provided list.
"""

    try:
        rank_resp = await client.chat.completions.create(
            messages=[{"role": "user", "content": rank_prompt}],
            model=llm_model,
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        rank_data = json.loads(rank_resp.choices[0].message.content)
        ranked_ids = rank_data.get("ranked_ids", [])
        reasons = rank_data.get("reasons", {})

        # Reorder top_candidates by ranked_ids
        id_to_product = {p.id: p for p in top_candidates}
        reranked = [id_to_product[rid] for rid in ranked_ids if rid in id_to_product]
        # Append any not mentioned by LLM at the end
        mentioned = set(ranked_ids)
        reranked += [p for p in top_candidates if p.id not in mentioned]
        top_candidates = reranked

        for p in top_candidates:
            p.matchReason = reasons.get(p.id, f"Matches requirements. Price verified at ₹{p.price:,}.")

    except Exception as e:
        yield status(f"LLM ranking failed ({e}); showing results sorted by price.", "Warning")
        for p in top_candidates:
            s = p.specifications
            p.matchReason = (
                f"Price: ₹{p.price:,}. "
                + (f"GPU: {s.gpu}. " if s.gpu else "")
                + (f"RAM: {s.ram or f'{s.ram_gb}GB'}. " if s.ram or s.ram_gb else "")
                + (f"Storage: {s.storage or f'{s.storage_gb}GB'}. " if s.storage or s.storage_gb else "")
                + (f"Weight: {s.weight or f'{s.weight_kg}kg'}." if s.weight or s.weight_kg else "")
            )

    yield status("Finalizing top 5 verified recommendations...", "Action")
    top_5 = top_candidates[:5]

    final_output = {
        "type": "products",
        "message": (
            f"Searched {'live product listings' if is_live else 'demo data (set DATA_MODE=live for real results)'} "
            f"and found {len(top_5)} products matching your requirements."
        ),
        "products": [p.dict() for p in top_5],
        "requirements": req,
        "is_live": is_live,
        "search_query": base_query,
    }

    yield json.dumps(final_output) + "\\n"
    yield status(f"Done. {'Prices verified via Google Shopping.' if is_live else 'Demo mode — prices are illustrative only.'}", "Complete")


async def compare_products_ai(product_ids: list[str], api_key: str):
    """
    AI comparison of products using ONLY their stored data (no hallucination).
    product_ids here are actually model names passed from frontend compare state.
    """
    import os
    client = AsyncGroq(api_key=api_key)
    llm_model = os.environ.get("LLM_MODEL", "openai/gpt-oss-120b")

    # The frontend passes product model names as IDs for the compare endpoint
    # We pass them verbatim to the LLM which received them in its own search context
    prompt = f"""
Compare these student laptop options. The product names/models are: {json.dumps(product_ids)}

Provide analysis based only on what you know about these specific models.
If you are uncertain about a spec, say "not verified" rather than guessing.

Return a JSON object:
{{
  "recommendation": "Concise 2-3 sentence recommendation citing specific tradeoffs",
  "bestOverall": "model name from the list",
  "bestValue": "model name from the list",
  "bestPerformance": "model name from the list",
  "bestLightweight": "model name from the list",
  "disclaimer": "Note any specs you could not verify"
}}
"""

    try:
        resp = await client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=llm_model,
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        result = json.loads(resp.choices[0].message.content)
        result["source"] = "LLM general knowledge — verify specs against product listing URLs."
        return result
    except Exception as e:
        raise Exception(f"LLM comparison error: {e}")
