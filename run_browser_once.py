#!/usr/bin/env python3
"""
Запусти один раз для получения cookies
Отворяет видимый браузер, ты вручную логинишься, потом cookies сохраняются
"""
import asyncio
from playwright.async_api import async_playwright
import json
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def login_once():
    """Отворяет видимый браузер, ты вручную логинишься, потом cookies сохраняются"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # ← ВИДИМОЕ ОКНО!
        page = await browser.new_page()

        logger.info("🔐 Opening Yandex login...")
        await page.goto(
            "https://market.yandex.ru", wait_until="domcontentloaded", timeout=120000
        )

        logger.info("⏳ Ждем входа... Напиши логин/пароль вручную в браузере")
        logger.info("⏳ После входа нажми Enter в консоли...")

        input()  # Жди пока пользователь залогинится

        # Сохрани cookies
        logger.info("💾 Сохраняю cookies...")
        storage_state = await page.context.storage_state()

        cookies_file = os.path.join(os.path.dirname(__file__), "cookies.json")
        with open(cookies_file, "w", encoding="utf-8") as f:
            json.dump(storage_state, f, indent=2)

        logger.info(f"✅ Cookies saved to {cookies_file}")
        logger.info("✅ Теперь можно запускать бота!")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(login_once())
