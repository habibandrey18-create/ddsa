import asyncio
from services.smart_search_service import SmartSearchService

async def test_catalog_parsing():
    service = SmartSearchService()

    # Тестируем один каталог
    test_url = 'https://market.yandex.ru/catalog--naushniki/'
    print(f'Testing catalog parsing: {test_url}')

    # Получаем HTML
    html = await service._fetch_catalog_page(test_url)
    if html:
        print(f'Fetched HTML: {len(html)} chars')

        # Парсим товары
        products = service._parse_catalog_products(html)
        print(f'Parsed products: {len(products)}')

        # Показываем первые 3 товара
        for i, product in enumerate(products[:3]):
            print(f'  Product {i+1}: {product.get("title", "No title")[:50]}... Price: {product.get("price", "N/A")}')
    else:
        print('Failed to fetch HTML')

if __name__ == '__main__':
    asyncio.run(test_catalog_parsing())