.PHONY: dev-api dev-web test typecheck compose-up compose-down

dev-api:
	cd backend && uvicorn app.main:app --reload

dev-web:
	cd web && npm run dev

test:
	cd backend && pytest

typecheck:
	cd web && npm run typecheck

compose-up:
	docker compose up --build -d

compose-down:
	docker compose down

