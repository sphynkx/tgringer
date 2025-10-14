import os
from pathlib import Path

## Load .env BEFORE importing anything that reads environment variables
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
except Exception as _e:
    print(f"[MAIN] dotenv load skipped or failed: {_e}")

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

## Core routes
from server.routes.app import router as app_router
from server.routes.invite import router as invite_router
from server.routes.login import router as login_router
from server.routes.ws import router as ws_router
from server.routes.health import router as health_router
from server.routes.avatar import router as avatar_router

## Recording (chunk streaming, finalize)
from server.routes.record import router as record_router

## Bot notification route (mounted here for one-process setup)
from bot.routes.record_notify import router as bot_record_router

app = FastAPI(
    title="Tgringer Server",
    version="1.0.0",
)

## CORS (open for MVP; restrict on prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   ## TODO: restrict
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

## Register routers
app.include_router(app_router)
app.include_router(invite_router)
app.include_router(login_router)
app.include_router(ws_router)
app.include_router(health_router)
app.include_router(avatar_router)
app.include_router(record_router)
app.include_router(bot_record_router)

## Static files (avatars, records, js)
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


## Root simple check
@app.get("/")
async def root():
    return {"ok": True, "msg": "Tgringer server running"}


## Debug route: environment snapshot (do not expose on prod)
@app.get("/_env")
async def show_env():
    return {
        "BOT_RECORD_NOTIFY_URL": os.environ.get("BOT_RECORD_NOTIFY_URL"),
        "BOT_TOKEN?": bool(os.environ.get("BOT_TOKEN")),
    }

