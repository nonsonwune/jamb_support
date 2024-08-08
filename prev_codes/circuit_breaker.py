# circuit_breaker.py
import asyncio
from functools import wraps


class CircuitBreaker:
    def __init__(self, failure_threshold, recovery_timeout):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.circuit_open = False
        self.last_failure_time = 0

    async def call(self, func, *args, **kwargs):
        if self.circuit_open:
            if (
                asyncio.get_event_loop().time() - self.last_failure_time
                > self.recovery_timeout
            ):
                self.circuit_open = False
                self.failures = 0
            else:
                raise Exception("Circuit is open")

        try:
            result = await func(*args, **kwargs)
            self.failures = 0
            return result
        except Exception as e:
            self.failures += 1
            if self.failures >= self.failure_threshold:
                self.circuit_open = True
                self.last_failure_time = asyncio.get_event_loop().time()
            raise e


def circuit_breaker(failure_threshold, recovery_timeout):
    breaker = CircuitBreaker(failure_threshold, recovery_timeout)

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await breaker.call(func, *args, **kwargs)

        return wrapper

    return decorator
