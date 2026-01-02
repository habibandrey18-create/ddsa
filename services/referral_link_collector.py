# services/referral_link_collector.py
"""Сервис для автоматического сбора партнерских ссылок через браузер"""
import asyncio
import logging
import os
from typing import List, Optional
from datetime import datetime
from playwright.async_api import async_playwright, Browser, Page
import json

logger = logging.getLogger(__name__)


class ReferralLinkCollector:
    """Собирает партнерские ссылки с страницы referral_products через браузер"""

    def __init__(
        self,
        cookies_path: str = "cookies.json",
        output_file: str = "referral_links.txt",
    ):
        self.cookies_path = cookies_path
        self.output_file = output_file
        self.collected_links = []

    async def load_cookies(self, page: Page) -> bool:
        """Загружает cookies из файла"""
        try:
            if os.path.exists(self.cookies_path):
                with open(self.cookies_path, "r", encoding="utf-8") as f:
                    cookies = json.load(f)
                    if isinstance(cookies, list):
                        await page.context.add_cookies(cookies)
                        logger.info(f"Загружено {len(cookies)} cookies")
                        return True
            return False
        except Exception as e:
            logger.error(f"Ошибка загрузки cookies: {e}")
            return False

    async def get_product_links_from_page(
        self, page: Page, max_products: int = 50
    ) -> List[str]:
        """Получает ссылки на товары со страницы referral_products"""
        product_links = []

        try:
            # Ждем загрузки страницы
            await page.wait_for_load_state("networkidle", timeout=30000)
            await asyncio.sleep(2)  # Дополнительная задержка для динамического контента

            # Прокручиваем страницу для загрузки всех товаров
            for i in range(3):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(1)

            # Ищем все ссылки на товары
            links = await page.query_selector_all(
                'a[href*="/card/"], a[href*="/product/"], a[href*="/cc/"]'
            )

            seen_urls = set()
            for link in links:
                if len(product_links) >= max_products:
                    break

                href = await link.get_attribute("href")
                if not href:
                    continue

                # Преобразуем относительные ссылки в абсолютные
                if href.startswith("/"):
                    href = f"https://market.yandex.ru{href}"

                # Убираем параметры для проверки уникальности
                url_base = href.split("?")[0].split("#")[0]

                if url_base not in seen_urls and (
                    "/card/" in href or "/product/" in href or "/cc/" in href
                ):
                    seen_urls.add(url_base)
                    product_links.append(href)

            logger.info(f"Найдено {len(product_links)} ссылок на товары")
            return product_links

        except Exception as e:
            logger.error(f"Ошибка получения ссылок со страницы: {e}")
            return product_links

    async def get_partner_link(self, page: Page, product_url: str) -> Optional[str]:
        """Получает партнерскую ссылку для товара через кнопку 'Поделиться'"""
        try:
            # Переходим на страницу товара
            await page.goto(product_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            # Ищем кнопку "Поделиться"
            share_button = None
            selectors = [
                'button[aria-label*="Поделиться"]',
                'button[aria-label*="поделиться"]',
                'button:has-text("Поделиться")',
                'button:has-text("поделиться")',
                '[data-testid*="share"]',
                ".share-button",
                'button[class*="share"]',
            ]

            for selector in selectors:
                try:
                    share_button = await page.wait_for_selector(selector, timeout=3000)
                    if share_button:
                        break
                except:
                    continue

            if not share_button:
                logger.warning(
                    f"Кнопка 'Поделиться' не найдена для {product_url[:100]}"
                )
                return None

            # Кликаем на кнопку "Поделиться"
            await share_button.click()
            await asyncio.sleep(2)

            # Ждем появления модального окна и ищем партнерскую ссылку
            partner_link = None

            # Метод 1: Ищем в input поле
            try:
                input_selectors = [
                    'input[value*="/cc/"]',
                    'input[value*="market.yandex.ru/cc/"]',
                    'input[type="text"][value*="/cc/"]',
                ]
                for selector in input_selectors:
                    input_elem = await page.wait_for_selector(selector, timeout=3000)
                    if input_elem:
                        partner_link = await input_elem.get_attribute("value")
                        if partner_link and "/cc/" in partner_link:
                            # Извлекаем чистую ссылку
                            import re

                            match = re.search(
                                r"https?://market\.yandex\.ru/cc/([A-Za-z0-9_-]+)",
                                partner_link,
                            )
                            if match:
                                partner_link = (
                                    f"https://market.yandex.ru/cc/{match.group(1)}"
                                )
                                logger.info(
                                    f"Найдена партнерская ссылка: {partner_link[:50]}..."
                                )
                                return partner_link
            except:
                pass

            # Метод 2: Перехватываем сетевые запросы
            try:
                async with page.expect_response(
                    lambda response: "resolveSharingPopupV2" in response.url
                    or "sharing" in response.url.lower(),
                    timeout=5000,
                ) as response_info:
                    response = await response_info.value
                    data = await response.json()

                    # Ищем shortUrl в ответе
                    def find_short_url(obj, path=""):
                        if isinstance(obj, dict):
                            for key, value in obj.items():
                                if (
                                    key in ["shortUrl", "short_url", "url", "link"]
                                    and isinstance(value, str)
                                    and "/cc/" in value
                                ):
                                    return value
                                elif isinstance(value, (dict, list)):
                                    result = find_short_url(value, f"{path}.{key}")
                                    if result:
                                        return result
                        elif isinstance(obj, list):
                            for i, item in enumerate(obj):
                                result = find_short_url(item, f"{path}[{i}]")
                                if result:
                                    return result
                        return None

                    short_url = find_short_url(data)
                    if short_url:
                        import re

                        match = re.search(
                            r"https?://market\.yandex\.ru/cc/([A-Za-z0-9_-]+)",
                            short_url,
                        )
                        if match:
                            partner_link = (
                                f"https://market.yandex.ru/cc/{match.group(1)}"
                            )
                            logger.info(
                                f"Найдена партнерская ссылка из API: {partner_link[:50]}..."
                            )
                            return partner_link
            except:
                pass

            # Метод 3: Ищем в тексте страницы
            try:
                page_content = await page.content()
                import re

                matches = re.findall(
                    r"https?://market\.yandex\.ru/cc/([A-Za-z0-9_-]{5,30})",
                    page_content,
                )
                if matches:
                    partner_link = f"https://market.yandex.ru/cc/{matches[0]}"
                    logger.info(
                        f"Найдена партнерская ссылка в тексте: {partner_link[:50]}..."
                    )
                    return partner_link
            except:
                pass

            # Закрываем модальное окно (ESC или клик вне окна)
            try:
                await page.keyboard.press("Escape")
            except:
                pass

            return None

        except Exception as e:
            logger.error(
                f"Ошибка получения партнерской ссылки для {product_url[:100]}: {e}"
            )
            return None

    async def collect_links(
        self, referral_url: str, max_products: int = 50
    ) -> List[str]:
        """Собирает партнерские ссылки с страницы referral_products"""
        collected_links = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True
            )  # headless=True - браузер работает в фоне
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            )
            page = await context.new_page()

            try:
                # Загружаем cookies
                await self.load_cookies(page)

                # Переходим на страницу referral_products
                logger.info(f"Переход на страницу: {referral_url[:100]}...")
                await page.goto(referral_url, wait_until="networkidle", timeout=60000)
                await asyncio.sleep(3)

                # Получаем ссылки на товары
                product_links = await self.get_product_links_from_page(
                    page, max_products
                )
                logger.info(f"Найдено {len(product_links)} товаров для обработки")

                # Для каждого товара получаем партнерскую ссылку
                for i, product_url in enumerate(product_links, 1):
                    logger.info(
                        f"[{i}/{len(product_links)}] Обработка: {product_url[:100]}..."
                    )

                    partner_link = await self.get_partner_link(page, product_url)

                    if partner_link:
                        collected_links.append(partner_link)
                        logger.info(f"✅ Получена ссылка: {partner_link}")
                    else:
                        logger.warning(
                            f"⚠ Не удалось получить партнерскую ссылку для {product_url[:100]}"
                        )

                    # Небольшая задержка между товарами
                    await asyncio.sleep(2)

            except Exception as e:
                logger.error(f"Ошибка сбора ссылок: {e}")
            finally:
                await browser.close()

        self.collected_links = collected_links
        return collected_links

    def save_links_to_file(self, links: List[str] = None) -> str:
        """Сохраняет ссылки в txt файл"""
        if links is None:
            links = self.collected_links

        output_path = self.output_file

        # Добавляем новые ссылки к существующим (если файл уже есть)
        existing_links = set()
        if os.path.exists(output_path):
            with open(output_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and line.startswith("http"):
                        existing_links.add(line)

        # Объединяем и сохраняем
        all_links = existing_links | set(links)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(
                f"# Партнерские ссылки от {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            )
            f.write(f"# Всего ссылок: {len(all_links)}\n\n")
            for link in sorted(all_links):
                f.write(f"{link}\n")

        logger.info(f"Сохранено {len(all_links)} ссылок в {output_path}")
        return output_path
