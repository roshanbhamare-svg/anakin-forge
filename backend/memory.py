from typing import List, Dict, Optional, Any
from models import StudentProfile, PriceTrack, Product
from datetime import datetime, timezone


class MemoryStore:
    def __init__(self):
        self.profile = StudentProfile()
        self.watchlist: Dict[str, PriceTrack] = {}
        self._debug_info: Dict[str, Any] = {}

    def get_profile(self) -> StudentProfile:
        return self.profile

    def update_profile(self, new_data: dict) -> StudentProfile:
        for k, v in new_data.items():
            if hasattr(self.profile, k):
                setattr(self.profile, k, v)
        return self.profile

    def add_to_watchlist(self, product: Product, target_price: int, stores: List[str]) -> PriceTrack:
        track = PriceTrack(
            productId=product.id,
            productName=f"{product.brand} {product.model}",
            targetPrice=target_price,
            currentPrice=product.price,
            stores=stores,
            lastChecked=datetime.now(timezone.utc).isoformat(),
        )
        self.watchlist[product.id] = track
        return track

    def get_watchlist(self) -> List[PriceTrack]:
        return list(self.watchlist.values())

    def update_tracked_price(self, product_id: str, current_price: int) -> Optional[PriceTrack]:
        if product_id in self.watchlist:
            self.watchlist[product_id].currentPrice = current_price
            self.watchlist[product_id].lastChecked = datetime.now(timezone.utc).isoformat()
            if current_price <= self.watchlist[product_id].targetPrice:
                self.watchlist[product_id].status = "target_reached"
            return self.watchlist[product_id]
        return None

    def store_debug_info(self, info: Dict[str, Any]):
        self._debug_info = info

    def get_debug_info(self) -> Dict[str, Any]:
        return self._debug_info


# Global instance
memory = MemoryStore()
