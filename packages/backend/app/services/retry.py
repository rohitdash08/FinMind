
"""
Resilient background job retry with exponential backoff.
"""
import time
import logging
from typing import Callable, Any, Optional
from datetime import datetime

logger = logging.getLogger("finmind.retry")


class RetryConfig:
    def __init__(self, max_retries=3, base_delay=1.0, max_delay=60.0, backoff_factor=2.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor


def retry_with_backoff(config: Optional[RetryConfig] = None):
    """Decorator for retrying failed operations with exponential backoff."""
    cfg = config or RetryConfig()
    
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs) -> Any:
            last_error = None
            for attempt in range(cfg.max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < cfg.max_retries:
                        delay = min(cfg.base_delay * (cfg.backoff_factor ** attempt), cfg.max_delay)
                        logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay:.1f}s")
                        time.sleep(delay)
                    else:
                        logger.error(f"All {cfg.max_retries + 1} attempts failed: {e}")
            raise last_error
        return wrapper
    return decorator
