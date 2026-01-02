@echo off
REM Запуск браузера Yandex с remote debugging для автоматизации
REM Этот скрипт запускает браузер Yandex с портом 9222 для подключения через CDP

set BROWSER_PATH=C:\Users\NewAdmin\AppData\Local\Yandex\YandexBrowser\Application\browser.exe
set DEBUG_PORT=9222

echo Запуск браузера Yandex с remote debugging на порту %DEBUG_PORT%...
echo Браузер будет доступен для подключения через CDP: http://127.0.0.1:%DEBUG_PORT%

start "" "%BROWSER_PATH%" --remote-debugging-port=%DEBUG_PORT%

echo.
echo Браузер запущен. Теперь можно запускать бота.
echo Для остановки просто закройте окно браузера.
pause



