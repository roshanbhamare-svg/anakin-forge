"""
sources.py — Product search adapters

DATA_MODE env var controls which source is used:
  live (default when SERPAPI_API_KEY is set): Google Shopping via SerpAPI
  mock: hardcoded development data, clearly labelled as non-live

Architecture:
  ProductSource (abstract)
  ├── SerpApiLiveSource   ← real Google Shopping data
  └── MockSource          ← development/testing only, clearly labelled
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from models import Product, SpecsInfo, PricingInfo, VerificationInfo, SourceInfo
from datetime import datetime, timezone
import os
import re
import hashlib


# ---------------------------------------------------------------------------
# GPU tier table for deterministic comparison
# Higher number = more powerful
# ---------------------------------------------------------------------------
GPU_TIERS: dict[str, int] = {
    # NVIDIA RTX 40 series
    "rtx 4090": 100, "rtx 4080": 90, "rtx 4070 ti": 85, "rtx 4070": 80,
    "rtx 4060 ti": 72, "rtx 4060": 65, "rtx 4050": 55,
    # NVIDIA RTX 30 series
    "rtx 3080 ti": 88, "rtx 3080": 82, "rtx 3070 ti": 76, "rtx 3070": 70,
    "rtx 3060 ti": 60, "rtx 3060": 52, "rtx 3050 ti": 42, "rtx 3050": 38,
    # AMD RX 7000
    "rx 7900 xtx": 98, "rx 7900 xt": 92, "rx 7800 xt": 78, "rx 7700 xt": 66,
    "rx 7600": 54,
    # AMD RX 6000
    "rx 6800 xt": 80, "rx 6800": 75, "rx 6700 xt": 64, "rx 6700": 58,
    "rx 6600 xt": 48, "rx 6600": 44, "rx 6500m": 30, "rx 6500 xt": 28,
    # Intel Arc
    "arc a770": 50, "arc a750": 45, "arc a380": 22,
    # Apple
    "m3 max gpu": 68, "m3 pro gpu": 52, "m3 gpu": 40,
    "m2 max gpu": 62, "m2 pro gpu": 46, "m2 gpu": 34,
    "m1 max gpu": 58, "m1 pro gpu": 42, "m1 gpu": 30, "7-core gpu": 28,
}


def gpu_tier(gpu_str: Optional[str]) -> int:
    """Return numeric GPU tier from a string like 'NVIDIA RTX 4050'."""
    if not gpu_str:
        return 0
    s = gpu_str.lower()
    for key, tier in GPU_TIERS.items():
        if key in s:
            return tier
    return 0


def parse_ram_gb(ram_str: Optional[str]) -> Optional[int]:
    """Parse '16GB DDR5' → 16"""
    if not ram_str:
        return None
    m = re.search(r"(\d+)\s*gb", ram_str, re.IGNORECASE)
    return int(m.group(1)) if m else None


def parse_storage_gb(storage_str: Optional[str]) -> Optional[int]:
    """Parse '512GB SSD' → 512, '1TB SSD' → 1024"""
    if not storage_str:
        return None
    s = storage_str.lower()
    m = re.search(r"(\d+(?:\.\d+)?)\s*tb", s)
    if m:
        return int(float(m.group(1)) * 1024)
    m = re.search(r"(\d+)\s*gb", s)
    if m:
        return int(m.group(1))
    return None


def parse_weight_kg(weight_str: Optional[str]) -> Optional[float]:
    """Parse '2.4kg' → 2.4"""
    if not weight_str:
        return None
    m = re.search(r"([\d.]+)\s*kg", weight_str, re.IGNORECASE)
    return float(m.group(1)) if m else None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id(store: str, title: str) -> str:
    raw = f"{store.lower()}-{title.lower()}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------
class ProductSource(ABC):
    @abstractmethod
    async def search(self, query: str) -> List[Product]:
        pass


# ---------------------------------------------------------------------------
# LIVE SOURCE — Google Shopping via SerpAPI
# ---------------------------------------------------------------------------
class SerpApiLiveSource(ProductSource):
    """
    Fetches real product listings from Google Shopping.
    Prices, URLs and titles come directly from the retrieved JSON — never invented.
    """

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def search(self, query: str) -> List[Product]:
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_search, query)

    def _sync_search(self, query: str) -> List[Product]:
        from serpapi import GoogleSearch

        params = {
            "engine": "google_shopping",
            "q": query,
            "gl": "in",
            "hl": "en",
            "api_key": self.api_key,
        }
        try:
            results = GoogleSearch(params).get_dict()
        except Exception as e:
            print(f"[SerpAPI] Search error: {e}")
            return []

        if "error" in results:
            print(f"[SerpAPI] API returned error: {results['error']}")
            return []

        raw = results.get("shopping_results", [])
        products = []
        retrieved_at = now_iso()

        for item in raw:
            extracted_price = item.get("extracted_price")
            if not extracted_price:
                continue  # skip listings with no parseable price

            title = item.get("title", "Unknown")
            source_name = item.get("source", "Unknown Store")
            url = item.get("link") or item.get("product_link") or ""
            delivery = item.get("delivery", "")
            rating = item.get("rating")
            review_count = item.get("reviews")
            thumbnail = item.get("thumbnail", "")

            # Only use listings from known Indian retailers for relevance
            store = self._normalize_store(source_name)

            specs = self._extract_specs_from_title(title)
            pid = stable_id(store, title)

            pricing = PricingInfo(
                current=int(extracted_price),
                original=None,
                currency="INR",
                price_type="listed_price",
                checked_at=retrieved_at,
            )

            verification = VerificationInfo(
                price=True,   # extracted from live source
                url=bool(url),
                specs=False,  # specs inferred from title, not from spec sheet
            )

            product = Product(
                id=pid,
                title=title,
                brand=self._extract_brand(title),
                model=self._extract_model(title),
                store=store,
                url=url,
                price=int(extracted_price),
                originalPrice=None,
                rating=float(rating) if rating else None,
                reviewCount=int(review_count) if review_count else None,
                availability=True,
                delivery=delivery or None,
                image=thumbnail or None,
                specifications=specs,
                pricing=pricing,
                verification=verification,
                source=SourceInfo(
                    name=source_name,
                    url=url,
                    retrieved_at=retrieved_at,
                ),
                confidence="partially_verified",  # price verified, specs inferred
            )
            products.append(product)

        return products

    def _normalize_store(self, source: str) -> str:
        s = source.lower()
        if "amazon" in s:
            return "Amazon"
        if "flipkart" in s:
            return "Flipkart"
        if "croma" in s:
            return "Croma"
        if "reliance" in s:
            return "Reliance Digital"
        if "vijay" in s:
            return "Vijay Sales"
        if "tata" in s or "cliq" in s:
            return "Tata Cliq"
        if "myntra" in s:
            return "Myntra"
        return source.title()

    def _extract_brand(self, title: str) -> str:
        brands = ["Lenovo", "ASUS", "Acer", "HP", "Dell", "Apple", "MSI",
                  "Samsung", "Gigabyte", "Razer", "LG", "Microsoft"]
        for b in brands:
            if b.lower() in title.lower():
                return b
        return title.split()[0] if title else "Unknown"

    def _extract_model(self, title: str) -> str:
        # Return first ~5 words as model approximation
        return " ".join(title.split()[:5])

    def _extract_specs_from_title(self, title: str) -> SpecsInfo:
        """
        Best-effort extraction from title string.
        All fields marked as verified=False because they come from the title, not spec sheet.
        """
        t = title.lower()

        # RAM — handle formats like '16GB DDR5', '16GB LPDDR5', '16 GB RAM'
        # Explicitly EXCLUDE GPU VRAM patterns (e.g. '6GB GDDR6')
        ram_str = None
        ram_gb = None
        # Remove GPU VRAM patterns first to avoid confusion
        t_no_gddr = re.sub(r"\d+\s*GB\s*GDDR\d", "", t, flags=re.IGNORECASE)
        # Now search for RAM: number followed by GB optionally followed by DDR/LPDDR or RAM
        m = re.search(r"(\d+)\s*GB(?:\s*(?:LPDDR\d+|DDR\d+|RAM))?(?=\s|$|[,;|/])", t_no_gddr, re.IGNORECASE)
        if m:
            candidate = int(m.group(1))
            # Sanity check: system RAM is typically 4/8/12/16/24/32/48/64GB
            if candidate in [4, 8, 12, 16, 24, 32, 48, 64]:
                ram_gb = candidate
                ram_str = f"{ram_gb}GB"

        # Storage
        storage_str = None
        storage_gb = None
        m_tb = re.search(r"(\d+(?:\.\d+)?)\s*tb", t)
        m_gb = re.search(r"(\d+)\s*gb\s*(?:ssd|nvme|hdd)", t)
        if m_tb:
            storage_gb = int(float(m_tb.group(1)) * 1024)
            storage_str = f"{m_tb.group(1)}TB SSD"
        elif m_gb:
            storage_gb = int(m_gb.group(1))
            storage_str = f"{storage_gb}GB SSD"

        # GPU
        gpu_str = None
        gpu_patterns = [
            r"(rtx\s*\d{4}(?:\s*ti)?)",
            r"(gtx\s*\d{4}(?:\s*ti)?)",
            r"(rx\s*\d{4}(?:\s*xt)?)",
            r"(arc\s*a\d{3})",
            r"(m[123]\s*(?:max|pro)?)\s*gpu",
        ]
        for pat in gpu_patterns:
            m = re.search(pat, t)
            if m:
                gpu_str = m.group(1).upper().replace("  ", " ").strip()
                break

        # Display
        display_str = None
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:inch|\")", t)
        if m:
            display_str = f"{m.group(1)} inch"

        # Weight — rarely in title but try
        weight_str = None
        weight_kg = None
        m = re.search(r"([\d.]+)\s*kg", t)
        if m:
            weight_kg = float(m.group(1))
            weight_str = f"{weight_kg}kg"

        return SpecsInfo(
            processor=None,   # cannot reliably extract CPU from short title
            gpu=gpu_str,
            ram=ram_str,
            ram_gb=ram_gb,
            storage=storage_str,
            storage_gb=storage_gb,
            display=display_str,
            weight=weight_str,
            weight_kg=weight_kg,
        )


# ---------------------------------------------------------------------------
# MOCK SOURCE — Development/testing only, clearly labelled
# ---------------------------------------------------------------------------
MOCK_LAPTOPS = [
    {
        "model": "Lenovo LOQ 15IRX9",
        "brand": "Lenovo",
        "price_amazon": 109990,
        "price_flipkart": 107990,
        "specs": {
            "processor": "Intel Core i5-13450HX",
            "gpu": "NVIDIA RTX 4050",
            "ram": "16GB", "ram_gb": 16,
            "storage": "512GB SSD", "storage_gb": 512,
            "display": "15.6 FHD 144Hz",
            "weight": "2.4kg", "weight_kg": 2.4,
        },
        "tags": ["gaming", "coding", "performance"],
        "url_amazon": "https://www.amazon.in/dp/B0D1234567",
        "url_flipkart": "https://www.flipkart.com/lenovo-loq-15irx9",
    },
    {
        "model": "ASUS TUF Gaming F15",
        "brand": "ASUS",
        "price_amazon": 87990,
        "price_flipkart": 85990,
        "specs": {
            "processor": "Intel Core i5-12500H",
            "gpu": "NVIDIA RTX 4050",
            "ram": "16GB", "ram_gb": 16,
            "storage": "512GB SSD", "storage_gb": 512,
            "display": "15.6 FHD 144Hz",
            "weight": "2.2kg", "weight_kg": 2.2,
        },
        "tags": ["gaming", "portability", "coding"],
        "url_amazon": "https://www.amazon.in/dp/B0C1234568",
        "url_flipkart": "https://www.flipkart.com/asus-tuf-gaming-f15",
    },
    {
        "model": "Acer Nitro V 15",
        "brand": "Acer",
        "price_amazon": 79990,
        "price_flipkart": 77990,
        "specs": {
            "processor": "Intel Core i5-13420H",
            "gpu": "NVIDIA RTX 4050",
            "ram": "16GB", "ram_gb": 16,
            "storage": "512GB SSD", "storage_gb": 512,
            "display": "15.6 FHD 144Hz",
            "weight": "2.5kg", "weight_kg": 2.5,
        },
        "tags": ["gaming", "storage", "coding"],
        "url_amazon": "https://www.amazon.in/dp/B0E1234569",
        "url_flipkart": "https://www.flipkart.com/acer-nitro-v-15",
    },
    {
        "model": "Apple MacBook Air M2",
        "brand": "Apple",
        "price_amazon": 99990,
        "price_flipkart": 97990,
        "specs": {
            "processor": "Apple M2",
            "gpu": "8-core GPU",
            "ram": "8GB", "ram_gb": 8,
            "storage": "256GB SSD", "storage_gb": 256,
            "display": "13.6 Liquid Retina",
            "weight": "1.24kg", "weight_kg": 1.24,
        },
        "tags": ["coding", "college", "battery", "lightweight", "portability"],
        "url_amazon": "https://www.amazon.in/dp/B0B1234560",
        "url_flipkart": "https://www.flipkart.com/apple-macbook-air-m2",
    },
    {
        "model": "HP Victus 15 Gaming",
        "brand": "HP",
        "price_amazon": 74990,
        "price_flipkart": 72990,
        "specs": {
            "processor": "AMD Ryzen 5 7535HS",
            "gpu": "NVIDIA RTX 4050",
            "ram": "16GB", "ram_gb": 16,
            "storage": "512GB SSD", "storage_gb": 512,
            "display": "15.6 FHD 144Hz",
            "weight": "2.29kg", "weight_kg": 2.29,
        },
        "tags": ["gaming", "budget", "coding"],
        "url_amazon": "https://www.amazon.in/dp/B0D1234561",
        "url_flipkart": "https://www.flipkart.com/hp-victus-15",
    },
]


class MockSource(ProductSource):
    """
    ⚠ MOCK MODE — Development/testing data only.
    Prices and URLs in this source are NOT verified from live stores.
    Set DATA_MODE=live to use real SerpAPI data.
    """

    def __init__(self, store_name: str, price_key: str, url_key: str):
        self.store_name = store_name
        self.price_key = price_key
        self.url_key = url_key

    async def search(self, query: str) -> List[Product]:
        q = query.lower()
        results = []
        retrieved_at = now_iso()

        for l in MOCK_LAPTOPS:
            if (q in l["model"].lower() or q in l["brand"].lower() or
                    any(q in t for t in l["tags"]) or
                    "laptop" in q or "gaming" in q):

                specs_raw = l["specs"]
                pid = stable_id(self.store_name, l["model"])
                price = l[self.price_key]
                url = l[self.url_key]
                specs = SpecsInfo(
                    processor=specs_raw.get("processor"),
                    gpu=specs_raw.get("gpu"),
                    ram=specs_raw.get("ram"),
                    ram_gb=specs_raw.get("ram_gb"),
                    storage=specs_raw.get("storage"),
                    storage_gb=specs_raw.get("storage_gb"),
                    display=specs_raw.get("display"),
                    weight=specs_raw.get("weight"),
                    weight_kg=specs_raw.get("weight_kg"),
                )
                product = Product(
                    id=pid,
                    title=f"[DEMO] {l['brand']} {l['model']} ({specs_raw['ram']}, {specs_raw['storage']})",
                    brand=l["brand"],
                    model=l["model"],
                    store=self.store_name,
                    url=url,
                    price=price,
                    originalPrice=price + 5000,
                    rating=4.3,
                    reviewCount=1200,
                    availability=True,
                    delivery="2-3 days",
                    specifications=specs,
                    pricing=PricingInfo(
                        current=price,
                        original=price + 5000,
                        currency="INR",
                        price_type="listed_price",
                        checked_at=retrieved_at,
                    ),
                    verification=VerificationInfo(
                        price=False,   # NOT verified from live store
                        url=False,     # NOT verified
                        specs=True,    # specs are explicitly set
                    ),
                    source=SourceInfo(
                        name=f"{self.store_name} (Demo)",
                        url=url,
                        retrieved_at=retrieved_at,
                    ),
                    confidence="unverified",
                )
                results.append(product)
        return results


class AmazonMockSource(MockSource):
    def __init__(self):
        super().__init__("Amazon", "price_amazon", "url_amazon")


class FlipkartMockSource(MockSource):
    def __init__(self):
        super().__init__("Flipkart", "price_flipkart", "url_flipkart")


# ---------------------------------------------------------------------------
# Factory — picks source based on DATA_MODE env var
# ---------------------------------------------------------------------------
def get_sources() -> list[ProductSource]:
    """
    Returns configured product sources.
    - DATA_MODE=live + SERPAPI_API_KEY set → SerpApiLiveSource
    - Otherwise → MockSource (clearly labelled)
    """
    data_mode = os.environ.get("DATA_MODE", "live").lower()
    serp_key = os.environ.get("SERPAPI_API_KEY", "")

    if data_mode == "live" and serp_key:
        return [SerpApiLiveSource(api_key=serp_key)]
    else:
        print("[sources] ⚠ Running in MOCK mode. Set DATA_MODE=live and SERPAPI_API_KEY for real data.")
        return [AmazonMockSource(), FlipkartMockSource()]
