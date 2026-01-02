# Yandex Market Bot Setup Instructions

## Recent Updates (Groq AI Integration)

The bot has been updated to use **Groq AI** for generating dynamic product descriptions instead of ChatGPT. This provides faster and more cost-effective AI content generation.

## Quick Setup

### 1. Environment Variables

The bot requires several environment variables to be set. You can set them in several ways:

#### Option A: Using the Setup Script (Recommended)
Run the included setup script:
```batch
setup_env.bat
```

#### Option B: Create a .env file
Create a `.env` file in the project directory with your configuration:
```
# Required settings
GROQ_API_KEY=your_groq_api_key_here
BOT_TOKEN=your_telegram_bot_token_here
ADMIN_ID=your_telegram_user_id_here
CHANNEL_ID=@your_channel_username

# Optional settings (uncomment and modify as needed)
# REF_CODE=your_referral_code
# UTM_SOURCE=telegram
# UTM_MEDIUM=bot
# UTM_CAMPAIGN=marketi_tochka
```

#### Option C: Set Environment Variables Manually
```batch
setx GROQ_API_KEY "your_groq_api_key_here" /M
setx BOT_TOKEN "your_bot_token" /M
setx ADMIN_ID "your_user_id" /M
setx CHANNEL_ID "@your_channel" /M
```

### 2. Test Your Setup

Run the test script to verify everything is working:
```batch
python test_groq.py
```

You should see:
```
[SUCCESS] Groq API is working correctly!
The bot should now be able to generate AI descriptions.
```

### 3. Install Dependencies

Make sure all dependencies are installed:
```batch
pip install -r requirements.txt
```

### 4. Run the Bot

Start the bot:
```batch
python bot.py
```

## Required Configuration

### Telegram Bot Token
1. Go to [@BotFather](https://t.me/botfather) on Telegram
2. Create a new bot with `/newbot`
3. Copy the token and set it as `BOT_TOKEN`

### Admin ID
Your Telegram user ID. You can:
1. Message [@userinfobot](https://t.me/userinfobot) to get your ID
2. Or check bot logs when you interact with it

### Channel ID
Your Telegram channel username (e.g., `@mychannel`)

### Groq API Key
Already provided and configured in the setup script.

## Troubleshooting

### "GROQ_API_KEY not found"
- Run `setup_env.bat` or set the environment variable manually
- Restart your command prompt/terminal after setting environment variables

### Import errors
- Make sure you're in the correct directory
- Run `pip install -r requirements.txt`

### Bot won't start
- Check that all required environment variables are set
- Verify your bot token is correct
- Make sure the channel exists and the bot is added as administrator

## Recent Changes

- ✅ **Fixed critical bugs**: Removed `force` argument error and `Tuple` import error
- ✅ **New AI integration**: Replaced ChatGPT with Groq for faster, cheaper AI descriptions
- ✅ **Improved formatting**: Clean post template with better hashtag generation
- ✅ **Enhanced error handling**: More robust fallback mechanisms

The bot now generates posts in this format:
```
🔥 Product Title

💰 Price: XXXX ₽ (price may vary)

✍️ AI-generated description

👉 View on Market (link)

#hashtag1 #hashtag2 #покупки
```
