from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class PricingInfo(BaseModel):
    current: int
    original: Optional[int] = None
    currency: str = "INR"
    price_type: str = "listed_price"  # listed_price | bank_offer | exchange | coupon | emi
    checked_at: str  # ISO timestamp

class SpecsInfo(BaseModel):
    processor: Optional[str] = None
    gpu: Optional[str] = None
    ram: Optional[str] = None
    ram_gb: Optional[int] = None
    storage: Optional[str] = None
    storage_gb: Optional[int] = None
    display: Optional[str] = None
    refreshRate: Optional[str] = None
    weight: Optional[str] = None
    weight_kg: Optional[float] = None

class VerificationInfo(BaseModel):
    price: bool = False
    url: bool = False
    specs: bool = False

class SourceInfo(BaseModel):
    name: str
    url: str
    retrieved_at: str

class Product(BaseModel):
    id: str
    title: str
    brand: str
    model: str

    store: str
    url: str

    # Legacy flat fields (kept for backward compat with frontend)
    price: int
    originalPrice: Optional[int] = None
    rating: Optional[float] = None
    reviewCount: Optional[int] = None
    availability: bool = True
    delivery: Optional[str] = None
    image: Optional[str] = None

    specifications: SpecsInfo

    # New enriched fields
    pricing: Optional[PricingInfo] = None
    verification: Optional[VerificationInfo] = None
    source: Optional[SourceInfo] = None
    confidence: str = "unverified"  # verified | partially_verified | unverified
    matchReason: Optional[str] = None

# Legacy alias for backward compat
Specifications = SpecsInfo

class Requirement(BaseModel):
    category: str
    maxPrice: Optional[int] = None
    budget_max: Optional[int] = None
    gpu: Optional[Dict[str, str]] = None
    gpu_min: Optional[str] = None
    ram: Optional[Dict[str, int]] = None
    ram_min_gb: Optional[int] = None
    storage: Optional[Dict[str, int]] = None
    storage_min_gb: Optional[int] = None
    weight: Optional[Dict[str, float]] = None
    weight_max_kg: Optional[float] = None
    useCases: List[str] = Field(default_factory=list)
    use_cases: List[str] = Field(default_factory=list)
    hardRequirements: List[str] = Field(default_factory=list)
    softPreferences: List[str] = Field(default_factory=list)

class StudentProfile(BaseModel):
    budgetPreference: str = "Medium"
    priorities: List[str] = Field(default_factory=list)
    minimumRam: Optional[int] = None
    preferredGpu: Optional[str] = None
    preferredBrands: List[str] = Field(default_factory=list)
    avoid: List[str] = Field(default_factory=list)

class PriceTrack(BaseModel):
    productId: str
    productName: str
    targetPrice: int
    currentPrice: int
    stores: List[str]
    status: str = "tracking"
    lastChecked: str
