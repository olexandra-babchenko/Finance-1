"""Telegram entry point using long polling."""

import json
import logging
from pathlib import Path
from typing import Any

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from agent import Agent
from config import BASE_DIR, get_settings
from llm import OpenRouterClient
from storage import JsonStore

logger = logging.getLogger(__name__)
FRIENDLY_ERROR = "Sorry, I had trouble processing that message. Please try again."


def build_agent() -> Agent:
    settings = get_settings()
    field_path = BASE_DIR / "config" / "hr_fields.json"
    knowledge_path = BASE_DIR / "company_knowledge.md"
    with field_path.open("r", encoding="utf-8") as file:
        field_config: list[dict[str, Any]] = json.load(file)
    company_knowledge = knowledge_path.read_text(encoding="utf-8")
    if not field_config:
        raise RuntimeError("config/hr_fields.json does not define any fields")
    if not company_knowledge.strip():
        raise RuntimeError("company_knowledge.md is empty")
    return Agent(
        llm=OpenRouterClient(settings.openrouter_api_key, settings.openrouter_model),
        store=JsonStore(),
        field_config=field_config,
        company_knowledge=company_knowledge,
    )


def _agent(context: ContextTypes.DEFAULT_TYPE) -> Agent:
    return context.application.bot_data["agent"]


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(
            "Hello! I can answer questions using our company information and help "
            "you submit a job application. Use /apply to start, /status to check "
            "an application, /cancel to cancel it, or /reset to clear your session."
        )


async def apply_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message or not update.effective_chat:
        return
    try:
        reply = await _agent(context).start_application(str(update.effective_chat.id))
        await message.reply_text(reply)
    except Exception as exc:
        logger.error("Application start failed (%s)", type(exc).__name__)
        await message.reply_text(FRIENDLY_ERROR)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message or not update.effective_chat:
        return
    store = _agent(context).store
    state = await store.get_session(str(update.effective_chat.id))
    if not state or state.get("mode") != "hr_application":
        await message.reply_text("There is no active application. Use /apply to start one.")
        return
    await message.reply_text(_agent(context).status_text(state))


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message or not update.effective_chat:
        return
    store = _agent(context).store
    state = await store.get_session(str(update.effective_chat.id))
    await store.delete_session(str(update.effective_chat.id))
    if state and state.get("mode") == "hr_application":
        await message.reply_text("Your application has been cancelled.")
    else:
        await message.reply_text("There was no active application to cancel.")


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message or not update.effective_chat:
        return
    await _agent(context).store.delete_session(str(update.effective_chat.id))
    await message.reply_text("Your session has been reset.")


async def text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message or not update.effective_chat or not message.text:
        return
    chat_id = str(update.effective_chat.id)
    try:
        reply = await _agent(context).handle_text(chat_id, message.text)
        await message.reply_text(reply)
    except Exception as exc:
        logger.error("Message handling failed for chat_id=%s (%s)", chat_id, type(exc).__name__)
        await message.reply_text(FRIENDLY_ERROR)


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error = context.error
    logger.error("Telegram update failed (%s)", type(error).__name__ if error else "unknown")
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(FRIENDLY_ERROR)
        except Exception as exc:
            logger.error("Could not send error reply (%s)", type(exc).__name__)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = get_settings()
    agent = build_agent()
    application = Application.builder().token(settings.telegram_bot_token).build()
    application.bot_data["agent"] = agent
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("apply", apply_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message))
    application.add_error_handler(handle_error)
    logger.info("Starting Telegram bot with long polling")
    application.run_polling()


if __name__ == "__main__":
    main()
