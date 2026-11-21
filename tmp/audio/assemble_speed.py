from make import *
import json
R=24000
STAGE = ROOT / 'speed_revision'
CACHE = STAGE
STAGE = STAGE / f'set{SET:02}'
STAGE.mkdir(parents=True, exist_ok=True)
RATE = '+0%'
PITCH = {'m':'-14Hz','f':'-19Hz'}
RATE_OVERRIDES = {}

def speech_path(v, t):
 rate = RATE_OVERRIDES.get((v,t), RATE)
 digest = hashlib.sha1(f'{VOICES[v]}:{rate}:{PITCH[v]}:{t}'.encode()).hexdigest()[:16]
 return CACHE / (digest + '.mp3')
INTRO_CUES=[
 ('f','中文水平考试。',.81),('f','H S K 三点零，一级。',.84),
 ('f','全真模拟试卷。',.62),('f',NUM[SET-1]+'。',2.44),
 ('f','大家好。',.90),('f','欢迎参加 H S K 一级考试。',1.86),
 ('m','大家好。',.56),('m','欢迎参加 H S K 一级考试。',1.69),
 ('f','大家好。',.66),('f','欢迎参加 H S K 一级考试。',2.64),
 ('f','H S K 一级听力考试分四部分。',.61),('f','共二十题。',1.70),
 ('f','请大家注意。',.96),('f','听力考试现在开始。',2.15),
]
RANGES=['第一到五题。','第六到十题。','第十一到十五题。','第十六到二十题。']
MODES=['听句子。','听问题。','听对话。','听句子和问题。']
SELECT=['选择正确图片。','选择正确回答。','选择最匹配的图片。','选择正确答案。']
CLOSE='听力考试现在结束。'
GUIDE_GAPS=[[1.44,1.20,.61,1.15,1.81,2.12],[2.12,1.01,.50,1.15,2.30,2.25],
 [1.56,1.31,.64,1.08,1.81,2.23],[1.72,1.99,.51,1.17,1.85,2.22]]
CUES=[[label,RANGES[i],MODES[i],SELECT[i],'每题听两次。','例如。'] for i,label in enumerate(LABELS)]
START_GAPS=[2.21,2.40,1.93,2.61]
def spoken_count(t):
 return syll(t.replace('哪儿','哪').replace('那儿','那'))+len(re.findall(r'\b[HSK]\b',t))
def item(i,n,j):
 lines=speech(i,n)
 if i<2: return [('mf'[j],lines[0][1])]
 if i==2:return lines
 return [('mf'[j],lines[0][1]),('f',lines[1][1])]
def timeline(i):
 for cue,g in zip(CUES[i],GUIDE_GAPS[i]): yield ('f',cue,g,'guide')
 for n in PARTS[i]:
  if n: yield 'f',NUM[n-1]+'。',[1.60,1.65,1.87,1.76][i],'number'
  for j in range(2):
   lines=item(i,n,j)
   for k,(v,t) in enumerate(lines):
    if k<len(lines)-1:g=[0,0,1.43,1.88][i]
    elif j==0:g=[2.45,2.39,2.40,2.31][i] if n else [2.71,2.39,2.29,2.39][i]
    else:g=13.77 if n else [2.49,2.59,2.20,2.90][i]
    yield v,t,g,n
  if not n:yield 'f','现在开始第'+NUM[i*5]+'题。',START_GAPS[i],'guide'
def prep():
 return asyncio.run(tts_extra())
async def tts_extra():
 sem=asyncio.Semaphore(7)
 events=[(v,t) for v,t,*_ in INTRO_CUES]+[('f',CLOSE)]
 events.extend((v,t) for i in range(4) for v,t,*_ in timeline(i))
 async def gen(v,t):
  f=speech_path(v,t)
  if f.exists() and f.stat().st_size>1000:return
  pending = f.with_suffix('.partial')
  async with sem:
   for k in range(4):
    try:
     await edge_tts.Communicate(t,VOICES[v],rate=RATE_OVERRIDES.get((v,t), RATE),pitch=PITCH[v]).save(str(pending))
     pending.replace(f)
     return
    except Exception:
     if k==3:raise
     await asyncio.sleep(k+1)
 await asyncio.gather(*(gen(v,t) for v,t in sorted(set(events))))
def ffdecode(f):
 return np.frombuffer(subprocess.check_output([FF,'-v','error','-i',str(f),'-f','f32le','-ac','1','-ar',str(R),'-']),'<f4')
def trim(a):
 blocks=np.pad(a,(0,(-len(a))%240)).reshape(-1,240)
 active=np.flatnonzero(np.max(abs(blocks),axis=1)>.0158)
 return a[max(0,active[0]*240-120):min(len(a),(active[-1]+1)*240+120)].copy()
def clip(v,t):
 a=trim(ffdecode(speech_path(v,t)))
 voiced=a[abs(a)>.026]
 a*=min(.95/max(abs(a)),.145/np.sqrt(np.mean(voiced**2)))
 fade=np.linspace(0,1,120)
 a[:120]*=fade
 a[-120:]*=fade[::-1]
 return a
def silence(t):return np.zeros(round(t*R),dtype=np.float32)
def write(label,a):
 path=OUT/f'{STEM}{label}.mp3'
 subprocess.run([FF,'-y','-v','error','-f','f32le','-ar',str(R),'-ac','1','-i','-','-c:a','libmp3lame','-b:a','64k',str(path)],input=a.tobytes(),check=True)
 return {'pcm_seconds':len(a)/R,'decoded_seconds':len(ffdecode(path))/R}
def assemble():
 seen={}
 manifest=[]
 def arrange(events,i):
  seg=[]
  cursor=0
  for v,t,g,n in events:
   k=(v,t)
   if k not in seen: seen[k]=clip(*k)
   a=seen[k]
   manifest.append(dict(part=i,n=n,voice=v,text=t,syllables=spoken_count(t),start=cursor/R,sec=len(a)/R,gap=g))
   seg.extend([a,silence(g)])
   cursor+=len(a)+round(g*R)
  return np.concatenate(seg)
 a=[np.concatenate([silence(1.42),arrange([(v,t,g,'intro') for v,t,g in INTRO_CUES],0)])]
 stats={}
 for i in range(4):
  part=arrange(timeline(i),i+1)
  a.append(part)
  stats[LABELS[i]]=write(LABELS[i],np.concatenate([silence(.35),part]))
 a.append(arrange([('f',CLOSE,1.27,'end')],5))
 stats['전체']=write('전체',np.concatenate(a))
 (STAGE/'manifest.json').write_text(json.dumps(dict(stats=stats,events=manifest),ensure_ascii=False,indent=2),encoding='utf-8')
 print(stats)
if __name__=='__main__':
 OUT.mkdir(parents=True, exist_ok=True)
 prep()
 assemble()
