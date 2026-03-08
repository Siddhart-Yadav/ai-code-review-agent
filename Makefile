.PHONY: demo run stop logs test evals setup clean

# ── Quick Start ──────────────────────────────────────────────────────────

## Start in demo mode (no API key needed — uses pre-computed reviews)
demo:
	@echo "🚀 Starting in demo mode (no API key required)..."
	@cp -n backend/.env.example backend/.env 2>/dev/null || true
	DEMO_MODE=true docker compose up --build -d
	@echo ""
	@echo "✅ Ready! Open http://localhost:3000 and click 'Try Demo'"

## Start with live LLM reviews (requires an API key in backend/.env)
run:
	@echo "🚀 Starting with live LLM reviews..."
	@test -f backend/.env || (echo "❌ backend/.env not found. Run: cp backend/.env.example backend/.env && edit it" && exit 1)
	DEMO_MODE=false docker compose up --build -d
	@echo ""
	@echo "✅ Ready! Open http://localhost:3000"

# ── Operations ───────────────────────────────────────────────────────────

## Stop all services
stop:
	docker compose down

## View logs
logs:
	docker compose logs -f backend

## Run backend tests
test:
	cd backend && python -m pytest tests/ -v

## Run evaluation metrics
evals:
	cd backend && python -m evals.run_metrics

# ── Setup ────────────────────────────────────────────────────────────────

## First-time setup: copy .env and show instructions
setup:
	@cp -n backend/.env.example backend/.env 2>/dev/null || true
	@echo "📝 Created backend/.env from .env.example"
	@echo ""
	@echo "Choose your LLM provider (edit backend/.env):"
	@echo ""
	@echo "  Option A — Groq (FREE, recommended for deployment):"
	@echo "    GROQ_API_KEY=gsk_...       # Get at https://console.groq.com/keys"
	@echo ""
	@echo "  Option B — Gemini (free tier):"
	@echo "    GEMINI_API_KEY=your_key    # Get at https://aistudio.google.com/apikey"
	@echo ""
	@echo "  Option C — OpenAI:"
	@echo "    OPENAI_API_KEY=sk-...      # Get at https://platform.openai.com/api-keys"
	@echo ""
	@echo "  Option D — Anthropic:"
	@echo "    ANTHROPIC_API_KEY=sk-ant-...  # Get at https://console.anthropic.com"
	@echo ""
	@echo "  Option E — Demo only (no key needed):"
	@echo "    Just run: make demo"
	@echo ""

## Remove all containers and volumes
clean:
	docker compose down -v
	@echo "🧹 Cleaned up containers and volumes"
