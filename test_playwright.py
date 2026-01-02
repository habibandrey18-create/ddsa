import asyncio
import json
from playwright.async_api import async_playwright

HEADERS = {
    "Accept-Language": "ru-RU,ru;q=0.9",
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

async def fetch_market_catalog(url: str) -> list:
    """Playwright fetch for Yandex.Market catalog"""
    print(f"Fetching with Playwright: {url}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,   # в проде лучше True
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ]
        )

        context = await browser.new_context(
            user_agent=USER_AGENT,
            locale="ru-RU",
            extra_http_headers=HEADERS,
            viewport={"width": 1366, "height": 768},
        )

        page = await context.new_page()

        await page.goto(url, wait_until="networkidle", timeout=60000)

        # небольшая "человеческая" пауза
        await page.wait_for_timeout(3000)

        html = await page.content()
        await browser.close()

    return parse_next_data(html)

def parse_next_data(html: str) -> list:
    """Parse __NEXT_DATA__ from HTML"""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")

        script = soup.find("script", id="__NEXT_DATA__")
        if not script:
            print("❌ __NEXT_DATA__ not found")
            return []

        data = json.loads(script.string)

        # путь может меняться, но этот сейчас рабочий
        try:
            items = (
                data["props"]["pageProps"]
                ["initialState"]["search"]["results"]["items"]
            )
        except KeyError:
            print("❌ Items path not found in JSON")
            return []

        products = []

        for item in items:
            try:
                products.append({
                    "market_id": item["id"],
                    "title": item.get("titles", {}).get("raw", item.get("title", "No title")),
                    "price": item.get("prices", {}).get("value"),
                    "rating": item.get("rating"),
                    "reviews": item.get("reviewsCount"),
                    "url": f"https://market.yandex.ru/product/{item['id']}"
                })
            except KeyError as e:
                print(f"KeyError parsing item: {e}")
                continue

        return products

    except Exception as e:
        print(f"Error in parse_next_data: {e}")
        return []

async def main():
    """Test Playwright parsing"""
    url = "https://market.yandex.ru/catalog--naushniki/"
    products = await fetch_market_catalog(url)

    print(f"✅ Parsed products: {len(products)}")
    for p in products[:3]:
        print(f"  - {p['title']} | {p['price']} ₽ | Rating: {p.get('rating', 'N/A')}")

if __name__ == "__main__":
    asyncio.run(main())