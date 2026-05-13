"""
Simple rate limiter implementation for the gallery application.

This module provides rate limiting functionality without requiring external dependencies.
It uses in-memory storage to track request counts per IP address.
"""

import time
from functools import wraps
from flask import request, abort, g
from collections import defaultdict, deque
from threading import Lock
from logger import logger


class RateLimiter:
    """
    Simple in-memory rate limiter.
    
    Tracks requests per IP address and enforces configurable limits.
    """
    
    def __init__(self):
        self.requests = defaultdict(deque)
        self.lock = Lock()
        self.last_cleanup = time.time()
        self.cleanup_interval = 600  # Clean up every 10 minutes
    
    def is_rate_limited(self, key, limit, window):
        """
        Check if a key (typically IP address) has exceeded the rate limit.
        
        Args:
            key: Identifier for the client (e.g., IP address)
            limit: Maximum number of requests allowed
            window: Time window in seconds
        
        Returns:
            bool: True if rate limited, False otherwise
        """
        with self.lock:
            now = time.time()
            
            # Periodic global cleanup
            if now - self.last_cleanup > self.cleanup_interval:
                self.cleanup_old_entries()
                self.last_cleanup = now
            
            # Remove old requests outside the time window for this key
            timestamps = self.requests[key]
            while timestamps and now - timestamps[0] >= window:
                timestamps.popleft()
            
            # Check if limit exceeded
            if len(timestamps) >= limit:
                return True
            
            # Add current request
            timestamps.append(now)
            return False
    
    def cleanup_old_entries(self, max_age=3600):
        """
        Clean up old entries to prevent memory bloat.
        
        Args:
            max_age: Maximum age in seconds for entries to keep (default: 1 hour)
        """
        # Note: self.lock should be acquired by the caller or we should use a separate lock
        # if called internally. Since is_rate_limited holds the lock, we don't re-acquire here
        # to avoid deadlocks (Lock is not re-entrant by default, though we could use RLock).
        # Actually, let's make it safe to call independently too.
        
        # We'll use a local helper to avoid re-acquiring if already held, 
        # but for simplicity, let's just use the lock and ensure we don't nest it.
        
        now = time.time()
        keys_to_remove = []
        
        for key, timestamps in self.requests.items():
            # Remove old timestamps
            while timestamps and now - timestamps[0] >= max_age:
                timestamps.popleft()
            
            # Mark empty entries for removal
            if not timestamps:
                keys_to_remove.append(key)
        
        # Remove empty entries
        for key in keys_to_remove:
            del self.requests[key]


# Global rate limiter instance
_rate_limiter = RateLimiter()


def rate_limit(limit=1000, window=900, per='user'):
    """
    Decorator to apply rate limiting to a route.
    
    Args:
        limit: Maximum number of requests allowed
        window: Time window in seconds (default: 900 = 15 minutes)
        per: What to rate limit by ('ip' or 'user')
    
    Usage:
        @rate_limit(limit=100, window=900)
        def my_route():
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Determine the key to rate limit by: include the endpoint to make limits per-route
            endpoint = request.endpoint or 'unknown'
            if per == 'ip':
                client_id = request.remote_addr or 'unknown'
            else:
                client_id = getattr(g, 'user_id', request.remote_addr or 'unknown')
            
            key = f"{endpoint}:{client_id}"
            
            # Check rate limit
            if _rate_limiter.is_rate_limited(key, limit, window):
                logger.app_logger.warning(
                    f"Rate limit exceeded for {key} on {request.path}"
                )
                abort(429, description="Too many requests. Please try again later.")
            
            return func(*args, **kwargs)
        
        return wrapper
    return decorator


def get_rate_limiter():
    """Get the global rate limiter instance."""
    return _rate_limiter
