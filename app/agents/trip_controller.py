import os
from datetime import datetime

from app.agents import image_gen, rag, recommender, sql_agent, weather as weather_agent
from app.schemas import FoodRecommendation, ItineraryItem, ToolOutputs, TripArtifacts, TripState


class TripPlannerController:
    def __init__(self) -> None:
        self.weather_api_key = os.getenv("WEATHER_API", "")

    def build_plan(
        self,
        trip_state: TripState,
        *,
        prompt_override: str | None = None,
        style: str | None = None,
        mood: str | None = None,
        color_palette: str | None = None,
        extra_notes: str | None = None,
    ) -> tuple[TripArtifacts, ToolOutputs]:
        if trip_state.start_date and trip_state.end_date:
            estimated = self._estimate_days(
                trip_state.start_date, trip_state.end_date
            )
            if estimated > 0 and trip_state.days != estimated:
                trip_state.days = estimated
        weather_summary, weather_message, weather_tool, weather_days = self._get_weather(trip_state)
        rag_result, rag_tool = self._get_rag(trip_state)
        hawkers, sql_tool = self._get_hawkers(trip_state)

        plan = self._get_recommendations(
            trip_state=trip_state,
            weather_message=weather_message,
            weather_days=weather_days,
            rag_notes=rag_result.notes,
            hawkers=hawkers,
        )
        if not isinstance(plan, dict):
            plan = {}
        recommender_tool = {"status": "ok"}
        if plan.get("error"):
            recommender_tool = {
                "status": "error",
                "error": str(plan.get("error")),
                "trace": str(plan.get("error_trace") or ""),
            }

        itinerary = [
            ItineraryItem(
                day_label=item.get("day_label", ""),
                summary=item.get("summary", ""),
                activities=item.get("activities") or [],
                notes=item.get("notes"),
                estimated_time_hours=_coerce_estimated_time(
                    item.get("estimated_time_hours")
                    or item.get("estimated_time")
                    or item.get("estimated_time_in_hours")
                    or item.get("estimated_time (in hours)")
                ),
            )
            for item in plan.get("itinerary", [])
        ]
        food_items = plan.get("food_recommendations", [])
        if not isinstance(food_items, list):
            food_items = []
        food_recs = []
        for rec in food_items:
            if isinstance(rec, str):
                food_recs.append(
                    FoodRecommendation(name=rec.strip(), area=None, reason=None)
                )
                continue
            if not isinstance(rec, dict):
                continue
            food_recs.append(
                FoodRecommendation(
                    name=rec.get("name", ""),
                    area=rec.get("area"),
                    reason=rec.get("reason"),
                )
            )

        postcard_prompt, postcard_url = image_gen.generate_postcard(
            trip_state=trip_state,
            itinerary=itinerary,
            rag_notes=rag_result.notes,
            prompt_override=prompt_override,
            style=style,
            mood=mood,
            color_palette=color_palette,
            extra_notes=extra_notes,
        )

        artifacts = TripArtifacts(
            itinerary=itinerary,
            weather_summary=weather_message,
            food_recommendations=food_recs,
            rag_notes=rag_result.notes,
            postcard_prompt=postcard_prompt,
            postcard_image_url=postcard_url,
            citations=rag_result.citations,
        )
        tool_outputs = ToolOutputs(
            weather=weather_tool,
            rag=rag_tool,
            sql=sql_tool,
            recommender=recommender_tool,
        )
        return artifacts, tool_outputs

    def _get_weather(
        self, trip_state: TripState
    ) -> tuple[dict | None, str, dict, list[dict]]:
        if not self.weather_api_key:
            return (
                None,
                "Weather lookup pending. Set WEATHER_API to enable real forecast.",
                {"status": "missing_api_key"},
                [],
            )

        date_input = trip_state.start_date or ""
        if not date_input and trip_state.days > 0:
            date_input = "today"

        try:
            summary, message = weather_agent.fetch_weather(
                api_key=self.weather_api_key,
                location=trip_state.location or "Singapore",
                date_input=date_input,
            )
            weather_days: list[dict] = []
            if trip_state.start_date and trip_state.end_date:
                weather_days = weather_agent.fetch_weather_range(
                    api_key=self.weather_api_key,
                    location=trip_state.location or "Singapore",
                    start_date=trip_state.start_date,
                    end_date=trip_state.end_date,
                )
            tool = {"status": "ok", "summary": summary, "days": len(weather_days)}
            return summary, message, tool, weather_days
        except Exception as exc:
            return None, f"Weather lookup failed: {exc}", {"status": "error", "error": str(exc)}, []

    def _get_rag(self, trip_state: TripState) -> tuple[rag.RagResult, dict]:
        prefs = ", ".join(trip_state.activity_preferences) or "general sightseeing"
        query = (
            "Singapore travel tips and places for "
            f"{prefs}. Budget={trip_state.budget or 'any'}, "
            f"pace={trip_state.pace or 'balanced'}."
        )
        try:
            result = rag.rag_query(query, top_k=3)
            return result, {"status": "ok", "sources": result.citations}
        except Exception as exc:
            return rag.RagResult(notes=[], citations=[]), {
                "status": "error",
                "error": str(exc),
            }

    def _get_hawkers(
        self, trip_state: TripState
    ) -> tuple[list[dict], dict]:
        area_hint = None
        if trip_state.location and trip_state.location.lower() != "singapore":
            area_hint = trip_state.location

        prefs = ", ".join(trip_state.food_preferences) or "local food"
        question = (
            "Find hawker centres suitable for tourists "
            f"with preferences: {prefs}. "
            "Prioritize centres with many cooked food stalls. "
        )
        if area_hint:
            question += f"Focus on areas matching: {area_hint}."

        try:
            hawkers = sql_agent.query_hawkers(question)
        except Exception:
            hawkers = sql_agent.search_hawkers(area_hint, limit=5)

        payload = [h.__dict__ for h in hawkers]
        return payload, {"status": "ok", "count": len(payload)}

    def _get_recommendations(
        self,
        *,
        trip_state: TripState,
        weather_message: str,
        weather_days: list[dict],
        rag_notes: list[str],
        hawkers: list[dict],
    ) -> dict:
        return recommender.build_itinerary(
            trip_state=trip_state.model_dump(),
            weather_summary=weather_message,
            weather_days=weather_days,
            rag_notes=rag_notes,
            hawkers=hawkers,
        )

    def _stub_postcard_prompt(
        self, trip_state: TripState, itinerary: list[ItineraryItem]
    ) -> str:
        prefs = ", ".join(trip_state.activity_preferences) or "culture and food"
        return (
            "Postcard of Singapore with vibrant street life, "
            f"featuring {prefs}. Warm tropical colors, friendly vibe."
        )

    @staticmethod
    def _estimate_days(start_date: str, end_date: str) -> int:
        try:
            start = datetime.fromisoformat(start_date)
            end = datetime.fromisoformat(end_date)
            delta = (end - start).days + 1
            return max(1, delta)
        except ValueError:
            return 0


def _coerce_estimated_time(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value.strip()
    return str(value)
