"""Совместимость: python tg_list_chats.py"""

from telegram.list_chats import main

if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
