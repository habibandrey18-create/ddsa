"""
Proxy Service - Управление ротацией прокси для обхода анти-бот защиты
Поддерживает SOCKS5 прокси с автоматической ротацией и мониторингом качества
"""

import logging
import asyncio
import time
import random
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from urllib.parse import urlparse
import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class ProxyInfo:
    """Информация о прокси"""
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    protocol: str = "socks5"  # socks5, http, https
    country: str = "RU"
    last_used: float = 0
    success_count: int = 0
    failure_count: int = 0
    avg_response_time: float = 0
    is_active: bool = True

    def get_url(self) -> str:
        """Получить URL для использования в aiohttp"""
        if self.username and self.password:
            return f"{self.protocol}://{self.username}:{self.password}@{self.host}:{self.port}"
        else:
            return f"{self.protocol}://{self.host}:{self.port}"

    def get_proxy_dict(self) -> Dict[str, str]:
        """Получить словарь для aiohttp"""
        return {"http": self.get_url(), "https": self.get_url()}

    @property
    def success_rate(self) -> float:
        """Рассчитать процент успешных запросов"""
        total = self.success_count + self.failure_count
        return (self.success_count / total) * 100 if total > 0 else 100.0


class ProxyService:
    """
    Сервис для ротации прокси с поддержкой SOCKS5
    Автоматически управляет качеством прокси и ротацией
    """

    def __init__(self):
        self.proxies: List[ProxyInfo] = []
        self.current_index = 0
        self.requests_per_proxy = 5  # Количество запросов на один прокси перед ротацией
        self.requests_count = 0
        self.cooldown_period = 30  # Секунд отдыха между использованием одного прокси
        self.min_success_rate = 50.0  # Минимальный процент успеха для активации прокси

        # Загружаем прокси из конфига
        self._load_proxies_from_config()

    def _load_proxies_from_config(self):
        """Загрузить прокси из конфигурации"""
        import config

        proxy_str = getattr(config, 'PROXY_LIST_STR', '')
        if not proxy_str:
            logger.warning("No proxy list configured in PROXY_LIST_STR")
            return

        proxies = [p.strip() for p in proxy_str.split(',') if p.strip()]
        for proxy_url in proxies:
            try:
                proxy_info = self._parse_proxy_url(proxy_url)
                if proxy_info:
                    self.proxies.append(proxy_info)
                    logger.info(f"Added proxy: {proxy_info.host}:{proxy_info.port}")
            except Exception as e:
                logger.error(f"Failed to parse proxy {proxy_url}: {e}")

        logger.info(f"Loaded {len(self.proxies)} proxies")

    def _parse_proxy_url(self, proxy_url: str) -> Optional[ProxyInfo]:
        """
        Парсит URL прокси в формате: protocol://user:pass@host:port
        или socks5://user:pass@host:port
        """
        try:
            parsed = urlparse(proxy_url)

            # Определяем протокол
            protocol = parsed.scheme if parsed.scheme in ['socks5', 'http', 'https'] else 'socks5'

            # Извлекаем хост и порт
            host = parsed.hostname
            port = parsed.port

            if not host or not port:
                # Попробуем разобрать как host:port
                if ':' in proxy_url:
                    parts = proxy_url.split(':')
                    if len(parts) >= 2:
                        host = parts[0]
                        port = int(parts[1].split('@')[0]) if '@' in parts[1] else int(parts[1])
                        protocol = 'socks5'  # По умолчанию

            if not host or not port:
                raise ValueError(f"Invalid proxy format: {proxy_url}")

            # Извлекаем credentials
            username = parsed.username
            password = parsed.password

            # Если credentials в URL не найдены, попробуем найти в строке
            if not username and '@' in proxy_url:
                auth_part = proxy_url.split('@')[0]
                if '://' in auth_part:
                    auth_part = auth_part.split('://')[1]
                if ':' in auth_part:
                    username, password = auth_part.split(':', 1)

            return ProxyInfo(
                host=host,
                port=port,
                username=username,
                password=password,
                protocol=protocol
            )

        except Exception as e:
            logger.error(f"Failed to parse proxy URL {proxy_url}: {e}")
            return None

    def add_proxy(self, proxy: ProxyInfo):
        """Добавить прокси в пул"""
        self.proxies.append(proxy)
        logger.info(f"Added proxy: {proxy.host}:{proxy.port}")

    def remove_proxy(self, host: str, port: int):
        """Удалить прокси из пула"""
        self.proxies = [p for p in self.proxies if not (p.host == host and p.port == port)]
        logger.info(f"Removed proxy: {host}:{port}")

    def get_next_proxy(self) -> Optional[ProxyInfo]:
        """
        Получить следующий прокси с учётом ротации и качества

        Returns:
            ProxyInfo или None если нет доступных прокси
        """
        if not self.proxies:
            return None

        # Фильтруем активные прокси с хорошим качеством
        active_proxies = [
            p for p in self.proxies
            if p.is_active and p.success_rate >= self.min_success_rate
        ]

        if not active_proxies:
            logger.warning("No active proxies with good quality available")
            # Если нет хороших прокси, используем любые активные
            active_proxies = [p for p in self.proxies if p.is_active]

        if not active_proxies:
            logger.error("No active proxies available")
            return None

        # Выбираем прокси с учётом времени последнего использования
        current_time = time.time()
        available_proxies = [
            p for p in active_proxies
            if current_time - p.last_used >= self.cooldown_period
        ]

        if not available_proxies:
            # Если все прокси в cooldown, выбираем тот, который ждал дольше всего
            available_proxies = sorted(active_proxies, key=lambda p: p.last_used)

        # Выбираем прокси
        selected_proxy = available_proxies[0]
        selected_proxy.last_used = current_time

        # Обновляем счётчик запросов
        self.requests_count += 1
        if self.requests_count >= self.requests_per_proxy:
            self.requests_count = 0
            # Принудительная ротация

        logger.debug(f"Selected proxy: {selected_proxy.host}:{selected_proxy.port} (success rate: {selected_proxy.success_rate:.1f}%)")
        return selected_proxy

    def get_random_proxy(self) -> Optional[ProxyInfo]:
        """Получить случайный прокси (альтернативная стратегия)"""
        if not self.proxies:
            return None

        active_proxies = [p for p in self.proxies if p.is_active]
        if not active_proxies:
            return None

        # Взвешенный случайный выбор по success_rate
        total_weight = sum(p.success_rate for p in active_proxies)
        if total_weight == 0:
            return random.choice(active_proxies)

        pick = random.uniform(0, total_weight)
        current_weight = 0

        for proxy in active_proxies:
            current_weight += proxy.success_rate
            if pick <= current_weight:
                proxy.last_used = time.time()
                return proxy

        return active_proxies[-1]

    def report_proxy_result(self, proxy: ProxyInfo, success: bool, response_time: float = 0):
        """
        Сообщить результат использования прокси

        Args:
            proxy: Использованный прокси
            success: True если запрос успешен
            response_time: Время ответа в секундах
        """
        if success:
            proxy.success_count += 1
            # Обновляем среднее время ответа
            if proxy.avg_response_time == 0:
                proxy.avg_response_time = response_time
            else:
                proxy.avg_response_time = (proxy.avg_response_time + response_time) / 2
        else:
            proxy.failure_count += 1

        # Деактивируем прокси если слишком много ошибок
        total_attempts = proxy.success_count + proxy.failure_count
        if total_attempts >= 10 and proxy.success_rate < self.min_success_rate:
            proxy.is_active = False
            logger.warning(f"Deactivated proxy {proxy.host}:{proxy.port} (success rate: {proxy.success_rate:.1f}%)")

    async def test_proxy(self, proxy: ProxyInfo, test_url: str = "https://httpbin.org/ip") -> bool:
        """
        Протестировать прокси на работоспособность

        Args:
            proxy: Прокси для тестирования
            test_url: URL для тестового запроса

        Returns:
            True если прокси работает
        """
        try:
            async with aiohttp.ClientSession() as session:
                start_time = time.time()
                async with session.get(
                    test_url,
                    proxy=proxy.get_url(),
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    response_time = time.time() - start_time
                    success = response.status == 200

                    self.report_proxy_result(proxy, success, response_time)
                    return success

        except Exception as e:
            logger.debug(f"Proxy test failed for {proxy.host}:{proxy.port}: {e}")
            self.report_proxy_result(proxy, False)
            return False

    async def test_all_proxies(self):
        """Протестировать все прокси в пуле"""
        logger.info("Testing all proxies...")

        tasks = []
        for proxy in self.proxies:
            if proxy.is_active:
                task = asyncio.create_task(self.test_proxy(proxy))
                tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = sum(1 for r in results if r is True)
        logger.info(f"Proxy testing completed: {success_count}/{len(tasks)} successful")

    def get_stats(self) -> Dict:
        """Получить статистику прокси"""
        total = len(self.proxies)
        active = len([p for p in self.proxies if p.is_active])
        avg_success_rate = sum(p.success_rate for p in self.proxies) / total if total > 0 else 0

        return {
            'total_proxies': total,
            'active_proxies': active,
            'avg_success_rate': avg_success_rate,
            'proxies': [
                {
                    'host': p.host,
                    'port': p.port,
                    'success_rate': p.success_rate,
                    'success_count': p.success_count,
                    'failure_count': p.failure_count,
                    'avg_response_time': p.avg_response_time,
                    'is_active': p.is_active,
                    'last_used': p.last_used
                }
                for p in self.proxies
            ]
        }


# Глобальный экземпляр
_proxy_service = None


def get_proxy_service() -> ProxyService:
    """Получить глобальный экземпляр прокси сервиса"""
    global _proxy_service
    if _proxy_service is None:
        _proxy_service = ProxyService()
    return _proxy_service


def get_proxy_for_request() -> Optional[Dict[str, str]]:
    """
    Получить прокси для HTTP запроса

    Returns:
        Словарь с proxy для aiohttp или None
    """
    service = get_proxy_service()
    proxy = service.get_next_proxy()
    return proxy.get_proxy_dict() if proxy else None
