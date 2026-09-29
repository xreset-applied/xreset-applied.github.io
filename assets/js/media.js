/* Files contain their complete playback window; the browser owns looping. */
const mounted = new Set();
const visibility = new IntersectionObserver((entries) => {
  for (const entry of entries) if (!entry.isIntersecting) entry.target.pause();
}, { threshold: 0 });
document.addEventListener('visibilitychange', () => {
  if (document.hidden) for (const video of mounted) video.pause();
});

export function mountMedia(root) {
  const videos = root instanceof HTMLVideoElement ? [root] : [...root.querySelectorAll('video')];
  const cleanup = [];
  for (const video of videos) {
    if (mounted.has(video)) continue;
    mounted.add(video);
    video.loop = true;
    visibility.observe(video);
    cleanup.push(() => {
      video.pause();
      visibility.unobserve(video);
      mounted.delete(video);
    });
  }
  return () => { for (const dispose of cleanup) dispose(); };
}
