#!/usr/bin/env python3
"""Test script to verify dynamic AI content generation strategies"""

import asyncio
import os
import sys

async def test_dynamic_ai_strategies():
    """Test all four AI content generation strategies"""

    # Set up environment
    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key:
        print("[FAIL] GROQ_API_KEY not found in environment")
        return False

    try:
        from services.ai_content_service import AIContentService
        print("[OK] AI Content Service imported successfully")

        # Create service instance
        ai_service = AIContentService(groq_key)
        print("[OK] AI Content Service initialized")

        # Test data for different strategies
        test_cases = [
            {
                "name": "Reviews Summary Strategy",
                "data": {
                    "title": "Беспроводные наушники Sony WH-1000XM5",
                    "reviews": [
                        "Отличный звук и шумоподавление!",
                        "Батарея держит долго, очень удобно",
                        "Качество сборки на высоте"
                    ]
                }
            },
            {
                "name": "Key Feature Strategy",
                "data": {
                    "title": "Механическая клавиатура Keychron K8",
                    "specs": "Переключатели: Gateron Brown; Подсветка: RGB; Батарея: 3000mAh"
                }
            },
            {
                "name": "Buyer Persona Strategy",
                "data": {
                    "title": "Игровая мышь Logitech G305"
                }
            },
            {
                "name": "Human Translation Strategy",
                "data": {
                    "title": "Смартфон Samsung Galaxy S24",
                    "marketing_description": "Инновационная технология искусственного интеллекта с профессиональной камерой на 50 МП и ультрабыстрым процессором Snapdragon 8 Gen 3 обеспечивает непревзойденную производительность и качество фотографий."
                }
            }
        ]

        # Test each strategy
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n--- Testing Strategy {i}: {test_case['name']} ---")
            try:
                description = await ai_service.generate_dynamic_description(test_case['data'])
                print(f"[OK] Generated description: {description}")
                print(f"[OK] Length: {len(description)} characters")
            except Exception as e:
                print(f"[FAIL] Strategy {i} failed: {e}")
                return False

        print("\n[SUCCESS] All AI strategies are working correctly!")
        print("The dynamic content generation system is ready.")
        return True

    except ImportError as e:
        print(f"[FAIL] Import error: {e}")
        return False
    except Exception as e:
        print(f"[FAIL] Unexpected error: {e}")
        return False

async def main():
    """Main test function"""
    print("Testing Dynamic AI Content Generation Strategies")
    print("=" * 50)

    success = await test_dynamic_ai_strategies()

    if not success:
        sys.exit(1)

    print("\n" + "=" * 50)
    print("Test completed successfully!")
    print("\nNext steps:")
    print("1. Run the bot to see diverse content generation in action")
    print("2. Check the Telegram channel for varied post descriptions")
    print("3. Each product should use a different AI strategy")

if __name__ == "__main__":
    asyncio.run(main())
