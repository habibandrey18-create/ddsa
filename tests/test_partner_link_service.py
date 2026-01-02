"""
Unit тесты для PartnerLinkService
"""

import pytest
from unittest.mock import AsyncMock, patch
from services.partner_link_service import ensure_partner_link, PartnerLinkInfo


class TestEnsurePartnerLink:
    """Тесты для ensure_partner_link"""

    @pytest.mark.asyncio
    async def test_ensure_partner_link_cc_direct(self):
        """Тест 17: Передан cc-URL напрямую"""
        url = "https://market.yandex.ru/cc/ABC123"
        url_info = {"is_cc": True, "cc_code": "ABC123", "normalized_card_url": None}

        result = await ensure_partner_link(url, url_info, None)

        assert isinstance(result, PartnerLinkInfo)
        assert result.has_ref is True
        assert result.ref_link == "https://market.yandex.ru/cc/ABC123"
        assert result.source == "from_input"
        assert "cc_url_direct" in result.flags

    @pytest.mark.asyncio
    async def test_ensure_partner_link_from_scraper(self):
        """Тест 18: В данных уже есть ref_link"""
        url = "https://market.yandex.ru/card/product/123456"
        url_info = {"is_cc": False, "is_card": True, "normalized_card_url": url}
        existing_data = {
            "ref_link": "https://market.yandex.ru/cc/XYZ789",
            "product_url": url,
            "has_ref": True,
            "flags": ["from_scraper"],
        }

        result = await ensure_partner_link(url, url_info, existing_data)

        assert result.has_ref is True
        assert result.ref_link == "https://market.yandex.ru/cc/XYZ789"
        assert result.source == "from_scraper"

    @pytest.mark.asyncio
    async def test_ensure_partner_link_extracted(self):
        """Тест 19: CC код извлечён из параметров URL"""
        url = "https://market.yandex.ru/card/product?cc=DEF456"
        url_info = {
            "is_cc": False,
            "is_card": True,
            "normalized_card_url": "https://market.yandex.ru/card/product",
        }

        result = await ensure_partner_link(url, url_info, None)

        assert result.has_ref is True
        assert result.ref_link == "https://market.yandex.ru/cc/DEF456"
        assert result.source == "extracted"
        assert "cc_found_in_params" in result.flags

    @pytest.mark.asyncio
    async def test_ensure_partner_link_none(self):
        """Тест 20: Партнёрская ссылка не найдена"""
        url = "https://market.yandex.ru/card/product/123456"
        url_info = {"is_cc": False, "is_card": True, "normalized_card_url": url}
        existing_data = {"has_ref": False, "flags": []}

        result = await ensure_partner_link(url, url_info, existing_data)

        assert result.has_ref is False
        assert result.ref_link is None
        assert result.source == "none"
        assert "no_partner_link" in result.flags
