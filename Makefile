.PHONY: db-up db-down db-migrate test demo web clean

db-up:
	docker compose -f docker/docker-compose.yml up -d

db-down:
	docker compose -f docker/docker-compose.yml down

db-migrate:
	alembic upgrade head

test:
	pytest -v

demo:
	python examples/run_claim.py

web:
	python -m uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
