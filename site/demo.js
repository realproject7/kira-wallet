"use strict";

// Authored examples only. The page never calls a wallet/provider or agent host.
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
    try {
      await navigator.clipboard.writeText(source.textContent);
      copy.textContent = 'Copied';
      status.textContent = source.id === 'install-prompt'
        ? 'Installation prompt copied. Paste it into your agent.'
        : 'Installation commands copied.';
    } catch {
      const range = document.createRange();
      range.selectNodeContents(source);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      status.textContent = source.id === 'install-prompt'
        ? 'Prompt selected. Copy it to continue.' : 'Commands selected. Copy them to continue.';
    }
  });
}

const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
const motionStates = [...document.querySelectorAll('[data-motion]')].map(root => {
  const steps = [...root.querySelectorAll('.sim-step')].map(node => ({
    node,
    fields: [...node.querySelectorAll('[data-type]')].map(field => ({
      node: field, full: field.textContent, answer: field.dataset.type === 'answer'
    })),
    reveals: [...node.querySelectorAll('[data-reveal]')].map(field => ({node: field, at: Number(field.dataset.reveal)}))
  }));
  const duration = Number(root.dataset.duration);
  return {
    root, steps, duration, cycle: duration * steps.length,
    elapsed: reducedMotion.matches ? duration * steps.length - .05 : 0,
    paused: reducedMotion.matches, visible: true, reading: false, seeked: false,
    scroll: root.querySelector('.sim-chat-viewport, .host-agent-scroll'),
    details: root.querySelector('.motion-transcript'),
    toggle: root.querySelector('.motion-toggle'),
    chapters: [...root.querySelectorAll('[data-seek]')],
    appViews: [...root.querySelectorAll('[data-app-view]')],
    appTabs: [...root.querySelectorAll('[data-app-tab]')],
    appScroll: root.querySelector('.app-native-content'), app: root.querySelector('.native-app'), loading: root.querySelector('.browser-loading'),
    breadcrumb: root.querySelector('[data-app-breadcrumb]'), current: -1
  };
});

function setText(node, value) {
  if (node.textContent !== value) node.textContent = value;
}
function show(node, visible) {
  if (node && node.hidden === visible) node.hidden = !visible;
}
function isRunning(state) {
  return !state.paused && !state.reading && state.visible && !document.hidden && !reducedMotion.matches;
}
function renderMotion(state, dt = 0) {
  const time = state.elapsed % state.cycle;
  const index = Math.floor(time / state.duration);
  const local = time - index * state.duration;
  const step = state.steps[index];
  const staticFrame = state.paused || reducedMotion.matches;
  state.root.dataset.step = String(index + 1);
  state.root.dataset.time = time.toFixed(2);
  state.root.dataset.phase = local < 1.8 ? 'question' : local < 3.4 ? 'working' : 'answer';
  state.root.dataset.running = String(isRunning(state));
  for (const item of state.steps) show(item.node, item === step);
  for (const field of step.fields) {
    const start = field.answer ? 3.4 : 0;
    const length = field.answer ? 1.1 : 1.65;
    const progress = Math.max(0, Math.min(1, (local - start) / length));
    const characters = staticFrame && state.seeked ? field.full.length : Math.ceil(progress * field.full.length);
    setText(field.node, field.full.slice(0, characters));
  }
  for (const item of step.reveals) show(item.node, local >= item.at);
  const chapter = state.root.dataset.motion === 'hero' ? Math.min(index, 2) : index;
  for (const button of state.chapters) button.setAttribute('aria-current', Number(button.dataset.seek) === chapter ? 'step' : 'false');
  const name = state.root.dataset.motion === 'hero' ? 'agent' : 'workspace';
  state.toggle.disabled = reducedMotion.matches;
  setText(state.toggle, reducedMotion.matches ? 'Static' : state.paused ? 'Play ▷' : 'Pause Ⅱ');
  state.toggle.setAttribute('aria-label', reducedMotion.matches
    ? `${name} simulation uses reduced motion; choose a chapter`
    : `${state.paused ? 'Play' : 'Pause'} ${name} simulation`);
  if (state.app) {
    const loading = index === 0 && local < 3.4;
    show(state.loading, loading);
    show(state.app, !loading);
    const view = step.node.dataset.app;
    for (const node of state.appViews) show(node, node.dataset.appView === view);
    for (const node of state.appTabs) node.classList.toggle('is-selected', node.dataset.appTab === view || view === 'token' && node.dataset.appTab === 'tokens');
    setText(state.breadcrumb, ` / ${view === 'home' ? 'Overview' : view === 'tokens' ? 'All tokens' : view === 'token' ? 'Base / USDC' : 'Activity'}`);
  }
  if (index !== state.current) {
    state.scroll.scrollTop = 0;
    if (state.appScroll) state.appScroll.scrollTop = 0;
    state.current = index;
  }
  if (state.appScroll) {
    const bottom = Math.max(0, state.appScroll.scrollHeight - state.appScroll.clientHeight);
    const appTarget = local > 7 ? bottom : 0;
    const distance = appTarget - state.appScroll.scrollTop;
    state.appScroll.scrollTop = dt > 0 ? state.appScroll.scrollTop + distance * (1 - Math.exp(-dt / 180)) : appTarget;
  }
  const target = Math.max(0, state.scroll.scrollHeight - state.scroll.clientHeight);
  const delta = target - state.scroll.scrollTop;
  state.scroll.scrollTop = dt > 0 ? state.scroll.scrollTop + delta * (1 - Math.exp(-dt / 120)) : target;
}

