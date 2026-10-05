"""Render the responsive public chat film from synthetic examples only."""
from functools import lru_cache
from pathlib import Path
import json
import math
import subprocess
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'site' / 'assets'
FPS, SCALE, SECONDS = 24, 2, 16
FONT = '/System/Library/Fonts/SFNS.ttf'
INK, MUTED, PLUM = '#302735', '#716078', '#735183'
BACKGROUND, CARD, LINE = '#fdfbff', '#f5f0f8', '#e8dff0'
CASES = [
    {
        'id': 'tokens', 'label': 'Find value',
        'question': 'What are my overlooked tokens worth? Show balances, prices and markets.',
        'working': 'Reading your holdings and recorded markets…',
        'answer': 'Start with these three. CASHCAT has a market to review; SIGNET still needs a price.',
        'summary': 'Recorded spot value', 'total': '$233.00', 'note': '+ 1 unpriced token',
        'tokens': [
            {'symbol': 'CASHCAT', 'icon': 'cashcat', 'chain': 'Robinhood · Daily wallet', 'quantity': '1,200 CASHCAT', 'price': '$0.1800 each', 'value': '$216.00', 'market': 'Uniswap v4 · CASHCAT / USDG'},
            {'symbol': 'APE', 'icon': 'ape', 'chain': 'Ethereum · Daily wallet', 'quantity': '20 APE', 'price': '$0.8500 each', 'value': '$17.00', 'market': 'Uniswap v3 · APE / WETH'},
            {'symbol': 'SIGNET', 'icon': 'signet', 'chain': 'Base · Trading wallet', 'quantity': '650 SIGNET', 'price': 'Price unavailable', 'value': 'Unpriced', 'market': 'No funded market recorded'},
        ],
    },
    {
        'id': 'blast', 'label': 'Review Blast',
        'question': 'Review my Blast wallets. What do I hold, and where can these tokens trade?',
        'working': 'Grouping your Blast wallets and token records…',
        'answer': 'Your Blast holdings, together. Keep some ETH for fees before moving funds.',
        'summary': 'Recorded spot value', 'total': '$400.66', 'note': 'across 2 wallets',
        'tokens': [
            {'symbol': 'ETH', 'icon': 'eth', 'chain': 'Blast · Daily wallet', 'quantity': '0.050 ETH', 'price': '$2,700.00 each', 'value': '$135.00', 'market': 'Native gas asset'},
            {'symbol': 'USDB', 'icon': 'usdb', 'chain': 'Blast · Daily wallet', 'quantity': '250 USDB', 'price': '$1.0000 each', 'value': '$250.00', 'market': 'Thruster v3 · USDB / WETH'},
            {'symbol': 'BLAST', 'icon': 'blast', 'chain': 'Blast · Trading wallet', 'quantity': '100,000 BLAST', 'price': '$0.0001566 each', 'value': '$15.66', 'market': 'Thruster v3 · BLAST / WETH'},
        ],
    },
    {
        'id': 'compare', 'label': 'See changes',
        'question': 'What changed since the last time you checked my wallet?',
        'working': 'Comparing your saved balances and prices…',
        'answer': 'Your balances stayed the same. Prices moved, and a few coverage gaps were filled.',
        'summary': 'Change in priced value', 'total': '+$14.50', 'note': 'balances unchanged',
        'tokens': [
            {'symbol': 'CASHCAT', 'icon': 'cashcat', 'chain': '1,200 CASHCAT · unchanged', 'quantity': 'Price', 'previous_price': '$0.1800', 'price': '$0.1900', 'value': '+$12.00', 'market': 'Robinhood · recorded spot value'},
            {'symbol': 'ETH', 'icon': 'eth', 'chain': '0.050 ETH · unchanged', 'quantity': 'Price', 'previous_price': '$2,700', 'price': '$2,750', 'value': '+$2.50', 'market': 'Blast · recorded spot value'},
            {'coverage': True, 'symbol': 'Two balances verified as zero', 'detail': 'Previously unknown. Now observed on-chain.'},
        ],
    },
]
PROFILES = {
    'desktop': {'width': 520, 'height': 570, 'body': 14, 'detail': 13, 'card': 128, 'composer': 100},
    'mobile': {'width': 440, 'height': 520, 'body': 16, 'detail': 14, 'card': 128, 'composer': 108},
    'compact': {'width': 360, 'height': 520, 'body': 16, 'detail': 14, 'card': 128, 'composer': 108},
}
ICONS = {name: Image.open(ASSETS / (name + '.png')).convert('RGBA') for name in ('cashcat', 'ape', 'signet', 'eth', 'usdb', 'blast')}
ART = {name: Image.open(ASSETS / ('kira-' + name + '.png')).convert('RGBA') for name in ('explain', 'research')}
LOGO = Image.open(ASSETS / 'kira-logo.png').convert('RGBA')

