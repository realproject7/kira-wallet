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
 {'label':'Find overlooked tokens','question':'Which networks or tokens might be missing from my recorded holdings?','working':'Checking network coverage and token records…','answer':'Three places worth a closer look. Small tokens are easy to miss when an indexer skips a network.','tokens':[('APE','Ethereum','ape'),('CASHCAT','Robinhood · example','cashcat'),('SIGNET','Base','signet')],'next':'Next: refresh the gaps. Keep unverified balances unknown.'},
 {'label':'Check a whole network','question':'Which tokens do I have on Blast across all my wallets?','working':'Reading Blast holdings across your wallets…','answer':'Here is your Blast exposure, together. Keep enough ETH for fees before moving anything.','tokens':[('ETH','Blast · gas token','eth'),('USDB','Blast · stablecoin','usdb'),('BLAST','Blast · governance token','blast')],'next':'Next: check live routes and costs for the tokens you want to move.'},
 {'label':'Remember forgotten LPs','question':'Do I have a liquidity pool position on Aerodrome or Uniswap?','working':'Inspecting pool positions and their networks…','answer':'Two positions surfaced in this example. Check the underlying tokens and fees before deciding your next move.','tokens':[('WETH / USDC','Base · Aerodrome','lp'),('ETH / USDC','Ethereum · Uniswap','lp')],'next':'LP discovery preview. Current release tracks direct token holdings.'}
]
ASSETS=ROOT/'site/assets'
ICONS={}
for name in ('ape','signet','eth','usdc'):
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
    d.text((W-160,32),'CONCEPT DEMO',font=font(12,True),fill=MUTED)
    d.line((25,76,W-25,76),fill='#e8e0ed',width=1)
    d.text((30,96),case['label'],font=font(15,True),fill=PURPLE)
    # Request is typed in the floating input, sent, then answered.
    text=case['question'];typing=min(1,max(0,t/2.4));sent=t>=2.7;answer=t>=5.2
    if sent:
        rows=wrap(d,text,21,W-136);bottom=153+len(rows)*29
        d.rounded_rectangle((78,139,W-28,bottom+17),radius=15,fill='#eee7f4')
        for i,row in enumerate(rows):d.text((96,153+i*29),row,font=font(21),fill=INK)
        y=bottom+45
        pose='explain' if answer else 'research';art=ART[pose].copy();art.thumbnail((80,100))
        im.paste(art,(28,y),art)
        d.text((124,y+14),'Kira',font=font(22,True),fill=PURPLE)
        if not answer:
            for i,row in enumerate(wrap(d,case['working'],18,W-165)):d.text((124,y+48+i*25),row,font=font(18),fill=MUTED)
            for i in range(3):
                pulse=(math.sin(t*5-i*.5)+1)/2
                d.ellipse((124+i*16,y+110-pulse*3,130+i*16,y+116-pulse*3),fill=PURPLE)
        else:
            y+=114
            for row in wrap(d,case['answer'],21,W-64):d.text((32,y),row,font=font(21),fill=INK);y+=30
            y+=18
            for i,(symbol,network,icon) in enumerate(case['tokens']):
                if t<5.35+i*.18:continue
                d.rounded_rectangle((30,y,W-30,y+74),radius=12,fill='#f2edf6')
                if icon=='lp' and 'eth' in ICONS and 'usdc' in ICONS:
                    for name,x in [('eth',46),('usdc',67)]:
                        logo=ICONS[name].resize((32,32));im.paste(logo,(x,y+21),logo)
                elif icon in ICONS:im.paste(ICONS[icon],(46,y+15),ICONS[icon])
                else:
                    colors={'cashcat':'#68977e','usdb':'#b4c343','blast':'#d3e44a','lp':'#7c6da8'}
                    d.ellipse((46,y+15,90,y+59),fill=colors.get(icon,PURPLE))
                    label={'cashcat':'CC','usdb':'$','blast':'B','lp':'LP'}.get(icon,symbol[:2])
                    box=d.textbbox((0,0),label,font=font(17,True));d.text((68-(box[2]-box[0])/2,y+27),label,font=font(17,True),fill='white')
                d.text((105,y+14),symbol,font=font(21,True),fill=INK);d.text((105,y+43),network,font=font(16),fill=MUTED);y+=85
            y+=10
            for row in wrap(d,case['next'],16,W-64):d.text((32,y),row,font=font(16),fill=PURPLE);y+=23
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
    (ASSETS/'kira-scenarios.json').write_text(json.dumps({'kind':'reconstructed_concept_demo','seconds':42,'fps':FPS,'cases':CASES,'notes':'All answers and findings are illustrative. CASHCAT/Robinhood and LP rows are concept scenarios, not measured holdings. CC, USDB and BLAST use illustrative monogram icons. LP rows use paired ETH and USDC artwork.'},indent=2)+'\n')
    print('Rendered 42-second reconstructed scenario video.')
if __name__=='__main__':main()
