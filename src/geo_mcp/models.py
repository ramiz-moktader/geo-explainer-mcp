"""Strict Pydantic v2 schemas: the SceneGraph (LLM input) and example payload."""
from __future__ import annotations

from typing import Annotated, List, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

LonLat = Annotated[
    Tuple[float, float],
    Field(description="[longitude, latitude] in WGS84 degrees, e.g. [-1.5, 52.5]"),
]
Expression = Literal["neutral", "angry", "shocked", "smug", "sad"]
Action = Literal["idle", "bounce", "slash", "shake", "grow"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _check_lonlat(v: Tuple[float, float]) -> Tuple[float, float]:
    lon, lat = v
    if not (-180 <= lon <= 360 and -90 <= lat <= 90):
        raise ValueError(f"expected [lon, lat]; got {list(v)} (did you swap them?)")
    return v


class Camera(_Strict):
    center: LonLat
    zoom: float = Field(4.5, ge=0, le=18, description="MapLibre zoom. ~3 continent, ~5 country, ~7 region")
    pitch: float = Field(0, ge=0, le=75, description="Tilt in degrees (0 = top-down)")
    bearing: float = Field(0, description="Rotation in degrees clockwise from north")
    transition_sec: float = Field(1.2, ge=0, le=10, description="Eased fly time from the previous scene's camera")

    _v = field_validator("center")(_check_lonlat)


class Polygon(_Strict):
    geojson_file: str = Field(description="File name from geo://assets/catalog, e.g. '_starter_uk.geojson'")
    feature_id: str = Field(description="Region id or name from the catalog, e.g. 'GB-ENG'")
    fill_color: str = "#e0314b"
    border_color: str = "#ffffff"
    opacity: float = Field(0.65, ge=0, le=1)
    transition_to_color: Optional[str] = Field(None, description="If set, the fill blends to this colour at trigger_word")
    trigger_word: Optional[str] = Field(
        None,
        description="With transition_to_color: when the colour change fires. Without: when the polygon appears (default: scene start)",
    )


class Character(_Strict):
    id: str
    flag_code: str = Field(description="ISO 3166-1 alpha-2 ('fr'), a flag-icons code ('gb-eng'), or a custom file stem in assets/flags")
    coords: LonLat
    expression: Expression = "neutral"
    hat: Optional[str] = Field(None, description="Prop name worn on the head, e.g. 'crown', 'helmet'")
    prop: Optional[str] = Field(None, description="Prop name held in the hand, e.g. 'sword', 'castle', 'scroll', 'money_bag'")
    action: Action = "idle"
    trigger_word: Optional[str] = Field(None, description="When the character pops in (default: scene start)")

    _v = field_validator("coords")(_check_lonlat)


class Label(_Strict):
    text: str
    coords: LonLat
    curve: float = Field(0, ge=-1, le=1, description="-1 smile ... 0 straight ... 1 arch")
    style: Literal["country", "callout"] = "country"
    pointer_to: Optional[LonLat] = Field(None, description="Draws an arrow from the label to this point")
    trigger_word: Optional[str] = None

    _v = field_validator("coords")(_check_lonlat)


class Badge(_Strict):
    icon: str = Field(description="Prop name used as the icon, e.g. 'crown', 'passport', 'gavel'")
    label: str
    screen_pos: Tuple[float, float] = Field(description="[x_pct, y_pct] of the 1080x1920 frame, 0-100. Keep y < 70 to clear captions")
    trigger_word: Optional[str] = None

    @field_validator("screen_pos")
    @classmethod
    def _pct(cls, v):
        if not all(0 <= c <= 100 for c in v):
            raise ValueError("screen_pos values are percentages (0-100)")
        return v


class Sfx(_Strict):
    sound: str = Field(description="SFX name from the catalog: whoosh, pop, thud, clang, ding, or a custom WAV stem")
    trigger_word: str
    volume: float = Field(0.6, ge=0, le=1)


class Scene(_Strict):
    scene_id: str
    start_word: str = Field(
        description="Exact word or short phrase from `narration` at which this scene begins. Scenes must be in narration order; scene 0 always starts at frame 0."
    )
    camera: Camera
    polygons: List[Polygon] = Field(default_factory=list)
    characters: List[Character] = Field(default_factory=list)
    labels: List[Label] = Field(default_factory=list)
    badges: List[Badge] = Field(default_factory=list)
    sfx: List[Sfx] = Field(default_factory=list)


class SceneGraph(_Strict):
    title: str
    narration: str = Field(min_length=1, description="Full voiceover script, spoken exactly as written")
    voice: str = Field("en-US-AndrewNeural", description="Edge-TTS voice name (or an ElevenLabs voice id when ELEVENLABS_API_KEY is set)")
    music_mood: Optional[str] = Field(None, description="Optional background bed: 'epic', 'calm', 'tense', 'upbeat', or a file stem in assets/music")
    scenes: List[Scene] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_scene_ids(self):
        ids = [s.scene_id for s in self.scenes]
        if len(set(ids)) != len(ids):
            raise ValueError("scene_id values must be unique")
        return self


def example_scene_graph() -> dict:
    """A complete, working SceneGraph that only uses the bundled starter assets."""
    return {
        "title": "Why is the UK four countries?",
        "narration": (
            "The United Kingdom is not one country. It is four. "
            "England conquered Wales in the thirteenth century. "
            "Then Scotland joined by treaty, and Northern Ireland stayed when Ireland left."
        ),
        "voice": "en-US-AndrewNeural",
        "music_mood": None,
        "scenes": [
            {
                "scene_id": "intro",
                "start_word": "The United Kingdom",
                "camera": {"center": [-3.4, 54.6], "zoom": 5.0, "pitch": 0, "bearing": 0, "transition_sec": 1.0},
                "polygons": [
                    {"geojson_file": "_starter_uk.geojson", "feature_id": "GB-ENG", "fill_color": "#e0314b", "border_color": "#ffffff", "opacity": 0.65, "trigger_word": "four"},
                    {"geojson_file": "_starter_uk.geojson", "feature_id": "GB-SCT", "fill_color": "#2f6fd6", "border_color": "#ffffff", "opacity": 0.65, "trigger_word": "four"},
                    {"geojson_file": "_starter_uk.geojson", "feature_id": "GB-WLS", "fill_color": "#27a85a", "border_color": "#ffffff", "opacity": 0.65, "trigger_word": "four"},
                    {"geojson_file": "_starter_uk.geojson", "feature_id": "GB-NIR", "fill_color": "#f0a500", "border_color": "#ffffff", "opacity": 0.65, "trigger_word": "four"},
                ],
                "characters": [
                    {"id": "uk", "flag_code": "gb", "coords": [-2.0, 53.6], "expression": "smug", "hat": "crown", "prop": None, "action": "bounce"}
                ],
                "labels": [],
                "badges": [{"icon": "crown", "label": "4 countries", "screen_pos": [50, 16], "trigger_word": "four"}],
                "sfx": [{"sound": "pop", "trigger_word": "four", "volume": 0.6}],
            },
            {
                "scene_id": "conquest",
                "start_word": "England conquered",
                "camera": {"center": [-2.6, 52.5], "zoom": 6.0, "pitch": 20, "bearing": 0, "transition_sec": 1.2},
                "polygons": [
                    {"geojson_file": "_starter_uk.geojson", "feature_id": "GB-ENG", "fill_color": "#e0314b", "border_color": "#ffffff", "opacity": 0.65},
                    {"geojson_file": "_starter_uk.geojson", "feature_id": "GB-WLS", "fill_color": "#27a85a", "border_color": "#ffffff", "opacity": 0.65, "transition_to_color": "#e0314b", "trigger_word": "Wales"},
                ],
                "characters": [
                    {"id": "eng", "flag_code": "gb-eng", "coords": [-1.0, 52.6], "expression": "angry", "hat": "helmet", "prop": "sword", "action": "slash"},
                    {"id": "wls", "flag_code": "gb-wls", "coords": [-3.9, 52.3], "expression": "shocked", "hat": None, "prop": None, "action": "shake", "trigger_word": "Wales"},
                ],
                "labels": [{"text": "England", "coords": [-1.2, 53.9], "curve": 0.4, "style": "country"}],
                "badges": [{"icon": "castle", "label": "1283", "screen_pos": [70, 18], "trigger_word": "thirteenth"}],
                "sfx": [
                    {"sound": "whoosh", "trigger_word": "England", "volume": 0.5},
                    {"sound": "clang", "trigger_word": "Wales", "volume": 0.6},
                ],
            },
            {
                "scene_id": "union",
                "start_word": "Then Scotland",
                "camera": {"center": [-4.2, 55.6], "zoom": 5.3, "pitch": 0, "bearing": 0, "transition_sec": 1.4},
                "polygons": [
                    {"geojson_file": "_starter_uk.geojson", "feature_id": "GB-ENG", "fill_color": "#e0314b", "border_color": "#ffffff", "opacity": 0.65},
                    {"geojson_file": "_starter_uk.geojson", "feature_id": "GB-WLS", "fill_color": "#e0314b", "border_color": "#ffffff", "opacity": 0.65},
                    {"geojson_file": "_starter_uk.geojson", "feature_id": "GB-SCT", "fill_color": "#2f6fd6", "border_color": "#ffffff", "opacity": 0.65},
                    {"geojson_file": "_starter_uk.geojson", "feature_id": "GB-NIR", "fill_color": "#f0a500", "border_color": "#ffffff", "opacity": 0.65, "trigger_word": "Northern Ireland"},
                ],
                "characters": [
                    {"id": "sct", "flag_code": "gb-sct", "coords": [-4.0, 56.9], "expression": "neutral", "hat": None, "prop": "scroll", "action": "idle"},
                    {"id": "nir", "flag_code": "gb-nir", "coords": [-8.6, 55.7], "expression": "sad", "hat": None, "prop": None, "action": "idle", "trigger_word": "Northern Ireland"},
                ],
                "labels": [
                    {"text": "Scotland", "coords": [-4.0, 58.0], "curve": 0.3, "style": "country"},
                    {"text": "Union 1707", "coords": [0.0, 55.3], "curve": 0, "style": "callout", "pointer_to": [-3.2, 55.95], "trigger_word": "treaty"},
                ],
                "badges": [],
                "sfx": [{"sound": "ding", "trigger_word": "treaty", "volume": 0.5}],
            },
        ],
    }
