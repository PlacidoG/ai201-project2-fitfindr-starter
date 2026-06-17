"""
Pytest bootstrap.

Adds the repo root to sys.path so tests under tests/ can `import tools` and
`from utils.data_loader import ...` regardless of how pytest is invoked.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
