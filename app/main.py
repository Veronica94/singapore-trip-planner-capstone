import os

from fastapi import FastAPI

from app.controller import router

from dotenv import load_dotenv
load_dotenv()


app = FastAPI(title="Singapore Trip Planner API")
app.include_router(router)

@app.get("/")
def root():
    """Health check endpoint"""
    return {
        "status": "running",
        "message": "Singapore Trip Planner API",
        "endpoints": {
            "POST /chat": "Chat with the trip planner",
            "POST /postcard": "Generate a postcard",
            "GET /debug/session/{session_id}": "Get session debug info",
            "GET /debug/env": "Check environment variables"
        }
    }

@app.get("/health")
def health():
    """Health check for monitoring"""
    return {"status": "healthy"}

@app.get("/debug/env")
def debug_env():
    key = os.getenv("OPENAI_API_KEY")
    return {
        "OPENAI_MODEL": os.getenv("OPENAI_MODEL"),
        "OPENAI_API_KEY_set": bool(key),
        "OPENAI_API_KEY_prefix": (key[:7] + "...") if key else None,
    }