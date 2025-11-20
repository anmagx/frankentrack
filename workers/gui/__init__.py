"""
gui package for frankentrack.

Provides gui components.
"""

# Keep package init lightweight. Importing test modules at package
# import time can cause the test submodule to be loaded twice when
# executed with `python -m workers.gui.test_panels` which triggers
# the RuntimeWarning seen during development. Tests and harnesses
# should be imported only by callers when needed.

__all__ = []
