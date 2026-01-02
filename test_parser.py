import asyncio
from services.smart_search_service import SmartSearchService

async def test_parser():
    # Test with saved HTML file
    try:
        with open('yandex_search_page.html', 'r', encoding='utf-8') as f:
            html = f.read()

        print(f'Testing parser with {len(html)} chars of HTML')

        # Create service instance
        service = SmartSearchService()

        # Test extraction
        products = service._extract_products_from_search(html)

        print(f'Extracted {len(products)} products:')
        for i, product in enumerate(products[:3]):
            print(f'  Product {i+1}: {product["title"][:50]}... Price: {product.get("price", "N/A")}')

    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(test_parser())