"use strict";

// Deliberate, keyboard-accessible examples. No autoplay or pause controls.
const tabs = Array.from(document.querySelectorAll('.demo-tabs [role="tab"]'));
const panels = Array.from(document.querySelectorAll('.demo-panel'));
function selectTab(tab, focus = false) {
  for (const item of tabs) {
    const selected = item === tab;
    item.setAttribute('aria-selected', String(selected));
    item.tabIndex = selected ? 0 : -1;
  }
  for (const panel of panels) panel.hidden = panel.id !== tab.getAttribute('aria-controls');
  if (focus) tab.focus();
}
for (const tab of tabs) {
  tab.addEventListener('click', () => selectTab(tab));
  tab.addEventListener('keydown', event => {
    const index = tabs.indexOf(tab);
    let next;
    if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
    if (event.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length;
    if (event.key === 'Home') next = 0;
    if (event.key === 'End') next = tabs.length - 1;
    if (next !== undefined) {
      event.preventDefault();
      selectTab(tabs[next], true);
    }
  });
}

const copy = document.getElementById('copy-install');
copy.addEventListener('click', async () => {
  const command = document.getElementById('install-command');
  const status = document.getElementById('copy-status');
  try {
    await navigator.clipboard.writeText(command.textContent);
    copy.textContent = 'Copied';
    status.textContent = 'Installation commands copied.';
  } catch {
    const range = document.createRange();
    range.selectNodeContents(command);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    status.textContent = 'Commands selected. Copy them to continue.';
  }
});
