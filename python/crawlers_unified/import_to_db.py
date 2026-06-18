"""Import unified problem JSON files directly into PostgreSQL."""
import json
import os
import uuid
from pathlib import Path
import psycopg2
import psycopg2.extras

DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:jm050711@localhost:5432/acm_agent",
)

DATA_DIR = Path(__file__).parent.parent / "data" / "unified"

SQL_UPSERT = """
INSERT INTO problems (
    id, source_platform, source_id, source_url, title,
    difficulty_raw, difficulty_normalized,
    tags_normalized, tags_platform,
    full_content, raw_detail,
    created_at, updated_at
) VALUES (
    %(id)s::uuid, %(sourcePlatform)s, %(sourceId)s, %(sourceUrl)s, %(title)s,
    %(difficultyRaw)s, %(difficultyNormalized)s,
    %(tagsNormalized)s, %(tagsPlatform)s::jsonb,
    %(fullContent)s, %(rawDetail)s::jsonb,
    NOW(), NOW()
)
ON CONFLICT (source_platform, source_id)
DO UPDATE SET
    title = EXCLUDED.title,
    source_url = EXCLUDED.source_url,
    difficulty_raw = EXCLUDED.difficulty_raw,
    difficulty_normalized = EXCLUDED.difficulty_normalized,
    tags_normalized = EXCLUDED.tags_normalized,
    tags_platform = EXCLUDED.tags_platform,
    full_content = EXCLUDED.full_content,
    raw_detail = EXCLUDED.raw_detail,
    updated_at = NOW()
RETURNING id, title;
"""


def import_all(data_dir: Path = None):
    if data_dir is None:
        data_dir = DATA_DIR

    json_files = sorted(data_dir.glob("*.json"))
    if not json_files:
        print(f"No JSON files in {data_dir}")
        return

    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            for filepath in json_files:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)

                params = {
                    "id": str(uuid.uuid4()),
                    "sourcePlatform": data["sourcePlatform"],
                    "sourceId": data["sourceId"],
                    "sourceUrl": data.get("sourceUrl") or "",
                    "title": data["title"],
                    "difficultyRaw": data.get("difficultyRaw") or "",
                    "difficultyNormalized": data.get("difficultyNormalized", 5.0),
                    "tagsNormalized": data.get("tagsNormalized") or [],
                    "tagsPlatform": json.dumps(data.get("tagsPlatform") or {}),
                    "fullContent": data.get("fullContent") or "",
                    "rawDetail": json.dumps(data.get("rawDetail") or {}, ensure_ascii=False),
                }

                cur.execute(SQL_UPSERT, params)
                row = cur.fetchone()
                if row:
                    print(f"  ✅ [{data['sourcePlatform']}] {data['title'][:50]} → {row[0]}")

        conn.commit()
        print(f"\nImported {len(json_files)} problems.")

    except Exception as e:
        conn.rollback()
        print(f"  ❌ Error: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import_all()
