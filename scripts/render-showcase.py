"""Render the public reconstructed chat demo. No portfolio input is read."""
from pathlib import Path
import json,math,subprocess,textwrap
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
W,H,FPS=720,860,24
FONT='/System/Library/Fonts/Supplemental/Arial.ttf'
BOLD='/System/Library/Fonts/Supplemental/Arial Bold.ttf'
def font(size,bold=False):return ImageFont.truetype(BOLD if bold else FONT,size)
INK='#38313f';MUTED='#87748f';PURPLE='#715285'
CASES=[
 {'label':'Find overlooked value','question':'Which tokens have been sitting idle, and what could I receive if I sold them?',
  'working':'Checking activity evidence, holdings and exit routes…',
  'answer':'Three holdings to review in this example. Spot value and expected sale output are different.',
  'tokens':[
   {'symbol':'CASHCAT','icon':'cashcat','chain':'Robinhood','balance':'1,200','price':'$0.1800','value':'$216.00',
    'chain_id':4663,'contract':'0x020bfc650a365f8bb26819deaabf3e21291018b4',
    'pool':'0xa92a3df27a00a276183ff7265fd8affa11df1fe8bb23ddfaf13f6c879a3f818b',
    'market_url':'https://lptoken.fun/trade/robinhood/0x020bfc650a365f8bb26819deaabf3e21291018b4',
    'route':'Uniswap v4 · CASHCAT / USDG','output':'Simulated output 212.19 USDG · gas $0.55',
    'detail':'Example: no transfers in 180 days · impact 1.5% · fee 0.269%'},
   {'symbol':'APE','icon':'ape','chain':'Ethereum','balance':'20','price':'$0.8500','value':'$17.00',
    'chain_id':1,'contract':'0x4d224452801aced8b2f0aebe155379bb5d594381',
    'route':'Uniswap v3 · APE / WETH','output':'Sale output unknown · no execution quote',
    'detail':'Example: no transfers in 90 days · gas and impact unknown'},
   {'symbol':'SIGNET','icon':'signet','chain':'Base','balance':'650','price':'Unknown','value':'Unknown',
    'chain_id':8453,'contract':'0xdf2b673ec06d210c8a8be89441f8de60b5c679c9',
    'route':'No funded market recorded','output':'Sale output unknown',
    'detail':'Activity history unavailable · inactivity unconfirmed'}],
  'next':'CASHCAT net example: $211.64 after gas, assuming USDG = $1. All figures are illustrative; refresh before acting.'},
 {'label':'Review a whole network','question':'Review my Blast holdings across wallets. What is liquid, and what should I check before moving it?',
  'working':'Grouping wallets, token identities and recorded pools…',
  'answer':'Your Blast exposure, grouped in this demo. Preserve ETH for fees and quote each exit separately.',
  'tokens':[
   {'symbol':'ETH','icon':'eth','chain':'Blast · Wallet A','balance':'0.050','price':'$2,700','value':'$135.00',
    'chain_id':81457,'contract':'native',
    'route':'Native gas asset · bridge route not quoted','output':'Keep ETH for gas · bridge fees unknown','detail':'Balance and price: example observation only'},
   {'symbol':'USDB','icon':'usdb','chain':'Blast · Wallet A','balance':'250','price':'$1.000','value':'$250.00',
    'chain_id':81457,'contract':'0x4300000000000000000000000000000000000003',
    'pool':'0xf00da13d2960cf113edcef6e3f30d92e52906537',
    'market_url':'https://dexscreener.com/blast/0xf00da13d2960cf113edcef6e3f30d92e52906537',
    'route':'Thruster v3 · USDB / WETH','output':'Sale output unknown · quote full balance first','detail':'Pool liquidity $158,000 · illustrative observation'},
   {'symbol':'BLAST','icon':'blast','chain':'Blast · Wallet B','balance':'100,000','price':'$0.0001566','value':'$15.66',
    'chain_id':81457,'contract':'0xb1a5700fa2358173fe465e6ea4ff52e36e88e2ad',
    'pool':'0x9a0aa28d999a21d3cf6f2703cdbba9feaf4a32f7',
    'market_url':'https://dexscreener.com/blast/0x9a0aa28d999a21d3cf6f2703cdbba9feaf4a32f7',
    'route':'Thruster v3 · BLAST / WETH','output':'Sale output unknown · costs can matter','detail':'Pool liquidity $15,000 · illustrative observation'}],
  'next':'Demo spot total: $400.66. Neither a bridge quote nor cash proceeds. Check unpriced tokens and missing wallet coverage too.'},
 {'label':'Understand an LP position · preview','question':'Could I have forgotten LP positions? Show the underlying tokens, fees and what withdrawing would return.',
  'working':'Previewing position ownership and underlying assets…',
  'answer':'Two reconstructed positions. Pool links alone do not prove that you own liquidity.',
  'tokens':[
   {'symbol':'WETH / USDC','icon':'lp','chain':'Base · Aerodrome','balance':'LP position','price':'Preview','value':'$154.00',
    'route':'Underlying: 0.030 WETH + 73.00 USDC','output':'Illustrative fees: $2.00 · withdrawal unquoted','detail':'Ownership, fee and exit data are concept-only'},
   {'symbol':'ETH / USDC','icon':'lp','chain':'Ethereum · Uniswap','balance':'Position NFT','price':'Preview','value':'$278.00',
    'route':'Underlying: 0.060 ETH + 116.00 USDC','output':'Illustrative fees: $4.50 · withdrawal unquoted','detail':'Values use illustrative ETH/WETH = $2,700'}],
  'next':'LP discovery preview. Current Kira research covers direct holdings. No position, fee or withdrawal in this demo is measured.'}
]
ASSETS=ROOT/'site/assets'
ICONS={}
for name in ('ape','signet','eth','usdc','cashcat','blast','usdb'):
    path=ASSETS/(name+'.png')
    if path.exists():ICONS[name]=Image.open(path).convert('RGBA').resize((44,44))
