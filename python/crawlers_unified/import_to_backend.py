"""Import crawled JSON files into the backend via REST API."""
import json
import os
import requests
from pathlib import Path

API_BASE = os.environ.get("API_BASE", "http://localhost:3000/api")
IMPORT_URL = f"{API_BASE}/problems/import"

DATA_DIR = Path(__file__).parent.parent / "data" / "unified"


def import_all(data_dir: Path = None):
    """Import all JSON files from the data directory."""
    if data_dir is None:
        data_dir = DATA_DIR

    if not data_dir.exists():
        print(f"❌ Data directory not found: {data_dir}")
        return

    json_files = sorted(data_dir.glob("*.json"))
    if not json_files:
        print(f"❌ No JSON files found in {data_dir}")
        return

    success = 0
    failed = 0

    for filepath in json_files:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            platform = data.get("sourcePlatform", "unknown")
            source_id = data.get("sourceId", "unknown")
            title = data.get("title", source_id)

            resp = requests.post(IMPORT_URL, json=data, timeout=10)
            if resp.status_code in (200, 201):
                db_id = resp.json().get("id", "?")
                print(f"  ✅ [{platform}] {title} → {db_id}")
                success += 1
            else:
                print(f"  ⚠️ [{platform}] {title}: HTTP {resp.status_code} - {resp.text[:200]}")
                failed += 1

        except requests.exceptions.ConnectionError:
            print(f"  ❌ Cannot connect to backend at {API_BASE}")
            print(f"     Start the backend first: cd backend && npm run start:dev")
            failed = len(json_files) - success
            break
        except Exception as e:
            print(f"  ❌ [{filepath.name}]: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Done: {success} imported, {failed} failed")


if __name__ == "__main__":
    import_all()
