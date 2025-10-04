import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
APP_BASE_URL = os.environ.get("APP_BASE_URL")
MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", 3306))
MYSQL_DB = os.environ.get("MYSQL_DB", "tgringer01")
MYSQL_USER = os.environ.get("MYSQL_USER", "tgringer01_user")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
