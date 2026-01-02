from bs4 import BeautifulSoup
import json

# Load saved HTML
with open('yandex_search_page.html', 'r', encoding='utf-8') as f:
    html = f.read()

print(f"HTML length: {len(html)} chars")
soup = BeautifulSoup(html, 'lxml')

# Check JSON-LD scripts
json_scripts = soup.find_all('script', type='application/ld+json')
print(f'\\nFound {len(json_scripts)} JSON-LD scripts')

for i, script in enumerate(json_scripts):
    try:
        data = json.loads(script.string)
        print(f'\\nScript {i+1}: {type(data)}')
        if isinstance(data, dict):
            print(f'  Keys: {list(data.keys())}')
            if '@type' in data:
                print(f'  Type: {data.get("@type")}')
            if 'name' in data:
                print(f'  Name: {data.get("name")[:100]}...')
        elif isinstance(data, list) and len(data) > 0:
            print(f'  First item type: {data[0].get("@type") if isinstance(data[0], dict) else type(data[0])}')
            if len(data) <= 10:
                print(f'  Items: {len(data)}')
            else:
                print(f'  Items: {len(data)} (showing first 3)')
                for j, item in enumerate(data[:3]):
                    if isinstance(item, dict) and '@type' in item:
                        print(f'    Item {j+1}: {item.get("@type")} - {item.get("name", "No name")[:50]}...')
    except Exception as e:
        print(f'Script {i+1}: Failed to parse JSON - {e}')

# Look for data-zone-name attributes
zone_elements = soup.find_all(attrs={'data-zone-name': True})
print(f'\\nFound {len(zone_elements)} data-zone-name elements')
zone_counts = {}
for elem in zone_elements:
    zone_name = elem.get('data-zone-name')
    zone_counts[zone_name] = zone_counts.get(zone_name, 0) + 1

for zone_name, count in sorted(zone_counts.items()):
    print(f'  {zone_name}: {count}')

# Look for any script tags that might contain product data
all_scripts = soup.find_all('script')
print(f'\\nTotal script tags: {len(all_scripts)}')

# Look for scripts with state or data
state_scripts = []
for script in all_scripts:
    content = script.string
    if content and len(content) > 1000:  # Only large scripts
        if 'state' in content.lower() or 'product' in content.lower() or 'товар' in content.lower():
            state_scripts.append((len(content), content[:200] + '...'))

print(f'\\nFound {len(state_scripts)} potentially relevant scripts:')
for i, (length, preview) in enumerate(state_scripts[:3]):
    print(f'  Script {i+1}: {length} chars')
    print(f'    Preview: {preview}')

# Look for any divs with data-bem attributes (old Yandex structure)
bem_elements = soup.find_all(attrs={'data-bem': True})
print(f'\\nFound {len(bem_elements)} data-bem elements')

# Look for any elements with product-related classes
product_classes = ['product', 'item', 'card', 'snippet', 'goods']
for class_name in product_classes:
    elements = soup.find_all(class_=lambda x: x and class_name in x.lower())
    print(f'Elements with "{class_name}" in class: {len(elements)}')

print("\\n=== Analysis Complete ===")