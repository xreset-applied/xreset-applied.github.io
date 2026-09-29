import { mountMedia } from "./media.js";

const sourceRoot = new URL("../storyboard/source/", import.meta.url);
const clipRoot = new URL("../video/clips/", import.meta.url);

function setOptions(select, values, selected, label, allLabel) {
  const fragment = document.createDocumentFragment();
  if (allLabel) fragment.append(new Option(allLabel, "all"));
  for (const value of values) fragment.append(new Option(label(value), value));
  select.replaceChildren(fragment);
  select.value = selected;
  select.disabled = select.options.length === 1;
}

function makeClip(clip, catalog) {
  const figure = document.createElement("figure");
  figure.className = "gallery-clip";
  const video = document.createElement("video");
  video.controls = true;
  video.playsInline = true;
  video.loop = true;
  video.preload = "none";
  video.src = new URL(clip.video, clipRoot).href;
  video.poster = new URL(clip.poster, sourceRoot).href;
  const condition = catalog.conditions[clip.condition];
  const detail = clip.recording
    ? `Recording ${clip.recording} · ${clip.familiarity}`
    : condition;
  video.setAttribute("aria-label", `${clip.objectLabel} — ${detail}`);

  const caption = document.createElement("figcaption");
  const title = document.createElement("strong");
  title.textContent = clip.objectLabel;
  const description = document.createElement("span");
  description.textContent = detail;
  caption.append(title, description);
  if (clip.outcome) {
    const outcome = document.createElement("span");
    outcome.textContent = clip.outcome;
    caption.append(outcome);
  }

  const error = document.createElement("p");
  error.className = "gallery-media-error";
  error.setAttribute("role", "alert");
  error.hidden = true;
  const download = document.createElement("a");
  download.href = video.src;
  download.textContent = "Open the video file.";
  error.append("This recording could not be loaded. ", download);
  video.addEventListener("error", () => { error.hidden = false; }, { once: true });
  figure.append(video, caption, error);
  return figure;
}

export async function initGallery() {
  const root = document.querySelector("[data-rollout-gallery]");
  if (!root) return;
  const fields = root.querySelector("fieldset");
  const results = root.querySelector("[data-gallery-results]");
  const count = root.querySelector("[data-gallery-count]");
  const status = root.querySelector("[data-gallery-status]");
  const selects = Object.fromEntries(
    [...fields.querySelectorAll("select")].map(select => [select.name, select]),
  );

  let catalog;
  try {
    const response = await fetch(new URL("../data/rollouts.json", import.meta.url));
    if (!response.ok) throw new Error(`Rollout catalog: HTTP ${response.status}`);
    catalog = await response.json();
    if (!Array.isArray(catalog.clips) || !catalog.clips.length) {
      throw new Error("The rollout catalog contains no recordings.");
    }
  } catch (error) {
    results.setAttribute("aria-busy", "false");
    status.textContent = "The rollout catalog could not be loaded. Please reload this page to try again.";
    status.hidden = false;
    count.textContent = "Recordings unavailable";
    console.error(error);
    return;
  }

  const state = { ...catalog.defaults };
  let disposeMedia;
  const values = (clips, field) => [...new Set(clips.map(clip => clip[field]))];

  function updateFilters() {
    const domains = values(catalog.clips, "domain");
    if (!domains.includes(state.domain)) state.domain = domains[0];
    const inDomain = catalog.clips.filter(clip => clip.domain === state.domain);
    const robots = values(inDomain, "robot");
    if (!robots.includes(state.robot)) state.robot = robots[0];
    const onRobot = inDomain.filter(clip => clip.robot === state.robot);
    const objects = values(onRobot, "object");
    if (!objects.includes(state.object)) state.object = "all";
    const forObject = onRobot.filter(clip => state.object === "all" || clip.object === state.object);
    const conditions = values(forObject, "condition");
    if (state.condition !== "all" && !conditions.includes(state.condition)) state.condition = "all";

    setOptions(selects.domain, domains, state.domain, value => catalog.domains[value]);
    setOptions(selects.robot, robots, state.robot, value => catalog.robots[value]);
    setOptions(selects.object, objects, state.object,
      value => onRobot.find(clip => clip.object === value).objectLabel, "All objects");
    setOptions(selects.condition, conditions, state.condition,
      value => catalog.conditions[value], "All conditions");
    selects.condition.disabled = conditions.length === 1;
    return forObject.filter(clip => state.condition === "all" || clip.condition === state.condition);
  }

  function render() {
    const clips = updateFilters();
    disposeMedia?.();
    const fragment = document.createDocumentFragment();
    for (const group of catalog.groups) {
      const groupClips = clips.filter(clip => clip.group === group.id);
      if (!groupClips.length) continue;
      const block = document.createElement("div");
      block.className = "gallery-group";
      const heading = document.createElement("h3");
      heading.textContent = group.title;
      block.append(heading);
      if (group.description) {
        const explanation = document.createElement("p");
        explanation.className = "gallery-context";
        explanation.textContent = group.description;
        block.append(explanation);
      }
      const grid = document.createElement("div");
      grid.className = "gallery-grid";
      grid.classList.toggle("gallery-grid--comparison", group.comparison);
      grid.classList.toggle("gallery-grid--real", state.domain === "real");
      grid.dataset.count = groupClips.length;
      for (const clip of groupClips) grid.append(makeClip(clip, catalog));
      block.append(grid);
      fragment.append(block);
    }
    results.replaceChildren(fragment);
    results.setAttribute("aria-busy", "false");
    count.textContent = `${clips.length} ${clips.length === 1 ? "recording" : "recordings"} · ${catalog.domains[state.domain]} · ${catalog.robots[state.robot]}`;
    disposeMedia = mountMedia(results);
  }

  fields.disabled = false;
  fields.addEventListener("change", event => {
    if (!(event.target instanceof HTMLSelectElement)) return;
    state[event.target.name] = event.target.value;
    render();
  });
  render();
}
