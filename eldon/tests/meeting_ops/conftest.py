"""Shared test fixtures for meeting_ops tests."""
import sys
import os

# Ensure eldon/src is importable
_src = os.path.join(os.path.dirname(__file__), "..", "..", "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

# Ensure gateway app is importable as 'lola'  
_gw = os.path.join(os.path.dirname(__file__), "..", "..", "gateway", "app")
if _gw not in sys.path:
    sys.path.insert(0, _gw)