ART={pose:Image.open(ASSETS/('kira-'+pose+'.png')).convert('RGBA') for pose in ('explain','research')}
def wrap(draw,text,size,width):
    words=text.split();rows=[];line=''
    for word in words:
        candidate=(line+' '+word).strip()
        if draw.textlength(candidate,font=font(size))>width and line:rows.append(line);line=word
        else:line=candidate
    return rows+[line] if line else rows

def frame(case,t):
    im=Image.new('RGB',(W,H),'#fcfafc');d=ImageDraw.Draw(im)
    d.rounded_rectangle((1,1,W-2,H-2),radius=24,outline='#dfd4e7',width=2)
    d.text((30,25),'Kira Chat',font=font(24,True),fill=INK)
    d.text((W-192,32),'ILLUSTRATIVE DEMO',font=font(12,True),fill=MUTED)
    d.line((25,76,W-25,76),fill='#e8e0ed',width=1)
    d.text((30,96),case['label'],font=font(15,True),fill=PURPLE)
    # Request is typed in the floating input, sent, then answered.
    text=case['question'];typing=min(1,max(0,t/2.4));sent=t>=2.7;answer=t>=5.2
    if sent:
        rows=wrap(d,text,19,W-136);bottom=147+len(rows)*25
        d.rounded_rectangle((78,139,W-28,bottom+17),radius=15,fill='#eee7f4')
        for i,row in enumerate(rows):d.text((96,147+i*25),row,font=font(19),fill=INK)
        y=bottom+24
        pose='explain' if answer else 'research';art=ART[pose].copy();art.thumbnail((46,58))
        im.paste(art,(28,y),art)
        d.text((88,y+10),'Kira',font=font(22,True),fill=PURPLE)
        if not answer:
            for i,row in enumerate(wrap(d,case['working'],18,W-165)):d.text((124,y+48+i*25),row,font=font(18),fill=MUTED)
            for i in range(3):
                pulse=(math.sin(t*5-i*.5)+1)/2
                d.ellipse((124+i*16,y+99-pulse*3,130+i*16,y+116-pulse*3),fill=PURPLE)
        else:
            y+=65
            for row in wrap(d,case['answer'],18,W-64):d.text((32,y),row,font=font(18),fill=INK);y+=25
            y+=18
            for i,token in enumerate(case['tokens']):
                if t<5.35+i*.18:continue
                symbol,icon=token['symbol'],token['icon']
                d.rounded_rectangle((30,y,W-30,y+99),radius=12,fill='#f2edf6')
                if icon=='lp':
                    for name,x in [('eth',43),('usdc',61)]:
                        logo=ICONS[name].resize((30,30));im.paste(logo,(x,y+12),logo)
                elif icon in ICONS:im.paste(ICONS[icon],(43,y+9),ICONS[icon])
                else:raise ValueError('Missing researched token artwork: '+icon)
                d.text((102,y+12),symbol+' · '+token['chain'],font=font(17,True),fill=INK)
                d.text((102,y+36),token['balance']+' × '+token['price']+' = '+token['value'],font=font(15),fill=MUTED)
                d.text((43,y+58),token['route'],font=font(14),fill=MUTED)
                d.text((43,y+78),token['output'],font=font(15,True),fill=PURPLE)
                y+=105
            y+=3
            for row in wrap(d,case['next'],14,W-64):d.text((32,y),row,font=font(14),fill=PURPLE);y+=20
            assert y<735, 'Demo content overlaps composer'
    # The input is always at the bottom; it does not cover the answer.
    if 2.7<t<5.2:
        pulse=(math.sin(t*5)+1)/2
        for inset in range(9,0,-1):d.rounded_rectangle((25-inset,742-inset,W-25+inset,830+inset),radius=20,outline=('#d8c3e7' if pulse>.45 else '#e7dcef'),width=1)
    d.rounded_rectangle((25,742,W-25,830),radius=16,fill='white',outline='#c8b7d4',width=2)
    shown='Ask Kira to check your wallets…' if sent else text[:int(len(text)*typing)]
    for i,row in enumerate(wrap(d,shown,16,W-114)[:2]):d.text((43,758+i*22),row,font=font(16),fill=MUTED)
    d.text((44,803),'Your own AI',font=font(12),fill=MUTED)
    d.rounded_rectangle((W-74,780,W-39,817),radius=9,fill=PURPLE)
    d.line((W-56,806,W-56,790),fill='white',width=2);d.line((W-61,796,W-56,790,W-51,796),fill='white',width=2)
    return im

