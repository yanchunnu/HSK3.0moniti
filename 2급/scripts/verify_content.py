"""Compare a rebuilt booklet against its backup and render the changed pages."""
import argparse
from collections import defaultdict
from io import BytesIO
import json
from pathlib import Path
import re

import pymupdf as fitz
from PIL import Image
from pypdf import PdfReader
import zxingcpp

from audio import parse
from booklet import HAN, content_cells, content_items, photos, replacement_photo, writing_content
from verify import render


def answer_table(page):
    answers = dict((int(n),value.strip()) for n,value in
                   re.findall(r'(?m)^(\d{2}) +([^\n]+)$',page.get_text()))
    assert set(answers) == set(range(1,61))
    return answers


def items(page):
    pieces = re.split(r'(?m)^(\d{1,2})\.[ \t]*$',page.get_text())
    return pieces[0],{int(n):body for n,body in zip(pieces[1::2],pieces[2::2])}


def spans(page):
    return [s for b in page.get_text('dict',flags=fitz.TEXTFLAGS_TEXT)['blocks']
            for line in b['lines'] for s in line['spans']]


def item_text(cells):
    return [value for cell in cells for value in cell if value]


def expected_text(writing,reading,listening):
    expected = {}
    for n,entry in writing.items():
        expected[n] = [f"{entry['pinyin']} / {entry['meaning_ko']}",f"? {entry['given_right']}",'→']
    for n,entry in reading.items():
        expected[n] = item_text(content_cells(entry))
    for n,entry in listening.items():
        expected[n] = item_text(content_cells(entry['question']))
    for n,entry in (writing | listening).items():
        expected[n] += [value for option in entry['options']
                        for value in [option['label'],*item_text(content_cells(option))]]
    return expected


def check_images(old,new,replacements,raw,source):
    before,after = [page.get_image_info(hashes=True,xrefs=True) for page in (old,new)]
    assert len(before) == len(after)
    if replacements:
        assert len(after) == 6
        source_page,slots = replacements
        clips = list(photos(raw,source_page))
        labels = [s for s in spans(new) if re.fullmatch('[A-F]',s['text'])
                  and s['origin'][1] < 535]
        assert [s['text'] for s in labels] == list('ABCDEF')
    else:
        slots = {}
    for i,(a,b) in enumerate(zip(before,after)):
        assert a['bbox'] == b['bbox']
        assert (a['width'],a['height']) == (b['width'],b['height'])
        if replacements:
            picture,label = fitz.Rect(b['bbox']),fitz.Rect(labels[i]['bbox'])
            assert picture.y1 <= label.y0 and picture.x0 < label.x0 < label.x1 < picture.x1
        if i not in slots:
            assert a['digest'] == b['digest']
            continue
        clip = clips[i]
        original = source[source_page].get_pixmap(matrix=fitz.Matrix(2,2),clip=clip)
        photo = replacement_photo(slots[i],clip,(original.width,original.height))
        jpg = BytesIO()
        photo.save(jpg,'JPEG',quality=85,optimize=True)
        assert a['digest'] != b['digest']
        assert new.parent.extract_image(b['xref'])['image'] == jpg.getvalue()


