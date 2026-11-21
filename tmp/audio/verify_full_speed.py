from assemble_speed import *
d=json.loads((STAGE/'manifest.json').read_text(encoding='utf-8'))
full=ffdecode(OUT/f'{STEM}전체.mp3')
offset=round(1.42*R)
for i in range(6):
 e=[x for x in d['events'] if x['part']==i]
 n=round((e[-1]['start']+e[-1]['sec']+e[-1]['gap'])*R)
 if 1<=i<=4:
  part=ffdecode(OUT/f'{STEM}{LABELS[i-1]}.mp3')[8400:]
  assert n==len(part)
  cor=[]
  for k in range(0,n,R*20):
   z=min(k+R*20,n)
   left=part[k:z:7]
   right=full[offset+k:offset+z:7]
   if np.max(np.abs(left))<.004:
    assert np.max(np.abs(right))<.004
   else:
    cor.append(float(np.corrcoef(left,right)[0,1]))
  print(LABELS[i-1],round(offset/R,3),round(min(cor),6))
  assert min(cor)>.99  # The independently encoded MP3 streams use different frame boundaries.
 else:
  assert np.max(abs(full[offset:offset+n]))>.04
 offset+=n
assert offset==len(full)
