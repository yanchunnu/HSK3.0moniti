"""Verify one numbered booklet against the source and write visual review sheets."""
import argparse
from collections import Counter
from pathlib import Path
import re

from PIL import Image, ImageDraw
import pymupdf as fitz
import zxingcpp

from booklet import answers, PAGE_RANGES, PARTS

def render(page,matrix=fitz.Matrix(1.5,1.5)):
    pix=page.get_pixmap(matrix=matrix)
    return Image.frombytes('RGB',(pix.width,pix.height),pix.samples)

def compact(text):
    return ''.join(text.split())

def sheet(images,target):
    output=Image.new('RGB',(300*len(images),445),'#dddddd')
    for x,image in enumerate(images):
        image.thumbnail((292,419))
        output.paste(image,(x*300+4,20))
        ImageDraw.Draw(output).text((x*300+8,3),str(x+1),fill='black')
    output.save(target)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('set_number',type=int,choices=range(1,11))
    n=parser.parse_args().set_number
    stem=f'HSK3.0_2급_제{n:02}회_'
    with (fitz.open(Path('input/sets')/(stem+'표지통일_전체듣기QR.pdf')) as source,
          fitz.open(Path('output')/(stem+'문제지.pdf')) as question,
          fitz.open(Path('output')/(stem+'정답및해설.pdf')) as solution):
        keys,scripts=answers(source)
        assert len(question)==16
        assert Path(question.name).stat().st_size<=5_000_000
        answer_text=solution[0].get_text()
        for i,answer in keys.items():
            assert re.search(rf'(?m)^{i:02}\s+{re.escape(answer)}\s*$',answer_text),(i,answer)
        contents=[]
        for page in solution[1:]:
            text=page.get_text()
            assert not re.search('[가-힣À-ž]',text)
            contents += [line for line in text.splitlines() if line and line not in
                         (*PARTS,'听力原文') and not line.startswith('HSK') and not line.isdigit()]
        transcript='\n'.join(contents)
        assert [int(i) for i in re.findall(r'(?m)^(\d+)\.$',transcript)]==list(range(1,26))
        assert transcript.splitlines().count('例')==3
        for i,lines in scripts.items():
            hit=re.search(rf'(?ms)^{i}\.\n(.*?)(?=^\d+\.$|^例$|\Z)',transcript)
            assert compact(hit[1])==''.join(lines),(i,hit[1],lines)
        url=f'https://yanchunnu.github.io/-/hsk-listening.html?level=2&set={n}'
        for i,page in enumerate(question):
            assert [item.text for item in zxingcpp.read_barcodes(render(page))]==([url] if i==0 else [])
            assert [item['uri'] for item in page.get_links()]==([url] if i==0 else [])
            text=compact(page.get_text())
            assert not any(item in text for item in ('사진AI생성','한국어해설','답안기록지'))
        for p,(first,last) in enumerate(PAGE_RANGES,1):
            result=question[p+1 if p<=5 else p+2].get_text()
            assert re.findall(r'(?m)^0?(\d{1,2})\.(?=\s|$)',result)==[str(i) for i in range(first,last+1)], (p,result)
            if p>=4 and p!=6:
                original=source[p].get_text(clip=fitz.Rect(37,149,558,788))
                omitted=Counter(original.split())-Counter(result.split())
                assert not omitted,(p,omitted)
        sheet([render(page) for page in solution],Path(f'tmp/answers{n:02}.jpg'))
        print('60 source answers, 25 transcripts, 60 question numbers, source text, cover QR and links verified')

if __name__=='__main__':
    main()
