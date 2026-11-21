from pathlib import Path
import numpy as np
import wave,re,sys
import sherpa_onnx
root=Path('tmp/audio')
model=next(root.glob('sherpa-*'))
r=sherpa_onnx.OfflineRecognizer.from_sense_voice(model=str(model/'model.onnx'),tokens=str(model/'tokens.txt'),language='zh',use_itn=False,num_threads=3)
def rec(a):
 s=r.create_stream()
 s.accept_waveform(16000,np.pad(a,(1600,2000)))
 r.decode_stream(s)
 return s.result.text
def pitch(a):
 out=[]
 for i in range(0,len(a)-640,320):
  x=a[i:i+640].copy()
  if np.std(x)<0.009: continue
  x-=x.mean()
  c=np.correlate(x,x,'full')[639:]
  peaks=[j for j in range(40,220) if c[j]>=c[j-1] and c[j]>c[j+1]]
  if not peaks:continue
  best=max(c[j] for j in peaks)
  if best/c[0]<0.48:continue
  j=next(j for j in peaks if c[j]>=0.88*best)
  out.append(16000/j)
 return round(np.median(out)) if out else 0
if __name__=='__main__':
 with wave.open(str(root/'ref.wav'),'rb') as w: a=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(np.float32)/32768
 s=(root/'silence.txt').read_text(encoding='utf-8',errors='replace')
 end=0.
 with (root/'ref.tsv').open('w',encoding='utf-8',buffering=1) as o:
  for b,e in re.findall(r'silence_end: ([\d.]+) \| silence_duration: ([\d.]+)',s):
   b,e=float(b),float(e)
   if e<.47:continue
   start=b-e
   if start-end>.14:
    x=a[round(end*16000):round(start*16000)]
    print(f'{end:.3f}\t{start:.3f}\t{e:.3f}\t{pitch(x)}\t{rec(x)}',file=o)
   end=b
