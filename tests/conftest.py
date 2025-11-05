# Ensure project root is on sys.path so tests can import top-level packages.
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Also ensure the parent directory (project root) is available
parent = project_root.parent
if str(parent) not in sys.path:
    sys.path.insert(0, str(parent))