// One clock serves both examples. No work runs offscreen, in hidden tabs, while
// reading a transcript, on user pause, or with reduced motion enabled.
let frameRequest = null;
let previousTime = 0;
let previousPaint = 0;
function tick(now) {
  frameRequest = null;
  const dt = Math.min(100, Math.max(0, now - previousTime));
  previousTime = now;
  for (const state of motionStates) if (isRunning(state)) state.elapsed += dt / 1000;
  const sincePaint = now - previousPaint;
  if (sincePaint >= 50) {
    for (const state of motionStates) if (isRunning(state)) renderMotion(state, sincePaint);
    previousPaint = now;
  }
  if (motionStates.some(isRunning)) frameRequest = requestAnimationFrame(tick);
}
function syncPlayback() {
  for (const state of motionStates) state.root.dataset.running = String(isRunning(state));
  const running = motionStates.some(isRunning);
  if (running && frameRequest === null) {
    previousTime = performance.now();
    previousPaint = previousTime - 50;
    frameRequest = requestAnimationFrame(tick);
  } else if (!running && frameRequest !== null) {
    cancelAnimationFrame(frameRequest);
    frameRequest = null;
  }
}
for (const state of motionStates) {
  state.root.querySelector('.motion-controls').hidden = false;
  state.toggle.addEventListener('click', () => {
    if (reducedMotion.matches) return;
    state.paused = !state.paused;
    if (!state.paused && state.seeked) {
      state.elapsed = Math.floor((state.elapsed % state.cycle) / state.duration) * state.duration;
      state.seeked = false;
    }
    renderMotion(state);
    syncPlayback();
  });
  for (const button of state.chapters) button.addEventListener('click', () => {
    state.elapsed = Number(button.dataset.seek) * state.duration + state.duration - .05;
    state.paused = true;
    state.seeked = true;
    renderMotion(state);
    syncPlayback();
  });
  state.details.addEventListener('toggle', () => {
    state.reading = state.details.open;
    syncPlayback();
  });
  renderMotion(state);
}
if ('IntersectionObserver' in window) {
  const observer = new IntersectionObserver(entries => {
    for (const entry of entries) {
      const state = motionStates.find(item => item.root === entry.target);
      if (state) state.visible = entry.isIntersecting;
    }
    syncPlayback();
  }, {threshold: .05});
  for (const state of motionStates) observer.observe(state.root);
}
document.addEventListener('visibilitychange', syncPlayback);
reducedMotion.addEventListener('change', () => {
  for (const state of motionStates) {
    state.paused = reducedMotion.matches;
    if (reducedMotion.matches) {
      state.elapsed = state.cycle - .05;
      state.seeked = true;
    }
    renderMotion(state);
  }
  syncPlayback();
});
syncPlayback();
