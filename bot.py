"""
Bot de Telegram @alexiavegavipbot

Responde a /start (y a /start vip, que llega desde el enlace del canal gratuito)
con un mensaje de bienvenida y un botón que abre el enlace de invitación al canal VIP.
"""

import hashlib
import logging
import os
import sys

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Carga las variables del archivo .env (si existe). En producción también
# se pueden definir directamente como variables de entorno del servidor.
load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
# IMPORTANTE: la librería httpx registra cada petición con la URL completa,
# y esa URL contiene el token del bot. Subimos su nivel para que nunca aparezca.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("vipbot")

WELCOME_TEXT = (
    "Has llegado hasta aquí… así que supongo que tienes curiosidad 😏\n\n"
    "He dejado mi contenido más privado dentro del VIP 🔥\n\n"
    "Entrar es totalmente gratis.\n\n"
    "Nos vemos dentro… 💋"
)
BUTTON_TEXT = "🔥 ENTRAR AL VIP 🔥"

PLACEHOLDERS = {"", "YOUR_BOT_TOKEN", "YOUR_VIP_INVITE_URL"}

# Se rellena al arrancar; solo se usa para borrar el token de cualquier mensaje de error.
_TOKEN = ""


def redact(text: str) -> str:
    """Elimina el token de cualquier texto antes de escribirlo en los logs."""
    if _TOKEN:
        text = text.replace(_TOKEN, "***")
    return text


def load_config() -> tuple[str, str]:
    """Lee y valida las variables de entorno. Detiene el bot si falta algo."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    vip_url = os.getenv("VIP_INVITE_URL", "").strip()

    missing = []
    if token in PLACEHOLDERS:
        missing.append("TELEGRAM_BOT_TOKEN")
    if vip_url in PLACEHOLDERS:
        missing.append("VIP_INVITE_URL")
    if missing:
        logger.error(
            "Faltan variables de entorno: %s. Revisa tu archivo .env.",
            ", ".join(missing),
        )
        sys.exit(1)

    if not vip_url.startswith(("https://t.me/", "https://telegram.me/")):
        logger.error(
            "VIP_INVITE_URL no parece un enlace de Telegram válido. "
            "Debe empezar por https://t.me/"
        )
        sys.exit(1)

    return token, vip_url


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Responde a /start y a /start vip (deep link) con el mismo mensaje y botón."""
    message = update.effective_message
    if message is None:
        return

    # context.args contiene ["vip"] si el usuario llega desde t.me/alexiavegavipbot?start=vip.
    # La respuesta es idéntica en ambos casos, así que no hace falta distinguirlos.
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(BUTTON_TEXT, url=context.bot_data["vip_url"])]]
    )
    await message.reply_text(WELCOME_TEXT, reply_markup=keyboard)


async def add_button_to_channel_photo(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Añade el botón "ENTRAR AL VIP" debajo de cada foto publicada en el canal gratuito.

    El bot debe ser administrador de ese canal con permiso para editar mensajes.
    Nota: Telegram no permite botones en álbumes (varias fotos en una sola publicación),
    así que esas publicaciones se dejan tal cual.
    """
    post = update.channel_post
    if post is None or post.media_group_id or post.reply_markup:
        return

    deep_link = f"https://t.me/{context.bot.username}?start=vip"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(BUTTON_TEXT, url=deep_link)]])
    await post.edit_reply_markup(reply_markup=keyboard)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Registra errores sin mostrar secretos y sin detener el bot."""
    error = context.error
    logger.error(
        "Error procesando una actualización: %s: %s",
        type(error).__name__,
        redact(str(error)),
    )


def main() -> None:
    global _TOKEN
    token, vip_url = load_config()
    _TOKEN = token

    app = (
        Application.builder()
        .token(token)
        .concurrent_updates(True)  # atiende a varios usuarios a la vez
        .build()
    )
    app.bot_data["vip_url"] = vip_url

    # Solo responde en chats privados con el bot (no en grupos ni canales).
    app.add_handler(CommandHandler("start", start, filters=filters.ChatType.PRIVATE))
    # Añade el botón a cada foto publicada en los canales donde el bot es administrador.
    app.add_handler(
        MessageHandler(
            filters.UpdateType.CHANNEL_POST & filters.PHOTO,
            add_button_to_channel_photo,
        )
    )
    app.add_error_handler(on_error)

    allowed = ["message", "channel_post"]
    public_url = os.getenv("RENDER_EXTERNAL_URL", "").strip()

    if public_url:
        # En el servidor (Render): Telegram envía los mensajes a una dirección web del bot.
        # La ruta y la clave secreta se derivan del token, así que nunca aparece el token.
        secret = hashlib.sha256(token.encode()).hexdigest()
        logger.info("Bot iniciado en modo servidor (webhook).")
        app.run_webhook(
            listen="0.0.0.0",
            port=int(os.getenv("PORT", "10000")),
            url_path=secret[:32],
            webhook_url=f"{public_url.rstrip('/')}/{secret[:32]}",
            secret_token=secret[32:],
            allowed_updates=allowed,
        )
    else:
        # En tu ordenador: el bot pregunta a Telegram si hay mensajes nuevos.
        logger.info("Bot iniciado. Pulsa Ctrl+C para detenerlo.")
        app.run_polling(allowed_updates=allowed)


if __name__ == "__main__":
    main()
