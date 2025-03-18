import logging

from fastapi import Request
from starlette.templating import Jinja2Templates

from app.setup import create_app

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
app = create_app()

templates = Jinja2Templates(directory="templates")


@app.get("/status")
async def main():
    return {"status": "OK"}


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("main.html", {"request": request})
