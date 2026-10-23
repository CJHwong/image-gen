"""Opt-in real API checks against an owned server and external reference assets."""

import base64
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest


@pytest.mark.live
@pytest.mark.parametrize("scene,width,height,frames", [("forest", 768, 448, 49), ("well-high", 1920, 1088, 17)])
def test_layout_to_render_live(scene, width, height, frames):
    root_value = os.environ.get("STUDIO_LAYOUT_LIVE_ROOT")
    url = os.environ.get("STUDIO_LAYOUT_LIVE_URL")
    if not root_value or not url:
        pytest.skip("Set STUDIO_LAYOUT_LIVE_ROOT and STUDIO_LAYOUT_LIVE_URL for the owned GPU check.")
    assert url != "http://127.0.0.1:8765", "Use an owned non-default server."
    root = Path(root_value)

    def call(route, value=None):
        request = urllib.request.Request(
            url + route,
            data=json.dumps(value).encode() if value is not None else None,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            return json.loads(raw) if "json" in response.headers.get("Content-Type", "") else raw

    payload = {
        "kind": "video",
        "backend": "ltx25_mlx",
        "mode": "edit",
        "adapter": "layout-to-render",
        "prompt": "An autumn forest beside a grassy pond, warm sunlight, vibrant yellow and orange leaves."
        if scene == "forest"
        else "A weathered stone well in golden summer grass, rough stone and timber in warm sunlight.",
        "width": width,
        "height": height,
        "num_frames": frames,
        "frame_rate": 24,
        "seed": 42,
        "clip": {"name": "layout.mp4", "data": base64.b64encode((root / f"{scene}-layout.mp4").read_bytes()).decode()},
        "references": [
            {
                "name": "look.png",
                "image": base64.b64encode((root / f"{scene}-look.png").read_bytes()).decode(),
                "frame_index": 0,
                "strength": 1.0,
            }
        ],
    }
    start = time.monotonic()
    operation = call("/api/v1/operations", payload)
    observed = []
    while True:
        status = call(operation["status_url"])
        observed.append(status.get("progress", {}))
        if status["status"] in ("succeeded", "failed", "cancelled"):
            break
        assert time.monotonic() - start < 1800, "Layout check exceeded 30 minutes"
        time.sleep(2)
    (root / f"{scene}-operation.json").write_text(json.dumps(status, indent=2))
    assert status["status"] == "succeeded", status
    output = root / f"{scene}-result.mp4"
    output.write_bytes(call(status["result_url"]))
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(output), "-f", "null", "-"], check=True, capture_output=True)
    info = json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,nb_frames",
                "-of",
                "json",
                str(output),
            ]
        )
    )["streams"][0]
    assert info == {"width": width, "height": height, "nb_frames": str(frames)}
    assert any(item.get("step", 0) > 0 for item in observed), observed
    (root / f"{scene}-check.json").write_text(
        json.dumps({"dimensions": info, "seconds": time.monotonic() - start, "progress": observed}, indent=2)
    )
