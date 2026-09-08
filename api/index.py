from app.main import app
# Vercel expects `app` or `handler` in api/index.py for Python runtime
# This wrapper re-exports the FastAPI app for serverless
