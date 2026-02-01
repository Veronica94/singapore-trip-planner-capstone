import json
import os
from typing import List

from openai import OpenAI
from pydantic import ValidationError

from app.schemas import CampaignBundle, CampaignState, IntakeResult, Message

LEVEL_RANGE_OPTIONS = ["1-4", "5-10", "11-16", "17-20"]


def is_ready(campaign_state: CampaignState) -> bool:
    return not _missing_fields(campaign_state)


def build_clarifying_question(
    campaign_state: CampaignState, messages: List[Message]
) -> str:
    missing = _missing_fields(campaign_state)
    if missing.get("setting"):
        return "What setting should the campaign take place in?"
    if missing.get("tone"):
        return "What tone should the campaign have (e.g., dark, funny, serious)?"
    if missing.get("player_count"):
        return "How many players are in the party?"
    if missing.get("level_range"):
        return "What level range should the campaign target (e.g., level 1-3)?"
    return "Any other preferences for the campaign?"


def fill_defaults(campaign_state: CampaignState) -> None:
    if not campaign_state.setting:
        campaign_state.setting = "frontier towns"
    if not campaign_state.tone:
        campaign_state.tone = "serious"
    if campaign_state.player_count <= 0:
        campaign_state.player_count = 4
    if not campaign_state.level_range:
        campaign_state.level_range = "1-3"


def intake_step(
    campaign_state: CampaignState, messages: List[Message]
) -> IntakeResult:
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    client = OpenAI(api_key=api_key)

    prompt = _build_intake_prompt(campaign_state, messages)
    raw_json = _call_llm(
        client=client,
        model=model,
        prompt=prompt,
        response_format="json_object",
    )

    try:
        return _enforce_intake_constraints(_parse_intake(raw_json))
    except (json.JSONDecodeError, ValidationError):
        fix_prompt = _build_intake_fix_prompt(raw_json)
        fixed_json = _call_llm(
            client=client,
            model=model,
            prompt=fix_prompt,
            response_format="json_object",
        )
        return _enforce_intake_constraints(_parse_intake(fixed_json))


def infer_setting_from_text(text: str) -> tuple[bool, str | None]:
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return False, None

    if not text.strip():
        return False, None

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    client = OpenAI(api_key=api_key)

    prompt = json.dumps(
        {
            "task": "Decide if the user text includes a campaign setting. "
            "If yes, extract a concise setting phrase.",
            "input_text": text,
            "output_schema": {
                "has_setting": "boolean",
                "setting": "string or null",
            },
            "constraints": ["Return JSON only."],
        },
        ensure_ascii=True,
    )

    try:
        raw_json = _call_llm(
            client=client,
            model=model,
            prompt=prompt,
            response_format="json_object",
        )
        data = json.loads(raw_json)
        has_setting = bool(data.get("has_setting"))
        setting = data.get("setting") if has_setting else None
        if isinstance(setting, str):
            setting = setting.strip()
        if has_setting and setting:
            return True, setting
    except Exception:
        return False, None

    return False, None


def _missing_fields(campaign_state: CampaignState) -> dict[str, bool]:
    return {
        "setting": not campaign_state.setting,
        "tone": not campaign_state.tone,
        "player_count": campaign_state.player_count <= 0,
        "level_range": not campaign_state.level_range,
    }


def generate_campaign(
    campaign_state: CampaignState, messages: List[Message]
) -> CampaignBundle:
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    client = OpenAI(api_key=api_key)

    prompt = _build_generation_prompt(campaign_state, messages)
    raw_json = _call_llm(
        client=client,
        model=model,
        prompt=prompt,
        response_format="json_object",
    )

    try:
        return _parse_bundle(raw_json)
    except (json.JSONDecodeError, ValidationError):
        fix_prompt = _build_fix_prompt(raw_json)
        fixed_json = _call_llm(
            client=client,
            model=model,
            prompt=fix_prompt,
            response_format="json_object",
        )
        return _parse_bundle(fixed_json)


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
                    "You are a narrative designer. "
                    "Return valid JSON only, no markdown."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        response_format={"type": response_format},
    )
    return response.choices[0].message.content or "{}"


