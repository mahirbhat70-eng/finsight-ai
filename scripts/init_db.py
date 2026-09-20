"""Dev DB bootstrap: create_all + vector/tsvector indexes are added lazily by
app/rag/indexing.py once chunks exist. Production: alembic upgrade head."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db.session import dispose_engine, init_models


async def main() -> None:
    await init_models()
    print("create_all complete (use alembic for versioned migrations)")
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
