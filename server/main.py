import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from server.routes.app import router as app_router
from server.routes.invite import router as invite_router
from server.routes.login import router as login_router
from server.routes.ws import router as ws_router
from server.routes.health import router as health_router
from server.routes.avatar import router as avatar_router  # NEW

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  ## Must close on prod!!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(app_router)
app.include_router(invite_router)
app.include_router(login_router)
app.include_router(ws_router)
app.include_router(health_router)
app.include_router(avatar_router)

app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
