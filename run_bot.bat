@echo off
REM Простой скрипт запуска бота с активацией виртуального окружения
chcp 65001 >nul
echo ========================================
echo   Запуск Yandex.Market Bot
echo ========================================
echo.

REM Проверка наличия виртуального окружения
if not exist "venv\Scripts\activate.bat" (
    echo [ОШИБКА] Виртуальное окружение не найдено!
    echo Запустите setup_and_run.bat для установки зависимостей
    pause
    exit /b 1
)

REM Активация виртуального окружения
echo [INFO] Активация виртуального окружения...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ОШИБКА] Не удалось активировать виртуальное окружение
    pause
    exit /b 1
)

REM Проверка наличия bot.py
if not exist "bot.py" (
    echo [ОШИБКА] Файл bot.py не найден!
    pause
    exit /b 1
)

REM Запуск бота
echo [INFO] Запуск бота...
echo Для остановки нажмите Ctrl+C
echo.
python bot.py

pause


