def spacings(page, selected=None):
    rows = defaultdict(list)
    for s in spans(page):
        rows[round(s['origin'][1],2)].append(s)
    rows = sorted(rows.items())
    gaps,columns = [],[]
    item = None
    for y,row in rows:
        for span in row:
            if re.fullmatch(r'\d{2}\.',span['text']):
                item = int(span['text'][:-1])
        for han in (s for s in row if re.search(HAN,s['text'])):
            h = fitz.Rect(han['bbox'])
            for later,ruby in rows:
                if not y < later <= y+35:
                    continue
                for sp in ruby:
                    r = fitz.Rect(sp['bbox'])
                    if sp['color']==0x4e5e70 and r.x0 < h.x1 and h.x0 < r.x1:
                        gaps.append(r.y0-h.y1)
        ordered = sorted(row,key=lambda s:s['bbox'][0])
        labels = [i for i,s in enumerate(ordered) if s['text'] in ('A','B','C')]
        if (selected is None or item in selected) and [ordered[i]['text'] for i in labels] == list('ABC'):
            for a,b in zip(labels,labels[1:]):
                columns.append(ordered[b]['bbox'][0]-max(s['bbox'][2] for s in ordered[a:b]))
    return gaps,columns


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('content',type=Path)
    parser.add_argument('--before',type=Path,default=Path('tmp/before_dedup2'))
    args = parser.parse_args()
    content = json.loads(args.content.read_text(encoding='utf8'))
    n = content['set']
    prefix = f'HSK3.0_2급_제{n:02}회_'
    problem,solution = (prefix+suffix+'.pdf' for suffix in ('문제지','정답및해설'))
    path = Path('input/sets')/(prefix+'표지통일_전체듣기QR.pdf')
    raw = PdfReader(path)
    l2,l3,r1 = (content_items(content,part) for part in ('L2','L3','R1'))
    w1 = writing_content(content)
    expected = expected_text(w1,r1,l3)
    with (fitz.open(args.before/problem) as old, fitz.open(Path('output')/problem) as new,
          fitz.open(args.before/solution) as previous, fitz.open(Path('output')/solution) as current,
          fitz.open(path) as source):
        assert (len(old),len(previous)) == (len(new),len(current))
        assert all(Path(d.name).stat().st_size <= 5_000_000 for d in (new,current))
        keys = answer_table(previous[0])
        keys.update({i:e['answer'] for i,e in (l2 | l3 | r1).items()})
        keys.update({i:e['answer_key'] for i,e in w1.items()})
        assert answer_table(current[0]) == keys
        scripts = parse(previous.name)
        for i,entry in (l2 | l3).items():
            assert ''.join(scripts[i]) != ''.join(entry['script'])
            scripts[i] = [line[j:j+32] for line in entry['script'] for j in range(0,len(line),32)]
        assert parse(current.name) == scripts
        for page in current[1:]:
            lines = [line for line in page.get_text().splitlines() if not line.startswith('HSK')]
            assert all(re.fullmatch(r'[\u3400-\u9fff：，、。？！；]+|\d+\.?',line)
                       for line in lines if line)
        assert not any(zxingcpp.read_barcodes(render(p)) for p in current)

        url = f'https://yanchunnu.github.io/-/hsk-listening.html?level=2&set={n}'
        gaps,columns,existing_narrow,numbers = [],[],[],[]
        replaced = l3.keys() | w1.keys()
        for a,b in zip(old,new):
            page = b.number+1
            old_head,old_items = items(a)
            head,new_items = items(b)
            assert head == old_head, page
            assert list(old_items) == list(new_items), page
            numbers.extend(new_items)
            for i,body in new_items.items():
                if i in expected:
                    assert body.split() == ' '.join(expected[i]).split(), (i,body,expected[i])
                else:
                    assert body == old_items[i], (page,i)
            slots = None
            for p,first,last,entries in ((2,6,10,l2),(3,11,15,l2),(6,26,30,r1)):
                replacements = {'ABCDEF'.index(e['answer']):e['image'] for i,e in entries.items()
                                if first <= i <= last and i in new_items}
                if replacements:
                    slots = p,replacements
            check_images(a,b,slots,raw,source)
            matrix = fitz.Matrix(1.65,1.65)
            before,after = render(a,matrix),render(b,matrix)
            assert [c.text for c in zxingcpp.read_barcodes(after)] == ([url] if page==1 else [])
            assert [link['uri'] for link in b.get_links()] == ([url] if page==1 else [])
            g,c = spacings(b,replaced)
            assert len(c) == 2*len(replaced & new_items.keys()), page
            gaps.extend((value,page) for value in g)
            columns.extend((value,page) for value in c)
            untouched = (new_items.keys() - replaced) | {None}
            unchanged_columns = spacings(b,untouched)[1]
            assert unchanged_columns == spacings(a,untouched)[1], page
            existing_narrow.extend((value,page) for value in unchanged_columns if value<20)
            if slots or set(new_items) & expected.keys():
                comparison = Image.new('RGB',(before.width+after.width+12,before.height),'#ccc')
                comparison.paste(before,(0,0))
                comparison.paste(after,(before.width+12,0))
                comparison.save(Path('output/preview')/f'비교2_제{n:02}회-{page:02}.png')
                print('Comparison page',page)
            else:
                assert before.tobytes() == after.tobytes(), page
        assert numbers == list(range(1,61))
        print('60 answers and 60 questions, 25 scripts and 3 examples, replacement images, QR and page counts verified')
        print('Minimum Han to next pinyin (pt, PDF page):',min(gaps))
        print('Minimum option gap on pages with replaced options:',min(columns,default=None))
        print('Existing option gaps below 20 pt:',existing_narrow)
        assert min(gaps)[0]>=3 and all(gap>=20 for gap,_ in columns)


if __name__ == '__main__':
    main()
