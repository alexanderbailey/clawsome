import os
from pathlib import Path

ROOT = Path(__file__).parent.parent

# Where the SQLite database and saved screenshots live. Overridable so a test
# run (or a container) can point at scratch storage instead of the checkout.
DATA_DIR = Path(os.environ.get("CLAWSOME_DATA_DIR") or ROOT / "data")

PROFILES_DIR = Path(os.environ.get("CLAWSOME_PROFILES_DIR") or ROOT / "profiles")
SCREENSHOTS_DIR = DATA_DIR / "screenshots"
DB_PATH = DATA_DIR / "clawsome.db"
