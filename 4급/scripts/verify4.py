"""Check the two exam PDFs against the original and decode all QR symbols."""
import argparse
from os import environ
from pathlib import Path
import re
import subprocess

from PIL import Image
import pymupdf as fitz
import zxingcpp

from check_option_gaps4 import measure
from source4 import compact
from content_model4 import load

def extracted(path,tool,layout=False):
    args=[tool,'-enc','UTF-8',*(['-layout'] if layout else []),'-','-']
    return subprocess.run(args,input=path.read_bytes(),capture_output=True,check=True).stdout.decode('utf8')

def verify(level,number,tool):
    stem=Path('output')/f'HSK3.0_{level}급_제{number:02}회_'
    question,answer=(stem.with_name(stem.name+kind+'.pdf') for kind in ('문제지','정답및해설'))
    _,keys,transcripts,asks,listen,words,fill,reading,sentences,hints,essay,writing,oral,_=load(number)
    for path in (question,answer):
        assert path.stat().st_size<=5_000_000
        text=extracted(path,tool)
        assert not re.search(r'[123]급|[一二三]级|level\s*=\s*[123]\b|hsk\s*[123](?![\d.])|AI\s*생성',text,re.I),path
        with fitz.open(path) as pdf:
            assert all(len(p.get_text().strip())>35 for p in pdf)
            assert all('HSK 3.0 • '+str(level)+'급' in p.get_text() for p in pdf[1:])
            symbols=[]
            for i,page in enumerate(pdf):
                p=page.get_pixmap(matrix=fitz.Matrix(1.2,1.2))
                im=Image.frombytes('RGB',(p.width,p.height),p.samples)
                symbols.extend((i,code.text) for code in zxingcpp.read_barcodes(im,formats=zxingcpp.BarcodeFormat.QRCode))
            expected=[(0,f'https://yanchunnu.github.io/-/hsk-listening.html?level={level}&set={number}')] if path==question else []
            assert symbols==expected,(path,symbols)
    with fitz.open(question) as qdoc, fitz.open(answer) as adoc:
        qtext='\n'.join(p.get_text() for p in qdoc)
        atext='\n'.join(p.get_text() for p in adoc)
        assert [int(n) for n in re.findall(r'(?m)^(\d+)\.',qtext)]==[*range(1,58), *range(65,76)]
        assert [int(n) for n in re.findall(r"（\s*(5[89]|6[0-4])\s*）",qtext)]==list(range(58,65))
        q,a=compact(qtext),compact(atext)
        blocks=[*listen.values(),*words,*fill.values(),*[v for _,_,rows in reading for _,_,v in rows]]
        content=[v for block in blocks for v in block]
        content += [p for _,p,_ in reading]+[q for _,_,rows in reading for _,q,_ in rows]
        content += [re.sub(r'_+','____',p) for p,_ in sentences]+[v for _,vs in sentences for v in vs]
        content += [*hints.values(),essay,oral[74][0],oral[75][0]]
        for value in content:
            assert compact(value) in q,value
        for value in [*asks.values(),*[v for lines in transcripts.values() for v in lines],
                      *[v for values in writing.values() for v in values],*[v for lines in oral.values() for v in lines]]:
            assert compact(value) in a,value
        assert all(compact(oral[n][-1]) not in q for n in oral)
        answer_rows=re.findall(r'(?m)^(\d+)\.\s*\n([A-F])$',adoc[0].get_text())
        assert [(int(n),key) for n,key in answer_rows]==sorted(keys.items())
        writing_page, = [page for page in qdoc if '第65-69题' in page.get_text()]
        assert re.findall(r'(?m)^(6[5-9])\.',writing_page.get_text())==['65','66','67','68','69']
        assert '例：' in writing_page.get_text()
        # Korean is confined to the requested running header.
        header=f'HSK 3.0 • {level}급 제{number}회 모의고사'
        assert not re.search('[가-힣]',atext.replace(header,''))
    print('문항 75개, 객관식 정답 64개, 쓰기·말하기 답안, 듣기 원문, 표지 QR 검사 통과')
    gap,rows,count=measure(question,tool)
    print(f'선택지 {count}개, 같은 줄 인접 간격 {rows}개, 최소 {gap:.3f}pt')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--level',type=int,choices=[4],required=True)
    ap.add_argument('--set',type=int,choices=range(1,11),required=True)
    args=ap.parse_args()
    verify(args.level,args.set,environ.get('PDFTOTEXT','pdftotext'))

if __name__=='__main__':
    main()


