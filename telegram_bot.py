import os

import structlog
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

load_dotenv()

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = int(os.environ["TELEGRAM_CHAT_ID"])

log = structlog.get_logger()


async def _allowlist_filter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ignore silently any update not from CHAT_ID."""
    if update.effective_chat and update.effective_chat.id != CHAT_ID:
        return


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_text("pong")


def main() -> None:
    app = ApplicationBuilder().token(TOKEN).build()
    # Allowlist: drop updates from other chat_ids
    app.add_handler(MessageHandler(~filters.Chat(CHAT_ID), _allowlist_filter))
    app.add_handler(CommandHandler("ping", cmd_ping, filters=filters.Chat(CHAT_ID)))
    log.info("telegram_bot_starting", chat_id=CHAT_ID)
    app.run_polling()


if __name__ == "__main__":
    main()
