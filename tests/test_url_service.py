"""
Unit тесты для UrlService
"""

import pytest
from services.url_service import UrlService


class TestUrlService:
    """Тесты для UrlService"""

    def test_parse_url_card_valid(self):
        """Тест 1: Парсинг валидного card-URL"""
        url = "https://market.yandex.ru/card/product-name/123456"
        result = UrlService.parse_url(url)

        assert result["is_card"] is True
        assert result["type"] == "card"
        assert result["normalized_card_url"] is not None
        assert "/card/" in result["normalized_card_url"]

    def test_parse_url_card_with_params(self):
        """Тест 2: Парсинг card-URL с параметрами"""
        url = "https://market.yandex.ru/card/product?cc=ABC123&utm=test"
        result = UrlService.parse_url(url)

        assert result["is_card"] is True
        assert result["type"] == "card"
        # CC код должен извлекаться отдельным методом
        cc_code = UrlService.extract_cc_code(url)
        assert cc_code == "ABC123"

    def test_parse_url_card_broken(self):
        """Тест 3: Парсинг битого card-URL"""
        url = "https://market.yandex.ru/card/"
        result = UrlService.parse_url(url)

        assert result["is_card"] is True
        assert result["type"] == "card"
        # Нормализованный URL должен быть установлен, даже если путь короткий
        assert result["normalized_card_url"] is not None

    def test_parse_url_card_unknown_format(self):
        """Тест 4: Парсинг неизвестного формата"""
        url = "https://market.yandex.ru/unknown/path"
        result = UrlService.parse_url(url)

        assert result["type"] == "unknown"
        assert result["is_card"] is False
        assert result["is_cc"] is False

    def test_parse_url_cc_valid(self):
        """Тест 5: Парсинг валидного cc-URL"""
        url = "https://market.yandex.ru/cc/ABC123"
        result = UrlService.parse_url(url)

        assert result["is_cc"] is True
        assert result["type"] == "cc"
        assert result["cc_code"] == "ABC123"

    def test_parse_url_cc_broken(self):
        """Тест 6: Парсинг битого cc-URL"""
        url = "https://market.yandex.ru/cc/"
        result = UrlService.parse_url(url)

        assert result["is_cc"] is True
        assert result["type"] == "cc"
        assert result["cc_code"] is None

    def test_parse_url_cc_with_tail(self):
        """Тест 7: Парсинг cc-URL с хвостом"""
        url = "https://market.yandex.ru/cc/ABC123,tail"
        result = UrlService.parse_url(url)

        assert result["is_cc"] is True
        assert result["cc_code"] == "ABC123"  # Хвост должен быть обрезан

    def test_extract_cc_from_params(self):
        """Тест 8: Извлечение CC из параметров"""
        url = "https://market.yandex.ru/card/product?cc=XYZ789"
        cc_code = UrlService.extract_cc_code(url)

        assert cc_code == "XYZ789"

    def test_extract_cc_from_tail(self):
        """Тест 9: Извлечение CC из хвоста"""
        url = "https://market.yandex.ru/card/product,ccDEF456"
        cc_code = UrlService.extract_cc_code(url)

        assert cc_code == "DEF456"

    def test_build_cc_link(self):
        """Тест: Построение cc-ссылки из кода"""
        cc_code = "TEST123"
        link = UrlService.build_cc_link(cc_code)

        assert link == "https://market.yandex.ru/cc/TEST123"

    def test_should_use_direct_cc(self):
        """Тест: Проверка необходимости использования cc напрямую"""
        # С cc-ссылкой
        url1 = "https://market.yandex.ru/cc/ABC123"
        should_use1, link1 = UrlService.should_use_direct_cc(url1)
        assert should_use1 is True
        assert link1 == url1

        # С card-URL и cc в параметрах
        url2 = "https://market.yandex.ru/card/product?cc=XYZ789"
        should_use2, link2 = UrlService.should_use_direct_cc(url2)
        assert should_use2 is True
        assert link2 == "https://market.yandex.ru/cc/XYZ789"

        # Без cc
        url3 = "https://market.yandex.ru/card/product"
        should_use3, link3 = UrlService.should_use_direct_cc(url3)
        assert should_use3 is False
        assert link3 is None
