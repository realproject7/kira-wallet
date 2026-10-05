"use strict";

const demo = document.getElementById('demo');
const film = document.getElementById('demo-film');
const reading = demo.querySelector('.demo-body');
const composer = demo.querySelector('.demo-composer');
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
const mobile = window.matchMedia('(max-width: 700px)');
const compact = window.matchMedia('(max-width: 420px)');
let visible = true;
let ready = false;
let failed = false;
let revision = 0;
let pendingSeek = 0;

function readingHasFocus() {
  return document.activeElement === demo || reading.contains(document.activeElement);
}

function showFilm(show) {
  // A recovered source must not hide the transcript beneath a focused link.
  show = show && !readingHasFocus();
  film.hidden = !show;
  reading.classList.toggle('sr-only', show);
  reading.tabIndex = show ? -1 : 0;
  composer.hidden = show;
  for (const link of reading.querySelectorAll('a')) {
    if (show) link.setAttribute('tabindex', '-1');
    else link.removeAttribute('tabindex');
  }
}

function updatePlayback() {
  if (!ready || failed || reducedMotion.matches || !visible || document.hidden || readingHasFocus()) {
    film.pause();
    return;
  }
  const currentRevision = revision;
  film.play().catch(error => {
    // Source switches abort prior play requests without indicating a failure.
    if (currentRevision === revision && error.name !== 'AbortError') {
      failed = true;
      showFilm(false);
    }
  });
}

function configureFilm() {
  if (ready && Number.isFinite(film.currentTime)) pendingSeek = film.currentTime;
  revision += 1;
  film.pause();
  ready = false;
  failed = false;
  if (reducedMotion.matches) {
    film.removeAttribute('src');
    film.load();
    showFilm(false);
    return;
  }
  const profile = !mobile.matches ? 'Desktop' : compact.matches ? 'Compact' : 'Mobile';
  film.poster = film.dataset['poster' + profile];
  film.src = film.dataset[profile.toLowerCase()];
  film.load();
}

film.addEventListener('loadedmetadata', () => {
  ready = true;
  film.currentTime = Math.min(pendingSeek, Math.max(0, film.duration - .1));
});
film.addEventListener('canplay', () => {
  if (!failed && !reducedMotion.matches) showFilm(true);
  updatePlayback();
});
film.addEventListener('error', () => {
  failed = true;
  showFilm(false);
});
demo.addEventListener('focusin', () => {
  if (readingHasFocus()) showFilm(false);
  updatePlayback();
});
demo.addEventListener('focusout', event => {
  if (!demo.contains(event.relatedTarget)) {
    if (ready && !failed && !reducedMotion.matches) showFilm(true);
    updatePlayback();
  }
});
document.addEventListener('visibilitychange', updatePlayback);
if ('IntersectionObserver' in window) {
  new IntersectionObserver(entries => {
    visible = entries[0].isIntersecting;
    updatePlayback();
  }, {threshold: .05}).observe(demo);
}
reducedMotion.addEventListener('change', configureFilm);
mobile.addEventListener('change', configureFilm);
compact.addEventListener('change', configureFilm);
configureFilm();

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
