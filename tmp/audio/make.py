from pathlib import Path
from pypdf import PdfReader
import argparse, re, asyncio, hashlib, subprocess
import edge_tts, imageio_ffmpeg
import numpy as np
ROOT=Path('tmp/audio')
OUT=Path('output/audio')
LABELS=['第一部分','第二部分','第三部分','第四部分']
NUM='一 二 三 四 五 六 七 八 九 十 十一 十二 十三 十四 十五 十六 十七 十八 十九 二十'.split()
VOICES={'m':'zh-CN-YunxiNeural','f':'zh-CN-XiaoxiaoNeural'}
parser = argparse.ArgumentParser()
parser.add_argument('set_number', type=int, choices=range(1, 11))
SET = parser.parse_args().set_number
STEM = f'HSK3.0_1급_제{SET:02}회_'
PDF = Path('output') / (STEM + '정답및해설.pdf')
def parse():
 parts=[]
 for page in PdfReader(PDF).pages[1:]:
  for line in page.extract_text().splitlines()[3:]:
   line=line.strip()
   if line in LABELS:
    parts.append({})
   elif line=='例' or re.fullmatch(r'\d+\.',line):
    key=0 if line=='例' else int(line[:-1])
    parts[-1][key]=[]
   elif line:
    parts[-1][key].append(line)
 assert [list(part) for part in parts]==[[0,*range(i,i+5)] for i in range(1,21,5)]
 return parts
PARTS=parse()
FF=imageio_ffmpeg.get_ffmpeg_exe()
def syll(t):
 return len(re.findall(r'[\u3400-\u9fff]',t))
def key(v,t): return hashlib.sha1(('slow:'+VOICES[v]+t).encode()).hexdigest()[:16]
def speech(i,n):
 out=[]
 for j,t in enumerate(PARTS[i][n]):
  if t.startswith(('男：','女：')): v='m' if t[0]=='男' else 'f'; t=t[2:]
  elif t.startswith('问：'): v='f' if n%2==0 else 'm'; t=t[2:]
  else: v=('m' if n%2==0 else 'f') if i==3 else ('f' if n%2==0 else 'm')
  out.append((v,t))
 return out
INTRO=['您好！欢迎参加HSK一级考试。','HSK一级听力考试分四部分，共二十题。','请大家注意，听力考试现在开始。']
END='听力考试现在结束。'
def tasks():
 for t in INTRO+[END,*LABELS,'例如：','现在开始第一题。','现在开始第六题。','现在开始第十一题。','现在开始第十六题。',*[f'第{n}题。' for n in NUM]]:
  yield 'f',t
 for i,p in enumerate(PARTS):
  for n in p: yield from speech(i,n)
async def tts():
 sem=asyncio.Semaphore(6)
 async def generate(v,t):
  f=ROOT/(key(v,t)+'.mp3')
  if f.exists() and f.stat().st_size>1000:return
  async with sem:
   for k in range(4):
    try:
     await edge_tts.Communicate(t,VOICES[v],rate='-13%',pitch={'m':'-8Hz','f':'-10Hz'}[v]).save(str(f))
     return
    except Exception:
     if k==3:raise
     await asyncio.sleep(k+1)
 await asyncio.gather(*(generate(v,t) for v,t in sorted(set(tasks()))))
if __name__=='__main__': asyncio.run(tts())
