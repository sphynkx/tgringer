from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
import os

router = APIRouter()

TEMPLATES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'templates'))
templates = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(['html', 'xml'])
)


@router.get("/app/login", response_class=HTMLResponse)
async def login_form(request: Request, room: str = "", lang: str = "en"):
    tmpl = templates.get_template("login_form.html")
    return HTMLResponse(tmpl.render(room=room, lang=lang))

