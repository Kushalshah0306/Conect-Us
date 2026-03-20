from app import app, init_db

# Ensure DB tables exist on cold start in serverless environments.
init_db()

app = app
