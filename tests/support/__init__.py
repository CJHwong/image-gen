"""Helpers the mirrored tests share: a fake engine, a reference image, a child.

A test file mirrors its module, so it sits at a depth the module does not share.
Anything that needs a path into the source tree asks here rather than counting
`parents`, which breaks the moment a test moves.
"""

from pathlib import Path

# tests/support/__init__.py -> tests/support -> tests -> the repository root.
REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPO_ROOT / "studio"

# A stand-in engine child. A test spawns it through StdioChild, so it must be a
# real file on disk that `uv run` can execute, not an import.
FAKE_CHILD = Path(__file__).with_name("fake_child.py")
