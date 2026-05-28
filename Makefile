# Classroom Companion — developer shortcuts
#
# Usage:
#   make install    Install all dependencies
#   make run        Start the application (uvicorn + bot + scheduler)
#   make dev        Same as run but forces DEBUG=true
#   make test       Run the full test suite
#   make test-unit  Run unit tests only
#   make test-int   Run integration tests only
#   make cov        Run tests with HTML coverage report
#   make seed       Seed the database with demo data
#   make clean      Remove caches, logs, and the local SQLite DB

PYTHON      ?= python
PYTEST      ?= $(PYTHON) -m pytest
PIP         ?= $(PYTHON) -m pip
UVICORN     ?= $(PYTHON) -m uvicorn

# ── Installation ──────────────────────────────────────────────────────────────
.PHONY: install
install:
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

# ── Run ───────────────────────────────────────────────────────────────────────
.PHONY: run
run:
	$(PYTHON) main.py

.PHONY: dev
dev:
	DEBUG=true $(PYTHON) main.py

# ── Tests ─────────────────────────────────────────────────────────────────────
.PHONY: test
test:
	$(PYTEST) tests/

.PHONY: test-unit
test-unit:
	$(PYTEST) tests/unit/

.PHONY: test-int
test-int:
	$(PYTEST) tests/integration/

.PHONY: cov
cov:
	$(PYTEST) tests/ \
		--cov=. \
		--cov-omit="tests/*,static/*,logs/*,.venv/*" \
		--cov-report=term-missing \
		--cov-report=html:htmlcov
	@echo "Coverage report: htmlcov/index.html"

# ── Database ──────────────────────────────────────────────────────────────────
.PHONY: seed
seed:
	$(PYTHON) -c "\
import asyncio; \
from database.database import init_db, get_async_session; \
from database.seed import seed_demo_data; \
async def _run(): \
    await init_db(); \
    async with get_async_session() as db: \
        await seed_demo_data(db); \
        print('Demo data seeded.'); \
asyncio.run(_run())"

# ── Clean ─────────────────────────────────────────────────────────────────────
.PHONY: clean
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name htmlcov -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -f classroom_companion.db test_classroom_companion.db
	rm -f logs/*.log logs/*.gz
	@echo "Clean complete."
