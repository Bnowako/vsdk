import logging


from app.setup import create_app

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
app = create_app()


@app.get("/status")
async def main():
    return {"status": "OK"}
