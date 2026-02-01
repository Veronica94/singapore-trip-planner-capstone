import json
import os
import re
from datetime import date, datetime
from typing import List

from openai import OpenAI
from pydantic import ValidationError

from app.agents import weather
from app.schemas import IntakeResult, Message, TripState


REQUIRED_FIELDS = [
    "trip_dates_or_days",
    "activity_preferences",
    "pace",
    "budget",
    "group_size",
    "food_preferences",
]


def intake_step(trip_state: TripState, messages: List[Message]) -> IntakeResult:
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    client = OpenAI(api_key=api_key)

    prompt = _build_intake_prompt(trip_state, messages)
    raw_json = _call_llm(
        client=client,
        model=model,
        prompt=prompt,
        response_format="json_object",
    )

    try:
        return _enforce_intake_constraints(
            _parse_intake(raw_json), messages
        )
    except (json.JSONDecodeError, ValidationError):
        fix_prompt = _build_intake_fix_prompt(raw_json)
        fixed_json = _call_llm(
            client=client,
            model=model,
            prompt=fix_prompt,
            response_format="json_object",
        )
        return _enforce_intake_constraints(
            _parse_intake(fixed_json), messages
        )


def _has_trip_timing(trip_state: TripState) -> bool:
    has_dates = bool(trip_state.start_date and trip_state.end_date)
    has_days = trip_state.days > 0
    return has_dates or has_days


def _build_intake_prompt(trip_state: TripState, messages: List[Message]) -> str:
    recent_messages = [
        {"role": msg.role, "content": msg.content} for msg in messages[-12:]
    ]
    payload = {
        "task": (
            "You are running an intake conversation for a Singapore trip planner. "
            "Extract or update trip_state from the conversation so far. "
            "If any required fields are missing, ask exactly ONE clarifying "
            "question to obtain the most critical missing field."
        ),
        "required_fields": REQUIRED_FIELDS,
        "trip_state": trip_state.model_dump(),
        "recent_messages": recent_messages,
        "output_schema": {
            "trip_state": {
                "location": "string",
                "start_date": "string",
                "end_date": "string",
                "days": "integer",
                "activity_preferences": ["string"],
                "pace": "string",
                "budget": "string",
                "group_size": "integer",
                "food_preferences": ["string"],
                "summary": "string",
            },
            "missing_fields": ["string"],
            "next_question": "string or null",
            "needs_confirmation": "boolean",
            "confirmation_prompt": "string or null",
            "user_requested_generation": "boolean",
        },
        "rules": [
            "Return JSON only, no markdown.",
            "Ask exactly one question if missing_fields is not empty.",
            "If missing_fields is empty, set needs_confirmation=true and provide a confirmation_prompt summarizing the fields.",
            "If the user asks to generate without all fields, set user_requested_generation=true and keep missing_fields accurate.",
            "If location is missing, default to Singapore.",
            "If the user gives a date range, fill start_date and end_date.",
            "If the user gives duration (e.g., 3 days), set days.",
            "trip_dates_or_days is satisfied if either start_date/end_date are present or days is present.",
        ],
    }
    return json.dumps(payload, ensure_ascii=True)


def _build_intake_fix_prompt(raw_json: str) -> str:
    payload = {
        "task": "Fix the JSON to match the intake schema exactly.",
        "schema": {
            "trip_state": {
                "location": "string",
                "start_date": "string",
                "end_date": "string",
                "days": "integer",
                "activity_preferences": ["string"],
                "pace": "string",
                "budget": "string",
                "group_size": "integer",
                "food_preferences": ["string"],
                "summary": "string",
            },
            "missing_fields": ["string"],
            "next_question": "string or null",
            "needs_confirmation": "boolean",
            "confirmation_prompt": "string or null",
            "user_requested_generation": "boolean",
        },
        "rules": [
            "Return JSON only.",
            "Ask exactly one question if missing_fields is not empty.",
            "If missing_fields is empty, needs_confirmation must be true and confirmation_prompt must be provided.",
        ],
        "input_json": raw_json,
    }
    return json.dumps(payload, ensure_ascii=True)


def _parse_intake(raw_json: str) -> IntakeResult:
    data = json.loads(raw_json)
    return IntakeResult.model_validate(data)


