#!/usr/bin/env python3
"""Build the looping simulation opener from canonical recordings (Python + FFmpeg).

Run: python3 tools/build_sim_grid.py
Only website outputs are written; decoded intermediates live in a temporary folder.
The 20 fps sampling uses source presentation timestamps, not retimed motion. Each
cell clamps to its exact, zero-based successFrame before the whole grid holds.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from contextlib import ExitStack
from fractions import Fraction
import hashlib
import json
import math
import mmap
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[1]
COLUMNS = ["ur7e_sharpa", "kuka_sharpa", "ur7e_robotiq"]
LABELS = ["UR7e + Sharpa", "KUKA + Sharpa", "UR7e + Robotiq"]
WIDTH, HEIGHT, FPS, HOLD_CS = 960, 540, 20, 250
CELL_WIDTH, CELL_HEIGHT = WIDTH // 3, HEIGHT // 3
CELL_BYTES = CELL_WIDTH * CELL_HEIGHT * 3


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def ffmpeg(*args: str) -> None:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-threads", "1",
         "-filter_threads", "1", "-filter_complex_threads", "1", *args],
        check=True,
    )


def probe(path: Path) -> dict:
    return json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
        "stream=width,height,time_base,r_frame_rate,avg_frame_rate,sample_aspect_ratio:"
        "frame=best_effort_timestamp", "-of", "json", str(path),
    ]))


def original_path(mounts: dict, route: str) -> Path:
    if not route.startswith("/") or ".." in Path(route).parts:
        raise ValueError(f"Invalid canonical video path: {route}")
    mount, _, relative = route.lstrip("/").partition("/")
    base = mounts[mount].resolve()
    original = (base / relative).resolve(strict=True)
    if not original.is_relative_to(base):
        raise ValueError(f"Video escapes its canonical mount: {route}")
    return original


def build(source: Path, destination: Path, temporary: Path) -> dict:
    selection = source / "prototype-assets/embodiment-clips.json"
    mount_file = source / "serve_storyboard.py"
    catalog = json.loads(selection.read_text())
    if catalog["columns"] != COLUMNS or len(catalog["rows"]) != 3:
        raise ValueError("Expected the canonical three-column, three-row embodiment grid")
    mounts = runpy.run_path(str(mount_file))["MOUNTS"]
    cells = []
    for row_index, row in enumerate(catalog["rows"]):
        if len(row) != 3:
            raise ValueError("Every canonical grid row must have three cells")
        for column_index, clip in enumerate(row):
            if clip["robot"] != COLUMNS[column_index]:
                raise ValueError("Canonical cell does not match its column")
            original = original_path(mounts, clip["video"])
            metadata = probe(original)
            stream = metadata["streams"][0]
            time_base = Fraction(stream["time_base"])
            pts = [int(frame["best_effort_timestamp"]) for frame in metadata["frames"]]
            if not pts or any(b <= a for a, b in zip(pts, pts[1:])):
                raise ValueError(f"Expected increasing video timestamps: {original}")
            success = clip["successFrame"]
            if not isinstance(success, int) or not 0 <= success < len(pts):
                raise ValueError(f"Invalid successFrame in {clip['video']}")
            timestamps = [(value - pts[0]) * time_base for value in pts[:success + 1]]
            decoded = temporary / f"cell-{row_index}-{column_index}.rgb"
            # Contain the full display aspect ratio, including non-square pixels.
            scale = (
                f"scale=w='min({CELL_WIDTH},trunc({CELL_HEIGHT}*dar))':"
                f"h='min({CELL_HEIGHT},trunc({CELL_WIDTH}/dar))':flags=lanczos,"
                f"setsar=1,pad={CELL_WIDTH}:{CELL_HEIGHT}:(ow-iw)/2:(oh-ih)/2:black"
            )
            ffmpeg("-noautorotate", "-i", str(original), "-map", "0:v:0", "-an",
                   "-vf", scale, "-frames:v", str(success + 1), "-fps_mode", "passthrough",
                   "-pix_fmt", "rgb24", "-f", "rawvideo", str(decoded))
            if decoded.stat().st_size != (success + 1) * CELL_BYTES:
                raise ValueError(f"Decoded frame count differs from source selection: {original}")
            cells.append({
                "decoded": decoded, "timestamps": timestamps,
                "provenance": {
                    "row": row_index, "column": column_index,
                    "robot": clip["robot"], "object": clip["object"], "demo": clip["demo"],
                    "canonicalRoute": clip["video"],
                    "sourcePath": os.path.relpath(original, REPO),
                    "sourceSha256": digest(original), "sourceBytes": original.stat().st_size,
                    "sourceWidth": stream["width"], "sourceHeight": stream["height"],
                    "sourceSampleAspectRatio": stream.get("sample_aspect_ratio", "1:1"),
                    "sourceFrameRate": stream["r_frame_rate"],
                    "sourceTimeBase": stream["time_base"],
                    "sourceStartFrame": 0, "successFrame": success,
                    "sourceSuccessPts": pts[success],
                    "sourceSuccessSeconds": float(timestamps[-1]),
                    "canonicalStopSeconds": clip["stopSeconds"],
                    "sourceRollout": clip["sourceRollout"], "envId": clip["envId"],
                    "freezeOutputFrame": math.ceil(timestamps[-1] * FPS),
                },
            })

    # A cell's endpoint is inserted even when the 30 -> 20 fps cadence would skip it.
    # Earlier cells then keep that same decoded frame while later cells finish.
    last_frame = max(cell["provenance"]["freezeOutputFrame"] for cell in cells)
    grid = temporary / "grid.rgb"
    final = temporary / "final.rgb"
    canvas = bytearray(WIDTH * HEIGHT * 3)
    canvas_view = memoryview(canvas)
    row_bytes = CELL_WIDTH * 3
    with ExitStack() as stack:
        recordings = [stack.enter_context(mmap.mmap(
            stack.enter_context(cell["decoded"].open("rb")).fileno(), 0, access=mmap.ACCESS_READ,
        )) for cell in cells]
        output = stack.enter_context(grid.open("wb"))
        for cell in cells:
            cell["provenance"]["sampledSourceFrames"] = []
        for frame_index in range(last_frame + 1):
            when = Fraction(frame_index, FPS)
            for cell, recording in zip(cells, recordings):
                info = cell["provenance"]
                selected = bisect_right(cell["timestamps"], when) - 1
                info["sampledSourceFrames"].append(selected)
                start = selected * CELL_BYTES
                for line in range(CELL_HEIGHT):
                    target = ((info["row"] * CELL_HEIGHT + line) * WIDTH
                              + info["column"] * CELL_WIDTH) * 3
                    offset = start + line * row_bytes
                    canvas_view[target:target + row_bytes] = recording[offset:offset + row_bytes]
            output.write(canvas)
        final.write_bytes(canvas)
        for cell, recording in zip(cells, recordings):
            start = cell["provenance"]["successFrame"] * CELL_BYTES
            cell["provenance"]["scaledSuccessRgbSha256"] = hashlib.sha256(
                recording[start:start + CELL_BYTES],
            ).hexdigest()

    raw_input = ["-f", "rawvideo", "-pixel_format", "rgb24", "-video_size",
                 f"{WIDTH}x{HEIGHT}", "-framerate", str(FPS)]
    gif = temporary / "sim-grid.gif"
    still = temporary / "sim-grid-still.png"
    # A stable global palette and ordered dither avoid temporal quantization shimmer.
    # FFmpeg stores the final hold as one GIF delay, not 50 repeated raster frames.
    palette_filter = (
        "split[frames][colors];"
        "[colors]palettegen=stats_mode=full:max_colors=256:reserve_transparent=1[palette];"
        "[frames][palette]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle"
    )
    ffmpeg(*raw_input, "-i", str(grid), "-filter_complex", palette_filter,
           "-threads", "1", "-loop", "0", "-final_delay", str(HOLD_CS), str(gif))
    ffmpeg(*raw_input, "-i", str(final), "-frames:v", "1", "-threads", "1", str(still))
    result = {
        "generator": "tools/build_sim_grid.py", "generatorSha256": digest(Path(__file__)),
        "ffmpegVersion": subprocess.check_output(["ffmpeg", "-version"], text=True).splitlines()[0],
        "inputs": [
            {"path": os.path.relpath(path, REPO), "sha256": digest(path)}
            for path in (selection, mount_file)
        ],
        "columns": [{"id": robot, "label": label} for robot, label in zip(COLUMNS, LABELS)],
        "layout": {"rows": 3, "columns": 3, "order": "row-major", "width": WIDTH,
                   "height": HEIGHT, "cellWidth": CELL_WIDTH, "cellHeight": CELL_HEIGHT,
                   "fit": "contain; no crop, labels, or slide content"},
        "playback": {
            "fps": FPS, "rate": 1, "frameCount": last_frame + 1,
            "motionSeconds": last_frame / FPS, "finalHoldCentiseconds": HOLD_CS,
            "loopSeconds": last_frame / FPS + HOLD_CS / 100, "loopCount": 0,
            "sampling": "Latest source presentation timestamp at each 20 fps tick, clamped to exact successFrame",
            "timingQuantization": "Success appears on the first 20 fps tick at or after its source timestamp (<50 ms later)",
            "holdEncoding": "Final GIF frame delay is 250 centiseconds; 0 loop count means infinite",
        },
        "palette": {"colors": 256, "mode": "global", "dither": "bayer", "bayerScale": 3},
        "cells": [cell["provenance"] for cell in cells],
        "outputs": [
            {"path": path.name, "format": kind, "width": WIDTH, "height": HEIGHT,
             "bytes": path.stat().st_size, "sha256": digest(path)}
            for path, kind in ((gif, "GIF89a"), (still, "PNG"))
        ],
    }
    destination.mkdir(parents=True, exist_ok=True)
    for path in (gif, still):
        shutil.copyfile(path, destination / path.name)
    (destination / "sim-grid.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=REPO.parent / "paper-figures/projects/xreset/video")
    parser.add_argument("--output", type=Path, default=REPO / "assets/video")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="xreset-sim-grid-") as temporary:
        result = build(args.source.resolve(), args.output.resolve(), Path(temporary))
    print(f"Generated {WIDTH}x{HEIGHT} GIF: {result['playback']['motionSeconds']:.2f}s motion + "
          f"{HOLD_CS / 100:.2f}s final hold, {FPS} fps, infinite loop, "
          f"{result['outputs'][0]['bytes']:,} bytes. Exact success frames preserved.")


if __name__ == "__main__":
    main()
