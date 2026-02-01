import json
import os
import traceback
from typing import Any

from openai import OpenAI


def build_itinerary(
    *,
    trip_state: dict[str, Any],
    weather_summary: str,
    weather_days: list[dict],
    rag_notes: list[str],
    hawkers: list[dict[str, Any]],
) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    timeout_seconds = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "120"))
    client = OpenAI(api_key=api_key, timeout=timeout_seconds)

    safe_trip_state = trip_state if isinstance(trip_state, dict) else {}
    payload = {
        "trip_state": safe_trip_state,
        "trip_days": safe_trip_state.get("days"),
        "trip_dates": {
            "start_date": safe_trip_state.get("start_date"),
            "end_date": safe_trip_state.get("end_date"),
        },
        "weather": weather_summary,
        "weather_days": weather_days,
        "rag_notes": rag_notes,
        "hawkers": hawkers,
    }

    trip_days = int(safe_trip_state.get("days") or 0)
    try:
        if trip_days <= 7:
            return _build_direct_plan(client, model, payload, trip_days)
        outline = _build_week_outline(client, model, payload, trip_days)
        return _expand_week_outline(client, model, payload, outline, trip_days)
    except Exception as exc:
        trace = traceback.format_exc(limit=5)
        return {
            "summary": f"Recommendation error: {exc}",
            "itinerary": [],
            "food_recommendations": [],
            "error": str(exc),
            "error_trace": trace,
        }


def _build_direct_plan(
    client: OpenAI, model: str, payload: dict, trip_days: int
) -> dict[str, Any]:
    system = (
        "You are an expert Singapore itinerary planner.\n\n"
        "Your task is to generate a realistic, geographically coherent, multi-day itinerary for visitors to Singapore.\n"
        "You MUST strictly follow the planning rules and heuristics provided in rag_notes. "
        "These rules override general creativity.\n\n"
        "Use the following inputs:\n"
        "- trip_state: traveler preferences such as number of days, pace, budget, interests, group size\n"
        "- trip_days and trip_dates: total number of days and travel window\n"
        "- weather_days: daily weather signals that determine indoor vs outdoor emphasis\n"
        "- rag_notes: planning rules, neighborhood clusters, and feasibility constraints\n"
        "- hawkers: food options to place NEAR the day's activity cluster\n\n"
        "PLANNING CONSTRAINTS (MANDATORY):\n"
        "1. Each day MUST focus on ONE primary geographic cluster.\n"
        "   - A maximum of ONE nearby secondary cluster is allowed.\n"
        "   - NEVER combine distant clusters (e.g. Changi/Jewel with Marina Bay or Botanic Gardens in the same day).\n\n"
        "2. Each day MUST follow a realistic time-block structure:\n"
        "   - Morning: outdoor or physically demanding activities (if weather allows)\n"
        "   - Midday: indoor or shaded activities\n"
        "   - Afternoon: light walking, cafes, museums, shopping\n"
        "   - Evening: food-focused or scenic night activities\n"
        "   Limit to 3–5 activities per day.\n\n"
        "3. Weather enforcement:\n"
        "   - On high rain or thunderstorm days, prioritize indoor activities.\n"
        "   - On hot but dry days, schedule outdoor activities early or late.\n"
        "   - Avoid exposed parks, trails, or waterfronts on stormy days.\n\n"
        "4. Food placement rule:\n"
        "   - Lunch MUST be near the day’s main activity cluster.\n"
        "   - Do NOT recommend restaurants without clear area context unless explicitly marked as optional.\n\n"
        "5. Travel realism:\n"
        "   - Assume 30–45 minutes travel between distant clusters.\n"
        "   - Avoid more than one cross-cluster movement per day.\n\n"
        "SELF-CHECK (DO THIS BEFORE FINALIZING):\n"
        "- Verify each day stays within one geographic cluster.\n"
        "- Verify activities are ordered logically by location and time of day.\n"
        "- If any day violates these rules, REVISE the itinerary before returning it.\n\n"
        "OUTPUT FORMAT (STRICT):\n"
        "Return JSON ONLY with keys:\n"
        "- itinerary (list of day objects)\n"
        "- food_recommendations (list of at least 3-5 hawker centers or restaurants, each with name, area, and reason)\n"
        "- summary (string)\n\n"
        "Each day object MUST include:\n"
        "- day_label\n"
        "- summary\n"
        "- activities (3–5 bullet points)\n"
        "- notes\n"
        "- estimated_time_hours (numeric, hours)\n\n"
        f"Return EXACTLY {max(trip_days, 1)} day objects.\n"
        "Do NOT include departure activities until the final day.\n"
        "Keep tone friendly, calm, and practical."
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=True)},
        ],
        temperature=0.4,
        response_format={"type": "json_object"},
    )
    parsed = json.loads(response.choices[0].message.content or "{}")
    return parsed if isinstance(parsed, dict) else {}


