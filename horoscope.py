import os
import sys
import time
import random
import logging
from pathlib import Path
from datetime import datetime, timedelta
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

ZODIAC_SIGNS = [
    "♈ Овен", "♉ Телец", "♊ Близнецы", "♋ Рак",
    "♌ Лев", "♍ Дева", "♎ Весы", "♏ Скорпион",
    "♐ Стрелец", "♑ Козерог", "♒ Водолей", "♓ Рыбы"
]

COMMON_TOPICS = [
    "утренняя кофеварка или чайник, издающие зловещие звуки",
    "загадочные посылки в пункте выдачи заказов (Ozon / Wildberries)",
    "кот или собака, требующие еду на рассвете как языческое божество",
    "попытка навести порядок в ящике с проводами, носками или пакетами",
    "внезапно севший телефон в самый неподходящий момент",
    "загадочный контейнер с едой в глубине холодильника",
    "сосед с перфоратором или странными звуками из-за стены",
    "поход в супермаркет на голодный желудок и битвы у кассы",
    "капризный Wi-Fi роутер, требующий ритуальной перезагрузки",
    "непредсказуемая погода и мучительный выбор одежды по сезону",
    "спонтанные ночные перекусы и переговоры с собственной совестью",
    "поиск ключей, пульта или второй перчатки перед выходом",
    "сообщения в соседском или семейном чате",
    "непрочитанные вкладки в браузере и попытка всё успеть"
]

WEEKDAY_TOPICS = [
    "утренний будильник и попытка выторговать ещё пять минут сна",
    "рабочий созвон, где все кивают, но никто не понимает задачу",
    "дорога, светофоры и загадочные маршруты навигатора",
    "офисная или домашняя кухня в обеденный перерыв",
    "переписка с коллегами и дедлайны, подкравшиеся из тумана",
    "вечернее возвращение домой с мечтой о горизонтальном положении"
]

WEEKEND_TOPICS = [
    "попытка выспаться в выходной, которую срывают бытовые дела",
    "генеральная уборка, грозящая открыть портал в другое измерение",
    "готовка сложного блюда по рецепту из интернета",
    "поездка на дачу, рынок или в строительный магазин",
    "выбор фильма или сериала на вечер, затянувшийся на два часа",
    "планы отдохнуть весь день, внезапно превратившиеся в мелкий ремонт"
]

SYSTEM_PROMPT = (
    "Ты — Говард Филлипс Лавкрафт, который с абсолютно серьёзным лицом пишет шутливый "
    "бытовой гороскоп на русском языке. Главный комедийный приём: высокий, напыщенный слог "
    "«космического ужаса, неевклидовой геометрии, бездны и циклопических тайн» сталкивается "
    "с самыми приземлёнными житейскими мелочами (кофеваркой, доставкой, котом, уборкой, чатами).\n\n"
    "Строгие правила стиля и языка:\n"
    "1. Никакой чернухи, кладбищ, смерти и безысходности — финал каждого знака должен быть ироничным, "
    "узнаваемым и вызывать улыбку.\n"
    "2. Не злоупотребляй словом «древний» (используй его максимум 1–2 раза на весь текст, заменяй "
    "на «неведомый», «исполинский», «непостижимый», «запредельный», «циклопический»).\n"
    "3. Строго используй заданную для каждого знака бытовую тему — сюжеты 12 знаков не должны повторяться.\n"
    "4. Безупречный русский язык. Строго запрещены любые латинские буквы и иностранные слова.\n\n"
    "Строгий формат вывода:\n"
    "- Выведи только 12 знаков зодиака без вступлений, заголовков и комментариев.\n"
    "- Первая строка каждого знака: эмодзи знака, пробел, название знака с заглавной буквы, точка.\n"
    "- Вторая строка (сразу с новой строки, без пустой строки после заголовка): один сплошной абзац "
    "из ровно трёх образных предложений без переносов строк внутри абзаца.\n"
    "- Между знаками ставь ровно одну пустую строку.\n"
    "- Объём каждого знака: около 46–54 слов за счёт богатых художественных деталей (весь текст из 12 знаков должен уложиться в 3700–3980 символов)."
)


def get_target_datetime() -> datetime:
    """Если генерация запущена вечером (после 16:00), готовим гороскоп на завтра."""
    now = datetime.now()
    if now.hour >= 16:
        return now + timedelta(days=1)
    return now


def build_user_prompt(target_dt: datetime) -> str:
    """Назначает каждому из 12 знаков свою уникальную житейскую тему."""
    day_name = DAYS_RU[target_dt.weekday()]
    is_weekend = target_dt.weekday() >= 5
    day_type = "выходной день" if is_weekend else "будний день"

    pool = COMMON_TOPICS + (WEEKEND_TOPICS if is_weekend else WEEKDAY_TOPICS)
    selected_topics = random.sample(pool, len(ZODIAC_SIGNS))

    assignments = "\n".join(
        f"- {sign}: {topic}" for sign, topic in zip(ZODIAC_SIGNS, selected_topics)
    )

    return (
        f"Напиши гороскоп на {day_name} ({day_type}). "
        f"Для каждого знака раскрой строго его персональную бытовую тему:\n{assignments}"
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


def generate(dry_run: bool = False) -> bool:
    """Запрос к DeepSeek с контролем длины текста, сохранение в архив и pending."""
    if not dry_run and PENDING_FILE.exists() and PENDING_FILE.read_text(encoding="utf-8").strip():
        logging.info("Pending-файл уже готов к отправке, ночная генерация пропущена.")
        return True

    target_dt = get_target_datetime()
    day_name = DAYS_RU[target_dt.weekday()]
    logging.info(f"Режим generate (на {day_name}, dry_run={dry_run}): запрос к DeepSeek...")

    user_prompt = build_user_prompt(target_dt)
    last_valid_text = ""

    for attempt in range(1, 4):
        try:
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=1.0,
                max_tokens=4000,
                stream=False
            )
            text = (response.choices[0].message.content or "").strip()
            if not text:
                logging.error("DeepSeek вернул пустой ответ")
                continue

            last_valid_text = text
            length = len(text)
            logging.info(f"Попытка {attempt}/3: сгенерировано {length} символов.")

            if 3600 <= length <= 4040 or attempt == 3:
                if dry_run:
                    print(f"=== ТЕСТОВЫЙ ВЫПУСК (на {day_name}, длина: {length} симв.) ===\n")
                    print(text)
                    return True

                ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
                filename = target_dt.strftime("%d-%m-%Y") + "_" + datetime.now().strftime("%H-%M") + ".txt"
                filepath = ARCHIVE_DIR / filename
                filepath.write_text(text + "\n", encoding="utf-8")
                logging.info(f"Сохранено в архив: {filepath}")

                PENDING_FILE.write_text(text + "\n", encoding="utf-8")
                logging.info(f"Сохранено в обработку: {PENDING_FILE}")
                return True

            logging.warning(f"Длина {length} вне диапазона 3600–4040 символов, пробую перегенерировать...")

        except Exception as e:
            logging.error(f"Ошибка DeepSeek (попытка {attempt}/3): {e}")
            if attempt < 3:
                time.sleep(10)

    if last_valid_text:
        if dry_run:
            print(last_valid_text)
            return True
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        filepath = ARCHIVE_DIR / (target_dt.strftime("%d-%m-%Y") + "_" + datetime.now().strftime("%H-%M") + ".txt")
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
    if mode == "--test" or mode == "test":
        generate(dry_run=True)
    elif mode == "generate":
        generate()
    elif mode == "send":
        send()
    else:
        if generate():
            send()


if __name__ == "__main__":
    main()
