function initTabGroup(group) {
  const tablist = group.querySelector('[data-explainer-tabs]');
  const tabs = Array.from(tablist.querySelectorAll('[role="tab"]'));
  const panels = tabs.map((tab) => document.getElementById(tab.getAttribute('aria-controls')));
  const media = panels.map((panel) => Array.from(panel.querySelectorAll('video')));

  function selectTab(index, focus = false) {
    tabs.forEach((tab, tabIndex) => {
      const selected = tabIndex === index;
      tab.setAttribute('aria-selected', String(selected));
      tab.tabIndex = selected ? 0 : -1;
      panels[tabIndex].hidden = !selected;
      if (!selected) media[tabIndex].forEach((video) => video.pause());
    });
    if (focus) tabs[index].focus();
  }

  tablist.addEventListener('click', (event) => {
    const index = tabs.indexOf(event.target.closest('[role="tab"]'));
    if (index !== -1) selectTab(index);
  });

  tablist.addEventListener('keydown', (event) => {
    const index = tabs.indexOf(event.target.closest('[role="tab"]'));
    if (index === -1) return;
    let next;
    if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
    else if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = tabs.length - 1;
    else return;
    event.preventDefault();
    selectTab(next, true);
  });
}

export function initExplainers() {
  document.querySelectorAll('[data-explainer]').forEach(initTabGroup);
}
