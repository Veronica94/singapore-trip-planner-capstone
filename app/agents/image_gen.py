import os
import random
from typing import Iterable

from openai import OpenAI

from app.schemas import ItineraryItem, TripState


PROMPT_VARIANTS = [
    "heritage_postcard",
    "modern_skyline",
    "food_focused",
]

def _select_variant() -> str:
    return random.choice(PROMPT_VARIANTS)


def _build_prompt(
    *,
    trip_state: TripState,
    itinerary: Iterable[ItineraryItem],
    rag_notes: list[str],
    variant: str,
    style: str | None = None,
    mood: str | None = None,
    color_palette: str | None = None,
    extra_notes: str | None = None,
) -> str:
    prefs = ", ".join(trip_state.activity_preferences) or "culture and food"
    food = ", ".join(trip_state.food_preferences) or "hawker delights"
    notes = "; ".join(rag_notes[:2]) if rag_notes else "Singapore highlights"
    day_summary = ""
    first_day = next(iter(itinerary), None)
    if first_day:
        day_summary = first_day.summary

    base = (
        "Create a postcard illustration of Singapore. "
        f"Theme: {prefs}. Food: {food}. "
        f"Include hints of: {notes}. "
        f"Day context: {day_summary}. "
        "Vibrant colors, travel-poster style, high detail."
    )

    if variant == "heritage_postcard":
        prompt = (
            base
            + " Focus on heritage shophouses, mosque domes, and warm sunset light. "
            "Add subtle batik patterns around the border."
        )
    elif variant == "modern_skyline":
        prompt = (
            base
            + " Focus on Marina Bay skyline, Supertrees, and clean modern lines. "
            "Add a minimal geometric border."
        )
    else:
        prompt = (
            base
            + " Focus on hawker culture, street food stalls, and lively night market lights. "
            "Add playful illustrated food icons around the border."
        )
    extras = []
    if style:
        extras.append(f"Art style: {style}.")
    if mood:
        extras.append(f"Mood: {mood}.")
    if color_palette:
        extras.append(f"Color palette: {color_palette}.")
    if extra_notes:
        extras.append(f"Extra notes: {extra_notes}.")
    if extras:
        prompt = prompt + " " + " ".join(extras)
    return prompt


def generate_postcard(
    *,
    trip_state: TripState,
    itinerary: list[ItineraryItem],
    rag_notes: list[str],
    prompt_override: str | None = None,
    style: str | None = None,
    mood: str | None = None,
    color_palette: str | None = None,
    extra_notes: str | None = None,
) -> tuple[str | None, str | None]:
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return None, None

    # Use DALL-E 3 for high-quality image generation
    # Falls back to dall-e-3 if OPENAI_IMAGE_MODEL not set
    model = os.getenv("OPENAI_IMAGE_MODEL", "dall-e-3")
    
    # Ensure we're using a valid DALL-E model
    if model not in ["dall-e-2", "dall-e-3"]:
        model = "dall-e-3"
    
    client = OpenAI(api_key=api_key)

    variant = _select_variant()
    if prompt_override and prompt_override.strip():
        prompt = prompt_override.strip()
    else:
        prompt = _build_prompt(
            trip_state=trip_state,
            itinerary=itinerary,
            rag_notes=rag_notes,
            variant=variant,
            style=style,
            mood=mood,
            color_palette=color_palette,
            extra_notes=extra_notes,
        )

    try:
        # DALL-E 3 specific parameters
        generate_params = {
            "model": model,
            "prompt": prompt,
            "size": "1024x1024",
            "n": 1,
        }
        
        # Only add quality param for DALL-E 3
        if model == "dall-e-3":
            generate_params["quality"] = "standard"
        
        response = client.images.generate(**generate_params)
        
        if not response.data:
            return prompt, None
        first = response.data[0]
        if getattr(first, "url", None):
            return prompt, first.url
        if getattr(first, "b64_json", None):
            data_url = f"data:image/png;base64,{first.b64_json}"
            return prompt, data_url
        return prompt, None
    except Exception as e:
        # Log the error for debugging
        print(f"Image generation error: {e}")
        import traceback
        traceback.print_exc()
        return prompt, None
