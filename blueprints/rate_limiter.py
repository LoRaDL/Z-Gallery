"""
Simple rate limiter implementation for the gallery application.

This module provides rate limiting functionality without requiring external dependencies.
It uses in-memory storage to track request counts per IP address.
"""

import time
from functools import wraps
from flask import request, abort, g
from collections import defaultdict
from threading import Lock
from logger import logger


class RateLimiter:
    """
    Simple in-memory rate limiter.
    
    Tracks requests per IP address and enforces configurable limits.
    """
    
    def __init__(self):
        self.requests = defaultdict(list)
        self.lock = Lock()
    
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
            
            # Remove old requests outside the time window
            self.requests[key] = [
                req_time for req_time in self.requests[key]
                if now - req_time < window
            ]
            
            # Check if limit exceeded
            if len(self.requests[key]) >= limit:
                return True
            
            # Add current request
            self.requests[key].append(now)
            return False
    
    def cleanup_old_entries(self, max_age=3600):
        """
        Clean up old entries to prevent memory bloat.
        
        Args:
            max_age: Maximum age in seconds for entries to keep
        """
        with self.lock:
            now = time.time()
            keys_to_remove = []
            
            for key, timestamps in self.requests.items():
                # Remove old timestamps
                self.requests[key] = [
                    ts for ts in timestamps
                    if now - ts < max_age
                ]
                
                # Mark empty entries for removal
                if not self.requests[key]:
                    keys_to_remove.append(key)
            
            # Remove empty entries
            for key in keys_to_remove:
                del self.requests[key]


# Global rate limiter instance
_rate_limiter = RateLimiter()


def rate_limit(limit=1000, window=3600, per='ip'):
    """
    Decorator to apply rate limiting to a route.
    
    Args:
        limit: Maximum number of requests allowed
        window: Time window in seconds (default: 3600 = 1 hour)
        per: What to rate limit by ('ip' or 'user')
    
    Usage:
        @rate_limit(limit=100, window=3600)
        def my_route():
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Determine the key to rate limit by
            if per == 'ip':
                key = request.remote_addr or 'unknown'
            else:
                key = getattr(g, 'user_id', request.remote_addr or 'unknown')
            
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
