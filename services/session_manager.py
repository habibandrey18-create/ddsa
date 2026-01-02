"""
Session Manager - Централизованное управление aiohttp сессиями
Решает проблему "Unclosed client session" warnings
"""

import logging
import asyncio
import atexit
from typing import Optional, Set
import aiohttp

logger = logging.getLogger(__name__)


class SessionManager:
    """Менеджер для отслеживания и закрытия всех HTTP сессий"""
    
    _instance: Optional["SessionManager"] = None
    _sessions: Set[aiohttp.ClientSession] = set()
    _cleanup_registered = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._cleanup_registered:
            atexit.register(self._sync_cleanup)
            self._cleanup_registered = True
    
    def register_session(self, session: aiohttp.ClientSession):
        """Регистрирует сессию для автоматического закрытия"""
        self._sessions.add(session)
        logger.debug(f"Registered session {id(session)}, total: {len(self._sessions)}")
    
    def unregister_session(self, session: aiohttp.ClientSession):
        """Удаляет сессию из списка отслеживаемых"""
        self._sessions.discard(session)
        logger.debug(f"Unregistered session {id(session)}, remaining: {len(self._sessions)}")
    
    async def close_all(self):
        """Закрывает все зарегистрированные сессии"""
        logger.info(f"Closing {len(self._sessions)} active sessions")
        closed_count = 0
        
        for session in list(self._sessions):
            try:
                if not session.closed:
                    await session.close()
                    closed_count += 1
            except Exception as e:
                logger.warning(f"Error closing session {id(session)}: {e}")
        
        self._sessions.clear()
        logger.info(f"Closed {closed_count} sessions")
    
    def _sync_cleanup(self):
        """Синхронный cleanup для atexit"""
        if self._sessions:
            logger.warning(f"Cleaning up {len(self._sessions)} unclosed sessions at exit")
            try:
                # Попытка закрыть в текущем event loop если есть
                loop = asyncio.get_event_loop()
                if not loop.is_closed():
                    loop.run_until_complete(self.close_all())
            except Exception as e:
                logger.error(f"Error in sync cleanup: {e}")


# Singleton instance
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """Получить глобальный экземпляр SessionManager"""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager


class ManagedSession:
    """Wrapper для aiohttp.ClientSession с автоматической регистрацией"""
    
    def __init__(self, *args, **kwargs):
        self._session = aiohttp.ClientSession(*args, **kwargs)
        self._manager = get_session_manager()
        self._manager.register_session(self._session)
    
    def __getattr__(self, name):
        """Proxy все атрибуты к внутренней сессии"""
        return getattr(self._session, name)
    
    async def close(self):
        """Закрыть сессию и удалить из менеджера"""
        self._manager.unregister_session(self._session)
        await self._session.close()
    
    async def __aenter__(self):
        await self._session.__aenter__()
        return self
    
    async def __aexit__(self, *args):
        await self.close()
        return await self._session.__aexit__(*args)


async def cleanup_all_sessions():
    """Утилита для закрытия всех сессий (вызывать при shutdown)"""
    manager = get_session_manager()
    await manager.close_all()

