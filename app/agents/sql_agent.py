import csv
import json
import os
import sqlite3
from dataclasses import dataclass

from openai import OpenAI


DATASET_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "ListofGovernmentMarketsHawkerCentres.csv",
)
DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data",
    "hawkers.db",
)


@dataclass
class HawkerCenter:
    name: str
    location: str
    center_type: str
    owner: str
    stalls: int
    cooked_stalls: int
    produce_stalls: int


def ensure_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS hawker_centers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                location TEXT NOT NULL,
                center_type TEXT,
                owner TEXT,
                stalls INTEGER,
                cooked_stalls INTEGER,
                produce_stalls INTEGER
            )
            """
        )
        cur.execute("SELECT COUNT(1) FROM hawker_centers")
        count = cur.fetchone()[0]
        if count == 0:
            _load_csv(cur)
        conn.commit()
    finally:
        conn.close()


def _load_csv(cur: sqlite3.Cursor) -> None:
    if not os.path.exists(DATASET_PATH):
        raise FileNotFoundError(
            f"Hawker dataset not found at {DATASET_PATH}"
        )
    with open(DATASET_PATH, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            cur.execute(
                """
                INSERT INTO hawker_centers
                    (name, location, center_type, owner, stalls, cooked_stalls, produce_stalls)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.get("name_of_centre", "").strip(),
                    row.get("location_of_centre", "").strip(),
                    row.get("type_of_centre", "").strip(),
                    row.get("owner", "").strip(),
                    int(row.get("no_of_stalls") or 0),
                    int(row.get("no_of_cooked_food_stalls") or 0),
                    int(row.get("no_of_mkt_produce_stalls") or 0),
                ),
            )


def search_hawkers(
    area_hint: str | None,
    *,
    limit: int = 5,
) -> list[HawkerCenter]:
    ensure_db()
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        if area_hint:
            like = f"%{area_hint.strip()}%"
            cur.execute(
                """
                SELECT name, location, center_type, owner, stalls, cooked_stalls, produce_stalls
                FROM hawker_centers
                WHERE name LIKE ? OR location LIKE ?
                ORDER BY cooked_stalls DESC, stalls DESC
                LIMIT ?
                """,
                (like, like, limit),
            )
        else:
            cur.execute(
                """
                SELECT name, location, center_type, owner, stalls, cooked_stalls, produce_stalls
                FROM hawker_centers
                ORDER BY cooked_stalls DESC, stalls DESC
                LIMIT ?
                """,
                (limit,),
            )
        rows = cur.fetchall()
        return _rows_to_centers(rows)
    finally:
        conn.close()


def query_hawkers(question: str) -> list[HawkerCenter]:
    ensure_db()
    plan = generate_query_plan(question)
    sql = generate_sql_from_plan(plan)
    headers, rows = execute_query(sql)
    if isinstance(rows, str):
        raise ValueError(rows)
    return _rows_to_centers(rows)


def _rows_to_centers(rows: list[tuple]) -> list[HawkerCenter]:
    return [
        HawkerCenter(
            name=row[0],
            location=row[1],
            center_type=row[2],
            owner=row[3],
            stalls=row[4],
            cooked_stalls=row[5],
            produce_stalls=row[6],
        )
        for row in rows
    ]


def get_schema() -> str:
    return """
Table: hawker_centers
Columns:
- name (TEXT)
- location (TEXT)
- center_type (TEXT)
- owner (TEXT)
- stalls (INTEGER)
- cooked_stalls (INTEGER)
- produce_stalls (INTEGER)
"""


def generate_query_plan(question: str) -> dict:
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a data analyst translating questions into SQL logic.\n"
                    "Given the database schema, output ONLY valid JSON with the keys:\n"
                    "intent, tables, joins, filters, select_fields, grouping, ordering, limit, assumptions.\n"
                    "Do NOT output SQL here.\n"
                    f"Schema:\n{get_schema()}"
                ),
            },
            {"role": "user", "content": question},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    content = resp.choices[0].message.content or "{}"
    return json.loads(content)


def generate_sql_from_plan(plan: dict) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a SQL expert. Use the schema and the provided query plan.\n"
                    "Return ONLY the SQL query. No markdown, no explanation.\n"
                    "SQL must be compatible with SQLite.\n"
                    f"Schema:\n{get_schema()}"
                ),
            },
            {
                "role": "user",
                "content": (
                    "Query plan (JSON):\n"
                    f"{json.dumps(plan, indent=2)}\n\n"
                    "Generate the SQL."
                ),
            },
        ],
        temperature=0.2,
    )
    sql = resp.choices[0].message.content or ""
    return sql.replace("```sql", "").replace("```", "").strip()


def validate_sql(sql: str) -> str:
    lowered = sql.lower()
    if any(word in lowered for word in ["drop", "delete", "update", "insert", "alter"]):
        raise ValueError("Only SELECT queries are allowed.")
    if "select" not in lowered:
        raise ValueError("Only SELECT queries are allowed.")
    return sql


def execute_query(sql: str) -> tuple[list[str], list[tuple] | str]:
    sql = validate_sql(sql)
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        headers = [desc[0] for desc in cur.description] if cur.description else []
        return headers, rows
    except Exception as exc:
        return [], f"Error: {exc}"
    finally:
        conn.close()
