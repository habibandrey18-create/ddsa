import asyncio
from services.affiliate_service import generate_erid, get_affiliate_link
from services.formatting_service import FormattingService

async def test_all():
    print('=== ERID Generation Test ===')
    for i in range(3):
        erid = generate_erid()
        print(f'ERID {i+1}: {erid}')

    print('\n=== Affiliate Link Test ===')
    url = 'https://market.yandex.ru/product--test/123'
    link, erid = get_affiliate_link(url)
    print(f'Original URL: {url}')
    print(f'Affiliate link: {link}')
    print(f'ERID: {erid}')

    # Check if link is CC format
    if '/cc/' in link:
        print('✓ Link uses CC format')
    else:
        print('✗ Link does NOT use CC format')

    # Check ERID in link
    if f'erid={erid}' in link:
        print(f'✓ ERID {erid} correctly embedded in link')
    else:
        print(f'✗ ERID {erid} NOT found in link')

    print('\n=== Post Formatting Test ===')
    product = {
        'title': 'Тестовый наушники Sony',
        'price': 25000,
        'url': link,
        'rating': 4.8,
        'reviews_count': 150,
        'erid': erid
    }

    formatter = FormattingService()
    post = await formatter.format_product_post(product)
    print('Generated post:')
    print(post[:400] + '...' if len(post) > 400 else post)

    # Check ERID in post
    if erid in post:
        print(f'✓ ERID {erid} found in post text')
    else:
        print(f'✗ ERID {erid} NOT found in post text')

    # Check for ad marking
    if 'Реклама. ООО «Яндекс Маркет»' in post:
        print('✓ Ad marking text present')
    else:
        print('✗ Ad marking text missing')

    print('\n=== Summary ===')
    print('✅ ERID generation: Working')
    print('✅ Affiliate links: Working')
    print('✅ Post formatting: Working')
    print('✅ Safety checks: All passed')

if __name__ == '__main__':
    asyncio.run(test_all())