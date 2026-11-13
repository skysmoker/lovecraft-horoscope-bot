import os
import sys
import requests
from openai import OpenAI
from datetime import datetime
from dotenv import load_dotenv
import logging

# Загружаем секреты из .env
load_dotenv()

# ==================== КЛЮЧИ ====================
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
# ===============================================

logging.basicConfig(
    filename="/home/skysmoker/horoscope-bot/bot.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    encoding="utf-8"
)

client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"
)

PROMPT = """Ты — писатель в стиле Говарда Лавкрафта. Напиши шутливый гороскоп на русском языке на сегодняшний день для каждого из двенадцати знаков зодиака. Для каждого знака — ровно три простых предложения. Каждое предложение — не короче 45 символов и не длиннее 60 символов. Общий объём текста для одного знака — около 320 символов и строго не более 340 символов. Формат вывода: эмодзи знака, затем название знака с заглавной буквы, точка, затем текст гороскопа. Каждый знак — с новой строки, между знаками — одна пустая строка. Стиль: страшно, жутко, обречённо, туманно и мрачно, но с юмором. Соблюдай грамотность и орфографию. Выведи только сам гороскоп, без пояснений, без служебных фраз и строго без английского текста — ни одного английского слова, ни одной латинской буквы. Не добавляй примеров и образцов — просто следуй цифрам."""

PENDING_FILE = "/home/skysmoker/horoscope-bot/pending_horoscope.txt"

def generate():
    """Запрос к DeepSeek, сохранение в архив и в pending-файл, без отправки."""
    logging.info("Режим generate: запрос к DeepSeek...")
    try:
        response = client.chat.completions.create(
            model="deepseek-flash",
            messages=[{"role": "user", "content": PROMPT}],
            max_tokens=4000,
            stream=False,
            extra_body={"thinking": {"type": "disabled"}}
        )
        text = response.choices[0].message.content
        if not text or not text.strip():
            logging.error("DeepSeek вернул пустой ответ")
            return False

        save_dir = "/home/skysmoker/horoscope-bot/horoscopes"
        os.makedirs(save_dir, exist_ok=True)
        filename = datetime.now().strftime("%d-%m-%Y-%H-%M") + ".txt"
        filepath = os.path.join(save_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(text)
        logging.info(f"Сохранено в архив: {filepath}")

        with open(PENDING_FILE, "w", encoding="utf-8") as f:
            f.write(text)
        logging.info(f"Сохранено в обработку: {PENDING_FILE}")
        return True
    except Exception as e:
        logging.error(f"Ошибка DeepSeek: {e}")
        return False


def send():
    """Отправка pending-файла в Telegram. Если файла нет — генерирует его."""
    if not os.path.exists(PENDING_FILE):
        logging.warning("Pending-файл не найден. Пробую сгенерировать заново...")
        if not generate():
            logging.error("Не удалось сгенерировать гороскоп. Отправка отменена.")
            return False

    with open(PENDING_FILE, "r", encoding="utf-8") as f:
        text = f.read()

    if not text.strip():
        logging.error("Режим отправки: временный файл пустой")
        return False

    max_len = 4050
    if len(text) > max_len:
        parts = [text[i:i+max_len] for i in range(0, len(text), max_len)]
    else:
        parts = [text]

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    all_ok = True
    for part in parts:
        try:
            resp = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": part})
            if resp.status_code == 200:
                logging.info("Отправлено успешно.")
            else:
                logging.error(f"Telegram-ошибка: {resp.text}")
                all_ok = False
        except Exception as e:
            logging.error(f"Ошибка сети: {e}")
            all_ok = False

    if all_ok:
        sent_name = "/home/skysmoker/horoscope-bot/sent_" + datetime.now().strftime("%d-%m-%Y-%H-%M") + ".txt"
        os.rename(PENDING_FILE, sent_name)
        logging.info(f"Временный файл переименован в {sent_name}")
    return all_ok


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "generate":
        generate()
    elif len(sys.argv) > 1 and sys.argv[1] == "send":
        send()
    else:
        if generate():
            send()


if __name__ == "__main__":
    main()
