import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_dir))  # backend/

# Find and add scripts directory
for parent in [backend_dir] + list(backend_dir.parents):
    cand = parent / "scripts"
    if (cand / "generate_novatech.py").exists() or (cand / "seed.py").exists():
        if str(cand) not in sys.path:
            sys.path.insert(0, str(cand))
        break
else:
    scripts_app = Path("/app/scripts")
    if scripts_app.exists() and str(scripts_app) not in sys.path:
        sys.path.insert(0, str(scripts_app))

import pytest

@pytest.fixture(autouse=True)
async def reset_db_engine():
    from app.db.session import dispose_engine
    await dispose_engine()
    yield
    await dispose_engine()
