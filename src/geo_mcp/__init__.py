"""geo-explainer-mcp: SceneGraph -> narrated 9:16 map explainer video."""

__version__ = "0.1.0"
import os as _os

# 60 by default; GEO_FPS=30 halves render time (allowed range 24-60).
try:
    FPS = min(60, max(24, int(_os.environ.get("GEO_FPS", "60"))))
except ValueError:
    FPS = 60
WIDTH = 1080
HEIGHT = 1920
