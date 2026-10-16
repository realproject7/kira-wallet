"""Preview public showcase HTML with production headers and optional QA clocks."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'site'
HEADERS = json.loads((SITE / 'vercel.json').read_text())['headers'][0]['headers']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8807)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--frame', type=float, help='Freeze a QA preview at 0–47 seconds.')
    modes.add_argument('--reduced-motion', action='store_true')
    modes.add_argument('--no-js', action='store_true')
    args = parser.parse_args()
    if args.frame is not None and not 0 <= args.frame <= 47:
        parser.error('--frame must be between 0 and 47 seconds')
    override = ''
    if args.frame is not None:
        override = '''
let queued = null;
window.requestAnimationFrame = callback => { queued = callback; return 1; };
window.cancelAnimationFrame = () => { queued = null; };
document.addEventListener('DOMContentLoaded', () => {
  let now = performance.now();
  for (let i = 0; i < FRAME_COUNT; i++) {
    const callback = queued;
    if (!callback) break;
    queued = null;
    now += 1000 / 60;
    callback(now);
  }
});
'''.replace('FRAME_COUNT', str(round(args.frame * 60)))
    elif args.reduced_motion:
        override = '''
const originalMatchMedia = window.matchMedia.bind(window);
window.matchMedia = query => query === '(prefers-reduced-motion: reduce)'
  ? {matches: true, addEventListener() {}} : originalMatchMedia(query);
'''

    class Handler(SimpleHTTPRequestHandler):
        def end_headers(self):
            for header in HEADERS:
                self.send_header(header['key'], header['value'])
            self.send_header('Cache-Control', 'no-store')
            super().end_headers()

        def respond(self, data, content_type):
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = self.path.split('?', 1)[0]
            if path == '/__preview-clock.js':
                self.respond(override.encode(), 'text/javascript; charset=utf-8')
            elif path in ('/', '/index.html'):
                page = (SITE / 'index.html').read_text()
                if args.no_js:
                    page = re.sub(r'\s*<script[^>]*src="/demo.js[^>]*></script>', '', page)
                elif override:
                    page = page.replace('<head>', '<head>\n<script src="/__preview-clock.js"></script>')
                self.respond(page.encode(), 'text/html; charset=utf-8')
            else:
                super().do_GET()

        def log_message(self, *_):
            pass

    print(f'Public showcase QA: http://127.0.0.1:{args.port}/', flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), partial(Handler, directory=str(SITE))).serve_forever()


if __name__ == '__main__':
    main()
