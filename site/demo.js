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
const placeholder = 'Ask your agent about your wallets…';

function setText(node, value) {
  if (node && node.textContent !== value) node.textContent = value;
}
function show(node, visible) {
  if (node && node.hidden === visible) node.hidden = !visible;
}
function prepareLegacy(root) {
  const motion = root.querySelector('.demo-motion');
  const stream = root.querySelector('.motion-stream');
  const welcome = document.createElement('div');
  welcome.className = 'motion-welcome';
  const art = document.createElement('img');
  art.src = '/assets/kira-explain.png'; art.alt = ''; art.width = 140; art.height = 188;
  const title = document.createElement('p'); title.textContent = 'Let’s look at your wallets.';
  const detail = document.createElement('span'); detail.textContent = 'Your agent session. Kira’s wallet tools.';
  welcome.append(art, title, detail); stream.append(welcome);
  const steps = [...root.querySelectorAll('.demo-body .demo-panel')].map(source => {
    const node = source.cloneNode(true);
    node.removeAttribute('id'); node.removeAttribute('aria-label');
    for (const link of node.querySelectorAll('a')) {
      const label = document.createElement('span'); label.className = link.className;
      label.textContent = link.textContent.replace(/\s*↗\s*$/, ''); link.replaceWith(label);
    }
    const working = document.createElement('div'); working.className = 'motion-working';
    const image = document.createElement('img'); image.src = '/assets/kira-research.png';
    image.alt = ''; image.width = 72; image.height = 108;
    const text = document.createElement('p'); text.textContent = source.dataset.working;
    working.append(image, text);
    const answer = node.querySelector('.demo-answer'); answer.before(working);
    const summary = node.querySelector('.demo-summary');
    const note = summary.querySelector('small'); summary.append(note); note.classList.add('motion-summary-note');
    stream.append(node);
    return {node, question: node.querySelector('.demo-question'), heading: node.querySelector('.demo-answer-heading'),
      answer, fullAnswer: answer.textContent, fullQuestion: node.querySelector('.demo-question').textContent,
      results: node.querySelector('.token-results'), rows: [...node.querySelectorAll('.token-results > article')], summary, working};
  });
  show(motion, true); show(root.querySelector('.legacy-fallback-composer'), false);
  return {steps, welcome, motion, draft: root.querySelector('.motion-draft'), scroll: root.querySelector('.motion-scroll')};
}
const motionStates = [...document.querySelectorAll('[data-motion]')].map(root => {
  const legacy = root.dataset.motion === 'legacy';
  const prepared = legacy ? prepareLegacy(root) : {};
  const steps = legacy ? prepared.steps : [...root.querySelectorAll('.sim-step')].map(node => ({
    node,
    fields: [...node.querySelectorAll('[data-type]')].map(field => ({node: field, full: field.textContent, answer: field.dataset.type === 'answer'})),
    reveals: [...node.querySelectorAll('[data-reveal]')].map(field => ({node: field, at: Number(field.dataset.reveal)}))
  }));
  const duration = Number(root.dataset.duration);
  const details = root.querySelector('.motion-transcript');
  if (legacy) details.open = false;
  return {root, legacy, ...prepared, steps, duration, cycle: duration * steps.length,
    elapsed: reducedMotion.matches ? duration * steps.length - .05 : 0,
    paused: reducedMotion.matches, visible: true, reading: false, seeked: reducedMotion.matches,
    scroll: prepared.scroll || root.querySelector('.host-agent-scroll'), details,
    toggle: root.querySelector('.motion-toggle'), chapters: [...root.querySelectorAll('[data-seek]')],
    appViews: [...root.querySelectorAll('[data-app-view]')], appTabs: [...root.querySelectorAll('[data-app-tab]')],
    appScroll: root.querySelector('.app-native-content'), breadcrumb: root.querySelector('[data-app-breadcrumb]'), current: -1, lastCycle: -1};
});
function isRunning(state) {
  return !state.paused && !state.reading && state.visible && !document.hidden && !reducedMotion.matches;
}
function followBottom(node, dt) {
  const target = Math.max(0, node.scrollHeight - node.clientHeight);
  const distance = target - node.scrollTop;
  node.scrollTop = dt > 0 ? node.scrollTop + distance * (1 - Math.exp(-dt / 120)) : target;
}
function renderLegacy(state, index, local) {
  show(state.welcome, index === 0 && local < 2.6);
  state.steps.forEach((item, i) => {
    const phase = i < index ? state.duration : i === index ? local : -1;
    show(item.node, phase >= 2.6); show(item.heading, phase >= 2.6);
    show(item.working, phase >= 2.6 && phase < 4.8); show(item.answer, phase >= 4.8);
    setText(item.answer, item.fullAnswer.slice(0, Math.ceil(Math.min(1, Math.max(0, (phase - 4.8) / .7)) * item.fullAnswer.length)));
    show(item.results, phase >= 5.6);
    item.rows.forEach((row, i) => show(row, phase >= 5.6 + i * 2)); show(item.summary, phase >= 12);
  });
  const question = state.steps[index].fullQuestion;
  setText(state.draft, local < 2.6 ? question.slice(0, Math.max(1, Math.round(Math.min(1, local / 2.3) * question.length))) : placeholder);
  state.draft.scrollTop = state.draft.scrollHeight;
}
function renderConversation(state, index, local) {
  // Keep completed turns in the stream. Only the active turn types; each follow-up
  // retains the earlier questions and answers until the complete story loops.
  state.steps.forEach((item, i) => {
    show(item.node, i <= index);
    const phase = i < index ? state.duration : i === index ? local : -1;
    for (const field of item.fields) {
      const start = field.answer ? 3.4 : 0;
      const length = field.answer ? 2.4 : 1.65;
      const progress = Math.max(0, Math.min(1, (phase - start) / length));
      setText(field.node, field.full.slice(0, Math.ceil(progress * field.full.length)));
    }
    for (const field of item.reveals) show(field.node, phase >= field.at);
  });
  const view = state.steps[index].node.dataset.app;
  for (const node of state.appViews) show(node, node.dataset.appView === view);
  for (const node of state.appTabs) node.classList.toggle('is-selected', node.dataset.appTab === 'overview');
  setText(state.breadcrumb, ` / ${view === 'base' ? 'Base' : view === 'signet' ? 'Base / SIGNET' : view === 'blast' ? 'Blast' : 'Blast / ETH'}`);
  if (state.current !== index) state.appScroll.scrollTop = 0;
}
function renderMotion(state, dt = 0) {
  const time = state.elapsed % state.cycle;
  const index = Math.floor(time / state.duration);
  const local = time - index * state.duration;
  const cycle = Math.floor(state.elapsed / state.cycle);
  state.root.dataset.step = String(index + 1); state.root.dataset.time = time.toFixed(2);
  state.root.dataset.phase = local < 1.8 ? 'question' : local < 3.4 ? 'working' : 'answer';
  state.root.dataset.running = String(isRunning(state));
  if (cycle !== state.lastCycle) { state.scroll.scrollTop = 0; state.lastCycle = cycle; }
  if (state.legacy) renderLegacy(state, index, local); else renderConversation(state, index, local);
  for (const button of state.chapters) button.setAttribute('aria-current', Number(button.dataset.seek) === index ? 'step' : 'false');
  const name = state.legacy ? 'agent' : 'workspace';
  state.toggle.disabled = reducedMotion.matches;
  setText(state.toggle, reducedMotion.matches ? 'Static' : state.paused ? 'Play ▷' : 'Pause Ⅱ');
  state.toggle.setAttribute('aria-label', reducedMotion.matches ? `${name} simulation uses reduced motion; choose a chapter` : `${state.paused ? 'Play' : 'Pause'} ${name} simulation`);
  if (state.appScroll) {
    const target = local > 11 ? Math.max(0, state.appScroll.scrollHeight - state.appScroll.clientHeight) : 0;
    state.appScroll.scrollTop = dt > 0 ? state.appScroll.scrollTop + (target - state.appScroll.scrollTop) * (1 - Math.exp(-dt / 350)) : target;
  }
  followBottom(state.scroll, dt); state.current = index;
}
// A single bounded clock drives both native text simulations. Visibility,
// transcripts, manual pause and reduced motion stop periodic DOM updates.
let frameRequest = null, previousTime = 0, previousPaint = 0;
function tick(now) {
  frameRequest = null;
  const dt = Math.min(100, Math.max(0, now - previousTime)); previousTime = now;
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
  if (running && frameRequest === null) { previousTime = performance.now(); previousPaint = previousTime - 50; frameRequest = requestAnimationFrame(tick); }
  else if (!running && frameRequest !== null) { cancelAnimationFrame(frameRequest); frameRequest = null; }
}
for (const state of motionStates) {
  show(state.root.querySelector('.motion-controls'), true);
  state.toggle.addEventListener('click', () => {
    if (reducedMotion.matches) return;
    state.paused = !state.paused;
    if (!state.paused && state.seeked) { state.elapsed = Math.floor((state.elapsed % state.cycle) / state.duration) * state.duration; state.seeked = false; }
    renderMotion(state); syncPlayback();
  });
  for (const button of state.chapters) button.addEventListener('click', () => {
    state.elapsed = Number(button.dataset.seek) * state.duration + state.duration - .05;
    state.paused = true; state.seeked = true; renderMotion(state); syncPlayback();
  });
  state.details.addEventListener('toggle', () => { state.reading = state.details.open; syncPlayback(); });
  renderMotion(state);
}
if ('IntersectionObserver' in window) {
  const observer = new IntersectionObserver(entries => {
    for (const entry of entries) { const state = motionStates.find(item => item.root === entry.target); if (state) state.visible = entry.isIntersecting; }
    syncPlayback();
  }, {threshold: .05});
  for (const state of motionStates) observer.observe(state.root);
}
document.addEventListener('visibilitychange', syncPlayback);
reducedMotion.addEventListener('change', () => {
  for (const state of motionStates) { state.paused = reducedMotion.matches; if (reducedMotion.matches) { state.elapsed = state.cycle - .05; state.seeked = true; } renderMotion(state); }
  syncPlayback();
});
syncPlayback();
