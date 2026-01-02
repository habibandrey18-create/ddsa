#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from services.analytics_service import AnalyticsService

def test_analytics_methods():
    # Создаем экземпляр сервиса
    analytics = AnalyticsService(None)

    # Проверяем все методы, которые вызываются в bot.py
    methods_to_check = [
        'get_category_stats',
        'get_price_range_stats',
        'get_error_stats',
        'get_time_distribution',
        'get_top_products'
    ]

    print('Проверяю наличие всех методов в AnalyticsService:')
    all_good = True

    for method_name in methods_to_check:
        exists = hasattr(analytics, method_name)
        callable_ = callable(getattr(analytics, method_name, None))
        status = 'OK' if exists and callable_ else 'FAIL'
        print(f'{method_name}: exists={exists}, callable={callable_} - {status}')
        if not (exists and callable_):
            all_good = False

    if all_good:
        print('\nВсе методы существуют и callable!')
    else:
        print('\nЕсть проблемы с методами!')

    return all_good

if __name__ == '__main__':
    test_analytics_methods()


