import { mountMedia } from './media.js';
import { initExplainers } from './native-explainer.js';
import { initGallery } from './gallery.js';

initExplainers();
mountMedia(document);
initGallery();

const goals = document.querySelector('#show-goals');
goals.addEventListener('change', () => {
  for (const guide of document.querySelectorAll('.goal-guide')) guide.toggleAttribute('hidden', !goals.checked);
});

const grid = document.querySelector('#sim-grid');
const still = grid.querySelector('source');
const toggle = document.querySelector('#sim-grid-toggle');
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
let animateGrid = !reduced.matches;
let gridVisible = false;
function paintGridMode() {
  still.media = animateGrid && gridVisible && !document.hidden ? 'not all' : 'all';
  toggle.textContent = animateGrid ? 'Show still' : 'Play animation';
}
toggle.hidden = false;
toggle.addEventListener('click', () => {
  animateGrid = !animateGrid;
  paintGridMode();
});
reduced.addEventListener('change', () => {
  animateGrid = !reduced.matches;
  paintGridMode();
});
new IntersectionObserver(([entry]) => {
  gridVisible = entry.isIntersecting;
  paintGridMode();
}).observe(grid);
document.addEventListener('visibilitychange', paintGridMode);
paintGridMode();
