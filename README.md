# Singapore Trip Planner

An AI-powered multi-agent travel planning system that generates personalized Singapore itineraries through natural conversation.

🌐 **[Live Demo](https://singapore-trip-planner-capstone.streamlit.app/)**

## Features

- 🤖 **Multi-Agent System**: 6 specialized agents (Trip Intake, Recommender, Weather, RAG, SQL, Image Gen)
- 💬 **Conversational Planning**: Natural multi-turn dialogue with memory
- 🗺️ **Geographic Coherence**: Realistic itineraries respecting district clustering and travel times
- 🌦️ **Weather-Aware**: Real-time forecasts influence indoor/outdoor activity scheduling
- 🍜 **Food Recommendations**: Hawker center suggestions near daily activities
- 🎨 **Personalized Postcards**: DALL-E 3 generated travel memorabilia with customizable styles
- 📅 **Flexible Duration**: Supports 1-30+ day trips with multi-pass generation strategy

## Tech Stack

- **Backend**: FastAPI, Python 3.11+
- **Frontend**: Streamlit
- **LLM**: OpenAI GPT-4o-mini
- **Image Gen**: DALL-E 3
- **RAG**: ChromaDB, text-embedding-3-small
- **Database**: SQLite (hawker centers)
- **APIs**: WeatherAPI
- **Deployment**: Render.com + Streamlit Cloud

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/Veronica94/singapore-trip-planner-capstone.git
cd singapore-trip-planner-capstone
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

Create `.env` file:

```bash
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4o-mini
OPENAI_IMAGE_MODEL=dall-e-3
WEATHER_API_KEY=your_weather_api_key
```

### 3. Run Backend

```bash
uvicorn app.main:app --reload
```

Backend runs at `http://localhost:8000`

### 4. Run Frontend

```bash
streamlit run streamlit_app.py
```

Frontend runs at `http://localhost:8501`

## Project Structure

```
├── app/
│   ├── agents/           # Specialized agents
│   │   ├── trip_intake.py
│   │   ├── recommender.py
│   │   ├── weather.py
│   │   ├── rag.py
│   │   ├── sql_agent.py
│   │   └── image_gen.py
│   ├── controller.py     # Session management
│   ├── main.py          # FastAPI app
│   └── schemas.py       # Pydantic models
├── data/
│   └── docs/            # RAG knowledge base
├── static/              # UI assets
├── streamlit_app.py     # Frontend
└── requirements.txt
```

## API Endpoints

- `GET /` - API info
- `GET /health` - Health check
- `POST /chat` - Conversational trip planning
- `POST /postcard` - Generate/regenerate postcard
- `GET /debug/session/{session_id}` - Debug session state

## Documentation

- **[Technical Report](TECHNICAL_REPORT.md)** - Complete implementation details
- **[Deployment Guide](DEPLOYMENT.md)** - Production deployment instructions
- **[API Docs](https://singapore-trip-planner-capstone.onrender.com/docs)** - Interactive API documentation

## Key Implementation Highlights

### Multi-Pass Generation
For trips >7 days, uses a two-phase strategy:
1. Week-level outline (themes and focus areas)
2. Daily expansion (detailed activities per day)

### RAG-Enhanced Planning
Pre-loaded documents enforce:
- Geographic clustering rules (one district per day)
- Time-block structure (morning/midday/afternoon/evening)
- Weather-based activity placement
- Travel time heuristics

### Fail-Soft Design
Non-critical agents (Weather, RAG, SQL) degrade gracefully without blocking itinerary generation.

## Testing

Manual testing covers:
- Trip duration variability (2-30+ days)
- Conversational flows and confirmation workflows
- Weather adaptation and budget constraints
- Agent coordination and error resilience
- UI/UX across browsers

## Future Enhancements

- User authentication and trip history
- PDF/calendar export
- Interactive map visualization
- Multi-language support
- Performance caching

## License

MIT

## Contact

**Author**: [Your Name]  
**Course**: [Course Name]  
**Repository**: https://github.com/Veronica94/singapore-trip-planner-capstone
