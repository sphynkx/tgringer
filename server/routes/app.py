from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from server.i18n.messages import tr
from server.config import APP_BASE_URL
from jinja2 import Environment, FileSystemLoader, select_autoescape
import os
import json
import base64

router = APIRouter()

TEMPLATES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'templates'))
templates = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(['html', 'xml'])
)


@router.get("/app", response_class=HTMLResponse)
async def serve_app_get(request: Request, room: str = "", u: str = "", lang: str = "en"):
    user_info = {}
    if u:
        try:
            user_info = json.loads(base64.urlsafe_b64decode(u.encode()).decode())
        except Exception:
            user_info = {}
    if not room:
        return HTMLResponse("Room ID required", status_code=400)

    # ВСЕГДА рендерим index.html — даже если user_info пустой!
    ui_strings = {
        k: tr(f"ui.{k}", user_info.get("lang", lang))
        for k in ("join", "hangup", "copy", "welcome")
    }
    app_base_url = APP_BASE_URL
    turn_urls = []
    has_turn = False

    tmpl = templates.get_template("index.html")
    html = tmpl.render(
        room=room,
        user_info=user_info,
        ui_strings=ui_strings,
        app_base_url=app_base_url,
        turn_urls=turn_urls,
        has_turn=has_turn
    )
    return HTMLResponse(html)

@router.post("/app", response_class=HTMLResponse)
async def serve_app_post(
    request: Request,
    room: str = Form(...),
    user_id: int = Form(...),
    username: str = Form(""),
    first_name: str = Form(""),
    last_name: str = Form(""),
    avatar_url: str = Form(""),
    lang: str = Form("en")
):
    ui_strings = {
        k: tr(f"ui.{k}", lang)
        for k in ("join", "hangup", "copy", "welcome")
    }
    user_info = dict(
        user_id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        avatar_url=avatar_url,
        lang=lang
    )
    app_base_url = APP_BASE_URL
    turn_urls = []
    has_turn = False

    tmpl = templates.get_template("index.html")
    html = tmpl.render(
        room=room,
        user_info=user_info,
        ui_strings=ui_strings,
        app_base_url=app_base_url,
        turn_urls=turn_urls,
        has_turn=has_turn
    )
    return HTMLResponse(html)