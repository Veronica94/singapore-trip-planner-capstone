import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests


SG_TZ = ZoneInfo("Asia/Singapore")
WEEKDAY_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
MONTH_INDEX = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


def parse_relative_date(raw: str, *, anchor: date | None = None) -> date | None:
    if not raw:
        return None
    if anchor is None:
        anchor = datetime.now(SG_TZ).date()

    text = raw.strip().lower()
    if text in {"today"}:
        return anchor
    if text in {"tomorrow"}:
        return anchor + timedelta(days=1)

    if text in {"this weekend", "thisweekend"}:
        return _next_weekday(anchor, WEEKDAY_INDEX["saturday"], allow_same_week=True)
    if text in {"next weekend", "nextweekend"}:
        return _next_weekday(anchor, WEEKDAY_INDEX["saturday"], allow_same_week=False)

    match = re.match(r"next\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)", text)
    if match:
        weekday = WEEKDAY_INDEX[match.group(1)]
        return _next_weekday(anchor, weekday, allow_same_week=False)

    return None


def parse_date_input(raw: str, *, anchor: date | None = None) -> date | None:
    if not raw:
        return None
    if anchor is None:
        anchor = datetime.now(SG_TZ).date()

    raw = raw.strip()
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        parsed = _parse_human_date(raw, anchor=anchor)
        if parsed:
            return parsed
        return parse_relative_date(raw, anchor=anchor)


def _parse_human_date(raw: str, *, anchor: date) -> date | None:
    text = raw.strip().lower()
    text = re.sub(r",", " ", text)
    text = re.sub(r"\s+", " ", text)

    match = re.match(
        r"^(?P<month>[a-z]+)\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?(?:\s+(?P<year>\d{4}))?$",
        text,
    )
    if match:
        return _build_date_from_parts(
            match.group("year"), match.group("month"), match.group("day"), anchor
        )

    match = re.match(
        r"^(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+(?P<month>[a-z]+)(?:\s+(?P<year>\d{4}))?$",
        text,
    )
    if match:
        return _build_date_from_parts(
            match.group("year"), match.group("month"), match.group("day"), anchor
        )

    return None


def _build_date_from_parts(
    year_text: str | None,
    month_text: str,
    day_text: str,
    anchor: date,
) -> date | None:
    month = MONTH_INDEX.get(month_text)
    if not month:
        return None
    day = int(day_text)
    year = int(year_text) if year_text else anchor.year
    try:
        candidate = date(year, month, day)
    except ValueError:
        return None
    if not year_text and candidate < anchor:
        try:
            candidate = date(year + 1, month, day)
        except ValueError:
            return None
    return candidate


def _next_weekday(anchor: date, weekday: int, *, allow_same_week: bool) -> date:
    days_ahead = (weekday - anchor.weekday()) % 7
    if days_ahead == 0 and not allow_same_week:
        days_ahead = 7
    return anchor + timedelta(days=days_ahead)


def get_weather_forecast(api_key: str, location: str, target_date: date) -> dict:
    today = datetime.now(SG_TZ).date()
    delta = (target_date - today).days

    if delta < 0:
        raise ValueError("date is in the past.")
    if delta <= 14:
        endpoint = "forecast.json"
    elif delta <= 300:
        endpoint = "future.json"
    else:
        raise ValueError("date too far out (WeatherAPI future supports up to ~300 days).")

    url = f"http://api.weatherapi.com/v1/{endpoint}"
    params = {
        "key": api_key,
        "q": location,
        "dt": target_date.isoformat(),
        "aqi": "no",
        "alerts": "no",
    }
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    return response.json()


def get_current_weather(api_key: str, location: str) -> dict:
    url = "http://api.weatherapi.com/v1/current.json"
    params = {"key": api_key, "q": location, "aqi": "no"}
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    return response.json()


def summarize_weather(weather_data: dict) -> dict:
    summary = {
        "condition": None,
        "temp_c": None,
        "min_c": None,
        "max_c": None,
        "chance_of_rain": None,
        "is_bad_outdoor": False,
    }

    if "forecast" in weather_data and weather_data["forecast"].get("forecastday"):
        day = weather_data["forecast"]["forecastday"][0]["day"]
        summary["condition"] = day["condition"]["text"]
        summary["min_c"] = day["mintemp_c"]
        summary["max_c"] = day["maxtemp_c"]
        summary["chance_of_rain"] = day.get("daily_chance_of_rain")
        cond = summary["condition"].lower()
        rain = int(summary["chance_of_rain"] or 0)
        summary["is_bad_outdoor"] = rain >= 60 or "rain" in cond or "thunder" in cond
    elif "current" in weather_data:
        cur = weather_data["current"]
        summary["condition"] = cur["condition"]["text"]
        summary["temp_c"] = cur["temp_c"]
        cond = summary["condition"].lower()
        summary["is_bad_outdoor"] = "rain" in cond or "thunder" in cond

    return summary


def fetch_weather(api_key: str, location: str, date_input: str | None) -> tuple[dict, str]:
    if not api_key:
        raise ValueError("WEATHER_API is not set.")
    if not location:
        raise ValueError("location is required.")

    target_date = parse_date_input(date_input or "")
    if target_date:
        data = get_weather_forecast(api_key, location, target_date)
        summary = summarize_weather(data)
        msg = (
            f"Forecast for {location} on {target_date.isoformat()}: "
            f"{summary['condition']}, "
            f"{summary['min_c']}–{summary['max_c']}°C, "
            f"chance of rain {summary['chance_of_rain']}%."
        )
        return summary, msg

    data = get_current_weather(api_key, location)
    summary = summarize_weather(data)
    msg = f"Current weather in {location}: {summary['condition']}, {summary['temp_c']}°C."
    return summary, msg


def fetch_weather_range(
    api_key: str, location: str, start_date: str, end_date: str
) -> list[dict]:
    if not api_key:
        raise ValueError("WEATHER_API is not set.")
    if not location:
        raise ValueError("location is required.")
    start = datetime.fromisoformat(start_date).date()
    end = datetime.fromisoformat(end_date).date()
    if end < start:
        raise ValueError("end_date is before start_date.")
    days = (end - start).days + 1
    results: list[dict] = []
    for offset in range(days):
        target = start + timedelta(days=offset)
        try:
            data = get_weather_forecast(api_key, location, target)
            summary = summarize_weather(data)
            results.append(
                {
                    "date": target.isoformat(),
                    "condition": summary["condition"],
                    "min_c": summary["min_c"],
                    "max_c": summary["max_c"],
                    "chance_of_rain": summary["chance_of_rain"],
                    "is_bad_outdoor": summary["is_bad_outdoor"],
                }
            )
        except Exception as exc:
            results.append(
                {
                    "date": target.isoformat(),
                    "error": str(exc),
                    "is_bad_outdoor": None,
                }
            )
    return results
