@echo off
chcp 65001 >nul

REM ============================================
REM Простой запуск всех тестов
REM ============================================

echo Запуск тестов...
echo.

REM Активация виртуального окружения (если есть)
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

REM Запуск тестов
python run_tests.py

echo.
echo Готово!
pause

