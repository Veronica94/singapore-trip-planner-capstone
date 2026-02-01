import os

from fastapi import FastAPI

from app.controller import router

from dotenv import load_dotenv
load_dotenv()


app = FastAPI()
app.include_router(router)

@app.get("/debug/env")
def debug_env():
    key = os.getenv("OPENAI_API_KEY")
    return {
        "OPENAI_MODEL": os.getenv("OPENAI_MODEL"),
        "OPENAI_API_KEY_set": bool(key),
        "OPENAI_API_KEY_prefix": (key[:7] + "...") if key else None,
    }