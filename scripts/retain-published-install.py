"""Keep the registry installation correction on the pre-design site."""
from pathlib import Path

page = Path(__file__).resolve().parents[1] / 'site/index.html'
source = page.read_text()
old = 'npm install -g github:realproject7/kira-wallet#codex/kira-release'
if old not in source:
    raise SystemExit('Expected the baseline site installation block. No changes made.')
source = source.replace(old, 'npm install -g kira-wallet')
source = source.replace('Install from the public source while the first npm release awaits publication.',
                        'Install the published npm package, then open local setup.')
source = source.replace('SOURCE INSTALL', 'NPM INSTALL')
page.write_text(source)
print('Published installation instructions retained.')
