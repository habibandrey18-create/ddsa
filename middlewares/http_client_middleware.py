from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from services.http_client import HTTPClient  # Adjust import path

class HttpClientMiddleware(BaseMiddleware):
    def __init__(self, http_client: HTTPClient):
        self.http_client = http_client

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        data['http_client'] = self.http_client
        return await handler(event, data)



