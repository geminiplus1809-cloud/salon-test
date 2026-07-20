import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("8317659250:AAHxFpIRTs4ZXe45yjHbQD9gKgaf0W4wDR0", "")
ADMIN_CHAT_ID = int(os.getenv("1625036105", "0"))
DB_PATH = os.getenv("DB_PATH", "salon.sqlite3")
