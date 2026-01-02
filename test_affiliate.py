#!/usr/bin/env python3
"""Test script to verify Yandex affiliate link generation"""

import os

def test_affiliate_service():
    """Test the affiliate service functionality"""

    # Set test environment variables
    os.environ["YANDEX_REF_CLID"] = "14432017"
    os.environ["YANDEX_REF_VID"] = "blog"
    os.environ["YANDEX_REF_ERID"] = "5jtCeReNx12oajxRXisMXab"

    try:
        from services.affiliate_service import AffiliateService

        service = AffiliateService()

        # Test URL with existing parameters
        test_url = "https://market.yandex.ru/product/12345?existing=param&another=value"

        affiliate_link = service.make_affiliate_link(test_url)
        print(f"Original URL: {test_url}")
        print(f"Affiliate URL: {affiliate_link}")

        # Check if affiliate parameters are present
        if "clid=14432017" in affiliate_link and "vid=blog" in affiliate_link and "erid=5jtCeReNx12oajxRXisMXab" in affiliate_link:
            print("[OK] Affiliate parameters added correctly")
        else:
            print("[FAIL] Affiliate parameters missing")
            return False

        # Check if UTM parameters are present
        if "utm_source=telegram" in affiliate_link and "distr_type=7" in affiliate_link:
            print("[OK] UTM and distribution parameters added correctly")
        else:
            print("[FAIL] UTM or distribution parameters missing")
            return False

        # Check if old parameters were cleaned
        if "existing=param" not in affiliate_link and "another=value" not in affiliate_link:
            print("[OK] Old parameters cleaned correctly")
        else:
            print("[FAIL] Old parameters not cleaned")
            return False

        # Test ad marking
        if service.should_add_ad_marking():
            marking_text = service.get_ad_marking_text()
            expected_marking = "\nРеклама. ООО «Яндекс Маркет», ИНН 9704254424, erid: 5jtCeReNx12oajxRXisMXab"
            if marking_text == expected_marking:
                print("[OK] Ad marking text generated correctly")
            else:
                print(f"[FAIL] Ad marking text incorrect: {marking_text}")
                return False
        else:
            print("[FAIL] Ad marking should be enabled")
            return False

        return True

    except Exception as e:
        print(f"[FAIL] Error testing affiliate service: {e}")
        return False

if __name__ == "__main__":
    print("Testing Yandex Affiliate Link Generation")
    print("=" * 50)

    success = test_affiliate_service()

    if success:
        print("\n[SUCCESS] Yandex affiliate link generation is working correctly!")
        print("The bot will now generate monetized links with proper ad-marking.")
    else:
        print("\n[FAILED] Affiliate service test failed.")