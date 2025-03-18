.PHONY: install run

install:
	cd backend && uv sync && uv pip install -e ../vsdk 

run:
	cd backend && uv run uvicorn app.main:app --port 8000