def main():
    for case in CASES:
        assert len(case['tokens'])<=3
        frame(case,8)  # Validate the complete layout before replacing the video.
    frames_per_case=14*FPS
    command=['ffmpeg','-y','-hide_banner','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-','-an','-c:v','libx264','-preset','fast','-crf','24','-pix_fmt','yuv420p','-movflags','+faststart',str(ASSETS/'kira-scenarios.mp4')]
    with subprocess.Popen(command,stdin=subprocess.PIPE) as video:
        for case_index,case in enumerate(CASES):
            for index in range(frames_per_case):
                t=index/FPS;im=frame(case,t)
                if t<.25:im=Image.blend(Image.new('RGB',(W,H),'#fcfafc'),im,t/.25)
                if t>13.65:im=Image.blend(im,Image.new('RGB',(W,H),'#fcfafc'),(t-13.65)/.35)
                video.stdin.write(im.tobytes())
            frame(case,8).save(ASSETS/f'kira-scenario-{case_index+1}.png',optimize=True)
        video.stdin.close();assert video.wait()==0
    frame(CASES[0],8).save(ASSETS/'kira-scenarios-poster.png',optimize=True)
    write_manifest()
    print('Rendered 42-second reconstructed scenario video and matching transcript.')

def write_manifest():
    (ASSETS/'kira-scenarios.json').write_text(json.dumps({'kind':'reconstructed_concept_demo','seconds':42,'fps':FPS,'illustrative_observed_at':'2026-10-05T00:00:00Z','cases':CASES,'notes':'All balances, prices, activity and outputs are illustrative. Linked market identities are public research references, not execution quotes. LP ownership and pools in the LP preview are concept-only. Dormancy, DEX quotes and LP discovery are previews. Artwork uses verified chain/contract metadata from lpTOKEN.fun, DEX Screener and CoinGecko; see token-artwork-sources.json.'},indent=2)+'\n')
    import html,re
    transcript='<details class="motion-transcript"><summary>Read the scenarios and assumptions</summary><div>'
    for case in CASES:
        transcript+='<h3>'+html.escape(case['label'])+'</h3><p>“'+html.escape(case['question'])+'”</p><p>'+html.escape(case['answer'])+'</p><ul>'
        for token in case['tokens']:
            text=' · '.join([token['symbol'],token['chain'],token['balance']+' × '+token['price']+' = '+token['value'],token['route'],token['output'],token['detail']])
            identity=(' · Chain ID '+str(token['chain_id'])+' · Contract '+token['contract']) if 'contract' in token else ''
            market=('<br><a href="'+html.escape(token['market_url'],quote=True)+'" target="_blank" rel="noreferrer">Public market reference ↗</a> · Pool '+html.escape(token['pool'])) if token.get('market_url') else ''
            transcript+='<li>'+html.escape(text+identity)+market+'</li>'
        transcript+='</ul><p>Illustrative observation: October 5, 2026, 00:00 UTC. Linked markets identify the token and venue; their live prices will differ.</p><p>'+html.escape(case['next'])+'</p>'
    transcript+='</div></details>'
    path=ROOT/'site/index.html';body=path.read_text()
    body=re.sub(r'<details class="motion-transcript">.*?</details>',lambda _:transcript,body,flags=re.S)
    path.write_text(body)
if __name__=='__main__':main()
