# utils/rate_limiter.py
import asyncio
import time
from collections import deque
from typing import Deque


class RateLimiter:
    """Rate limiter для API запросов"""

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Deque[float] = deque()
        self.lock = asyncio.Lock()

    async def acquire(self):
        """Ждет, пока можно будет сделать запрос"""
        async with self.lock:
            now = time.time()
            # Удаляем старые запросы
            while self.requests and self.requests[0] < now - self.window_seconds:
                self.requests.popleft()

            # Если достигнут лимит, ждем
            if len(self.requests) >= self.max_requests:
                wait_time = self.requests[0] + self.window_seconds - now
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                    # Повторно очищаем после ожидания
                    now = time.time()
                    while (
                        self.requests and self.requests[0] < now - self.window_seconds
                    ):
                        self.requests.popleft()

            # Добавляем текущий запрос
            self.requests.append(time.time())


# Глобальный rate limiter
_rate_limiter = None


def get_rate_limiter(max_requests: int = 10, window_seconds: int = 60):
    """Получить глобальный rate limiter"""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(max_requests, window_seconds)
    return _rate_limiter
