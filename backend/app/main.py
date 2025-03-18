from app.config import create_app
from fastapi.templating import Jinja2Templates
from fastapi import Request

app = create_app()

templates = Jinja2Templates(directory="templates")


@app.get("/status")
async def main():
    return {"status": "OK"}

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("main.html", {"request": request})