def _enforce_intake_constraints(
    intake: IntakeResult, messages: List[Message]
) -> IntakeResult:
    _normalize_dates(intake.trip_state, messages)
    missing_fields = list(intake.missing_fields or [])
    if not _has_trip_timing(intake.trip_state):
        if "trip_dates_or_days" not in missing_fields:
            missing_fields.append("trip_dates_or_days")

    if missing_fields:
        intake.missing_fields = missing_fields
        if not intake.next_question:
            intake.next_question = _build_clarifying_question(
                {"trip_dates_or_days": True}
            )
        intake.needs_confirmation = False
        intake.confirmation_prompt = None
    else:
        intake.needs_confirmation = True
        if not intake.confirmation_prompt:
            intake.confirmation_prompt = (
                "Please confirm these trip details before I generate the itinerary."
            )
    return intake


def _build_clarifying_question(missing: dict[str, bool]) -> str:
    if missing.get("trip_dates_or_days"):
        return "What dates are you visiting Singapore, or how many days is your trip?"
    if missing.get("activity_preferences"):
        return "What kinds of activities do you enjoy (culture, nature, food, shopping, nightlife)?"
    if missing.get("pace"):
        return "What pace do you prefer (relaxed, balanced, packed)?"
    if missing.get("budget"):
        return "What budget range should I plan for (budget, mid-range, splurge)?"
    if missing.get("group_size"):
        return "How many people are traveling?"
    if missing.get("food_preferences"):
        return "Any food preferences or must-try cuisines?"
    return "Any other preferences for the trip?"


def _normalize_dates(trip_state: TripState, messages: List[Message]) -> None:
    user_has_year = _user_mentioned_year(messages)
    today = datetime.now(weather.SG_TZ).date()
    derived = _derive_dates_from_messages(messages)
    if derived and not user_has_year:
        trip_state.start_date, trip_state.end_date = derived
    if trip_state.start_date:
        parsed = weather.parse_date_input(trip_state.start_date)
        if parsed:
            trip_state.start_date = _normalize_year(parsed, today, user_has_year)
    if trip_state.end_date:
        parsed = weather.parse_date_input(trip_state.end_date)
        if parsed:
            trip_state.end_date = _normalize_year(parsed, today, user_has_year)
    if not user_has_year and trip_state.start_date and trip_state.end_date:
        try:
            start = datetime.fromisoformat(trip_state.start_date).date()
            end = datetime.fromisoformat(trip_state.end_date).date()
        except ValueError:
            return
        if end < start:
            try:
                trip_state.end_date = end.replace(year=end.year + 1).isoformat()
            except ValueError:
                return


def _normalize_year(parsed: date, today: date, user_has_year: bool) -> str:
    if user_has_year:
        return parsed.isoformat()
    try:
        candidate = parsed.replace(year=today.year)
    except ValueError:
        return parsed.isoformat()
    if candidate < today:
        try:
            candidate = candidate.replace(year=today.year + 1)
        except ValueError:
            return parsed.isoformat()
    return candidate.isoformat()


def _user_mentioned_year(messages: List[Message]) -> bool:
    recent = [m for m in messages[-8:] if m.role == "user"]
    for msg in recent:
        if re.search(r"\b20\d{2}\b", msg.content):
            return True
    return False


def _derive_dates_from_messages(
    messages: List[Message],
) -> tuple[str, str] | None:
    recent = [m for m in messages[-6:] if m.role == "user"]
    if not recent:
        return None
    text = recent[-1].content.lower()
    parts = re.split(r"\bto\b|\buntil\b|-", text)
    if len(parts) < 2:
        return None
    start_raw = parts[0].strip()
    end_raw = parts[1].strip()
    start = weather.parse_date_input(start_raw)
    end = weather.parse_date_input(end_raw)
    if not start or not end:
        return None
    return start.isoformat(), end.isoformat()


def _call_llm(
    *,
    client: OpenAI,
    model: str,
    prompt: str,
    response_format: str,
) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a trip planner assistant. "
                    "Return valid JSON only, no markdown."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        response_format={"type": response_format},
    )
    return response.choices[0].message.content or "{}"
