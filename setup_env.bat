@echo off
REM Setup script for Yandex Market Bot environment variables

echo Setting up environment variables for Yandex Market Bot...

REM Set Groq API Key (replace with your actual key)
setx GROQ_API_KEY "your_groq_api_key_here" /M

echo.
echo Environment variables configured!
echo.
echo IMPORTANT: You also need to set these required variables:
echo - BOT_TOKEN (from @BotFather on Telegram)
echo - ADMIN_ID (your Telegram user ID)
echo - CHANNEL_ID (your Telegram channel username)
echo.
echo You can set them by:
echo 1. Creating a .env file in the project directory with these values
echo 2. Or setting them as environment variables using setx command
echo 3. Or editing this batch file to include them
echo.
echo Example .env file content:
echo BOT_TOKEN=your_telegram_bot_token_here
echo ADMIN_ID=your_telegram_user_id_here
echo CHANNEL_ID=@your_channel_username
echo GROQ_API_KEY=your_groq_api_key_here
echo.
pause