def _build_week_outline(
    client: OpenAI, model: str, payload: dict, trip_days: int
) -> dict[str, Any]:
    weeks = max(1, (trip_days + 6) // 7)
    system = (
        "You are an expert Singapore itinerary planner creating a HIGH-LEVEL weekly outline.\n\n"
        "Your goal is to define coherent themes and geographic focus for each week, NOT individual activities yet.\n\n"
        "Use:\n"
        "- trip_state for traveler preferences and trip duration\n"
        "- rag_notes for neighborhood clusters, planning rules, and feasibility constraints\n"
        "- weather_days for broad indoor vs outdoor emphasis\n"
        "- hawkers only as supporting context, not detailed planning\n\n"
        "PLANNING RULES:\n"
        "1. Each week should have a CLEAR geographic focus or small set of adjacent clusters.\n"
        "2. Avoid mixing distant areas within the same week theme.\n"
        "3. Weather should influence emphasis (e.g. indoor-heavy week vs outdoor-heavy week).\n\n"
        "WEEK STRUCTURE:\n"
        "Each week should describe:\n"
        "- overall theme (e.g. “Cultural Core”, “Nature & Outdoors”, “Food & Neighborhoods”)\n"
        "- focus_areas (list of neighborhoods or clusters)\n"
        "- must_do highlights (high-level, not time-specific)\n\n"
        "DO NOT list detailed schedules or times.\n"
        "DO NOT include transportation details yet.\n"
        "DO NOT exceed the requested number of weeks.\n\n"
        "OUTPUT FORMAT (STRICT):\n"
        "Return JSON ONLY with key:\n"
        "- weeks (list)\n\n"
        "Each week object MUST include:\n"
        "- week_label\n"
        "- theme\n"
        "- focus_areas (list)\n"
        "- must_do (list)\n\n"
        f"Return EXACTLY {weeks} weeks.\n"
        "Keep descriptions concise and realistic."
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=True)},
        ],
        temperature=0.4,
        response_format={"type": "json_object"},
    )
    parsed = json.loads(response.choices[0].message.content or "{}")
    return parsed if isinstance(parsed, dict) else {}


def _expand_week_outline(
    client: OpenAI,
    model: str,
    payload: dict,
    outline: dict,
    trip_days: int,
) -> dict[str, Any]:
    system = (
        "You are an expert Singapore itinerary planner expanding a weekly outline into a full daily itinerary.\n\n"
        "Use:\n"
        "- trip_state for preferences and constraints\n"
        "- week_outline for geographic focus and themes\n"
        "- weather_days to decide indoor vs outdoor scheduling\n"
        "- rag_notes for planning rules, neighborhood clusters, and feasibility heuristics\n"
        "- hawkers for food options NEAR daily activity clusters\n\n"
        "MANDATORY CONSTRAINTS:\n"
        "1. Each DAY must follow the geographic clustering rules from rag_notes.\n"
        "2. Each DAY must stay within the week’s focus_areas.\n"
        "3. Avoid repeating the same major attractions across multiple days.\n"
        "4. Weather rules MUST be enforced (indoor vs outdoor).\n"
        "5. Do NOT schedule departure until the final day.\n\n"
        "DAY STRUCTURE REQUIREMENTS:\n"
        "- 3–5 activities per day\n"
        "- Ordered logically by time of day and location\n"
        "- Realistic pacing (no rushing, no zig-zagging)\n\n"
        "SELF-CHECK BEFORE OUTPUT:\n"
        "For EACH day:\n"
        "- Confirm all activities belong to the same or adjacent neighborhood clusters.\n"
        "- Confirm weather compatibility.\n"
        "- If violations exist, REVISE before returning output.\n\n"
        "OUTPUT FORMAT (STRICT):\n"
        "Return JSON ONLY with keys:\n"
        "- itinerary (list of day objects)\n"
        "- food_recommendations (list of at least 3-5 hawker centers or restaurants, each with name, area, and reason)\n"
        "- summary (string)\n\n"
        "Each day object MUST include:\n"
        "- day_label\n"
        "- summary\n"
        "- activities (3–5 bullet points)\n"
        "- notes\n"
        "- estimated_time_hours (numeric)\n\n"
        f"Return EXACTLY {trip_days} day objects.\n"
        "Tone should be helpful, calm, and realistic."
    )
    outline_obj = outline if isinstance(outline, dict) else {}
    expanded_payload = dict(payload)
    expanded_payload["week_outline"] = outline_obj.get("weeks", outline_obj)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(expanded_payload, ensure_ascii=True)},
        ],
        temperature=0.4,
        response_format={"type": "json_object"},
    )
    parsed = json.loads(response.choices[0].message.content or "{}")
    return parsed if isinstance(parsed, dict) else {}
