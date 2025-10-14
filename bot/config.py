import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
APP_BASE_URL = os.environ.get("APP_BASE_URL")
BOT_RECORD_NOTIFY_URL = os.environ.get("BOT_RECORD_NOTIFY_URL")

MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", 3306))
MYSQL_DB = os.environ.get("MYSQL_DB", "tgringer")
MYSQL_USER = os.environ.get("MYSQL_USER", "tgringer_user")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
