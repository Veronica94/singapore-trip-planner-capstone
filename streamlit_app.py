import os
from uuid import uuid4

import base64
import requests
import streamlit as st


API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
API_TIMEOUT_SECONDS = int(os.getenv("API_TIMEOUT_SECONDS", "300"))


def post_chat(session_id: str, user_message: str) -> dict:
    try:
        response = requests.post(
            f"{API_BASE_URL}/chat",
            json={"session_id": session_id, "user_message": user_message},
            timeout=API_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        # Return a user-friendly error message
        return {
            "assistant_message": f"⚠️ Cannot connect to backend API. Please check:\n1. Backend is deployed and running\n2. API_BASE_URL is configured correctly in secrets\n\nError: {str(e)}",
            "artifacts": {},
            "tool_outputs": {}
        }


def post_postcard(
    session_id: str,
    prompt_override: str | None,
    style: str | None,
    mood: str | None,
    color_palette: str | None,
    extra_notes: str | None,
) -> dict:
    try:
        response = requests.post(
            f"{API_BASE_URL}/postcard",
            json={
                "session_id": session_id,
                "prompt_override": prompt_override,
                "style": style,
                "mood": mood,
                "color_palette": color_palette,
                "extra_notes": extra_notes,
            },
            timeout=API_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        result = response.json()
        
        # Log for debugging
        if not result.get("image_url"):
            print(f"Warning: Postcard API returned no image_url. Response: {result}")
        
        return result
    except requests.RequestException as e:
        print(f"Postcard API error: {e}")
        raise  # Re-raise to be caught by the caller


def get_debug_session(session_id: str) -> dict:
    try:
        response = requests.get(
            f"{API_BASE_URL}/debug/session/{session_id}",
            timeout=10,
        )
        if response.status_code == 404:
            return {}
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return {"error": "Could not connect to backend API"}


st.set_page_config(page_title="Singapore Trip Planner", layout="wide")
HEADER_IMAGE_PATH = "static/shophouse_illustration.jpg"


def _img_to_base64(path: str) -> str:
    try:
        with open(path, "rb") as fh:
            return base64.b64encode(fh.read()).decode("utf-8")
    except Exception:
        return ""


encoded_bg = _img_to_base64(HEADER_IMAGE_PATH)
if encoded_bg:
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Bree+Serif&family=Inter:wght@400;500&family=Poppins:wght@500;600&family=Fredoka:wght@500;600&display=swap');
        .stApp {{
            background-image:
                linear-gradient(rgba(255,255,255,0.85), rgba(255,255,255,0.85)),
                url("data:image/jpeg;base64,{encoded_bg}");
            background-size: cover;
            background-attachment: fixed;
            background-position: center;
        }}
        .block-container {{
            padding-top: 2rem;
            max-width: 1000px !important;
        }}
        .stChatMessage {{
            background: transparent;
            border-radius: 8px;
            padding: 8px 12px;
            margin-bottom: 12px;
        }}
        h1, h2, h3 {{ 
            margin-bottom: 0.6rem;
            color: #222;
        }}
        h5 {{
            color: #333;
        }}
        .banner {{
            max-width: 900px;
            margin: 0 auto 24px auto;
            background: rgba(30,30,30,0.75);
            border-radius: 16px;
            padding: 28px 32px;
            box-shadow: 0 12px 32px rgba(0,0,0,0.28);
        }}
        .banner-title {{
            font-family: 'Bree Serif', serif;
            font-size: 40px;
            text-align: center;
            color: #f8f8f8;
            margin-bottom: 8px;
        }}
        .banner-subtitle {{
            font-family: 'Inter', sans-serif;
            text-align: center;
            color: #e0e0e0;
            font-size: 17px;
        }}
        div[data-testid="stChatMessageContent"] {{
            background: transparent !important;
            color: #222 !important;
            font-size: 16px;
            line-height: 1.5;
        }}
        .stMarkdown, .stMarkdown p, .stMarkdown li {{
            color: #222 !important;
        }}
        .stSelectbox label, .stTextInput label, .stTextArea label {{
            color: #222 !important;
        }}
        div[data-testid="stChatInput"] {{
            position: relative !important;
            bottom: auto !important;
            background: rgba(245,245,245,0.9) !important;
            border-radius: 12px !important;
            padding: 8px !important;
            margin: 16px 0 !important;
        }}
        div[data-testid="stChatInput"] input {{
            font-size: 15px !important;
        }}
        .stButton > button {{
            font-size: 15px;
            font-weight: 500;
            padding: 10px 24px;
            border-radius: 10px;
            transition: all 0.2s ease;
        }}
        .stButton > button:hover {{
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }}
        .artifact-panel {{
            background: rgba(250,250,250,0.6);
            border-radius: 14px;
            padding: 20px 24px;
            margin-top: 20px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.08);
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

st.markdown(
    """
    <div class="banner">
      <div class="banner-title">Plan your Singapore trip now</div>
      <div class="banner-subtitle">Start by describing your trip now</div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.subheader("Session")
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid4())
    session_id = st.text_input(
        "Session ID",
        value=st.session_state.session_id,
    )
    col_new, col_refresh = st.columns(2)
    if col_new.button("New session"):
        st.session_state.session_id = str(uuid4())
        st.session_state.chat_log = []
        st.session_state.last_response = None
        st.rerun()
    if col_refresh.button("Refresh debug"):
        st.session_state.debug_session = get_debug_session(session_id)

    st.caption("API base URL")
    st.code(API_BASE_URL)

if "chat_log" not in st.session_state:
    st.session_state.chat_log = []
if "last_response" not in st.session_state:
    st.session_state.last_response = None
if "debug_session" not in st.session_state:
    st.session_state.debug_session = {}
if "intro_shown" not in st.session_state:
    st.session_state.intro_shown = False
if "plan_confirmed" not in st.session_state:
    st.session_state.plan_confirmed = False
if "postcard_style" not in st.session_state:
    st.session_state.postcard_style = "Illustration"
if "postcard_mood" not in st.session_state:
    st.session_state.postcard_mood = "Warm and welcoming"
if "postcard_colors" not in st.session_state:
    st.session_state.postcard_colors = "Pastel tones"
if "postcard_extra" not in st.session_state:
    st.session_state.postcard_extra = ""
if "postcard_prompt_edit" not in st.session_state:
    st.session_state.postcard_prompt_edit = ""


def _send_chat(session_id: str, message: str) -> None:
    st.session_state.chat_log.append(("user", message))
    try:
        with st.spinner("Sending your message…"):
            result = post_chat(session_id, message)
        assistant_message = result.get("assistant_message", "")
        st.session_state.last_response = result
    except requests.RequestException as exc:
        assistant_message = f"Request failed: {exc}"
        st.session_state.last_response = None
    st.session_state.chat_log.append(("assistant", assistant_message))
    st.rerun()


# Display chat history
for role, content in st.session_state.chat_log:
    with st.chat_message(role):
        st.markdown(content)

# Get last assistant message to check for confirmation
last_response = st.session_state.last_response or {}
assistant_message = (last_response.get("assistant_message") or "").strip().lower()

# Show confirmation buttons if needed
if "confirm" in assistant_message and st.session_state.chat_log:
    st.markdown("##### Confirm trip details")
    col_yes, col_no = st.columns(2)
    if col_yes.button("✓ Yes, generate itinerary", type="primary", use_container_width=True):
        st.session_state.chat_log.append(("user", "yes"))
        try:
            with st.spinner("Generating your plan…"):
                result = post_chat(session_id, "yes")
            assistant_message = result.get("assistant_message", "")
            st.session_state.last_response = result
        except requests.RequestException as exc:
            assistant_message = f"Request failed: {exc}"
            st.session_state.last_response = None
        st.session_state.chat_log.append(("assistant", assistant_message))
        st.rerun()
    if col_no.button("✎ No, revise details", use_container_width=True):
        st.session_state.chat_log.append(("user", "no"))
        try:
            result = post_chat(session_id, "no")
            assistant_message = result.get("assistant_message", "")
            st.session_state.last_response = result
        except requests.RequestException as exc:
            assistant_message = f"Request failed: {exc}"
            st.session_state.last_response = None
        st.session_state.chat_log.append(("assistant", assistant_message))
        st.rerun()

# Chat input at the bottom
user_message = st.chat_input("Type your message...")
if user_message:
    _send_chat(session_id, user_message)

st.markdown("---")

# Artifacts section
artifacts = (st.session_state.last_response or {}).get("artifacts") or {}
weather_summary = artifacts.get("weather_summary")

if weather_summary:
    st.markdown(f"**Weather**: {weather_summary}")

itinerary = artifacts.get("itinerary") or []
if itinerary:
    st.markdown("#### Itinerary")
    total_days = len(itinerary)
    if total_days <= 3:
        cols = st.columns(total_days)
    else:
        cols = st.columns(3)
    for idx, item in enumerate(itinerary):
        with cols[idx % len(cols)]:
            st.markdown(f"**{item.get('day_label', f'Day {idx + 1}')}**")
            st.write(item.get("summary"))
            activities = item.get("activities") or []
            if activities:
                st.markdown("Activities")
                for act in activities:
                    st.write(f"- {act}")
            notes = item.get("notes")
            if notes:
                st.markdown(f"Notes: {notes}")
            est = item.get("estimated_time_hours")
            if est:
                st.markdown(f"Estimated time: {est} hours")

    food_recs = artifacts.get("food_recommendations") or []
    if food_recs:
        st.markdown("#### Food Recommendations")
        for rec in food_recs:
            name = rec.get('name', '')
            area = rec.get('area', '')
            reason = rec.get('reason', '')
            
            if area and area.lower() != 'none':
                st.markdown(f"**{name}** ({area})")
            else:
                st.markdown(f"**{name}**")
            
            if reason and reason.lower() != 'none':
                st.write(reason)
            st.write("")

    if not st.session_state.plan_confirmed:
        st.markdown("---")
        st.markdown("#### Postcard Generation")
        st.write("Customize your postcard style before generating:")
        
        st.session_state.postcard_style = st.selectbox(
            "Style",
            ["Illustration", "Vintage poster", "Watercolor", "Minimalist", "Modern"],
            index=["Illustration", "Vintage poster", "Watercolor", "Minimalist", "Modern"].index(
                st.session_state.postcard_style
            )
            if st.session_state.postcard_style in ["Illustration", "Vintage poster", "Watercolor", "Minimalist", "Modern"]
            else 0,
        )
        st.session_state.postcard_mood = st.selectbox(
            "Mood",
            ["Warm and welcoming", "Energetic", "Calm", "Luxurious", "Playful"],
            index=["Warm and welcoming", "Energetic", "Calm", "Luxurious", "Playful"].index(
                st.session_state.postcard_mood
            )
            if st.session_state.postcard_mood in ["Warm and welcoming", "Energetic", "Calm", "Luxurious", "Playful"]
            else 0,
        )
        st.session_state.postcard_colors = st.text_input(
            "Color palette",
            value=st.session_state.postcard_colors,
        )
        st.session_state.postcard_extra = st.text_area(
            "Extra notes (optional)",
            value=st.session_state.postcard_extra,
        )
        
        col_plan_yes, col_plan_no = st.columns(2)
        if col_plan_yes.button("✓ Generate Postcard", type="primary", use_container_width=True):
            try:
                with st.spinner("Generating your postcard..."):
                    result = post_postcard(
                        session_id=session_id,
                        prompt_override=None,
                        style=st.session_state.postcard_style,
                        mood=st.session_state.postcard_mood,
                        color_palette=st.session_state.postcard_colors,
                        extra_notes=st.session_state.postcard_extra,
                    )
                    last = st.session_state.last_response or {}
                    artifacts = last.get("artifacts") or {}
                    artifacts["postcard_prompt"] = result.get("prompt")
                    artifacts["postcard_image_url"] = result.get("image_url")
                    last["artifacts"] = artifacts
                    st.session_state.last_response = last
                    st.session_state.plan_confirmed = True
                    st.rerun()
            except requests.RequestException as exc:
                st.error(f"Postcard generation failed: {exc}")
        if col_plan_no.button("✎ Revise Plan", use_container_width=True):
            _send_chat(session_id, "I'd like to revise the plan.")
            st.session_state.plan_confirmed = False

postcard_url = artifacts.get("postcard_image_url")
if st.session_state.plan_confirmed:
    if postcard_url:
        st.markdown("---")
        st.markdown("#### Your Personalized Postcard")
        st.image(postcard_url, width=600)
        
        col_download, col_regen = st.columns(2)
        if postcard_url.startswith("data:image"):
            col_download.download_button(
                "📥 Download Postcard",
                data=postcard_url.split(",", 1)[-1],
                file_name="singapore_postcard.png",
                mime="image/png",
                use_container_width=True,
            )
        else:
            col_download.markdown(f"[🔗 Share postcard]({postcard_url})")
        
        # Regenerate section
        with st.expander("✏️ Customize and Regenerate Postcard"):
        st.session_state.postcard_style = st.selectbox(
            "Style",
            ["Illustration", "Vintage poster", "Watercolor", "Minimalist", "Modern"],
            index=["Illustration", "Vintage poster", "Watercolor", "Minimalist", "Modern"].index(
                st.session_state.postcard_style
            )
            if st.session_state.postcard_style in ["Illustration", "Vintage poster", "Watercolor", "Minimalist", "Modern"]
            else 0,
            key="regen_style",
        )
        st.session_state.postcard_mood = st.selectbox(
            "Mood",
            ["Warm and welcoming", "Energetic", "Calm", "Luxurious", "Playful"],
            index=["Warm and welcoming", "Energetic", "Calm", "Luxurious", "Playful"].index(
                st.session_state.postcard_mood
            )
            if st.session_state.postcard_mood in ["Warm and welcoming", "Energetic", "Calm", "Luxurious", "Playful"]
            else 0,
            key="regen_mood",
        )
        st.session_state.postcard_colors = st.text_input(
            "Color palette",
            value=st.session_state.postcard_colors,
            key="regen_colors",
        )
        st.session_state.postcard_extra = st.text_area(
            "Extra notes",
            value=st.session_state.postcard_extra,
            key="regen_extra",
        )
        composed_prompt = (
            f"Postcard of Singapore. Style: {st.session_state.postcard_style}. "
            f"Mood: {st.session_state.postcard_mood}. "
            f"Colors: {st.session_state.postcard_colors}. "
            f"Notes: {st.session_state.postcard_extra}".strip()
        )
        st.session_state.postcard_prompt_edit = st.text_area(
            "Edit prompt directly",
            value=st.session_state.postcard_prompt_edit or composed_prompt,
            height=100,
            key="regen_prompt",
        )
        if st.button("🎨 Regenerate Postcard"):
            try:
                with st.spinner("Generating new postcard..."):
                    result = post_postcard(
                        session_id=session_id,
                        prompt_override=st.session_state.postcard_prompt_edit,
                        style=st.session_state.postcard_style,
                        mood=st.session_state.postcard_mood,
                        color_palette=st.session_state.postcard_colors,
                        extra_notes=st.session_state.postcard_extra,
                    )
                    last = st.session_state.last_response or {}
                    artifacts = last.get("artifacts") or {}
                    artifacts["postcard_prompt"] = result.get("prompt")
                    artifacts["postcard_image_url"] = result.get("image_url")
                    last["artifacts"] = artifacts
                    st.session_state.last_response = last
                    st.rerun()
            except requests.RequestException as exc:
                st.error(f"Postcard regeneration failed: {exc}")
    else:
        # Postcard generation failed
        st.markdown("---")
        st.markdown("#### Postcard Generation")
        st.warning("⚠️ Postcard generation failed. This could be due to:")
        st.write("""
        - OpenAI API rate limits
        - Content policy issues with the prompt
        - Network timeout
        - API key configuration
        
        Please check the Debug Information section below for details, or try again with different style settings.
        """)
        
        # Allow retry with different settings
        st.markdown("**Try generating again with different settings:**")
        st.session_state.postcard_style = st.selectbox(
            "Style",
            ["Illustration", "Vintage poster", "Watercolor", "Minimalist", "Modern"],
            index=0,
            key="retry_style",
        )
        st.session_state.postcard_mood = st.selectbox(
            "Mood",
            ["Warm and welcoming", "Energetic", "Calm", "Luxurious", "Playful"],
            index=0,
            key="retry_mood",
        )
        if st.button("🔄 Retry Postcard Generation", type="primary"):
            try:
                with st.spinner("Generating your postcard..."):
                    result = post_postcard(
                        session_id=session_id,
                        prompt_override=None,
                        style=st.session_state.postcard_style,
                        mood=st.session_state.postcard_mood,
                        color_palette=st.session_state.get("postcard_colors", "Pastel tones"),
                        extra_notes=st.session_state.get("postcard_extra", ""),
                    )
                    last = st.session_state.last_response or {}
                    artifacts = last.get("artifacts") or {}
                    artifacts["postcard_prompt"] = result.get("prompt")
                    artifacts["postcard_image_url"] = result.get("image_url")
                    last["artifacts"] = artifacts
                    st.session_state.last_response = last
                    st.rerun()
            except requests.RequestException as exc:
                st.error(f"Retry failed: {exc}")

# Debug section - collapsed by default
with st.expander("🔧 Debug Information"):
    # Show any errors first
    tool_outputs = (st.session_state.last_response or {}).get("tool_outputs", {}) or {}
    for name, payload in tool_outputs.items():
        if isinstance(payload, dict) and payload.get("status") == "error":
            st.error(f"{name} error")
            details = payload.get("error") or ""
            trace = payload.get("trace") or ""
            st.text_area(
                f"{name} error details",
                value=str(details),
                height=120,
            )
            if trace:
                st.text_area(
                    f"{name} error traceback",
                    value=str(trace),
                    height=200,
                )
    
    # RAG notes
    rag_notes = artifacts.get("rag_notes") or []
    if rag_notes:
        st.markdown("**RAG Notes**")
        for note in rag_notes:
            st.write(note)
    
    # Citations
    citations = artifacts.get("citations") or []
    if citations:
        st.markdown("**Citations**")
        for cite in citations:
            st.write(cite)
    
    # Postcard prompt
    postcard_prompt = artifacts.get("postcard_prompt")
    if postcard_prompt:
        st.markdown("**Postcard Prompt Used**")
        st.code(postcard_prompt)
    
    # Session state
    st.markdown("**Session State**")
    debug = st.session_state.debug_session or get_debug_session(session_id)
    st.json(debug)
