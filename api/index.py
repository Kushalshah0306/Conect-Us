from app import app, init_db

# Ensure DB tables exist on cold start in serverless environments.
try:
    init_db()
except Exception as e:
    print(f"Database initialization failed: {e}")

# This is the entry point for Vercel
app = app
