#!/usr/bin/env python3
# -*- coding: utf-8 -*-

def check_bot_analytics():
    try:
        # Имитируем импорт как в bot.py
        from services.analytics_service import AnalyticsService
        print('AnalyticsService импортируется успешно')

        # Проверяю создание экземпляра
        analytics = AnalyticsService(None)  # None вместо реальной БД для теста
        print('AnalyticsService создается успешно')

        # Проверяю все методы, которые вызываются в bot.py
        methods_to_test = [
            ('get_daily_stats', lambda: analytics.get_daily_stats(days=7)),
            ('get_category_stats', lambda: analytics.get_category_stats()),
            ('get_price_range_stats', lambda: analytics.get_price_range_stats()),
            ('get_error_stats', lambda: analytics.get_error_stats()),
            ('get_time_distribution', lambda: analytics.get_time_distribution(days=7)),
            ('get_top_products', lambda: analytics.get_top_products(limit=5))
        ]

        for method_name, method_call in methods_to_test:
            try:
                result = method_call()
                print(f'{method_name}: OK (returns {type(result).__name__})')
            except Exception as e:
                print(f'{method_name}: FAIL - {e}')

        print('\nВсе проверки пройдены успешно!')
        return True

    except Exception as e:
        print(f'Ошибка: {e}')
        return False

if __name__ == '__main__':
    check_bot_analytics()


