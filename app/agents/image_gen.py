import os
from typing import Iterable

from openai import OpenAI

from app.schemas import ItineraryItem, TripState


def _build_prompt(
    *,
    trip_state: TripState,
    itinerary: Iterable[ItineraryItem],
    rag_notes: list[str],
    style: str | None = None,
    mood: str | None = None,
    color_palette: str | None = None,
    extra_notes: str | None = None,
) -> str:
    """Build a concise DALL-E prompt with trip summary + user style preferences."""
    
    # Create brief trip summary from activity preferences
    trip_summary = "exploring Singapore"
    if trip_state.activity_preferences:
        # Just use first 2 preferences to keep it concise
        prefs = ", ".join(trip_state.activity_preferences[:2])
        if len(prefs) > 80:
            prefs = prefs[:80]
        trip_summary = f"{prefs} in Singapore"
    
    # Simple base prompt - the trip_summary and user inputs will define the style
    base = "Singapore travel postcard"
    
    # Build final prompt: base + trip vibe + user style inputs
    prompt_parts = [base, f"Trip theme: {trip_summary}"]
    
    if style:
        prompt_parts.append(f"Art style: {style[:100]}")
    if mood:
        prompt_parts.append(f"Mood: {mood[:80]}")
    if color_palette:
        prompt_parts.append(f"Color palette: {color_palette[:80]}")
    if extra_notes:
        # Allow generous room for extra notes
        prompt_parts.append(f"Details: {extra_notes[:800]}")
    
    prompt = ". ".join(prompt_parts) + "."
    
    # Safety check - should never hit this with the new concise format
    if len(prompt) > 3900:
        prompt = prompt[:3900] + "..."
    
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

    if prompt_override and prompt_override.strip():
        prompt = prompt_override.strip()
        # Truncate user's prompt if too long
        if len(prompt) > 4000:
            prompt = prompt[:3900] + "..."
    else:
        prompt = _build_prompt(
            trip_state=trip_state,
            itinerary=itinerary,
            rag_notes=rag_notes,
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