@lru_cache(maxsize=32)
def font(size, weight=400):
    result = ImageFont.truetype(FONT, round(size * SCALE))
    result.set_variation_by_axes([100, max(17, min(96, size)), 400, weight])
    return result

class Painter:
    def __init__(self, profile):
        self.p = profile
        self.width, self.height = profile['width'], profile['height']
        self.image = Image.new('RGB', (self.width * SCALE, self.height * SCALE), BACKGROUND)
        self.draw = ImageDraw.Draw(self.image)

    def rounded(self, box, radius=12, fill=None, outline=None, width=1):
        self.draw.rounded_rectangle(tuple(round(v * SCALE) for v in box), radius=radius * SCALE, fill=fill, outline=outline, width=width * SCALE)

    def text(self, x, y, value, size, color=INK, weight=400, right=False):
        self.draw.text((round(x * SCALE), round(y * SCALE)), value, font=font(size, weight), fill=color, anchor='rt' if right else 'lt')

    def wrapped(self, text, size, width, weight=400):
        lines, line = [], ''
        for word in text.split():
            trial = (line + ' ' + word).strip()
            if self.draw.textlength(trial, font=font(size, weight)) > width * SCALE and line:
                lines.append(line)
                line = word
            else:
                line = trial
        return lines + [line] if line else lines

    def lines(self, x, y, values, size, color=INK, line_height=None, weight=400):
        step = line_height or size * 1.55
        for value in values:
            self.text(x, y, value, size, color, weight)
            y += step
        return y

    def artwork(self, source, x, y, width, height):
        art = source.copy()
        art.thumbnail((round(width * SCALE), round(height * SCALE)), Image.Resampling.LANCZOS)
        self.image.paste(art, (round(x * SCALE), round(y * SCALE)), art)

    def logo(self, source, x, y, size):
        pixels = round(size * SCALE)
        icon = Image.new('RGBA', (pixels, pixels), '#ffffff')
        art = source.copy()
        art.thumbnail((pixels, pixels), Image.Resampling.LANCZOS)
        icon.paste(art, ((pixels - art.width) // 2, (pixels - art.height) // 2), art)
        mask = Image.new('L', (pixels, pixels), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, pixels - 1, pixels - 1), fill=255)
        self.image.paste(icon, (round(x * SCALE), round(y * SCALE)), mask)


def geometry(case, profile):
    p = Painter(profile)
    w, body = p.width, profile['body']
    margin = 24 if w > 400 else 18
    question = p.wrapped(case['question'], body, w - margin * 2 - 52)
    qbottom = 18 + 28 + len(question) * body * 1.55
    answer_y = qbottom + 66
    answer = p.wrapped(case['answer'], body, w - 2 * margin)
    cards_y = answer_y + len(answer) * body * 1.55 + 20
    bottom = cards_y + 3 * profile['card'] + 20
    return {'margin': margin, 'question': question, 'qbottom': qbottom,
            'answer_y': answer_y, 'answer': answer, 'cards_y': cards_y,
            'summary_y': bottom + 20, 'height': math.ceil(bottom + 75)}


def conversation(case, time, profile, layout):
    """One growing conversation block, positioned in a shared scroll stream."""
    p = Painter(dict(profile, height=layout['height']))
    w, body, detail = p.width, profile['body'], profile['detail']
    margin = layout['margin']
    if time < 2.6:
        return p.image
    qx, qy = margin + 26, 18
    p.rounded((qx, qy, w - margin, layout['qbottom']), 14, '#eee6f5')
    p.lines(qx + 16, qy + 14, layout['question'], body, '#504358')
    y = layout['qbottom'] + 24
    p.artwork(LOGO, margin, y, 28, 28)
    p.text(margin + 38, y + 6, 'Kira', body, PLUM, 600)
    y = layout['answer_y']
    if time < 4.8:
        art_w = 80 if w > 400 else 72
        p.artwork(ART['research'], margin, y + 8, art_w, 108)
        work_x = margin + art_w + 18
        p.lines(work_x, y + 18, p.wrapped(case['working'], body, w - margin - work_x), body, MUTED)
        for i in range(3):
            pulse = (math.sin(time * 4 - i * .5) + 1) / 2
            cx, cy = (work_x + i * 14) * SCALE, (y + 112 - pulse * 3) * SCALE
            p.draw.ellipse((cx, cy, cx + 5 * SCALE, cy + 5 * SCALE), fill='#8a659d')
        return p.image
    visible = min(len(case['answer']), round(max(0, time - 4.8) / .5 * len(case['answer'])))
    p.lines(margin, y, p.wrapped(case['answer'][:visible], body, w - 2 * margin), body, '#5f5369')
    for index, token in enumerate(case['tokens']):
        top = layout['cards_y'] + index * (profile['card'] + 10)
        progress = max(0, min(1, (time - 5.4 - index * 2.35) / .4))
        if not progress:
            continue
        top += 8 * (1 - progress) ** 2
        bottom = top + profile['card']
        coverage = token.get('coverage')
        p.rounded((margin, top, w - margin, bottom), 12, '#f0f6f2' if coverage else CARD, '#dde8e2' if coverage else LINE)
        left, right = margin + 14, w - margin - 14
        if coverage:
            p.rounded((left, top + 36, left + 30, top + 66), 15, '#e2eee7')
            p.draw.line([((left + 9) * SCALE, (top + 50) * SCALE), ((left + 13) * SCALE, (top + 55) * SCALE), ((left + 22) * SCALE, (top + 44) * SCALE)], fill='#56705f', width=2 * SCALE)
            headings = p.wrapped(token['symbol'], body, right - left - 42, 550)
            yy = p.lines(left + 42, top + 18, headings, body, '#56705f', body * 1.3, 550)
            ending = p.lines(left + 42, yy + 9, p.wrapped(token['detail'], detail, right - left - 42), detail, '#56705f', detail * 1.4)
            assert ending < bottom - 8, f'{case["id"]}/{w}: coverage card overflow'
        else:
            p.logo(ICONS[token['icon']], left, top + 14, 32)
            p.text(left + 42, top + 14, token['symbol'], body, INK, 600)
            color = '#35664d' if case['id'] == 'compare' else INK
            p.text(right, top + 14, token['value'], body, color, 600 if token['value'] != 'Unpriced' else 400, True)
            p.text(left + 42, top + 37, token['chain'], detail, '#74627f')
            comparison = case['id'] == 'compare'
            p.text(left, top + 60, 'Previous price' if comparison else 'Balance', 12, MUTED)
            p.text(right, top + 60, 'Current price' if comparison else 'Unit price', 12, MUTED, right=True)
            quantity = token['previous_price'] if comparison else token['quantity']
            price = token['price'].removesuffix(' each')
            p.text(left, top + 78, quantity, detail, INK, 500)
            p.text(right, top + 78, price, detail, INK, 500, right=True)
            assert p.draw.textlength(quantity, font=font(detail, 500)) + p.draw.textlength(price, font=font(detail, 500)) + 12 * SCALE < (right - left) * SCALE, f'{case["id"]}/{w}: balance and unit price overlap'
            p.text(left, top + 105, token['market'], detail, '#765887')
            assert p.draw.textlength(token['market'], font=font(detail)) < (right - left) * SCALE, f'{case["id"]}/{w}: market row overflow'
    if time >= 12.3:
        y = layout['summary_y']
        p.text(margin, y, case['summary'], detail, MUTED)
        p.text(w - margin, y, case['total'], body, '#35664d' if case['id'] == 'compare' else '#594064', 600, True)
        p.text(w - margin, y + 23, case['note'], 12 if w > 400 else 13, '#786484', right=True)
    return p.image


def ease(value):
    value = max(0, min(1, value))
    return value * value * (3 - 2 * value)


def frame(time, profile, layouts, completed):
    """Append three questions and answers, scrolling only inside the chat film."""
    p = Painter(profile)
    w, h, body = p.width, p.height, profile['body']
    index = min(len(CASES) - 1, int(time // SECONDS))
    t = time - index * SECONDS
    case, layout = CASES[index], layouts[index]
    margin = layout['margin']
    chat_h = h - profile['composer'] - 20
    offsets, position = [], 0
    for item in layouts:
        offsets.append(position)
        position += item['height'] + 20
    current_top = offsets[index]
    scroll = max(0, current_top - 20 - chat_h) if index else 0
    targets = [(2.6, layout['answer_y'] + 140),
               (4.8, layout['cards_y']),
               (5.4, layout['cards_y'] + profile['card'] + 18),
               (7.75, layout['cards_y'] + 2 * profile['card'] + 28),
               (10.1, layout['cards_y'] + 3 * profile['card'] + 38),
               (12.3, layout['height'])]
    for start, bottom in targets:
        target = max(scroll, current_top + bottom - chat_h)
        scroll += (target - scroll) * ease((t - start) / .85)
    content = Image.new('RGB', (w * SCALE, chat_h * SCALE), BACKGROUND)
    for prior in range(index):
        content.paste(completed[prior], (0, round((offsets[prior] - scroll) * SCALE)))
    if t >= 2.6:
        content.paste(conversation(case, t, profile, layout), (0, round((current_top - scroll) * SCALE)))
    elif index == 0:
        welcome = Painter(dict(profile, height=chat_h))
        art_w, art_h = (140, 188) if w > 400 else (112, 150)
        welcome.artwork(ART['explain'], (w - art_w) / 2, 24, art_w, art_h)
        for y, value, size in [(art_h + 53, 'Let’s look at your wallets.', body + 2),
                               (art_h + 89, 'Your questions. Your AI.', body)]:
            tw = welcome.draw.textlength(value, font=font(size, 500)) / SCALE
            welcome.text((w - tw) / 2, y, value, size, PLUM, 500)
        content = welcome.image
    # Quiet edge fades distinguish a scrolling transcript from a cropped frame.
    fade = Image.new('RGB', content.size, BACKGROUND)
    mask = Image.new('L', content.size, 255)
    md = ImageDraw.Draw(mask)
    for edge in range(10 * SCALE):
        opacity = round(255 * edge / (10 * SCALE))
        md.line((0, edge, content.width, edge), fill=opacity)
        md.line((0, content.height - edge - 1, content.width, content.height - edge - 1), fill=opacity)
    p.image.paste(Image.composite(content, fade, mask), (0, 0))
    # Fixed composer always fits inside the frame; long typing stays on two rows.
    top = h - profile['composer'] - 8
    sent = t >= 2.6
    typing = min(1, max(0, t / 2.3))
    shown = 'Ask Kira about your wallets…' if sent else case['question'][:round(len(case['question']) * typing)]
    rows = p.wrapped(shown, body, w - margin * 2 - 42) or ['Ask Kira about your wallets…']
    if len(rows) > 2:
        rows = rows[-2:]
    border = '#b998ca' if sent and t < 4.8 and math.sin(t * 4) > 0 else '#d4bfdf'
    p.rounded((margin - 8, top, w - margin + 8, h - 12), 14, '#ffffff', border)
    p.lines(margin + 6, top + 15, rows, body, '#7d698a')
    fy = h - 40
    assert top + 15 + len(rows) * body * 1.55 < fy - 4, 'Composer typing overlaps its footer'
    p.draw.ellipse(((margin + 8) * SCALE, (fy + 5) * SCALE, (margin + 13) * SCALE, (fy + 10) * SCALE), fill='#739284')
    p.text(margin + 20, fy + 2, 'Your AI account', 12 if w > 400 else 13, '#7d698a')
    bx = w - margin - 24
    p.rounded((bx, fy - 6, bx + 28, fy + 22), 7, '#87659b')
    p.draw.line([((bx + 14) * SCALE, (fy + 15) * SCALE), ((bx + 14) * SCALE, (fy + 2) * SCALE)], fill='white', width=2 * SCALE)
    p.draw.line([((bx + 9) * SCALE, (fy + 7) * SCALE), ((bx + 14) * SCALE, (fy + 2) * SCALE), ((bx + 19) * SCALE, (fy + 7) * SCALE)], fill='white', width=2 * SCALE)
    return p.image


def render(name, profile):
    suffix = '' if name == 'desktop' else '-' + name
    output = ASSETS / ('kira-scenarios' + suffix + '.mp4')
    layouts = [geometry(case, profile) for case in CASES]
    completed = [conversation(case, 14, profile, layout) for case, layout in zip(CASES, layouts)]
    command = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{profile["width"] * SCALE}x{profile["height"] * SCALE}', '-r', str(FPS), '-i', '-', '-an', '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(output)]
    initial = frame(0, profile, layouts, completed)
    with subprocess.Popen(command, stdin=subprocess.PIPE) as movie:
        assert movie.stdin is not None
        for index in range(SECONDS * len(CASES) * FPS):
            t = index / FPS
            image = frame(t, profile, layouts, completed)
            if t > SECONDS * len(CASES) - .5:
                image = Image.blend(image, initial, (t - SECONDS * len(CASES) + .5) / .5)
            movie.stdin.write(image.tobytes())
        movie.stdin.close()
        assert movie.wait() == 0
    if name == 'desktop':
        for i in range(len(CASES)):
            frame(i * SECONDS + 14, profile, layouts, completed).save(ASSETS / f'kira-scenario-{i + 1}.png', optimize=True)
    frame(7, profile, layouts, completed).save(ASSETS / ('kira-scenarios' + suffix + '-poster.png'), optimize=True)
    print(f'{name}: {output.name}, {output.stat().st_size:,} bytes', flush=True)


def main():
    for name, profile in PROFILES.items():
        render(name, profile)
    manifest = {
        'kind': 'synthetic_recorded_holdings_demo', 'seconds': SECONDS * len(CASES),
        'seconds_per_case': SECONDS, 'fps': FPS, 'render_scale': SCALE,
        'presentation': 'One continuous chat stream. Earlier messages remain above; new questions and answers append below with internal automatic scrolling.',
        'profiles': PROFILES, 'cases': CASES,
        'notes': 'Synthetic questions, balances and prices. Recorded spot values are not executable sale quotes. No private portfolio is read. Public token artwork provenance remains in token-artwork-sources.json.',
    }
    (ASSETS / 'kira-scenarios.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    print('Rendered three 48-second continuous films with typing, research, appended results and a loop.', flush=True)

if __name__ == '__main__':
    main()
