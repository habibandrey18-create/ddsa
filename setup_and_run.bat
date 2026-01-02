@echo off
REM Скрипт установки и запуска бота для Windows
setlocal enabledelayedexpansion

echo ============================================================
echo УСТАНОВКА И ЗАПУСК YANDEX.MARKET BOT
echo ============================================================
echo.

REM Проверка Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Python не найден! Установите Python 3.8+
    pause
    exit /b 1
)
echo [OK] Python найден
python --version

REM Создание виртуального окружения
if not exist "venv" (
    echo.
    echo [ШАГ 1] Создание виртуального окружения...
    python -m venv venv
    if errorlevel 1 (
        echo [ОШИБКА] Не удалось создать виртуальное окружение
        pause
        exit /b 1
    )
    echo [OK] Виртуальное окружение создано
) else (
    echo [OK] Виртуальное окружение уже существует
)

REM Активация виртуального окружения
echo.
echo [ШАГ 2] Активация виртуального окружения...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ОШИБКА] Не удалось активировать виртуальное окружение
    pause
    exit /b 1
)
echo [OK] Виртуальное окружение активировано

REM Обновление pip
echo.
echo [ШАГ 3] Обновление pip...
python -m pip install --upgrade pip --quiet
if errorlevel 1 (
    echo [ПРЕДУПРЕЖДЕНИЕ] Не удалось обновить pip, продолжаем...
) else (
    echo [OK] pip обновлен
)

REM Установка зависимостей
echo.
echo [ШАГ 4] Установка зависимостей из requirements.txt...
if not exist "requirements.txt" (
    echo [ОШИБКА] Файл requirements.txt не найден!
    pause
    exit /b 1
)
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ОШИБКА] Не удалось установить зависимости
    pause
    exit /b 1
)
echo [OK] Зависимости установлены

REM Установка Playwright браузеров
echo.
echo [ШАГ 5] Установка Playwright браузеров...
python -m playwright install chromium
if errorlevel 1 (
    echo [ПРЕДУПРЕЖДЕНИЕ] Не удалось установить Playwright браузеры
    echo Это не критично, но может потребоваться для получения партнерских ссылок
) else (
    echo [OK] Playwright браузеры установлены
)

REM Проверка .env файла
echo.
echo [ШАГ 6] Проверка конфигурации...
if not exist ".env" (
    echo [ПРЕДУПРЕЖДЕНИЕ] Файл .env не найден!
    echo Создайте файл .env с настройками бота:
    echo   BOT_TOKEN=ваш_токен
    echo   ADMIN_ID=ваш_id
    echo   CHANNEL_ID=@ваш_канал
    echo.
    set /p continue="Продолжить без .env? (y/n): "
    if /i not "!continue!"=="y" (
        pause
        exit /b 1
    )
) else (
    echo [OK] Файл .env найден
)

REM Опциональный тест
echo.
echo [ШАГ 7] Запуск тестов (опционально)...
if exist "tests\test_partner_link.py" (
    REM Проверяем наличие pytest
    python -c "import pytest" >nul 2>&1
    if errorlevel 1 (
        echo [INFO] pytest не установлен, пропускаем тесты
        echo Для установки: pip install pytest
    ) else (
        python tests\test_partner_link.py
        if errorlevel 1 (
            echo [ПРЕДУПРЕЖДЕНИЕ] Тесты не прошли, но это не критично
        ) else (
            echo [OK] Тесты прошли успешно
        )
    )
) else (
    echo [INFO] Тесты не найдены, пропускаем
)

REM Запуск бота
echo.
echo ============================================================
echo ЗАПУСК БОТА
echo ============================================================
echo.
echo Бот будет запущен. Для остановки нажмите Ctrl+C
echo.
pause

python bot.py

pause

