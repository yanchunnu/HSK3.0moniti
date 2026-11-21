from assemble_speed import *
from asr_ref import rec,pitch
from pypinyin import lazy_pinyin,Style
d=json.loads((STAGE/'manifest.json').read_text(encoding='utf-8'))
def normal(t):
 return ''.join(x for x in t if '\u3400'<=x<='\u9fff').replace('哪儿','哪').replace('那儿','那')
def py(t): return lazy_pinyin(normal(t),style=Style.TONE3)

def asr_samples(a):
 return np.interp(np.arange(0,len(a),1.5),np.arange(len(a)),a).astype(np.float32)

def event_audio(audio, event):
 start=round((.35+event['start'])*R)
 return audio[start:start+round(event['sec']*R)]
events=d['events']
for i,label in enumerate(LABELS,1):
 e=[x for x in events if x['part']==i]
 a=ffdecode(OUT/f'{STEM}{label}.mp3')
 assert abs(len(a)/R-(.35+e[-1]['start']+e[-1]['sec']+e[-1]['gap']))<.003
 for n in PARTS[i-1]:
  expected=[t for j in range(2) for v,t in item(i-1,n,j)]
  assert [x['text'] for x in e if x['n']==n]==expected
 for x in e:
  s=round((.35+x['start'])*R)
  z=s+round(x['sec']*R)
  assert np.max(abs(a[s:z]))>.04
  if x['gap']>.25:
   assert np.max(abs(a[z+2400:z+int(x['gap']*R)-2400]))<.004
  if isinstance(x['n'],int):
   y=asr_samples(a[s:z])
   transcript=rec(y)
   status='OK' if py(transcript)==py(x['text']) else 'REVIEW'
   if status=='REVIEW':
    # Give a misrecognized short utterance the context of both original readings.
    related=[row for row in e if row['n']==x['n']]
    clips=[event_audio(a,row) for row in related]
    context=rec(asr_samples(np.concatenate([np.r_[clip,silence(.5)] for clip in clips])))
    if py(context)==py(''.join(row['text'] for row in related)):
     status='OK (context)'
    transcript += f' / {context}'
   print(i,x['n'],x['voice'],x['text'],transcript,status,pitch(y),sep='\t',flush=True)
full=ffdecode(OUT/f'{STEM}전체.mp3')
offset=1.42
for i in range(6):
 e=[x for x in events if x['part']==i]
 if 1<=i<=4:
  part=ffdecode(OUT/f'{STEM}{LABELS[i-1]}.mp3')[8400:]
  s=round(offset*R)
  assert np.corrcoef(part[:len(part)//2:7],full[s:s+len(part)//2:7])[0,1]>.995
 offset+=e[-1]['start']+e[-1]['sec']+e[-1]['gap']
assert abs(offset-len(full)/R)<.003
