"""Make the `bot` package importable when pytest runs from apps/bot."""
import sys
from pathlib import Path

# apps/bot (parent of this tests/ dir's parent) so `import bot` works.
_APP_DIR = Path(__file__).resolve().parents[1]
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))
