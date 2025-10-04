from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from server.config import APP_BASE_URL, TURN_URLS, TURN_USERNAME, TURN_PASSWORD
import os

router = APIRouter()

## Config templates
templates = Environment(
    loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), '..', 'templates')),
    autoescape=select_autoescape(['html', 'xml'])
)


@router.get("/health")
async def health():
    return {"ok": True}


@router.get("/app", response_class=HTMLResponse)
async def serve_app(request: Request):
    tmpl = templates.get_template("index.html")
    html = tmpl.render(
        app_base_url=APP_BASE_URL,
        turn_urls=TURN_URLS,
        turn_username=TURN_USERNAME,
        turn_password=TURN_PASSWORD,
        has_turn=bool(TURN_USERNAME and TURN_PASSWORD)
    )
    return HTMLResponse(html)

