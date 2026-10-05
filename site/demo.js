"use strict";

const demo = document.getElementById('demo');
const motion = document.getElementById('demo-motion');
const reading = demo.querySelector('.demo-body');
const fallbackComposer = demo.querySelector(':scope > .demo-composer');
const viewport = motion.querySelector('.motion-scroll');
const stream = motion.querySelector('.motion-stream');
const draft = motion.querySelector('.motion-draft');
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
const placeholder = 'Ask Kira about your wallets…';
const caseSeconds = 16;
let visible = true;
let elapsed = 0;
let previousTime = 0;
let frameRequest = null;
let lastCycle = -1;

const welcome = document.createElement('div');
welcome.className = 'motion-welcome';
const welcomeArt = document.createElement('img');
welcomeArt.src = '/assets/kira-explain.png';
welcomeArt.alt = '';
welcomeArt.width = 140;
welcomeArt.height = 188;
const welcomeTitle = document.createElement('p');
welcomeTitle.textContent = 'Let’s look at your wallets.';
const welcomeDetail = document.createElement('span');
welcomeDetail.textContent = 'Your questions. Your AI.';
welcome.append(welcomeArt, welcomeTitle, welcomeDetail);
stream.append(welcome);

// Reuse the accessible transcript as the content source. The animated copy
// has no focus targets and no live announcements, so it cannot interrupt reading.
const cases = [...reading.querySelectorAll('.demo-panel')].map(source => {
  const panel = source.cloneNode(true);
  panel.removeAttribute('id');
  panel.removeAttribute('aria-label');
  for (const link of panel.querySelectorAll('a')) {
    const label = document.createElement('span');
    label.className = link.className;
    label.textContent = link.textContent.replace(/\s*↗\s*$/, '');
    link.replaceWith(label);
  }
  const question = panel.querySelector('.demo-question');
  const heading = panel.querySelector('.demo-answer-heading');
  const answer = panel.querySelector('.demo-answer');
  const results = panel.querySelector('.token-results');
  const rows = [...results.querySelectorAll(':scope > article')];
  const summary = results.querySelector('.demo-summary');
  const note = summary.querySelector('small');
  summary.append(note);
  note.classList.add('motion-summary-note');
  const working = document.createElement('div');
  working.className = 'motion-working';
  const art = document.createElement('img');
  art.src = '/assets/kira-research.png';
  art.alt = '';
  art.width = 72;
  art.height = 108;
  const message = document.createElement('div');
  const text = document.createElement('p');
  text.textContent = source.dataset.working;
  const dots = document.createElement('div');
  dots.className = 'motion-dots';
  dots.append(...Array.from({length: 3}, () => document.createElement('span')));
  message.append(text, dots);
  working.append(art, message);
  answer.before(working);
  stream.append(panel);
  return {panel, question, heading, answer, results, rows, summary, working,
    fullQuestion: question.textContent, fullAnswer: answer.textContent};
});
const cycleSeconds = cases.length * caseSeconds;

function setText(node, text) {
  if (node.textContent !== text) node.textContent = text;
}

function show(node, shown) {
  const hidden = !shown;
  if (node.hidden !== hidden) node.hidden = hidden;
}

function render(seconds, dt) {
  const cycle = Math.floor(seconds / cycleSeconds);
  const time = seconds % cycleSeconds;
  const active = Math.min(cases.length - 1, Math.floor(time / caseSeconds));
  const local = time - active * caseSeconds;
  if (cycle !== lastCycle) {
    viewport.scrollTop = 0;
    lastCycle = cycle;
  }
  show(welcome, active === 0 && local < 2.6);
  cases.forEach((item, index) => {
    const phase = index < active ? caseSeconds : index === active ? local : -1;
    show(item.panel, phase >= 2.6);
    show(item.heading, phase >= 2.6);
    show(item.working, phase >= 2.6 && phase < 4.8);
    show(item.answer, phase >= 4.8);
    const characters = Math.round(Math.min(1, Math.max(0, (phase - 4.8) / .7)) * item.fullAnswer.length);
    setText(item.answer, item.fullAnswer.slice(0, characters));
    show(item.results, phase >= 5.6);
    item.rows.forEach((row, rowIndex) => show(row, phase >= 5.6 + rowIndex * 2));
    show(item.summary, phase >= 12);
  });
  const typing = local < 2.6;
  const question = cases[active].fullQuestion;
  setText(draft, typing ? question.slice(0, Math.max(1, Math.round(Math.min(1, local / 2.3) * question.length))) : placeholder);
  draft.scrollTop = draft.scrollHeight;
  motion.dataset.phase = typing ? 'typing' : local < 4.8 ? 'researching' : 'answer';
  motion.dataset.case = String(active + 1);
  motion.dataset.time = time.toFixed(1);
  const opacity = Math.min(1, Math.max(0, (cycleSeconds - time) / .6));
  stream.style.opacity = String(opacity);
  const target = Math.max(0, viewport.scrollHeight - viewport.clientHeight);
  const distance = target - viewport.scrollTop;
  viewport.scrollTop = Math.abs(distance) < .75 ? target : viewport.scrollTop + distance * (1 - Math.exp(-dt / 120));
}

function tick(now) {
  frameRequest = null;
  const dt = Math.min(100, Math.max(0, now - previousTime));
  previousTime = now;
  elapsed += dt;
  render(elapsed / 1000, dt);
  frameRequest = requestAnimationFrame(tick);
}

function syncPlayback() {
  const running = !motion.hidden && visible && !document.hidden;
  motion.dataset.running = String(running);
  if (running && frameRequest === null) {
    previousTime = performance.now();
    frameRequest = requestAnimationFrame(tick);
  } else if (!running && frameRequest !== null) {
    cancelAnimationFrame(frameRequest);
    frameRequest = null;
  }
}

function syncMode() {
  const animated = !reducedMotion.matches && !reading.contains(document.activeElement);
  motion.hidden = !animated;
  reading.classList.toggle('sr-only', animated);
  reading.tabIndex = animated ? -1 : 0;
  fallbackComposer.hidden = animated;
  for (const link of reading.querySelectorAll('a')) {
    if (animated) link.setAttribute('tabindex', '-1');
    else link.removeAttribute('tabindex');
  }
  syncPlayback();
}

render(0, 0);
syncMode();
document.addEventListener('visibilitychange', syncPlayback);
if ('IntersectionObserver' in window) {
  new IntersectionObserver(entries => {
    visible = entries[0].isIntersecting;
    syncPlayback();
  }, {threshold: .05}).observe(demo);
}
reducedMotion.addEventListener('change', syncMode);
reading.addEventListener('focusin', syncMode);
reading.addEventListener('focusout', event => {
  if (!reading.contains(event.relatedTarget)) queueMicrotask(syncMode);
});

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
