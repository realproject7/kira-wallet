"use strict";

// Static examples combine Kira's wallet tools with tools supplied by the host.
// No provider calls, chat runtime, autoplay loop or analytics run on this page.
const tabs = [...document.querySelectorAll('[role="tab"]')];
function selectScenario(tab, focus = false) {
  for (const item of tabs) {
    const selected = item === tab;
    item.setAttribute('aria-selected', String(selected));
    item.tabIndex = selected ? 0 : -1;
    document.getElementById(item.getAttribute('aria-controls')).hidden = !selected;
  }
  if (focus) tab.focus();
}
if (tabs.length) selectScenario(tabs[0]);
for (const tab of tabs) {
  tab.addEventListener('click', () => selectScenario(tab));
  tab.addEventListener('keydown', event => {
    let index = tabs.indexOf(tab);
    if (event.key === 'ArrowRight') index = (index + 1) % tabs.length;
    else if (event.key === 'ArrowLeft') index = (index + tabs.length - 1) % tabs.length;
    else if (event.key === 'Home') index = 0;
    else if (event.key === 'End') index = tabs.length - 1;
    else return;
    event.preventDefault();
    selectScenario(tabs[index], true);
  });
}

for (const copy of document.querySelectorAll('[data-copy]')) {
  copy.addEventListener('click', async () => {
    const source = document.getElementById(copy.dataset.copy);
    const status = document.getElementById('copy-status');
    const isPrompt = source.id === 'install-prompt';
    try {
      await navigator.clipboard.writeText(source.textContent);
      copy.textContent = 'Copied';
      status.textContent = isPrompt ? 'Installation prompt copied. Paste it into your agent.' : 'Installation commands copied.';
    } catch {
      const range = document.createRange();
      range.selectNodeContents(source);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      status.textContent = isPrompt ? 'Prompt selected. Copy it to continue.' : 'Commands selected. Copy them to continue.';
    }
  });
}
