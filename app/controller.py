from datetime import datetime, timezone
import traceback

from fastapi import APIRouter, HTTPException

from app.agents import image_gen, trip_controller, trip_intake
from app.schemas import (
    ChatRequest,
    ChatResponse,
    Message,
    PostcardRequest,
    PostcardResponse,
    ToolOutputs,
    TripArtifacts,
    TripState,
    SessionState,
)

router = APIRouter()
SESSION_STORE: dict[str, SessionState] = {}


@router.get("/health")
def health_check() -> dict:
    return {"status": "ok"}


@router.get("/debug/session/{session_id}", response_model=SessionState)
def debug_session(session_id: str) -> SessionState:
    session = SESSION_STORE.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/postcard", response_model=PostcardResponse)
def postcard(request: PostcardRequest) -> PostcardResponse:
    session = SESSION_STORE.get(request.session_id)
    if not session or not session.last_artifacts:
        raise HTTPException(status_code=404, detail="Session not found")
    prompt, url = image_gen.generate_postcard(
        trip_state=session.trip_state,
        itinerary=session.last_artifacts.itinerary,
        rag_notes=session.last_artifacts.rag_notes,
        prompt_override=request.prompt_override,
        style=request.style,
        mood=request.mood,
        color_palette=request.color_palette,
        extra_notes=request.extra_notes,
    )
    session.last_artifacts.postcard_prompt = prompt
    session.last_artifacts.postcard_image_url = url
    SESSION_STORE[request.session_id] = session
    return PostcardResponse(prompt=prompt, image_url=url)


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    session = SESSION_STORE.get(request.session_id)
    if not session:
        session = SessionState(
            messages=[],
            trip_state=TripState(),
            clarifying_questions_asked=0,
            awaiting_confirmation=False,
        )

    user_message = request.user_message.strip()
    session.messages.append(
        Message(role="user", content=user_message, ts=_iso_now())
    )

    if session.awaiting_confirmation:
        if _is_affirmative(user_message):
            session.awaiting_confirmation = False
            try:
                messages_for_llm = list(session.messages)
                _append_assistant(session, "Building your itinerary...")
                planner = trip_controller.TripPlannerController()
                artifacts, tool_outputs = planner.build_plan(
                    session.trip_state,
                    prompt_override=request.postcard_prompt_override,
                    style=request.postcard_style,
                    mood=request.postcard_mood,
                    color_palette=request.postcard_colors,
                    extra_notes=request.postcard_extra_notes,
                )
                assistant_message = (
                    "Itinerary generated. "
                    "Details are ready in the artifacts."
                )
                _append_assistant(session, assistant_message)
                session.last_artifacts = artifacts
                session.last_tool_outputs = tool_outputs
                SESSION_STORE[request.session_id] = session
                return ChatResponse(
                    assistant_message=assistant_message,
                    trip_state=session.trip_state,
                    artifacts=artifacts,
                    tool_outputs=tool_outputs,
                )
            except Exception as exc:
                trace = traceback.format_exc(limit=8)
                assistant_message = (
                    "Sorry, I couldn't generate the itinerary right now. "
                    "Please try again."
                )
                _append_assistant(session, assistant_message)
                SESSION_STORE[request.session_id] = session
                return ChatResponse(
                    assistant_message=assistant_message,
                    trip_state=session.trip_state,
                    artifacts=TripArtifacts(),
                    tool_outputs=ToolOutputs(
                        recommender={
                            "status": "error",
                            "error": str(exc),
                            "trace": trace,
                        }
                    ),
                )
        if _is_negative(user_message):
            session.awaiting_confirmation = False
            assistant_message = (
                "Got it. Tell me what you'd like to update."
            )
            _append_assistant(session, assistant_message)
            SESSION_STORE[request.session_id] = session
            return ChatResponse(
                assistant_message=assistant_message,
                trip_state=session.trip_state,
                artifacts=TripArtifacts(),
                tool_outputs=ToolOutputs(),
            )
        session.awaiting_confirmation = False

    try:
        intake = trip_intake.intake_step(
            session.trip_state, session.messages
        )
    except Exception:
        assistant_message = (
            "Sorry, I couldn't process your input right now. "
            "Please try again."
        )
        _append_assistant(session, assistant_message)
        SESSION_STORE[request.session_id] = session
        return ChatResponse(
            assistant_message=assistant_message,
            trip_state=session.trip_state,
            artifacts=TripArtifacts(),
            tool_outputs=ToolOutputs(),
        )

    session.trip_state = intake.trip_state
    if request.postcard_prompt_override:
        session.trip_state.postcard_prompt_override = request.postcard_prompt_override
    if request.postcard_style:
        session.trip_state.postcard_style = request.postcard_style
    if request.postcard_mood:
        session.trip_state.postcard_mood = request.postcard_mood
    if request.postcard_colors:
        session.trip_state.postcard_colors = request.postcard_colors
    if request.postcard_extra_notes:
        session.trip_state.postcard_extra_notes = request.postcard_extra_notes
    session.trip_state.summary = _build_summary(
        session.trip_state, user_message
    )

    if intake.missing_fields:
        if intake.user_requested_generation:
            assistant_message = (
                "Missing required inputs: "
                + ", ".join(intake.missing_fields)
                + "."
            )
        else:
            assistant_message = intake.next_question or (
                "Please provide: " + ", ".join(intake.missing_fields) + "."
            )
        _append_assistant(session, assistant_message)
        SESSION_STORE[request.session_id] = session
        return ChatResponse(
            assistant_message=assistant_message,
            trip_state=session.trip_state,
            artifacts=TripArtifacts(),
            tool_outputs=ToolOutputs(),
        )

    confirmation_prompt = intake.confirmation_prompt or (
        "Please confirm these trip details: "
        f"location={session.trip_state.location}, "
        f"start_date={session.trip_state.start_date or 'unspecified'}, "
        f"end_date={session.trip_state.end_date or 'unspecified'}, "
        f"days={session.trip_state.days or 'unspecified'}, "
        f"pace={session.trip_state.pace or 'unspecified'}, "
        f"budget={session.trip_state.budget or 'unspecified'}, "
        f"group_size={session.trip_state.group_size or 'unspecified'}."
    )
    session.awaiting_confirmation = True
    _append_assistant(session, confirmation_prompt)
    SESSION_STORE[request.session_id] = session
    return ChatResponse(
        assistant_message=confirmation_prompt,
        trip_state=session.trip_state,
        artifacts=TripArtifacts(),
        tool_outputs=ToolOutputs(),
    )


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_affirmative(text: str) -> bool:
    return text.strip().lower() in {"yes", "y", "confirm", "ok", "okay"}


def _is_negative(text: str) -> bool:
    return text.strip().lower() in {"no", "n", "nope", "cancel"}


def _build_summary(state: TripState, user_message: str) -> str:
    intent = user_message.strip() or "No new user intent provided."
    summary = (
        f"Location: {state.location or 'Singapore'}. "
        f"Dates: {state.start_date or 'unspecified'} to {state.end_date or 'unspecified'}. "
        f"Days: {state.days or 'unspecified'}. "
        f"Pace: {state.pace or 'unspecified'}. "
        f"Latest user intent: {intent}."
    )
    return summary


def _append_assistant(session: SessionState, message: str) -> None:
    session.messages.append(
        Message(role="assistant", content=message, ts=_iso_now())
    )
    session.messages = session.messages[-12:]
