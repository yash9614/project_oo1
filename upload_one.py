import sys
from pathlib import Path
from assistant.repository import connection
from assistant.ingestion import store

if len(sys.argv) < 2:
    print("Usage: uv run upload_one.py path/to/file.md")
    sys.exit(1)

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

with connection() as conn:
    result = store(conn, text, path.name)
    print(result)