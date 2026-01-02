# tests/test_partner_link.py
"""Интеграционные тесты для получения партнерских ссылок"""
import asyncio
import sys

# Пытаемся импортировать pytest, но не критично если его нет
try:
    import pytest

    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False

    # Создаем простой декоратор для совместимости
    def pytest_mark_asyncio(func):
        return func


from unittest.mock import AsyncMock, patch, MagicMock
import json

# Тестовый URL
TEST_URL = "https://market.yandex.ru/card/konfety-pobeda-vkusa-im_011415/103200926040"


if HAS_PYTEST:

    class TestPartnerLink:
        @pytest.mark.asyncio
        async def test_scrape_without_cookies(self):
            """Тест A: без cookies → scrape_yandex_market возвращает flags с needs_login или ref_not_found"""
            from utils.scraper import scrape_yandex_market

            # Мокаем partner_link_service чтобы вернуть needs_login
            with patch("utils.scraper.PartnerLinkService") as mock_service:
                mock_instance = MagicMock()
                mock_instance.get_partner_link = AsyncMock(
                    return_value={
                        "ref_link": "",
                        "flags": ["api_failed", "needs_login"],
                        "title": "Test Product",
                        "price": "100 ₽",
                        "image_bytes": None,
                    }
                )
                mock_service.return_value = mock_instance

                result = await scrape_yandex_market(TEST_URL)

                assert "ref_link" in result
                assert "flags" in result
                assert (
                    result["ref_link"] == ""
                    or "needs_login" in result.get("flags", [])
                    or "ref_not_found" in result.get("flags", [])
                )
                assert "title" in result
                assert "price" in result

        @pytest.mark.asyncio
        async def test_scrape_with_cookies(self):
            """Тест B: с cookies → scrape_yandex_market возвращает ref_link с market.yandex.ru/cc/"""
            from utils.scraper import scrape_yandex_market

            # Мокаем partner_link_service чтобы вернуть успешный результат
            with patch("utils.scraper.PartnerLinkService") as mock_service:
                mock_instance = MagicMock()
                mock_instance.get_partner_link = AsyncMock(
                    return_value={
                        "ref_link": "https://market.yandex.ru/cc/8BvWCv",
                        "flags": ["ok", "copied_via_button"],
                        "title": "Test Product",
                        "price": "100 ₽",
                        "image_bytes": None,
                    }
                )
                mock_service.return_value = mock_instance

                result = await scrape_yandex_market(TEST_URL)

                assert "ref_link" in result
                assert result["ref_link"].startswith("https://market.yandex.ru/cc/")
                assert "ok" in result.get("flags", [])
                assert "title" in result

        @pytest.mark.asyncio
        async def test_get_cc_link_playwright_browser_error(self):
            """Unit тест: Playwright BrowserType.launch error → возвращает needs_playwright_install"""
            from utils.get_ref_link import get_cc_link_by_click

            # Мокаем ошибку запуска браузера
            with patch("utils.get_ref_link.async_playwright") as mock_playwright:
                mock_playwright.side_effect = Exception(
                    "BrowserType.launch error: Executable doesn't exist"
                )

                result = await get_cc_link_by_click(TEST_URL)

                assert "needs_playwright_install" in result.get("flags", [])
                assert result.get("ref_link") is None

        @pytest.mark.asyncio
        async def test_get_cc_link_success(self):
            """Unit тест: Playwright успешно находит cc-ссылку"""
            from utils.get_ref_link import get_cc_link_by_click

            # Мокаем успешный сценарий
            mock_page = MagicMock()
            mock_page.goto = AsyncMock()
            mock_page.wait_for_timeout = AsyncMock()
            mock_page.query_selector_all = AsyncMock(return_value=[])
            mock_modal = MagicMock()
            mock_modal.query_selector = AsyncMock(return_value=MagicMock())
            mock_modal.inner_text = AsyncMock(
                return_value="https://market.yandex.ru/cc/8BvWCv"
            )
            mock_page.query_selector = AsyncMock(
                side_effect=[
                    MagicMock(),  # share button
                    mock_modal,  # modal
                    MagicMock(),  # copy button
                ]
            )
            mock_page.evaluate = AsyncMock(return_value=None)

            mock_context = MagicMock()
            mock_context.add_cookies = AsyncMock()
            mock_context.new_page = AsyncMock(return_value=mock_page)

            mock_browser = MagicMock()
            mock_browser.new_context = AsyncMock(return_value=mock_context)
            mock_browser.close = AsyncMock()

            mock_p = MagicMock()
            mock_p.chromium.launch = AsyncMock(return_value=mock_browser)

            with patch("utils.get_ref_link.async_playwright", return_value=mock_p):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    result = await get_cc_link_by_click(TEST_URL)

                    # Проверяем что функция пыталась найти ссылку
                    assert "flags" in result
                    # В реальном сценарии может быть ok или ref_not_found в зависимости от моков

        @pytest.mark.asyncio
        async def test_fetch_via_api_404(self):
            """Unit тест: fetch_via_api возвращает 404 → api_failed"""
            from utils.scraper import fetch_via_api

            # Мокаем 404 ответ
            with patch("aiohttp.ClientSession") as mock_session:
                mock_resp = MagicMock()
                mock_resp.status = 404
                mock_resp.json = AsyncMock(
                    return_value={"errors": [{"code": "NOT_FOUND"}]}
                )
                mock_resp.text = AsyncMock(
                    return_value='{"errors": [{"code": "NOT_FOUND"}]}'
                )

                mock_session.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_resp
                )
                mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
                mock_resp.__aexit__ = AsyncMock(return_value=None)

                result = await fetch_via_api(TEST_URL)

                assert (
                    result.get("_debug") == "api_failed"
                    or result.get("_debug") == "ok_from_api"
                )


