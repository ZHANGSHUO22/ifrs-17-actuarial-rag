# backend/app/core/rate_limiter.py
import asyncio
import time
from collections import deque
from typing import Dict, Deque

class RateLimiter:
    """
    Sliding window rate limiter for debugging and production.
    """
    def __init__(self, requests_per_minute: int = 15):
        self.rate = requests_per_minute
        self.window = 60.0
        self.user_requests: Dict[str, Deque[float]] = {}
        self.lock = asyncio.Lock()

    async def check_limit(self, user_id: str) -> bool:
        """
        Returns True if the request is allowed, False otherwise.
        """
        async with self.lock:
            now = time.time()
            if user_id not in self.user_requests:
                self.user_requests[user_id] = deque()
            
            requests = self.user_requests[user_id]
            
            # Clean up old timestamps
            while requests and requests[0] <= now - self.window:
                requests.popleft()
            
            if len(requests) < self.rate:
                requests.append(now)
                return True
            return False

# Global instance for the application
global_limiter = RateLimiter(requests_per_minute=60) # Higher limit for Gemma Debugging
