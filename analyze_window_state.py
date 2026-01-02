import json
from bs4 import BeautifulSoup

# Load HTML and extract window.state
with open('yandex_search_page.html', 'r', encoding='utf-8') as f:
    html = f.read()

soup = BeautifulSoup(html, 'lxml')
scripts = soup.find_all('script')

# Find window.state script
state_script = None
for script in scripts:
    content = script.string
    if content and 'window.state=' in content:
        state_script = content
        break

if state_script:
    print('Found window.state script!')

    # Extract JSON part
    start = state_script.find('window.state=') + len('window.state=')
    json_str = state_script[start:].strip()

    # Remove trailing semicolon if present
    if json_str.endswith(';'):
        json_str = json_str[:-1]

    try:
        state_data = json.loads(json_str)
        print('Successfully parsed window.state JSON')
        print(f'Top-level keys: {list(state_data.keys())}')

        # Look for product data
        if 'entities' in state_data:
            entities = state_data['entities']
            print(f'\\nEntities keys: {list(entities.keys())}')

            # Look for products
            for key, value in entities.items():
                if 'product' in key.lower() or 'snippet' in key.lower():
                    print(f'\\nFound {key}: {type(value)}')
                    if isinstance(value, dict):
                        if len(value) <= 20:
                            print(f'  Content keys: {list(value.keys())}')
                        else:
                            print(f'  {len(value)} items, showing first 5:')
                            for i, (subkey, subvalue) in enumerate(list(value.items())[:5]):
                                if isinstance(subvalue, dict):
                                    print(f'    {subkey}: dict with keys {list(subvalue.keys())}')
                                else:
                                    print(f'    {subkey}: {type(subvalue)} - {str(subvalue)[:100]}...')

        # Look for search results or product lists
        search_related_keys = [k for k in state_data.keys() if 'search' in k.lower() or 'product' in k.lower() or 'result' in k.lower()]
        print(f'\\nSearch/product related keys: {search_related_keys}')

        for key in search_related_keys:
            value = state_data[key]
            print(f'\\n{key}: {type(value)}')
            if isinstance(value, list) and len(value) > 0:
                print(f'  List with {len(value)} items')
                for i, item in enumerate(value[:3]):
                    if isinstance(item, dict):
                        print(f'    Item {i+1}: {list(item.keys())}')
                    else:
                        print(f'    Item {i+1}: {type(item)} - {str(item)[:100]}...')
            elif isinstance(value, dict):
                print(f'  Dict with keys: {list(value.keys())}')

        # Check if there's a direct products array
        if 'products' in state_data:
            products = state_data['products']
            product_type = len(products) if isinstance(products, list) else "not a list"
            print(f'\\nDirect products array: {product_type}')
            if isinstance(products, list) and len(products) > 0:
                print(f'First product: {products[0]}')

    except json.JSONDecodeError as e:
        print(f'Failed to parse JSON: {e}')
        print(f'JSON preview: {json_str[:200]}...')

else:
    print('window.state script not found')