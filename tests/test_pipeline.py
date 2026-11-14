"""Fast offline tests (no TTS, no browser): `pytest tests/`."""
import asyncio
import json

import pytest

from geo_mcp.asset_catalog import build_catalog, resolve_feature
from geo_mcp.audio_aligner import estimate_timings, map_script_to_heard, split_words
from geo_mcp.models import SceneGraph, example_scene_graph
from geo_mcp.timeline_compiler import WordIndex, compile_timeline


def test_catalog_lists_starter_regions():
    cat = build_catalog()
    ids = {f["id"] for g in cat["geojson"] for f in g["features"]}
    assert {"GB-ENG", "GB-SCT", "GB-WLS", "GB-NIR"} <= ids
    assert {"whoosh", "pop", "thud", "clang", "ding"} <= set(cat["sfx"])
    assert {"crown", "sword", "castle", "scroll"} <= set(cat["props"])


def test_resolve_by_id_or_name_case_insensitive():
    assert resolve_feature("_starter_uk.geojson", "gb-eng")[1]["properties"]["name"] == "England"
    assert resolve_feature("anything.json", "northern ireland")[1]["properties"]["id"] == "GB-NIR"
    with pytest.raises(LookupError):
        resolve_feature("_starter_uk.geojson", "Atlantis")


def test_schema_rejects_bad_input():
    good = example_scene_graph()
    SceneGraph.model_validate(good)
    bad = json.loads(json.dumps(good))
    bad["scenes"][0]["characters"][0]["expression"] = "furious"
    with pytest.raises(Exception):
        SceneGraph.model_validate(bad)
    bad = json.loads(json.dumps(good))
    bad["scenes"][0]["camera"]["center"] = [54.6, -200]
    with pytest.raises(Exception):
        SceneGraph.model_validate(bad)


def test_script_words_keep_their_text_when_recogniser_mishears():
    script = split_words("Wales, conquered by England in 1283.")
    heard = [
        {"word": "Wales", "start": 0.2, "end": 0.6},
        {"word": "conkered", "start": 0.7, "end": 1.2},  # misheard
        {"word": "by", "start": 1.2, "end": 1.35},
        {"word": "England", "start": 1.4, "end": 1.9},
        {"word": "in", "start": 1.9, "end": 2.0},
        {"word": "twelve", "start": 2.0, "end": 2.3},  # number spoken as words
        {"word": "eighty-three", "start": 2.3, "end": 2.9},
    ]
    out = map_script_to_heard(script, heard, 3.2)
    assert [w["word"] for w in out] == script
    assert out[1]["start"] == pytest.approx(0.7) and out[3]["start"] == pytest.approx(1.4)
    assert 2.0 <= out[5]["start"] < out[5]["end"] <= 2.9
    assert all(a["start"] <= b["start"] for a, b in zip(out, out[1:]))


def test_triggers_resolve_in_narration_order(tmp_path):
    graph = SceneGraph.model_validate(example_scene_graph())
    words = split_words(graph.narration)
    timings = estimate_timings(words, 14.0)
    tl = compile_timeline(graph, timings, None, 14.0, tmp_path, warnings := [])
    starts = [s["start_frame"] for s in tl["scenes"]]
    assert starts[0] == 0 and starts == sorted(starts) and len(set(starts)) == 3
    idx = WordIndex(timings)
    # scene 2 starts on the *second* "England" ("England conquered"), not the first word match
    assert starts[1] == idx.frame(idx.find("England conquered"))
    wales = next(p for p in tl["scenes"][1]["polygons"] if p["feature_id"] == "GB-WLS")
    assert wales["trigger_frame"] == round(timings[words.index("Wales")]["start"] * 60)
    assert tl["total_frames"] == round((14.0 + 0.7) * 60)
    assert all(tl["scenes"][i]["end_frame"] == starts[i + 1] for i in range(2))
    assert not warnings
    assert (tmp_path / "sfx" / "pop.wav").exists()


def test_fuzzy_and_missing_triggers(tmp_path):
    g = example_scene_graph()
    g["scenes"][0]["sfx"][0]["trigger_word"] = "fuor"  # typo -> fuzzy match to "four"
    g["scenes"][1]["badges"][0]["trigger_word"] = "dragons"  # not in narration
    graph = SceneGraph.model_validate(g)
    timings = estimate_timings(split_words(graph.narration), 14.0)
    tl = compile_timeline(graph, timings, None, 14.0, tmp_path, warnings := [])
    four = next(w for w in timings if w["word"].startswith("four"))
    assert tl["sfx_events"][0]["frame"] == round(four["start"] * 60)
    assert any("dragons" in w for w in warnings)


def test_mcp_surface():
    from fastmcp import Client

    from geo_mcp.server import mcp

    async def go():
        async with Client(mcp) as c:
            tools = {t.name for t in await c.list_tools()}
            resources = {str(r.uri) for r in await c.list_resources()}
            cat = json.loads((await c.read_resource("geo://assets/catalog"))[0].text)
            schema = json.loads((await c.read_resource("geo://schema/scene-graph"))[0].text)
            status = await c.call_tool("check_render_status", {"job_id": "nope"})
            return tools, resources, cat, schema, status

    tools, resources, cat, schema, status = asyncio.run(go())
    assert tools == {"render_geo_short", "check_render_status", "preview_scene_frame"}
    assert resources == {"geo://assets/catalog", "geo://schema/scene-graph"}
    assert cat["geojson"] and "example" in schema and "json_schema" in schema
    assert status.data["status"] == "error"
