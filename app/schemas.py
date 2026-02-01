from typing import List, Literal, Optional

from pydantic import BaseModel, Field, conlist


class ChatRequest(BaseModel):
    session_id: str
    user_message: str
    postcard_prompt_override: Optional[str] = None
    postcard_style: Optional[str] = None
    postcard_mood: Optional[str] = None
    postcard_colors: Optional[str] = None
    postcard_extra_notes: Optional[str] = None


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    ts: str


class TripState(BaseModel):
    location: str = "Singapore"
    start_date: str = ""
    end_date: str = ""
    days: int = 0
    activity_preferences: List[str] = Field(default_factory=list)
    pace: str = ""
    budget: str = ""
    group_size: int = 0
    food_preferences: List[str] = Field(default_factory=list)
    summary: str = ""
    postcard_prompt_override: Optional[str] = None
    postcard_style: Optional[str] = None
    postcard_mood: Optional[str] = None
    postcard_colors: Optional[str] = None
    postcard_extra_notes: Optional[str] = None


class ItineraryItem(BaseModel):
    day_label: str
    summary: str
    activities: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    estimated_time_hours: Optional[str] = None


class FoodRecommendation(BaseModel):
    name: str
    area: Optional[str] = None
    reason: Optional[str] = None


class TripArtifacts(BaseModel):
    itinerary: List[ItineraryItem] = Field(default_factory=list)
    weather_summary: Optional[str] = None
    food_recommendations: List[FoodRecommendation] = Field(default_factory=list)
    rag_notes: List[str] = Field(default_factory=list)
    postcard_prompt: Optional[str] = None
    postcard_image_url: Optional[str] = None
    citations: List[str] = Field(default_factory=list)


class ToolOutputs(BaseModel):
    weather: Optional[dict] = None
    rag: Optional[dict] = None
    sql: Optional[dict] = None
    recommender: Optional[dict] = None


class SessionState(BaseModel):
    messages: List[Message]
    trip_state: TripState
    clarifying_questions_asked: int
    awaiting_confirmation: bool = False
    last_artifacts: Optional[TripArtifacts] = None
    last_tool_outputs: Optional[ToolOutputs] = None


class PostcardRequest(BaseModel):
    session_id: str
    prompt_override: Optional[str] = None
    style: Optional[str] = None
    mood: Optional[str] = None
    color_palette: Optional[str] = None
    extra_notes: Optional[str] = None


class PostcardResponse(BaseModel):
    prompt: Optional[str]
    image_url: Optional[str]


class IntakeResult(BaseModel):
    trip_state: TripState
    missing_fields: List[str]
    next_question: Optional[str] = None
    needs_confirmation: bool
    confirmation_prompt: Optional[str] = None
    user_requested_generation: bool = False


class ChatResponse(BaseModel):
    assistant_message: str
    trip_state: TripState
    artifacts: TripArtifacts
    tool_outputs: ToolOutputs
