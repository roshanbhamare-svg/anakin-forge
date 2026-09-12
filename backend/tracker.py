"""
tracker.py — Price monitoring agent

The Simulate Price Drop button is for hackathon demo only.
It is clearly labelled in the UI as a simulation.

For real price monitoring, the architecture is:
  stored product URL → re-query SerpAPI → compare price → notify
"""
from memory import memory


class PriceTrackerAgent:

    @staticmethod
    async def simulate_price_drop_for_demo(product_id: str, new_price: int):
        """
        DEMO ONLY — simulates a price drop on a tracked product.
        Does NOT perform a real price check.
        Returns a notification dict if target is reached, else None.
        """
        track = memory.update_tracked_price(product_id, new_price)
        if track and track.status == "target_reached":
            return {
                "type": "notification",
                "message": (
                    f"🎯 Target price reached!\n\n"
                    f"{track.productName} is now ₹{track.currentPrice:,}, "
                    f"which is ₹{track.targetPrice - track.currentPrice:,} below your target of ₹{track.targetPrice:,}.\n\n"
                    f"[This is a demo simulation — open the product URL to verify the real price]"
                ),
            }
        return None


tracker = PriceTrackerAgent()
