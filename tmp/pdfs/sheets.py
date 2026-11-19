from PIL import Image,ImageDraw
from pathlib import Path
p=Path('tmp/pdfs')
for tag in ['ref','src']:
 files=sorted(p.glob(tag+'-*.png'))
 for start in range(0,len(files),8):
  group=files[start:start+8]
  sheet=Image.new('RGB',(1100,824),'#dddddd')
  draw=ImageDraw.Draw(sheet)
  for i,f in enumerate(group):
   im=Image.open(f); im.thumbnail((271,382))
   x=i%4*275;y=i//4*412
   sheet.paste(im,(x,y+22));draw.text((x+5,y+3),f.stem,fill='black')
  sheet.save(p/f'{tag}{start}.jpg',quality=90)
