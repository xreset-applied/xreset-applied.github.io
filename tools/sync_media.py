#!/usr/bin/env python3
"""Package canonical images and physically selected, looping native-page clips.

The static site needs no Python or source workspace at runtime.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import runpy
import shutil
import subprocess
from urllib.parse import unquote, urljoin, urlsplit
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[1]
OUTPUT = REPO / "assets/storyboard"
PREFIX = "assets/storyboard/source/"
CLIPS = REPO / "assets/video/clips"
SELECTIONS = REPO / "assets/data/clip-selections.json"
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".svg", ".webp"}


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def canonical_path(source: Path, mounts: dict, route: str) -> Path:
    route = unquote(urlsplit(route).path)
    if not route.startswith("/") or ".." in Path(route).parts:
        raise ValueError(f"Invalid media path: {route}")
    first, _, remainder = route.lstrip("/").partition("/")
    return (mounts[first] / remainder if first in mounts else source / route.lstrip("/")).resolve(strict=True)


def probe_video(path: Path) -> dict:
    command = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
               "stream=codec_name,pix_fmt,width,height,avg_frame_rate,nb_frames", "-of", "json", str(path)]
    info = json.loads(subprocess.check_output(command, text=True))["streams"][0]
    if info.get("nb_frames", "N/A") == "N/A":
        count = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
                                         "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(path)], text=True)
        info["nb_frames"] = count.strip()
    return {"codec": info["codec_name"], "pixelFormat": info["pix_fmt"],
            "width": info["width"], "height": info["height"],
            "fps": info["avg_frame_rate"], "frameCount": int(info["nb_frames"])}


def package_clip(source: Path, mounts: dict, selection: dict, previous: dict, ffmpeg_version: str) -> dict:
    clip_id = selection["id"]
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", clip_id):
        raise ValueError(f"Invalid clip id: {clip_id}")
    original = canonical_path(source, mounts, selection["canonicalRoute"])
    source_hash = digest(original)
    source_info = probe_video(original)
    if Fraction(source_info["fps"]) != Fraction(selection["sourceFps"]):
        raise ValueError(f"Source fps changed for {clip_id}; revisit its frame selection")
    start = selection["startFrame"]
    end = selection["endFrame"]
    if end is None:
        end = source_info["frameCount"] - 1
    if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start <= end < source_info["frameCount"]:
        raise ValueError(f"Invalid source frame window for {clip_id}: {start}..{end}")
    trimmed = start != 0 or end != source_info["frameCount"] - 1
    arguments = ["-map", "0:v:0", "-an"]
    if trimmed:
        arguments += ["-vf", f"trim=start_frame={start}:end_frame={end + 1},setpts=PTS-STARTPTS",
                      "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
                      "-threads", "4", "-r", source_info["fps"], "-fps_mode", "cfr"]
    else:
        if source_info["codec"] != "h264" or source_info["pixelFormat"] != "yuv420p":
            raise ValueError(f"Complete excerpt is not H.264/yuv420p: {clip_id}")
        arguments += ["-c:v", "copy"]
    arguments += ["-map_metadata", "-1", "-movflags", "+faststart"]
    recipe = {"version": 1, "ffmpeg": ffmpeg_version, "arguments": arguments}
    cache_input = {"sourceSha256": source_hash, "selection": selection, "recipe": recipe}
    cache_key = hashlib.sha256(json.dumps(cache_input, sort_keys=True).encode()).hexdigest()
    destination = CLIPS / f"{clip_id}.mp4"
    cached = previous.get(clip_id)
    if cached and cached.get("cacheKey") == cache_key and destination.exists() and digest(destination) == cached["sha256"]:
        print(f"Cached {clip_id}", flush=True)
        return cached

    CLIPS.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp.mp4")
    try:
        subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(original),
                        *arguments, str(temporary)], check=True)
        output_info = probe_video(temporary)
        if (output_info["frameCount"] != end - start + 1
                or Fraction(output_info["fps"]) != Fraction(source_info["fps"])
                or (output_info["width"], output_info["height"]) != (source_info["width"], source_info["height"])
                or output_info["codec"] != "h264" or output_info["pixelFormat"] != "yuv420p"):
            raise ValueError(f"Encoded clip does not match its source selection: {clip_id}")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    mode = "trimmed" if trimmed else "remuxed"
    print(f"Packaged {clip_id}: {mode}, source frames {start}..{end}, {output_info['frameCount']} output frames", flush=True)
    return {"id": clip_id, "path": destination.relative_to(REPO).as_posix(),
            "canonicalRoute": selection["canonicalRoute"], "sourceSha256": source_hash,
            "sourceBytes": original.stat().st_size, "source": source_info,
            "startFrame": start, "endFrame": end, "naturalEnd": selection["endFrame"] is None,
            "output": output_info, "sha256": digest(destination), "bytes": destination.stat().st_size,
            "mode": mode, "recipe": recipe, "cacheKey": cache_key}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=REPO.parent / "paper-figures/projects/xreset/video")
    source = parser.parse_args().source.resolve()
    manifest_path = OUTPUT / "provenance.json"
    previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    references = set(re.findall(re.escape(PREFIX) + r"[^\s\"'<>]+", (REPO / "index.html").read_text()))
    catalog = json.loads((REPO / "assets/data/rollouts.json").read_text())
    references.update(PREFIX + clip["poster"] for clip in catalog["clips"])
    references = {ref for ref in references if Path(urlsplit(ref).path).suffix.lower() in IMAGE_TYPES}
    if not references:
        raise ValueError("No native media references found; refusing to prune the media package")
    routes = sorted("/" + ref.removeprefix(PREFIX) for ref in references)
    mounts = runpy.run_path(str(source / "serve_storyboard.py"))["MOUNTS"]
    selections = json.loads(SELECTIONS.read_text())["clips"]
    if not selections or len({entry["id"] for entry in selections}) != len(selections):
        raise ValueError("Clip selections must be nonempty with unique ids")
    previous_clips = {entry["id"]: entry for entry in previous.get("clips", [])}
    ffmpeg_version = subprocess.check_output(["ffmpeg", "-version"], text=True).splitlines()[0]
    clips = [package_clip(source, mounts, selection, previous_clips, ffmpeg_version) for selection in selections]
    assets, seen = [], set()
    while routes:
        route = unquote(urlsplit(routes.pop()).path)
        if route in seen:
            continue
        original = canonical_path(source, mounts, route)
        seen.add(route)
        if original.suffix.lower() not in IMAGE_TYPES:
            raise ValueError(f"Unexpected image type: {route}")
        destination = OUTPUT / "source" / route.lstrip("/")
        fingerprint = digest(original)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists() or digest(destination) != fingerprint:
            shutil.copyfile(original, destination)
        assets.append({"path": destination.relative_to(OUTPUT).as_posix(), "canonicalRoute": route, "sha256": fingerprint, "bytes": original.stat().st_size})
        if original.suffix == ".svg":
            for node in ET.parse(original).iter():
                for key, value in node.attrib.items():
                    if key.rsplit("}", 1)[-1] == "href" and not value.startswith(("#", "data:")):
                        if urlsplit(value).scheme:
                            raise ValueError(f"External SVG dependency: {route}")
                        routes.append(urljoin(route, value))

    guides = json.loads((source / "media/real/goal-guides.json").read_text())["references"]
    derived = []
    for selection, clip in zip(selections, clips):
        if not selection.get("poster"):
            continue
        video = REPO / clip["path"]
        destination = video.with_suffix(".jpg")
        arguments = ["-frames:v", "1", "-q:v", "2", "-update", "1"]
        subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                        "-i", str(video), *arguments, str(destination)], check=True)
        derived.append({"path": destination.relative_to(REPO).as_posix(), "sha256": digest(destination),
                        "sourceVideo": clip["path"], "sourceVideoSha256": clip["sha256"],
                        "frame": 0, "recipe": {"ffmpeg": ffmpeg_version, "arguments": arguments}})

    for object_name, guide in guides.items():
        svg = ET.Element("svg", {"xmlns": "http://www.w3.org/2000/svg", "viewBox": "0 0 960 960"})
        group = ET.SubElement(svg, "g", {"transform": guide["goalTransform"]})
        ET.SubElement(group, "path", {"d": guide["silhouette"], "fill": "none", "stroke": "white", "stroke-opacity": ".65", "stroke-width": "7", "stroke-linejoin": "round"})
        ET.SubElement(group, "path", {"d": guide["silhouette"], "fill": "#006cfa", "fill-opacity": ".18", "stroke": "#006cfa", "stroke-width": "3.5", "stroke-dasharray": "11 7", "stroke-linejoin": "round"})
        destination = REPO / "assets/data" / f"goal-{object_name}.svg"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(ET.tostring(svg, encoding="unicode") + "\n")
        derived.append({"path": destination.relative_to(REPO).as_posix(), "sha256": digest(destination)})

    inputs = ["storyboard-prototype.js", "serve_storyboard.py", "prototype-assets/embodiment-clips.json", "prototype-assets/transfer-clips.json", "media/filter/manifest.json", "media/real/goal-guides.json", "media/real/playback-selection.json", "media/real/additional-manifest.json"]
    source_bytes = sum(clip["sourceBytes"] for clip in clips)
    clip_bytes = sum(clip["bytes"] for clip in clips)
    manifest = {
        "generator": "tools/sync_media.py", "generatorSha256": digest(Path(__file__)),
        "canonical": "Selected media from the X-Reset canonical video workspace",
        "policy": "Source images are byte-identical; requested clip posters are extracted from the first packaged frame. Native clips are physically trimmed at inclusive source-frame selections, H.264/yuv420p with faststart, no audio, original resolution and fps. Complete excerpts are remuxed without re-encoding. Filter tests retain their already-encoded 0.25x slowdown. No source MP4 duplicates are published. Goal outlines remain illustrative, not calibrated.",
        "selectionManifest": {"path": SELECTIONS.relative_to(REPO).as_posix(), "sha256": digest(SELECTIONS)},
        "inputs": [{"name": name, "sha256": digest(source / name)} for name in inputs],
        "derived": derived,
        "assets": sorted(assets, key=lambda entry: entry["path"]),
        "clips": sorted(clips, key=lambda entry: entry["id"]),
        "summary": {"clipCount": len(clips), "sourceVideoBytes": source_bytes, "clipBytes": clip_bytes,
                    "bytesSaved": source_bytes - clip_bytes},
    }
    reachable = {asset["path"] for asset in assets}
    for asset in previous.get("assets", []):
        relative = Path(asset["path"])
        if relative.parts[0] != "source" or ".." in relative.parts:
            raise ValueError("Invalid previous media provenance path")
        if relative.as_posix() not in reachable:
            (OUTPUT / relative).unlink(missing_ok=True)
    # Deliberate cutover: the source package now contains images only.
    for obsolete in (OUTPUT / "source").rglob("*.mp4"):
        obsolete.unlink()
    reachable_clips = {clip["path"] for clip in clips}
    for clip in previous_clips.values():
        relative = Path(clip["path"])
        if relative.parent != Path("assets/video/clips") or ".." in relative.parts:
            raise ValueError("Invalid previous clip provenance path")
        if relative.as_posix() not in reachable_clips:
            (REPO / relative).unlink(missing_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(f"Packaged {len(clips)} native clips: {source_bytes:,} → {clip_bytes:,} bytes "
          f"({source_bytes - clip_bytes:,} saved, {(1 - clip_bytes / source_bytes):.1%} reduction). "
          f"Kept {len(assets)} source images and generated {len(derived)} derived assets. Canonical sources unchanged.")


if __name__ == "__main__":
    main()