def _build_intake_prompt(
    campaign_state: CampaignState, messages: List[Message]
) -> str:
    recent_messages = [
        {"role": msg.role, "content": msg.content} for msg in messages[-12:]
    ]
    payload = {
        "task": (
            "You are running an intake conversation for a tabletop campaign. "
            "Extract or update campaign_state from the conversation so far. "
            "If any required fields are missing, ask exactly ONE clarifying "
            "question to obtain the most critical missing field."
        ),
        "required_fields": [
            "setting",
            "tone",
            "player_count",
            "level_range",
        ],
        "level_range_options": LEVEL_RANGE_OPTIONS,
        "campaign_state": campaign_state.model_dump(),
        "recent_messages": recent_messages,
        "output_schema": {
            "campaign_state": {
                "setting": "string",
                "tone": "string",
                "player_count": "integer",
                "level_range": "string",
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
            "Level range must be one of level_range_options; ask the user to pick one if missing or invalid.",
            "If the user gives a plot idea or premise, put it in summary, not setting.",
        ],
    }
    return json.dumps(payload, ensure_ascii=True)


def _build_intake_fix_prompt(raw_json: str) -> str:
    payload = {
        "task": "Fix the JSON to match the intake schema exactly.",
        "schema": {
            "campaign_state": {
                "setting": "string",
                "tone": "string",
                "player_count": "integer",
                "level_range": "string",
                "summary": "string",
            },
            "missing_fields": ["string"],
            "next_question": "string or null",
            "needs_confirmation": "boolean",
            "confirmation_prompt": "string or null",
            "user_requested_generation": "boolean",
        },
        "level_range_options": LEVEL_RANGE_OPTIONS,
        "rules": [
            "Return JSON only.",
            "Ask exactly one question if missing_fields is not empty.",
            "If missing_fields is empty, needs_confirmation must be true and confirmation_prompt must be provided.",
            "Level range must be one of level_range_options; ask the user to pick one if missing or invalid.",
        ],
        "input_json": raw_json,
    }
    return json.dumps(payload, ensure_ascii=True)


def _parse_intake(raw_json: str) -> IntakeResult:
    data = json.loads(raw_json)
    return IntakeResult.model_validate(data)


def _enforce_intake_constraints(intake: IntakeResult) -> IntakeResult:
    if intake.campaign_state.level_range not in LEVEL_RANGE_OPTIONS:
        intake.campaign_state.level_range = ""
        if "level_range" not in intake.missing_fields:
            intake.missing_fields.append("level_range")
        intake.next_question = (
            "Choose a level range: " + ", ".join(LEVEL_RANGE_OPTIONS) + "."
        )
        intake.needs_confirmation = False
        intake.confirmation_prompt = None
    return intake


def _build_generation_prompt(
    campaign_state: CampaignState, messages: List[Message]
) -> str:
    recent_messages = [
        {"role": msg.role, "content": msg.content} for msg in messages[-6:]
    ]
    payload = {
        "campaign_state": campaign_state.model_dump(),
        "recent_messages": recent_messages,
        "schema": {
            "overview": "string, <= 350 words",
            "quests": [
                {
                    "title": "string",
                    "hook": "string",
                    "objective": "string",
                    "scenes": ["string", "string", "string"],
                    "twist": "string",
                    "reward": "string",
                }
            ],
            "npcs": [
                {
                    "name": "string",
                    "role": "string",
                    "goal": "string",
                    "secret": "string",
                    "voice_line": "string",
                }
            ],
            "boss": {
                "name": "string",
                "motive": "string",
                "weakness": "string",
                "foreshadowing": "string",
            },
        },
        "constraints": [
            "Return JSON only.",
            "overview <= 250 words.",
            "quests must be exactly 3 items.",
            "each quest.scenes must be exactly 3 items.",
            "npcs must be exactly 5 items.",
            "All arrays must be valid JSON arrays (no numeric keys).",
            "Do not include indices like 0:, 1:, 2: anywhere.",
        ],
    }
    return json.dumps(payload, ensure_ascii=True)


def _build_fix_prompt(raw_json: str) -> str:
    payload = {
        "task": "Fix the JSON to match the schema exactly.",
        "schema": {
            "overview": "string, <= 250 words",
            "quests": [
                {
                    "title": "string",
                    "hook": "string",
                    "objective": "string",
                    "scenes": ["string", "string", "string"],
                    "twist": "string",
                    "reward": "string",
                }
            ],
            "npcs": [
                {
                    "name": "string",
                    "role": "string",
                    "goal": "string",
                    "secret": "string",
                    "voice_line": "string",
                }
            ],
            "boss": {
                "name": "string",
                "motive": "string",
                "weakness": "string",
                "foreshadowing": "string",
            },
        },
        "constraints": [
            "Return JSON only.",
            "overview <= 250 words.",
            "quests must be exactly 3 items.",
            "each quest.scenes must be exactly 3 items.",
            "npcs must be exactly 5 items.",
            "All arrays must be valid JSON arrays (no numeric keys).",
            "Do not include indices like 0:, 1:, 2: anywhere.",
        ],
        "input_json": raw_json,
    }
    return json.dumps(payload, ensure_ascii=True)


def _parse_bundle(raw_json: str) -> CampaignBundle:
    data = json.loads(raw_json)
    return CampaignBundle.model_validate(data)
