"""zed-downloader Telegram bot package.

The bot is a thin client: it talks to the backend exclusively through the
internal HTTP API (see bot/services/api_client.py). It never touches the
database, Redis, or performs downloads itself -- the backend worker delivers
media files directly to Telegram chats.
"""
