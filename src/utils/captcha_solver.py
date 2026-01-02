"""
Captcha Solver - интеграция с сервисами обхода капчи (2captcha, anti-captcha и т.д.)
"""

import asyncio
import logging
import aiohttp
import time
from typing import Optional, Dict, Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class CaptchaSolver:
    """
    Класс для решения капчи через внешние сервисы.
    Поддерживает: 2captcha, anti-captcha, rucaptcha
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        service: str = "2captcha",
        timeout: int = 120,
    ):
        """
        Инициализация решателя капчи.

        Args:
            api_key: API ключ от сервиса обхода капчи
            service: Название сервиса (2captcha, anticaptcha, rucaptcha)
            timeout: Таймаут ожидания решения (секунды)
        """
        self.api_key = api_key or self._load_api_key()
        self.service = service.lower()
        self.timeout = timeout

        # API endpoints для разных сервисов
        self.endpoints = {
            "2captcha": {
                "submit": "http://2captcha.com/in.php",
                "result": "http://2captcha.com/res.php",
                "balance": "http://2captcha.com/res.php",
            },
            "rucaptcha": {
                "submit": "http://rucaptcha.com/in.php",
                "result": "http://rucaptcha.com/res.php",
                "balance": "http://rucaptcha.com/res.php",
            },
            "anticaptcha": {
                "submit": "https://api.anti-captcha.com/createTask",
                "result": "https://api.anti-captcha.com/getTaskResult",
                "balance": "https://api.anti-captcha.com/getBalance",
            },
        }

    def _load_api_key(self) -> Optional[str]:
        """Загрузить API ключ из переменных окружения или файла."""
        import os

        # Проверяем переменные окружения
        api_key = os.getenv("CAPTCHA_API_KEY") or os.getenv("2CAPTCHA_API_KEY")
        if api_key:
            return api_key

        # Проверяем файл .env
        try:
            from dotenv import load_dotenv

            load_dotenv()
            api_key = os.getenv("CAPTCHA_API_KEY") or os.getenv("2CAPTCHA_API_KEY")
            if api_key:
                return api_key
        except ImportError:
            pass

        # Пробуем загрузить из config
        try:
            import sys
            import os

            sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
            import src.config as config

            if hasattr(config, "CAPTCHA_API_KEY") and config.CAPTCHA_API_KEY:
                return config.CAPTCHA_API_KEY
        except Exception:
            pass

        return None

    async def solve_recaptcha_v2(
        self, site_key: str, page_url: str, invisible: bool = False
    ) -> Optional[str]:
        """
        Решить reCAPTCHA v2.

        Args:
            site_key: Site key капчи
            page_url: URL страницы с капчей
            invisible: True если это invisible reCAPTCHA

        Returns:
            Токен решения или None
        """
        if not self.api_key:
            logger.error("❌ API key not provided for captcha solver")
            return None

        if self.service in ["2captcha", "rucaptcha"]:
            return await self._solve_recaptcha_v2_2captcha(
                site_key, page_url, invisible
            )
        elif self.service == "anticaptcha":
            return await self._solve_recaptcha_v2_anticaptcha(
                site_key, page_url, invisible
            )
        else:
            logger.error(f"❌ Unsupported captcha service: {self.service}")
            return None

    async def _solve_recaptcha_v2_2captcha(
        self, site_key: str, page_url: str, invisible: bool
    ) -> Optional[str]:
        """Решить reCAPTCHA v2 через 2captcha API."""
        endpoints = self.endpoints["2captcha"]

        async with aiohttp.ClientSession() as session:
            # Шаг 1: Отправить задачу
            params = {
                "key": self.api_key,
                "method": "userrecaptcha",
                "googlekey": site_key,
                "pageurl": page_url,
                "json": 1,
            }

            if invisible:
                params["invisible"] = 1

            try:
                async with session.post(endpoints["submit"], params=params) as resp:
                    data = await resp.json()

                    if data.get("status") != 1:
                        logger.error(
                            f"❌ Failed to submit captcha: {data.get('request')}"
                        )
                        return None

                    task_id = data.get("request")
                    logger.info(f"✅ Captcha task submitted: {task_id}")

                    # Шаг 2: Ждать решения
                    for attempt in range(self.timeout // 5):
                        await asyncio.sleep(5)

                        result_params = {
                            "key": self.api_key,
                            "action": "get",
                            "id": task_id,
                            "json": 1,
                        }

                        async with session.get(
                            endpoints["result"], params=result_params
                        ) as result_resp:
                            result_data = await result_resp.json()

                            if result_data.get("status") == 1:
                                token = result_data.get("request")
                                logger.info(f"✅ Captcha solved: {token[:50]}...")
                                return token
                            elif result_data.get("request") == "CAPCHA_NOT_READY":
                                logger.debug(
                                    f"⏳ Waiting for captcha solution... ({attempt + 1})"
                                )
                                continue
                            else:
                                logger.error(
                                    f"❌ Captcha solving failed: {result_data.get('request')}"
                                )
                                return None

                    logger.error("❌ Captcha solving timeout")
                    return None

            except Exception as e:
                logger.error(f"❌ Error solving captcha: {e}")
                return None

    async def _solve_recaptcha_v2_anticaptcha(
        self, site_key: str, page_url: str, invisible: bool
    ) -> Optional[str]:
        """Решить reCAPTCHA v2 через Anti-Captcha API."""
        endpoints = self.endpoints["anticaptcha"]

        async with aiohttp.ClientSession() as session:
            # Шаг 1: Создать задачу
            task_data = {
                "clientKey": self.api_key,
                "task": {
                    "type": "RecaptchaV2TaskProxyless",
                    "websiteURL": page_url,
                    "websiteKey": site_key,
                    "isInvisible": invisible,
                },
            }

            try:
                async with session.post(endpoints["submit"], json=task_data) as resp:
                    data = await resp.json()

                    if data.get("errorId") != 0:
                        logger.error(
                            f"❌ Failed to submit captcha: {data.get('errorDescription')}"
                        )
                        return None

                    task_id = data.get("taskId")
                    logger.info(f"✅ Captcha task submitted: {task_id}")

                    # Шаг 2: Ждать решения
                    for attempt in range(self.timeout // 5):
                        await asyncio.sleep(5)

                        result_data = {"clientKey": self.api_key, "taskId": task_id}

                        async with session.post(
                            endpoints["result"], json=result_data
                        ) as result_resp:
                            result = await result_resp.json()

                            if result.get("status") == "ready":
                                token = result.get("solution", {}).get(
                                    "gRecaptchaResponse"
                                )
                                if token:
                                    logger.info(f"✅ Captcha solved: {token[:50]}...")
                                    return token
                            elif result.get("errorId") != 0:
                                logger.error(
                                    f"❌ Captcha solving failed: {result.get('errorDescription')}"
                                )
                                return None

                    logger.error("❌ Captcha solving timeout")
                    return None

            except Exception as e:
                logger.error(f"❌ Error solving captcha: {e}")
                return None

    async def solve_yandex_smartcaptcha(
        self, page_url: str
    ) -> Optional[Dict[str, Any]]:
        """
        Решить Яндекс SmartCaptcha (более сложная, требует специальной обработки).

        Args:
            page_url: URL страницы с капчей

        Returns:
            Словарь с токеном и другими данными или None
        """
        # Яндекс SmartCaptcha сложнее, обычно требует ручного решения
        # или использования специальных сервисов
        logger.warning(
            "⚠️ Yandex SmartCaptcha requires manual intervention or specialized service"
        )
        return None

    async def get_balance(self) -> Optional[float]:
        """Получить баланс на счету сервиса."""
        if not self.api_key:
            return None

        if self.service in ["2captcha", "rucaptcha"]:
            endpoints = self.endpoints[self.service]
            async with aiohttp.ClientSession() as session:
                params = {"key": self.api_key, "action": "getbalance", "json": 1}
                try:
                    async with session.get(endpoints["balance"], params=params) as resp:
                        data = await resp.json()
                        if data.get("status") == 1:
                            return float(data.get("request", 0))
                except Exception as e:
                    logger.error(f"Error getting balance: {e}")

        return None


async def detect_captcha_on_page(page) -> Optional[Dict[str, Any]]:
    """
    Обнаружить капчу на странице Playwright.

    Returns:
        Словарь с информацией о капче или None
    """
    try:
        # Проверка URL
        current_url = page.url
        if "captcha" in current_url.lower() or "showcaptcha" in current_url.lower():
            logger.warning("🚫 CAPTCHA detected in URL!")
            return {"type": "url", "url": current_url, "detected": True}

        # Проверка iframe с капчей
        captcha_iframes = await page.query_selector_all(
            'iframe[src*="captcha"], iframe[src*="showcaptcha"], iframe[src*="recaptcha"]'
        )
        if captcha_iframes:
            logger.warning("🚫 CAPTCHA iframe detected!")

            # Попробуем найти site key для reCAPTCHA
            site_key = None
            for iframe in captcha_iframes:
                try:
                    src = await iframe.get_attribute("src")
                    if src:
                        # Извлекаем site key из URL
                        import re

                        match = re.search(r"k=([^&]+)", src)
                        if match:
                            site_key = match.group(1)
                            break
                except Exception:
                    continue

            return {
                "type": "iframe",
                "iframes": len(captcha_iframes),
                "site_key": site_key,
                "detected": True,
            }

        # Проверка элементов капчи
        captcha_elements = await page.query_selector_all(
            '[class*="captcha"], [id*="captcha"], [data-captcha]'
        )
        if captcha_elements:
            logger.warning("🚫 CAPTCHA elements detected!")
            return {
                "type": "elements",
                "count": len(captcha_elements),
                "detected": True,
            }

        # Проверка текста "капча" или "captcha"
        page_text = await page.inner_text("body")
        if "капча" in page_text.lower() or "captcha" in page_text.lower():
            logger.warning("🚫 CAPTCHA text detected on page!")
            return {"type": "text", "detected": True}

        return None

    except Exception as e:
        logger.debug(f"Error detecting captcha: {e}")
        return None


async def solve_captcha_in_browser(
    page, captcha_info: Dict[str, Any], solver: Optional[CaptchaSolver] = None
) -> bool:
    """
    Решить капчу в браузере.

    Args:
        page: Playwright page object
        captcha_info: Информация о капче от detect_captcha_on_page
        solver: Опциональный решатель капчи

    Returns:
        True если капча решена, False иначе
    """
    if not captcha_info.get("detected"):
        return False

    # Если есть site key и решатель - решаем автоматически
    if captcha_info.get("site_key") and solver:
        site_key = captcha_info["site_key"]
        page_url = page.url

        logger.info(f"🔐 Solving reCAPTCHA with site key: {site_key[:20]}...")
        token = await solver.solve_recaptcha_v2(site_key, page_url)

        if token:
            # Вводим токен в браузер
            try:
                # Ищем textarea для токена
                token_input = await page.query_selector(
                    'textarea[name="g-recaptcha-response"]'
                )
                if token_input:
                    await token_input.fill(token)
                    logger.info("✅ Token entered into form")

                    # Нажимаем кнопку отправки если есть
                    submit_button = await page.query_selector(
                        'button[type="submit"], input[type="submit"]'
                    )
                    if submit_button:
                        await submit_button.click()
                        await page.wait_for_load_state("networkidle", timeout=10000)
                        return True
            except Exception as e:
                logger.error(f"Error entering token: {e}")

    # Если автоматическое решение не сработало - ждем ручного решения
    logger.warning("⏳ Waiting for manual captcha solution (60 seconds)...")
    logger.warning("⏳ Please solve the captcha manually in the browser")

    try:
        # Ждем изменения URL или исчезновения капчи
        await asyncio.wait_for(
            page.wait_for_function(
                "() => !document.querySelector('iframe[src*=\"captcha\"]') && !window.location.href.includes('captcha')",
                timeout=60000,
            ),
            timeout=60,
        )
        logger.info("✅ Captcha appears to be solved")
        return True
    except asyncio.TimeoutError:
        logger.error("❌ Captcha solving timeout")
        return False
    except Exception as e:
        logger.error(f"Error waiting for captcha: {e}")
        return False