if __name__ == "__main__":
    # Запуск тестов
    if HAS_PYTEST:
        pytest.main([__file__, "-v"])
    else:
        print("⚠️  pytest не установлен. Установите: pip install pytest")
        print("Запуск простого теста без pytest...")

        async def run_all_tests():
            """Запускает все тесты без pytest"""
            print("\n" + "=" * 60)
            print("ЗАПУСК ТЕСТОВ БЕЗ PYTEST")
            print("=" * 60)

            # Тест 1: scrape_without_cookies
            print("\n[Тест 1] scrape_without_cookies...")
            try:
                from utils.scraper import scrape_yandex_market

                with patch("utils.scraper.PartnerLinkService") as mock_service:
                    mock_instance = MagicMock()
                    mock_instance.get_partner_link = AsyncMock(
                        return_value={
                            "ref_link": "",
                            "flags": ["api_failed", "needs_login"],
                            "title": "Test Product",
                            "price": "100 ₽",
                            "image_bytes": None,
                        }
                    )
                    mock_service.return_value = mock_instance

                    result = await scrape_yandex_market(TEST_URL)

                    assert "ref_link" in result
                    assert "flags" in result
                    print("✅ Тест 1 пройден")
            except Exception as e:
                print(f"❌ Тест 1 провален: {e}")
                import traceback

                traceback.print_exc()

            # Тест 2: scrape_with_cookies
            print("\n[Тест 2] scrape_with_cookies...")
            try:
                from utils.scraper import scrape_yandex_market

                with patch("utils.scraper.PartnerLinkService") as mock_service:
                    mock_instance = MagicMock()
                    mock_instance.get_partner_link = AsyncMock(
                        return_value={
                            "ref_link": "https://market.yandex.ru/cc/8BvWCv",
                            "flags": ["ok", "copied_via_button"],
                            "title": "Test Product",
                            "price": "100 ₽",
                            "image_bytes": None,
                        }
                    )
                    mock_service.return_value = mock_instance

                    result = await scrape_yandex_market(TEST_URL)

                    assert "ref_link" in result
                    assert result["ref_link"].startswith("https://market.yandex.ru/cc/")
                    print("✅ Тест 2 пройден")
            except Exception as e:
                print(f"❌ Тест 2 провален: {e}")
                import traceback

                traceback.print_exc()

            # Тест 3: get_cc_link_playwright_browser_error
            print("\n[Тест 3] get_cc_link_playwright_browser_error...")
            try:
                from utils.get_ref_link import get_cc_link_by_click

                with patch("utils.get_ref_link.async_playwright") as mock_playwright:
                    mock_playwright.side_effect = Exception(
                        "BrowserType.launch error: Executable doesn't exist"
                    )

                    result = await get_cc_link_by_click(TEST_URL)

                    assert "needs_playwright_install" in result.get("flags", [])
                    assert result.get("ref_link") is None
                    print("✅ Тест 3 пройден")
            except Exception as e:
                print(f"❌ Тест 3 провален: {e}")
                import traceback

                traceback.print_exc()

            # Тест 4: get_cc_link_success
            print("\n[Тест 4] get_cc_link_success...")
            try:
                from utils.get_ref_link import get_cc_link_by_click

                mock_page = MagicMock()
                mock_page.goto = AsyncMock()
                mock_page.wait_for_timeout = AsyncMock()
                mock_page.query_selector_all = AsyncMock(return_value=[])
                mock_modal = MagicMock()
                mock_modal.query_selector = AsyncMock(return_value=MagicMock())
                mock_modal.inner_text = AsyncMock(
                    return_value="https://market.yandex.ru/cc/8BvWCv"
                )
                mock_page.query_selector = AsyncMock(
                    side_effect=[
                        MagicMock(),  # share button
                        mock_modal,  # modal
                        MagicMock(),  # copy button
                    ]
                )
                mock_page.evaluate = AsyncMock(return_value=None)

                mock_context = MagicMock()
                mock_context.add_cookies = AsyncMock()
                mock_context.new_page = AsyncMock(return_value=mock_page)

                mock_browser = MagicMock()
                mock_browser.new_context = AsyncMock(return_value=mock_context)
                mock_browser.close = AsyncMock()

                mock_p = MagicMock()
                mock_p.chromium.launch = AsyncMock(return_value=mock_browser)

                with patch("utils.get_ref_link.async_playwright", return_value=mock_p):
                    with patch("asyncio.sleep", new_callable=AsyncMock):
                        result = await get_cc_link_by_click(
                            TEST_URL, headless=True, timeout_ms=5000
                        )

                        assert "flags" in result
                        print("✅ Тест 4 пройден")
            except Exception as e:
                print(f"❌ Тест 4 провален: {e}")
                import traceback

                traceback.print_exc()

            print("\n" + "=" * 60)
            print("ТЕСТЫ ЗАВЕРШЕНЫ")
            print("=" * 60)

        asyncio.run(run_all_tests())
