import os
from dotenv import load_dotenv

load_dotenv()

APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:91")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
TURN_URLS = [u.strip() for u in os.getenv("TURN_URLS", "stun:stun.l.google.com:19302").split(",") if u.strip()]
TURN_USERNAME = os.getenv("TURN_USERNAME") or ""
TURN_PASSWORD = os.getenv("TURN_PASSWORD") or ""

## Recording pipeline:
## A = collect .webm then single-pass mp4 (current default)
## B = per-chunk mp4 transcode + fast concat on finish
RECORD_PIPELINE_MODE = os.getenv("RECORD_PIPELINE_MODE", "A").upper().strip()

## Target encoding params for MP4 (both A and B when mp4 used)
RECORD_MP4_PRESET = os.getenv("RECORD_MP4_PRESET", "ultrafast")
RECORD_MP4_CRF = int(os.getenv("RECORD_MP4_CRF", "28"))
RECORD_MP4_A_BPS = os.getenv("RECORD_MP4_A_BPS", "128k")
RECORD_MP4_AR = int(os.getenv("RECORD_MP4_AR", "48000"))

## Canvas/video target (must match for B to keep segments identical)
RECORD_TARGET_WIDTH = int(os.getenv("RECORD_TARGET_WIDTH", "1280"))
RECORD_TARGET_HEIGHT = int(os.getenv("RECORD_TARGET_HEIGHT", "720"))
RECORD_TARGET_FPS = int(os.getenv("RECORD_TARGET_FPS", "30"))
RECORD_TARGET_GOP = int(os.getenv("RECORD_TARGET_GOP", "60"))

## Per-segment duration in seconds for pipeline B
RECORD_SEGMENT_TIME = int(os.getenv("RECORD_SEGMENT_TIME", "4"))
