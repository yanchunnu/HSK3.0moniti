from pathlib import Path
from PIL import Image,ImageChops
from pypdf import PdfReader
import pypdfium2 as pdfium
import numpy as np

src_path=next(Path('input/sets').glob('*01*.pdf'))
out_path=next(Path('output').glob('*.pdf'))
a,b=pdfium.PdfDocument(src_path),pdfium.PdfDocument(out_path)
assert len(a)==22 and len(b)==27
pairs=[(0,0)]+[(n,n+5) for n in range(9,22)]
for i,j in pairs:
    sa=a[i].render(scale=1).to_pil()
    sb=b[j].render(scale=1).to_pil()
    assert not ImageChops.difference(sa,sb).getbbox(),(i,j)
print('Cover and original appendix render pixel-identically (14 pages).')
for i in (1,2,3):
    source=np.asarray(a[i].render(scale=4).to_pil().convert('L'))
    result=np.asarray(b[i+1].render(scale=4).to_pil().convert('L'))
    def modules(image,box):
        sx=(a[0].get_width()*4)/382
        sy=(a[0].get_height()*4)/540
        x1,y1,x2,y2=box
        ink=image[round(y1*sy):round(y2*sy),round(x1*sx):round(x2*sx)]<128
        ys,xs=np.where(ink)
        ink=ink[ys.min():ys.max()+1,xs.min():xs.max()+1]
        first=next(j for j in range(1,ink.shape[1]) if not ink[2,j])
        size=min(range(21,90,4),key=lambda n:abs(n-7*ink.shape[1]/first))
        assert size<89 and size>=21
        y=((np.arange(size)+.5)*ink.shape[0]/size).astype(int)
        x=((np.arange(size)+.5)*ink.shape[1]/size).astype(int)
        return ink[np.ix_(y,x)]
    q1=modules(source,(310,33,352,76))
    q2=modules(result,(313,40,353,79))
    assert np.array_equal(q1,q2),(q1.shape,q2.shape)
    print(f'Listening QR {i}: identical {q1.shape[0]}x{q1.shape[1]} modules.')
pdf=PdfReader(out_path)
key=pdf.pages[13].extract_text()
expected='ABCBA CABCB EAFCD BCABC BEACD CEABD DCBEA BACBA'.replace(' ','')
assert all(f'{i}  {letter}' in key for i,letter in enumerate(expected,1))
for f in Path('output/preview').glob('*.png'):
    with Image.open(f) as im:
        im.verify()
print('40 keyed answers and preview PNG integrity verified.')

