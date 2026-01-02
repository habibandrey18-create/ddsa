import asyncio
import aiohttp
import re
from bs4 import BeautifulSoup

async def test_yandex_html():
    """Test current Yandex.Market HTML structure"""
    url = 'https://market.yandex.ru/search?text=наушники&page=1'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
    }

    async with aiohttp.ClientSession() as session:
        try:
            print(f"Fetching: {url}")
            async with session.get(url, headers=headers) as resp:
                html = await resp.text()
                print(f'HTML length: {len(html)} chars')

                # Save HTML for analysis
                with open('yandex_search_page.html', 'w', encoding='utf-8') as f:
                    f.write(html)
                print("HTML saved to yandex_search_page.html")

                # Parse with BeautifulSoup
                soup = BeautifulSoup(html, 'lxml')

                # Try different selectors for product cards
                selectors = [
                    '[data-product-id]',  # Old Yandex selector
                    '[data-zone-name="product-card"]',  # New Yandex selector
                    '.product-snippet',  # Common product snippet
                    'article[data-product-id]',  # Article with product ID
                    '.card',  # Generic card class
                    '.product',  # Generic product class
                    '[data-bem]',  # BEM data attributes
                ]

                print("\n=== Testing CSS Selectors ===")
                for selector in selectors:
                    elements = soup.select(selector)
                    print(f"{selector}: {len(elements)} elements found")

                # Look for JSON-LD structured data
                json_scripts = soup.find_all('script', type='application/ld+json')
                print(f"\nJSON-LD scripts: {len(json_scripts)}")

                # Look for data-product-id attributes
                product_ids = []
                for tag in soup.find_all(attrs={'data-product-id': True}):
                    product_ids.append(tag.get('data-product-id'))

                print(f"data-product-id attributes found: {len(product_ids)}")
                if product_ids:
                    print(f"Sample IDs: {product_ids[:5]}")

                # Look for title elements
                titles = soup.find_all(['h1', 'h2', 'h3', 'h4'], class_=re.compile(r'.*title.*', re.I))
                print(f"Title elements: {len(titles)}")
                for i, title in enumerate(titles[:5]):
                    print(f"  Title {i+1}: {title.get_text().strip()[:100]}...")

                # Look for price elements
                prices = soup.find_all(attrs={'data-auto': 'price-value'})
                print(f"Price elements: {len(prices)}")
                for i, price in enumerate(prices[:5]):
                    print(f"  Price {i+1}: {price.get_text().strip()}")

                print("\n=== First 2000 chars of HTML ===")
                print(html[:2000])

        except Exception as e:
            print(f'Error: {e}')
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(test_yandex_html())