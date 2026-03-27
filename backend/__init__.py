import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

__version__ = "2.0.0"
__all__ = ['__version__']
