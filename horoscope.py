import os
import sys
import time
import random
import logging
from pathlib import Path
from datetime import datetime
import requests
from openai import OpenAI
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# ==================== КЛЮЧИ ====================
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
# ===============================================

logging.basicConfig(
    filename=BASE_DIR / "bot.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    encoding="utf-8"
)

client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"
)

PENDING_FILE = BASE_DIR / "pending_horoscope.txt"
ARCHIVE_DIR = BASE_DIR / "horoscopes"

DAYS_RU = [
    "понедельник", "вторник", "среду", "четверг",
    "пятницу", "субботу", "воскресенье"
]

DAILY_THEMES = [
    "рабочие созвоны, дедлайны и странные сообщения в рабочих чатах",
    "деньги, импульсивные покупки и внезапные бытовые траты",
    "дорога, пробки, навигатор и неожиданные маршруты",
    "домашний уют, капризная техника, еда и соседи",
    "утренний подъём, кофе, расписание и попытки всё успеть",
    "случайные встречи, новости и общение с людьми"
]


def build_prompt() -> str:
    """Формирует промпт с ориентиром по количеству слов (13-15 слов на предложение)."""
    now = datetime.now()
    day_name = DAYS_RU[now.weekday()]
    theme = random.choice(DAILY_THEMES)

    return (
        f"Ты — писатель в стиле Говарда Лавкрафта. Напиши шутливый гороскоп на русском языке "
        f"на {day_name} для каждого из двенадцати знаков зодиака. "
        f"Используй как лёгкий фоновый мотив тему: {theme}, но не повторяй одни и те же ключевые слова "
        "в каждом знаке — пусть у каждого знака будет своя уникальная ситуация, детали и богатая лексика. "
        "Строгий формат для каждого из двенадцати знаков:\n"
        "Первая строка: эмодзи знака, пробел, название знака с заглавной буквы, точка.\n"
        "Вторая строка (сразу с новой строки, без пустой строки после заголовка): один сплошной абзац "
        "из ровно трёх образных предложений без переносов строк внутри этого абзаца.\n"
        "Между знаками ставь ровно одну пустую строку.\n"
        "Строгий объём: в каждом предложении должно быть от 13 до 15 слов (примерно 40–44 слова на один знак). "
        "Весь гороскоп из двенадцати знаков должен занять 500–530 слов (около 3700–3950 символов, но не больше 4000 символов). "
        "Стиль: космический ужас и древняя обречённость абсурдно сталкиваются с бытовой повседневностью, "
        "мрачно, иронично и смешно. Соблюдай безупречную грамотность и орфографию. "
        "Выведи только сам гороскоп, без вступлений, без комментариев, без разметки и строго без латинских букв."
    )


def split_message_by_blocks(text: str, max_len: int = 4050) -> list[str]:
    """Разбивает длинный текст по границам блоков (знаков), не разрывая абзацы."""
    blocks = [b.strip() for b in text.strip().split("\n\n") if b.strip()]
    parts = []
    current_part = ""

    for block in blocks:
        candidate = f"{current_part}\n\n{block}" if current_part else block
        if len(candidate) <= max_len:
            current_part = candidate
        else:
            if current_part:
                parts.append(current_part)
            current_part = block

    if current_part:
        parts.append(current_part)

    return parts


def generate() -> bool:
    """Запрос к DeepSeek с контролем длины текста, сохранение в архив и pending."""
    logging.info("Режим generate: запрос к DeepSeek...")
    prompt = build_prompt()
    last_valid_text = ""

    for attempt in range(1, 4):
        try:
            response = client.chat.completions.create(
                model="deepseek-flash",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4000,
                stream=False,
                extra_body={"thinking": {"type": "disabled"}}
            )
            text = (response.choices[0].message.content or "").strip()
            if not text:
                logging.error("DeepSeek вернул пустой ответ")
                continue

            last_valid_text = text
            length = len(text)
            logging.info(f"Попытка {attempt}/3: сгенерировано {length} символов.")

            if 3300 <= length <= 4040 or attempt == 3:
                ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
                filename = datetime.now().strftime("%d-%m-%Y-%H-%M") + ".txt"
                filepath = ARCHIVE_DIR / filename
                filepath.write_text(text + "\n", encoding="utf-8")
                logging.info(f"Сохранено в архив: {filepath}")

                PENDING_FILE.write_text(text + "\n", encoding="utf-8")
                logging.info(f"Сохранено в обработку: {PENDING_FILE}")
                return True

            logging.warning(f"Длина {length} вне диапазона 3300–4040 символов, пробую перегенерировать...")

        except Exception as e:
            logging.error(f"Ошибка DeepSeek (попытка {attempt}/3): {e}")
            if attempt < 3:
                time.sleep(10)

    if last_valid_text:
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        filepath = ARCHIVE_DIR / (datetime.now().strftime("%d-%m-%Y-%H-%M") + ".txt")
        filepath.write_text(last_valid_text + "\n", encoding="utf-8")
        PENDING_FILE.write_text(last_valid_text + "\n", encoding="utf-8")
        return True

    return False


def send() -> bool:
    """Отправка pending-файла в Telegram простым текстом."""
    if not PENDING_FILE.exists():
        logging.warning("Pending-файл не найден. Пробую сгенерировать заново...")
        if not generate():
            logging.error("Не удалось сгенерировать гороскоп. Отправка отменена.")
            return False

    text = PENDING_FILE.read_text(encoding="utf-8")
    if not text.strip():
        logging.error("Режим отправки: временный файл пустой")
        return False

    parts = split_message_by_blocks(text, max_len=4050)
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    all_ok = True

    for part in parts:
        try:
            resp = requests.post(
                url,
                data={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": part
                },
                timeout=15
            )
            if resp.status_code == 200:
                logging.info("Отправлено успешно.")
            else:
                logging.error(f"Telegram-ошибка ({resp.status_code}): {resp.text}")
                all_ok = False
        except Exception as e:
            logging.error(f"Ошибка сети при отправке в Telegram: {e}")
            all_ok = False

    if all_ok:
        PENDING_FILE.unlink(missing_ok=True)
        logging.info("Pending-файл успешно отправлен и удалён.")

    return all_ok


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode == "generate":
        generate()
    elif mode == "send":
        send()
    else:
        if generate():
            send()


if __name__ == "__main__":
    main()
