# X-Reset Website

Static research page for **X-Reset: Scaling Object-Centric Reinforcement Learning
via Cross-Embodiment Resets**, using the Applied research website template.

## Reading order

1. Paper title, resources, and manuscript abstract.
2. **How do we make generalist RL training feasible?** A looping 3×3 simulation
   GIF: each cell freezes on success, then the complete grid holds for 2.5 seconds.
3. **The task / Why resets?** Native HTML/SVG explanations and recorded exploration
   examples, selected directly rather than replayed on a slide timeline.
4. **The method:** Retarget → Filter → Reset bank → Object-centric learning.
5. **Rollouts:** domain, robot, object and training/deployment dropdowns.
6. **Perturbation recovery:** mustard and hammer recordings, always rendered below
   the gallery and unaffected by its filters. Illustrative goal outlines can be
   toggled independently. The full narrated overview is linked in the footer.

No iframes, fixed-size slide canvases, incoming/outgoing slide transitions, or
placeholder figures that change into a different layout after JavaScript loads.
The initial explanation is authored HTML. Media posters show the same recording.
The shared header, gutters, fonts and geometry remain in `assets/css/styles.css`.

## Ownership

| File | Responsibility |
|---|---|
| `index.html` | Static explanations, simulation GIF and native recording elements |
| `assets/js/native-explainer.js` | Semantic tabs, keyboard navigation, departing-panel pause |
| `assets/js/gallery.js` | Dependent filters and recording selection |
| `assets/data/rollouts.json` | Source-backed metadata for 26 unique gallery recordings |
| `assets/js/media.js` | Native looping and offscreen/hidden-page pause; no endpoint clamps |
| `assets/js/site.js` | Initialization, goal outlines, GIF/still and reduced-motion controls |
| `assets/css/site.css`, `native-explainer.css`, `gallery.css` | Token-based content styling |
| `assets/storyboard/source/` | Exact original images only; no source MP4 duplicates |
| `assets/video/clips/` | 32 finite, ready-to-loop MP4 excerpts and requested first-frame posters |
| `assets/data/clip-selections.json` | Canonical source routes and inclusive frame selections |
| `assets/storyboard/provenance.json` | Source/output hashes, frame windows and encoding recipes |
| `tools/sync_media.py` | Frame-exact clipping, image packaging and goal SVG generation |
| `tools/build_sim_grid.py` | Deterministic 3×3 GIF, final still and GIF provenance |
| `serve.py` | Local preview, including HTTP byte-range requests |

The gallery contains 12 task/embodiment simulation recordings, eight scaling and
fine-tuning recordings, and six real deployments. Simulation offers UR7e + Sharpa,
UR7e + Robotiq, and KUKA + Sharpa. Real-world recordings offer only UR7e + Sharpa.
Changing a filter preserves compatible selections and resets incompatible ones;
only combinations backed by recordings are offered. Perturbations are separate.

Source in-points and inclusive stop frames are baked into the files, not enforced
by JavaScript. Rollout clips that were trimmed at a success frame keep one
additional second of source footage after it (30 frames at 30 fps) before
looping; the recorded success frame and the extra second are both inside every
published excerpt. Native controls show the actual excerpt duration; playback loops
automatically at EOF. Clips without an earlier selected stop retain their recorded
end, including complete perturbation and filtering excerpts. The physical filter
clips already encode quarter speed, so browser playback remains at rate 1.

The reset comparison uses the original 1280×720 banana evaluation recording,
`draft/reset_eval/replay/reset_banana_demo00_env0_ep0.mp4`, not the separate
1280×1200 paper-tile render. Both comparison videos therefore have matching native
dimensions without padding or cropping. The banana excerpt still uses frames
0–105 inclusive. Setting `poster: true` in its clip selection generates a JPEG
from the first packaged frame and records the source clip hash in provenance.

The real GIF is 960×540 at 20 fps, with nine independently frozen success frames,
a 250-centisecond final delay, and an infinite 9.6-second cycle. The final PNG
contains those exact decoded success frames. Reduced-motion users see the still;
the Show still / Play animation control provides an explicit override. GIF and
PNG are 8.88 MB and 0.35 MB respectively. Neither source videos nor trajectories
are modified in the canonical workspace.

## Preview and synchronize

```sh
python3 serve.py --port 8901
python3 tools/sync_media.py
python3 tools/build_sim_grid.py
# Optional alternate canonical source directory:
python3 tools/sync_media.py --source ../paper-figures/projects/xreset/video
python3 -m unittest discover -s tests -v
```

Offline generation uses Python's standard library plus FFmpeg/ffprobe. The static
site needs none of those tools or the source workspace. The package contains 38
source images, two illustrative goal SVGs, one generated poster and 32 MP4 clips. Eighteen clips have
physically shortened windows; fourteen already-complete excerpts are losslessly
remuxed. Recording payload is 92.95 MB instead of 187.37 MB (50% smaller), excluding
the separate GIF and full narrated overview. Source MP4 duplicates are removed
from the website. Content hashes and encoding recipes cache unchanged outputs.
All media remains in ordinary Git with explicit ignore exceptions; no external host.

Browser verification covered native tab/keyboard selection, all three simulation
embodiments, real-domain restrictions, object/condition comparisons, decoded
playback, native EOF-to-start looping, goal toggling, and offscreen pause.
Checked 320, 390, 768 and 1440px layouts without horizontal overflow. File checks
verified all 32 frame counts, nine frozen GIF cells and the exact 2.5-second hold.
Without JavaScript all explanation panels remain readable and static recording
controls remain usable; filtering requires JavaScript. Reduced motion is honored.
HTTP range regressions remain under `tests/`.

Selected footage is not an aggregate statistic. Original paper plots remain in
a native disclosure below the gallery. Goal outlines are illustrative 2D guides,
not calibrated target-pose projections. The Paper action links to the in-repo
PDF at `assets/paper/x-reset.pdf` (opens in a new tab). The arXiv action links to
https://arxiv.org/abs/2609.35715. Code (Coming Soon) and BibTeX remain
disabled placeholders. No invented publication claim.

The site is developed in a private staging repository with an access-controlled
Pages preview; pushes to `main` deploy through `.github/workflows/pages.yml`.
Public release publishes the same tree as a single squashed commit from the
`public` remote to the public repository. Runtime links are relative and all
published media is included; no build or access to the source workspace is
needed. Repository and Pages visibility are destination settings, not files.
