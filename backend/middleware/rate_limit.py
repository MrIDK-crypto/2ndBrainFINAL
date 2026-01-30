"""
Rate Limiting Middleware
Per-tenant rate limiting to prevent abuse and control costs.
"""

import time
from typing import Dict, Optional, Tuple
from functools import wraps
from flask import request, jsonify, g
from datetime import datetime, timedelta
import threading


class RateLimiter:
    """
    Simple in-memory rate limiter with sliding window algorithm.
    For production, use Redis for distributed rate limiting.
    """

    def __init__(self):
        self._requests: Dict[str, list] = {}  # tenant_id -> list of timestamps
        self._lock = threading.Lock()

    def is_allowed(
        self,
        tenant_id: str,
        limit: int = 100,
        window_seconds: int = 60
    ) -> Tuple[bool, Optional[int]]:
        """
        Check if request is allowed for tenant.
        Returns (is_allowed, retry_after_seconds)
        """
        now = time.time()
        window_start = now - window_seconds

        with self._lock:
            # Get request timestamps for this tenant
            if tenant_id not in self._requests:
                self._requests[tenant_id] = []

            timestamps = self._requests[tenant_id]

            # Remove timestamps outside the window
            timestamps[:] = [ts for ts in timestamps if ts > window_start]

            # Check if limit exceeded
            if len(timestamps) >= limit:
                # Calculate retry after (time until oldest request expires)
                retry_after = int(timestamps[0] - window_start) + 1
                return False, retry_after

            # Add current timestamp
            timestamps.append(now)

            return True, None

    def cleanup(self, max_age_seconds: int = 3600):
        """Remove old entries to prevent memory leak"""
        now = time.time()
        cutoff = now - max_age_seconds

        with self._lock:
            for tenant_id in list(self._requests.keys()):
                timestamps = self._requests[tenant_id]
                timestamps[:] = [ts for ts in timestamps if ts > cutoff]

                # Remove tenant if no recent requests
                if not timestamps:
                    del self._requests[tenant_id]


# Global rate limiter instance
_rate_limiter = RateLimiter()


# ============================================================================
# RATE LIMIT DECORATORS
# ============================================================================

def rate_limit(
    limit: int = 100,
    window_seconds: int = 60,
    error_message: Optional[str] = None
):
    """
    Decorator to add rate limiting to Flask routes.

    Usage:
        @rate_limit(limit=50, window_seconds=60)
        @jwt_required()
        def my_endpoint():
            pass

    Args:
        limit: Maximum requests per window
        window_seconds: Time window in seconds
        error_message: Custom error message
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            # Get tenant ID from Flask g object (set by JWT decorator)
            tenant_id = getattr(g, 'tenant_id', None)

            if not tenant_id:
                # If no tenant ID, don't rate limit (will fail auth anyway)
                return f(*args, **kwargs)

            # Check rate limit
            is_allowed, retry_after = _rate_limiter.is_allowed(
                tenant_id,
                limit=limit,
                window_seconds=window_seconds
            )

            if not is_allowed:
                message = error_message or f"Rate limit exceeded. Maximum {limit} requests per {window_seconds} seconds."

                return jsonify({
                    "success": False,
                    "error": message,
                    "error_code": "RATE_LIMIT_EXCEEDED",
                    "retry_after": retry_after
                }), 429

            return f(*args, **kwargs)

        return decorated
    return decorator


# ============================================================================
# TIER-BASED RATE LIMITS
# ============================================================================

# Rate limits by tenant plan
RATE_LIMITS = {
    "free": {
        "search": (20, 60),        # 20 searches per minute
        "sync": (5, 3600),          # 5 syncs per hour
        "gap_analysis": (3, 3600),  # 3 analyses per hour
        "video": (2, 86400),        # 2 videos per day
        "general": (100, 60)        # 100 requests per minute
    },
    "starter": {
        "search": (50, 60),
        "sync": (10, 3600),
        "gap_analysis": (10, 3600),
        "video": (10, 86400),
        "general": (300, 60)
    },
    "professional": {
        "search": (100, 60),
        "sync": (20, 3600),
        "gap_analysis": (20, 3600),
        "video": (50, 86400),
        "general": (600, 60)
    },
    "enterprise": {
        "search": (500, 60),
        "sync": (100, 3600),
        "gap_analysis": (100, 3600),
        "video": (200, 86400),
        "general": (2000, 60)
    }
}


def get_tenant_plan_rate_limit(tenant_plan: str, action: str) -> Tuple[int, int]:
    """
    Get rate limit for tenant plan and action.
    Returns (limit, window_seconds)
    """
    plan = tenant_plan.lower() if tenant_plan else "free"

    if plan not in RATE_LIMITS:
        plan = "free"

    limits = RATE_LIMITS[plan]
    return limits.get(action, limits["general"])


def rate_limit_by_plan(action: str = "general"):
    """
    Decorator to apply tier-based rate limiting based on tenant plan.

    Usage:
        @rate_limit_by_plan("search")
        @jwt_required()
        def search_endpoint():
            pass
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            from database.config import get_db
            from database.models import Tenant

            tenant_id = getattr(g, 'tenant_id', None)
            if not tenant_id:
                return f(*args, **kwargs)

            # Get tenant plan from database
            db = next(get_db())
            try:
                tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
                plan = tenant.plan.value if tenant else "free"
            finally:
                db.close()

            # Get rate limit for plan
            limit, window = get_tenant_plan_rate_limit(plan, action)

            # Check rate limit
            is_allowed, retry_after = _rate_limiter.is_allowed(
                f"{tenant_id}:{action}",  # Unique key per action
                limit=limit,
                window_seconds=window
            )

            if not is_allowed:
                return jsonify({
                    "success": False,
                    "error": f"Rate limit exceeded for {plan} plan. Maximum {limit} {action} requests per {window} seconds.",
                    "error_code": "RATE_LIMIT_EXCEEDED",
                    "retry_after": retry_after,
                    "plan": plan,
                    "upgrade_url": "/settings/billing"  # Encourage upgrades
                }), 429

            return f(*args, **kwargs)

        return decorated
    return decorator


# ============================================================================
# CLEANUP TASK
# ============================================================================

def start_cleanup_task(interval_seconds: int = 3600):
    """
    Start background thread to cleanup old rate limit entries.
    Call this once when app starts.
    """
    import threading

    def cleanup_loop():
        while True:
            time.sleep(interval_seconds)
            _rate_limiter.cleanup()

    thread = threading.Thread(target=cleanup_loop, daemon=True)
    thread.start()
    print(f"[RateLimiter] Started cleanup task (every {interval_seconds}s)", flush=True)


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

"""
# Example 1: Simple rate limit
@app.route('/api/endpoint')
@rate_limit(limit=50, window_seconds=60)
@jwt_required()
def my_endpoint():
    return {"message": "OK"}


# Example 2: Tier-based rate limit
@app.route('/api/search')
@rate_limit_by_plan("search")
@jwt_required()
def search():
    return {"results": []}


# Example 3: Custom error message
@app.route('/api/expensive-operation')
@rate_limit(limit=10, window_seconds=3600, error_message="Please wait before trying again")
@jwt_required()
def expensive_op():
    return {"status": "processing"}


# Start cleanup task in app initialization
if __name__ == '__main__':
    start_cleanup_task()
    app.run()
"""
