# FastAPI Chat Stub

Minimal FastAPI project with health and chat endpoints.

## Requirements
- Python 3.11+

## Setup
```bash
python -m venv .venv
```
```bash
.venv\Scripts\activate
```
```bash
pip install fastapi uvicorn openai streamlit requests
```

## Run
```bash
uvicorn app.main:app --reload
```

## Step 3: Narrative agent
Set env vars (PowerShell example):
```bash
$env:OPENAI_API_KEY="your-key"
$env:OPENAI_MODEL="gpt-4o-mini"
```

## Test clarifying flow
## LLM intake flow
- The server uses an LLM to extract the required fields and ask one clarifying question per turn.
- When all fields are present, it asks for confirmation before generation.
- If generation is requested with missing fields, it returns an error listing missing inputs.
- When generating, the session log records a short "Generating campaign..." message.

## Streamlit UI
```bash
streamlit run streamlit_app.py
```
Set the API base URL if needed:
```bash
$env:API_BASE_URL="http://localhost:8000"
```

## Endpoints
- `GET /health` -> `{"status":"ok"}`
- `POST /chat` -> stub response

## Testing memory behavior
- Same session remembers: call `POST /chat` twice with the same `session_id` and check `GET /debug/session/{session_id}` for accumulated messages and updated campaign state.
- Different sessions don't leak: use two different `session_id` values and verify each debug response only contains its own messages/state.
- Messages capped at 6: send more than 3 chat requests (user + assistant = 2 entries each) and confirm the debug response shows only the last 6 messages.
