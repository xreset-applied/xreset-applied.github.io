# Research website — repo rules for agents

This is a **single static site**, deployed to GitHub Pages with **no build
step**. Keep it that way: plain HTML/CSS/JS, no bundler, no framework, no npm.
Python is used only for the preview server and offline media-generation tools;
the published site requires neither Python nor FFmpeg.

**Read [`STYLE.md`](STYLE.md) before changing any layout or visuals.** It is the
contract for how this site looks; the points below are the enforced hard rules.
A deeper guide for building pages lives in
[`.claude/skills/research-website/`](.claude/skills/research-website/SKILL.md).

## Design discipline (enforced)

- **Reuse the design system.** `assets/css/styles.css` is the shared Applied
  Intuition design system. Do **not** fork or rewrite it — put site-specific
  styles in `assets/css/site.css`, built only from the existing design tokens
  (`--blue`, `--ink`, `--gray`, the type and spacing scales). **Never hard-code
  a hex color or font stack that a token already covers.**
- **One UI accent color.** Applied Blue `#006CFA` is the only accent for new page
  UI. Original approved paper figures retain their existing colors and styling;
  do not redraw them to fit a different chart palette.
- **Consistent treatment, ordered by priority.** Sibling items share one card,
  spread, and nav style — no item is visually dominant. The *order* carries the
  emphasis: sequence by importance, not alphabetically.
- **Never fabricate.** Unreleased resources use native disabled buttons with
  `btn-disabled`; unknown numbers use `.tbd`. Never invent a URL, number, or claim.
- **Keep the page accessible.** Use native recording controls, semantic tabs and
  labeled selects. Videos loop after user-initiated playback; the opener GIF
  animates while visible, with a still/reduced-motion option. No iframe players,
  slide transitions or unrelated loading-figure substitutions.
- **Compose from existing components.** Use the shared figure, media, table and
  layout primitives, with site-specific refinements in `site.css`. The original
  template's `components.html` remains the visual catalog.
- **Preserve reference geometry.** Header and outer layout come from `styles.css`:
  a 1280px container, 24px gutters, and a floating 60px pill inset 14px from the top.
  Mobile uses the template's logo/menu circles and overlay. Do not replace this
  with a full-width sticky bar, shrink the container, or override hero type scales.

## Original paper figures

Preserve the original paper plots, uncertainty, labels and colors. They remain
available in the rollout section's disclosure; do not rebuild the chart data.

Structure: abstract → looping 3×3 simulation GIF → native The task / Why resets?
explanation → native method → filterable rollout gallery → perturbation pair.
The opener headline is “How do we make generalist RL training feasible?”
Explanations live in `index.html` as responsive HTML/SVG, not scaled slide canvases.
Use `assets/js/native-explainer.js` for direct semantic-state selection and
`assets/js/gallery.js` for domain/robot/object/condition filtering. Perturbation
videos remain rendered independently of every gallery filter.

## Local video assets

The user chose in-repo hosting. `assets/video/clips/` contains finite playback
excerpts; `assets/storyboard/source/` contains source images, not full source MP4s.
The complete narrated overview remains linked from the footer.

Keep canonical recordings unchanged outside this repo. `assets/data/clip-selections.json`
records source routes, starting frames and inclusive ending frames. Bake those
windows into published files; do not restore runtime endpoint pauses or seeks.
Every embedded recording uses native looping. Quarter-speed filter tests already
encode their slowdown: never multiply it again. Clips without an earlier stop
keep their recorded end. Preserve full perturbation excerpts and goal guides.

`tools/sync_media.py` makes frame-exact H.264/yuv420p faststart clips and maintains
source/output provenance. `tools/build_sim_grid.py` makes the actual 3×3 GIF:
canonical nine embodiment examples, exact success-frame freezes, 2.5 seconds
with all cells frozen, infinite repetition. Do not substitute a slide recording.
Preserve reduced-motion/manual still controls. The published gallery catalog
describes the encoded excerpts; source-frame metadata belongs in the offline
selection manifest. Do not invent robot/domain combinations.

Serve MP4s with byte-range support. Do not replace `serve.py` with a basic handler
that ignores Range; that breaks native scrubbing. HTTP regression tests live
under `tests/`; use browser checks for native interactions and responsive layout.

The Paper action links the in-repo PDF at `assets/paper/x-reset.pdf` (new tab).
arXiv stays a disabled placeholder until a real identifier exists; Code (Coming
Soon) and BibTeX remain disabled. No fabricated BibTeX/arXiv entry or badge.

## Preview

```sh
uv run serve.py           # http://127.0.0.1:8888, no-cache, binds 0.0.0.0
uv run serve.py --port N  # if 8888 is taken
```

The site is fully static — just refresh the browser after editing files.

## Deploy

Two remotes are configured:

- `origin` — the private staging repository.
  Push here to test; its enterprise Pages preview stays access-controlled.
  Push to `main`; `.github/workflows/pages.yml` publishes the repo root.
- `public` — `xreset-applied/xreset-applied.github.io`, the public user-site
  repository (`https://xreset-applied.github.io/`). Never push here without
  explicit user approval; it publishes immediately.

The public repo receives the same tree (site root at `/`, `.nojekyll`, media in
`assets/`). Its Pages workflow deploys on push to its default branch.
