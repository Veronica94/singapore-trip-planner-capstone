## Flow Overview (Trip Planner)

This flow chart shows how the scripts connect, and which inputs are used at each step.

```
User (Streamlit UI)
  |
  | 1) user message (chat_input)
  v
streamlit_app.py
  |
  | POST /chat
  | payload: {session_id, user_message}
  v
app/controller.py  (FastAPI /chat)
  |
  | Load or create SessionState
  | Append user Message
  |
  +--> If awaiting_confirmation is True:
  |       - "yes" -> build_plan(trip_state)
  |       - "no"  -> ask for updates
  |       - else  -> skip confirmation and continue intake
  |
  v
app/agents/trip_intake.py
  |
  | Inputs:
  |   - trip_state (current)
  |   - last 12 messages
  |   - OPENAI_API_KEY, OPENAI_MODEL
  |
  | LLM output -> IntakeResult:
  |   - trip_state (location, dates, days, prefs, pace, budget, group_size, food)
  |   - missing_fields, next_question
  |   - confirmation_prompt
  |
  | Normalizes dates using weather.parse_date_input()
  v
app/controller.py
  |
  | If missing_fields:
  |   - ask next_question
  | Else:
  |   - ask confirmation prompt
  |
  | On "yes":
  v
app/agents/trip_controller.py  (build_plan)
  |
  | Inputs:
  |   - trip_state (from intake)
  |   - WEATHER_API (optional)
  |   - OPENAI_API_KEY for RAG / SQL / recommender / image
  |
  +--> _get_weather()
  |     - uses weather.fetch_weather()
  |     - input: trip_state.start_date/location
  |
  +--> _get_rag()
  |     - uses rag.rag_query()
  |     - input: activity prefs, budget, pace
  |
  +--> _get_hawkers()
  |     - uses sql_agent.query_hawkers()
  |     - input: food prefs, location hint
  |
  +--> _get_recommendations()
  |     - uses recommender.build_itinerary()
  |     - input: trip_state, weather_message, rag_notes, hawkers
  |
  +--> image_gen.generate_postcard()
  |     - input: trip_state, itinerary, rag_notes
  |
  v
TripArtifacts (itinerary, food recs, rag notes, postcard, citations)
  |
  v
streamlit_app.py
  |
  | Renders:
  |   - itinerary day_label / summary / activities / notes / estimated_time_hours
  |   - food recommendations
  |   - rag notes + citations
  |   - postcard prompt + image (URL)
  v
User
```

## Exact Inputs and Sources

1) **Trip intake (LLM)**
   - Source: `app/agents/trip_intake.py`
   - Inputs:
     - User messages (last 12)
     - Current `trip_state`
     - `OPENAI_API_KEY`, `OPENAI_MODEL`
   - Output: `TripState` fields + confirmation prompt

2) **Weather**
   - Source: `app/agents/weather.py`
   - Inputs:
     - `trip_state.location`
     - `trip_state.start_date`
     - `WEATHER_API`

3) **RAG notes**
   - Source: `app/agents/rag.py`
   - Inputs:
     - Query composed from `activity_preferences`, `budget`, `pace`
     - `OPENAI_API_KEY`, `OPENAI_EMBED_MODEL`
     - Local docs in `data/docs` and cached index in `data/rag_index.json`

4) **Hawker data**
   - Source: `app/agents/sql_agent.py`
   - Inputs:
     - `food_preferences`
     - `trip_state.location` (optional area hint)
     - `OPENAI_API_KEY` (for SQL plan + SQL generation)
     - Local DB `data/hawkers.db` and CSV `ListofGovernmentMarketsHawkerCentres.csv`

5) **Recommender (itinerary + food recs)**
   - Source: `app/agents/recommender.py`
   - Inputs:
     - `trip_state` (including days, dates, pace, budget, group size, prefs)
     - `weather_message`, `rag_notes`, `hawkers`
     - `OPENAI_API_KEY`, `OPENAI_MODEL`

6) **Image generation**
   - Source: `app/agents/image_gen.py`
   - Inputs:
     - `trip_state`
     - `itinerary`
     - `rag_notes`
     - `OPENAI_API_KEY`, `OPENAI_IMAGE_MODEL`

