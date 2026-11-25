"""Verify one numbered booklet against the source and write visual review sheets."""
import argparse
from collections import Counter
from pathlib import Path
import re

from PIL import Image, ImageDraw
import pymupdf as fitz
import zxingcpp

from booklet import (answers, BODY_SIZE, PINYIN_SIZE, PAGE_RANGES, PARTS,
                     RUBY_SCALE, SECTION_HEADERS, range_title)

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
    parser.add_argument('set_number',type=int,nargs='?',choices=range(1,11))
    parser.add_argument('--level',type=int,choices=(2,3),default=2)
    parser.add_argument('--set',dest='named_set',type=int,choices=range(1,11))
    args=parser.parse_args()
    n=args.named_set or args.set_number
    if n is None:
        parser.error('supply --set N')
    if args.level == 3:
        from verify3 import verify
        return verify(n)
    stem=f'HSK3.0_2급_제{n:02}회_'
    with (fitz.open(Path('input/sets')/(stem+'표지통일_전체듣기QR.pdf')) as source,
          fitz.open(Path('output')/(stem+'문제지.pdf')) as question,
          fitz.open(Path('output')/(stem+'정답및해설.pdf')) as solution):
        keys,scripts=answers(source)
        assert not any(zxingcpp.read_barcodes(render(page)) for page in solution)
        assert all(Path(pdf.name).stat().st_size<=5_000_000 for pdf in (question,solution))
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
        number_pattern = r'(?m)^0?(\d{1,2})\.(?=\s|$)'
        numbered = [(page,[int(n) for n in re.findall(number_pattern,page.get_text())])
                    for page in question]
        numbered = [(page,numbers) for page,numbers in numbered if numbers]
        assert [n for _,numbers in numbered for n in numbers] == list(range(1,61))
        section_pages = {}
        for p,(first,last) in enumerate(PAGE_RANGES,1):
            pages = [(page,numbers) for page,numbers in numbered if first <= numbers[0] <= last]
            assert [n for _,numbers in pages for n in numbers] == list(range(first,last+1))
            section_pages[p] = [page for page,_ in pages]
            heading,continued = SECTION_HEADERS.get(p,((first,last),False))
            for index,(page,_) in enumerate(pages):
                assert range_title(heading,continued or index>0) in page.get_text()
                for block in page.get_text('dict',flags=fitz.TEXTFLAGS_TEXT)['blocks']:
                    for line in block['lines']:
                        for span in line['spans']:
                            y = span['origin'][1]
                            size = span['size']/(841.89/540)
                            if span['color']==0x4e5e70:
                                # MuPDF reports the geometric mean of the two axis scales.
                                assert abs(size-PINYIN_SIZE*RUBY_SCALE**.5)<.02, (p,span)
                            elif p>=4 and y>=188 and span['text']!='例' and span['font']=='SimHei':
                                assert abs(size-BODY_SIZE)<.02, (p,span)
                            if 188 <= y < 790:
                                x0,y0,x1,y1 = span['bbox']
                                assert x0>=30 and x1<=558 and y0>=160 and y1<793, (p,span)
        def item_text(pages):
            text = '\n'.join(pages)
            parts = re.split(r'(?m)^(\d{2})\.\s*',text)
            return {int(n): Counter(compact(body)) for n,body in zip(parts[1::2],parts[2::2])}

        original = item_text(source[i].get_text(clip=fitz.Rect(37,149,558,788))
                             for i in (10,11))
        result = item_text(page.get_text(clip=fitz.Rect(37,295 if p==10 and index==0 else 162 if index else 179,558,790))
                           for p in (10,11) for index,page in enumerate(section_pages[p]))
        assert original.keys()==result.keys()==set(range(46,51))
        for item in original:
            assert original[item]==result[item], (item,original[item]-result[item],result[item]-original[item])
        for p in (4,5,6,7,8,9,12,13):
            start = 442 if p==6 else 149
            original = source[p].get_text(clip=fitz.Rect(37,start,558,788))
            result = '\n'.join(page.get_text() for page in section_pages[p])
            omitted = Counter(compact(original))-Counter(compact(result))
            assert not omitted,(p,omitted)
        sheet([render(page) for page in solution],Path(f'tmp/answers{n:02}.jpg'))
        print('60 source answers, 25 transcripts, 60 question numbers, source text, cover QR and links verified')

if __name__=='__main__':
    main()
