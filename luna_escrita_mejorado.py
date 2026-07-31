"""
La Luna Escrita - Bot de Telegram, oráculo de programación en Python.

Mejoras aplicadas sobre la versión original:
1. Las claves (Telegram, Gemini, Groq) ya NO están escritas en el código.
   Se leen de variables de entorno, para no exponerlas si el código se sube
   a un repositorio público. Antes de correr el bot, define en tu sistema:

   export TELEGRAM_TOKEN="tu_token"
   export GEMINI_API_KEY="tu_clave"
   export GROQ_API_KEY="tu_clave"

   (En Windows: set TELEGRAM_TOKEN=tu_token, etc.)

2. Se reemplazó el "except:" genérico por "except Exception as e" con logging,
   para poder ver en consola qué falló exactamente si Gemini no responde.
3. Se evita un KeyError si el usuario llega a "procesar_solicitud" sin haber
   pasado por "elegir_modo" (context.user_data.get en vez de acceso directo).
4. Se valida que exista TELEGRAM_TOKEN antes de arrancar, con un mensaje claro
   si falta alguna variable de entorno.
5. Pequeños ajustes de nombres/documentación siguiendo PEP 8.21
"""

import logging
import os
import re
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from google import genai
from groq import Groq

# --- CONFIGURACIÓN ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

if not all([TELEGRAM_TOKEN, GEMINI_API_KEY, GROQ_API_KEY]):
    raise RuntimeError(
        "Faltan variables de entorno. Define TELEGRAM_TOKEN, GEMINI_API_KEY "
        "y GROQ_API_KEY antes de ejecutar el bot."
    )

client_gemini = genai.Client(api_key=GEMINI_API_KEY)
client_groq = Groq(api_key=GROQ_API_KEY)

MODO, ENTRADA = range(2)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Personalidad mística y técnica
INSTRUCCION_LUNA = (
    "Eres 'La Luna Escrita', un oráculo de programación en Python. "
    "Tu conocimiento es profundo y nocturno. Escribes código elegante, minimalista y robusto. "
    "Siempre usas PEP 8 y documentas tus funciones con sabiduría. "
    "Si el usuario pide código, dáselo en un bloque de Markdown y prepárate para entregarlo como archivo."
)

# ==========================================================
# MOTOR DE IA PARA WEB
# ==========================================================

def responder_web(mensaje, modo="💬 Chat IA"):
    """
    Función reutilizable para la página web.
    Telegram y la Web usarán el mismo motor.
    """

    prompt = f"""
Como 'La Luna Escrita', realiza la siguiente tarea.

Modo:
{modo}

Contenido del usuario:

{mensaje}

Si generas código:

- Usa Markdown.
- Colócalo entre bloques ```python```.
- Explica qué hace.
- Utiliza buenas prácticas.
- Sigue PEP8.
"""

    try:

        response = client_gemini.models.generate_content(

            model="gemini-2.5-flash",

            contents=prompt,

            config={
                "system_instruction": INSTRUCCION_LUNA
            }

        )

        return response.text

    except Exception as e:

        logger.warning(f"Gemini falló: {e}")

        completion = client_groq.chat.completions.create(

            model="llama-3.3-70b-versatile",

            messages=[

                {
                    "role":"system",
                    "content":INSTRUCCION_LUNA
                },

                {
                    "role":"user",
                    "content":prompt
                }

            ]

        )

        return completion.choices[0].message.content

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el menú principal con los tres modos del bot."""
    botones = [
        ["🚀 Superar un Reto (Debug)", "✨ Inventar algo nuevo"],
        ["📚 Expandir el Conocimiento"],
    ]

    saludo_lunar = (
        "🌙 *La Luna Escrita* 🐍\n\n"
        "¡Hola! Qué bueno verte por aquí. El entorno está listo y la mente despejada.\n\n"
        "¿Qué inventaremos hoy? ¿Tenemos un nuevo reto para seguir brillando o "
        "vamos a darle vida a una idea desde cero?"
    )

    await update.message.reply_text(
        saludo_lunar,
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(botones, one_time_keyboard=True, resize_keyboard=True),
    )
    return MODO


async def elegir_modo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guarda el modo elegido y pide el contenido correspondiente."""
    modo = update.message.text
    context.user_data["modo"] = modo

    opciones = {
        "🛠 Reparar Script": "Pega el código que ha perdido su luz (errores):",
        "📜 Escribir Hechizo (Código)": "¿Qué script deseas que la Luna escriba para ti?",
        "📖 Sabiduría Python": "¿Qué concepto deseas que te revele?",
    }

    await update.message.reply_text(
        opciones.get(modo, "Dime los detalles:"),
        reply_markup=ReplyKeyboardRemove(),
    )
    return ENTRADA


async def procesar_solicitud(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envía la solicitud del usuario a Gemini (con respaldo en Groq) y responde."""
    user_text = update.message.text
    # .get con valor por defecto evita un KeyError si se llega aquí sin pasar por elegir_modo
    modo = context.user_data.get("modo", "Sabiduría Python")

    await update.message.reply_text(
        "✨ *Consultando las constelaciones de código...*", parse_mode="Markdown"
    )

    prompt = (
        f"Como 'La Luna Escrita', realiza lo siguiente: {modo} con este contenido: {user_text}. "
        "Si generas código, ponlo entre bloques ```python ... ```"
    )

    try:
        response = client_gemini.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt,
            config={"system_instruction": INSTRUCCION_LUNA},
        )
        respuesta = response.text
    except Exception as e:
        logger.warning("Gemini falló, usando respaldo en Groq: %s", e)
        completion = client_groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": INSTRUCCION_LUNA},
                {"role": "user", "content": prompt},
            ],
        )
        respuesta = completion.choices[0].message.content

    # 1. Enviar la explicación por mensaje
    await update.message.reply_text(respuesta)

    # 2. Extraer código y enviarlo como archivo .py (solo si hay código)
    match = re.search(r"```python\s+(.*?)\s+```", respuesta, re.DOTALL)
    if match:
        codigo_extraido = match.group(1)
        filename = f"hechizo_{update.effective_user.id}.py"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(codigo_extraido)

        with open(filename, "rb") as doc:
            await update.message.reply_document(
                document=doc,
                filename="codigo_lunar.py",
                caption="🌙 Aquí tienes el archivo listo para ejecutar.",
            )
        os.remove(filename)

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela la conversación en curso."""
    await update.message.reply_text(
        "🌙 La Luna se oculta. Hasta pronto.", reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MODO: [MessageHandler(filters.TEXT & ~filters.COMMAND, elegir_modo)],
            ENTRADA: [MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_solicitud)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(handler)
    print("🌙 La Luna Escrita está brillando...")
    app.run_polling()
