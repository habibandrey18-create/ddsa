"""
Упрощенный сервис получения CC ссылки БЕЗ капч
Чистая версия без лишних проверок
"""

import asyncio
import logging
from typing import Optional
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


class RefLinkService:
    """Упрощенный сервис получения CC ссылки БЕЗ капч"""

    async def get_cc_link(self, product_url: str) -> Optional[str]:
        """
        Получает CC ссылку из браузера с cookies
        - Не кликает невидимые кнопки
        - Не решает капчи
        - Просто парсит от браузера
        """
        browser = None
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"],
                )

                # Загружаем cookies если есть
                import os

                cookies_file = os.path.join(
                    os.path.dirname(__file__), "..", "cookies.json"
                )
                context_options = {}

                if os.path.exists(cookies_file):
                    context_options["storage_state"] = cookies_file
                    logger.info("✅ Using saved cookies")

                context = await browser.new_context(**context_options)
                page = await context.new_page()

                logger.info(f"🌐 Opening: {product_url}")
                await page.goto(
                    product_url, wait_until="domcontentloaded", timeout=15000
                )
                await page.wait_for_load_state("networkidle", timeout=10000)

                # Попробуй кликнуть "Поделиться" БЕЗ проверки видимости
                try:
                    await page.click('button:has-text("Поделиться")', timeout=3000)
                    logger.info("✓ Clicked share button")
                except:
                    logger.warning("⚠ Share button click timeout (OK, не критично)")

                # Жди 2 секунды на загрузку модального окна
                await asyncio.sleep(2)

                # Парсь CC ссылку из DOM БЕЗ проверок видимости
                try:
                    cc_link = await page.input_value(
                        'input[value*="market.yandex.ru/cc/"]'
                    )
                    if cc_link and "market.yandex.ru/cc/" in cc_link:
                        logger.info(f"✅ Got CC link: {cc_link[:50]}...")
                        await browser.close()
                        return cc_link
                except Exception as e:
                    logger.warning(f"⚠ CC parsing failed: {e}")

                # Fallback: парсь из URL параметров (худший вариант)
                if "cc=" in product_url:
                    cc = product_url.split("cc=")[1].split("&")[0]
                    fallback_url = f"https://market.yandex.ru/cc/{cc}"
                    logger.warning(
                        f"⚠ Using fallback CC from URL: {fallback_url[:50]}..."
                    )
                    await browser.close()
                    return fallback_url

                await browser.close()
                return None

        except Exception as e:
            logger.error(f"❌ Error: {e}")
            if browser:
                await browser.close()
            return None


# Backward compatibility
async def get_cc_link_by_click(url: str, **kwargs) -> dict:
    """Backward compatibility wrapper"""
    service = RefLinkService()
    cc_link = await service.get_cc_link(url)

    if cc_link:
        return {
            "ref_link": cc_link,
            "flags": ["ok"],
            "note": "Successfully generated link",
        }
    else:
        return {
            "ref_link": None,
            "flags": ["error", "ref_not_found"],
            "note": "Failed to generate link",
        }
