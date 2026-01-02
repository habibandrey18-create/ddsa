# Simple test runner without pytest
from services.affiliate_service import get_affiliate_link
from services.formatting_service import generate_hashtags, format_post_simple
from services.post_service import is_product_valid
from services.publish_service import SimplePublishService
import collections

def test_get_affiliate_link_unique():
    print("Testing get_affiliate_link_unique...")
    link1, erid1 = get_affiliate_link("https://market.yandex.ru/product/1")
    link2, erid2 = get_affiliate_link("https://market.yandex.ru/product/1")
    assert link1 != link2, "Links should be different"
    assert erid1 != erid2, "ERIDs should be different"
    assert "ERID=" in link1, "Link should contain ERID"
    print("✓ PASSED")

def test_generate_hashtags_unique():
    print("Testing generate_hashtags_unique...")
    product_name = "Test Product"
    keywords = ["test", "product"]
    tags = generate_hashtags(product_name, keywords)
    assert "#test" in tags and "#product" in tags, "Should contain test tags"
    print("✓ PASSED")

def test_format_post_content():
    print("Testing format_post_content...")
    title = "Test"
    price = 1000
    affiliate_link = "http://test"
    content = format_post_simple(title, price, affiliate_link, title, ["test"])
    assert title in content, "Should contain title"
    assert affiliate_link in content, "Should contain affiliate link"
    print("✓ PASSED")

def test_is_product_valid():
    print("Testing is_product_valid...")
    class GoodProduct:
        price = 100
        discount = 20
        rating = 4.5
        reviews = 100
        title = "Good"
    is_valid, reasons = is_product_valid(GoodProduct())
    assert is_valid, "Good product should be valid"
    assert reasons == [], "Should have no reasons"

    class BadProduct:
        price = 0
        discount = 0
        rating = 3.0
        reviews = 10
        title = "Bad"
    is_valid, reasons = is_product_valid(BadProduct())
    assert not is_valid, "Bad product should be invalid"
    assert len(reasons) > 0, "Should have reasons"
    print("✓ PASSED")

def test_brand_repetition():
    print("Testing brand_repetition...")
    ps = SimplePublishService()
    ps.last_brands = collections.deque(["A", "A", "A"], maxlen=3)
    post = type("P", (), {"link": "http://example.com", "brand": "A", "price": 100})
    ps.add_to_queue(post)
    ps.publish_scheduled()
    # После попытки публикации с повторяющимся брендом, очередь должна опустеть
    assert not ps.queue, "Queue should be empty after publishing repeated brand"
    print("✓ PASSED")

if __name__ == "__main__":
    print("Running service tests...")

    try:
        test_get_affiliate_link_unique()
        test_generate_hashtags_unique()
        test_format_post_content()
        test_is_product_valid()
        test_brand_repetition()

        print("\n🎉 All tests passed!")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()