"""Audit Level 3 question and solution PDFs against the original source."""
import argparse
from pathlib import Path
import re

import pymupdf as fitz
from PIL import Image
import zxingcpp

from level3 import EX, parse

HAN = re.compile(r'[\u3400-\u9fff]+')


def compact(value):
    return re.sub(r'\s+', '', value)


def rendered_text(document):
    return compact(''.join(page.get_text() for page in document))


def verify(number):
    original, pages, answers, listening, oral = parse(number)
    stem = f'HSK3.0_3급_제{number:02}회_'
    with fitz.open(Path('output')/(stem+'문제지.pdf')) as question, \
         fitz.open(Path('output')/(stem+'정답및해설.pdf')) as solution:
        url = f'https://yanchunnu.github.io/-/hsk-listening.html?level=3&set={number}'
        for doc in (question, solution):
            for i,page in enumerate(doc):
                pix = page.get_pixmap()
                image = Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
                qr = [barcode.text for barcode in zxingcpp.read_barcodes(image)]
                assert qr == ([url] if i==0 and doc is question else []), (i, qr)
                text = page.get_text()
                assert text.strip()
                assert f'{2}급' not in text, (doc.name, i+1)
                if doc is question and i:
                    header = f'HSK 3.0 • 3급 제{number}회 모의고사'
                    assert text.splitlines().count(header) == 1, (i, text)
                    assert page.get_text(clip=fitz.Rect(0,795,page.rect.width,841)).strip() == str(i)
                for block in page.get_text('blocks'):
                    if block[6] == 0:
                        assert page.rect.contains(fitz.Rect(block[:4])), (i,block)
        qtext = ''.join(page.get_text() for page in question[2:-3])
        assert [int(x) for x in re.findall(r'(?m)^\s*(\d+)\.', qtext)] == list(range(1,71))
        printed = compact(qtext)
        source_choices = re.findall(
            r'(?m)^\s*(\d+)\.\s+A\s+(.+?)\s+B\s+(.+?)\s+C\s+([^\n]+)', pages[2])
        assert len(source_choices) == 20
        for n, a, b, c in source_choices:
            assert compact(f'{n}.A{a}B{b}C{c}') in printed, n
        for left, right in ((0,290),(290,596)):
            col = original[3].get_text(clip=fitz.Rect(left,40,right,780),sort=True)
            for n, text in re.findall(r'(?m)^\s*([34]\d|50)\.\s*(.+)$',col):
                text=re.sub(r'\(_+\)|（_+）','（）',text)
                assert compact(f'{n}.{text}') in printed, n
        passages = re.findall(
            r'(?ms)^\s*(5[1-9]|60)\.\s*(.*?)\s*★\s*(.*?)\s*A\s+(.+?)\s+B\s+(.+?)\s+C\s+([^\n]+)',pages[4])
        assert len(passages) == 10
        for n, body, prompt, a,b,c in passages:
            assert compact(f'{n}.{body}★{prompt}A{a}B{b}C{c}') in printed, n
        for pageno, count in [(3,8),(4,5),(len(question)-3,6),(len(question)-1,5)]:
            assert len(question[pageno-1].get_image_info()) == count, pageno
        atext = compact(solution[0].get_text())
        for n, value in answers.items():
            assert f'{n}.{value}' in atext, (n,value)
        speech_q = rendered_text(question[-3:])
        speech_a = rendered_text(solution[1:3])
        for n, lines in oral.items():
            if n < 14:
                assert compact(lines[0]) not in speech_q, n
            else:
                assert compact(lines[0]) in speech_q, n
                assert compact(lines[-1]) not in speech_q, n
            for line in lines:
                assert compact(line) in speech_a, n
        transcripts = rendered_text(solution[3:])
        for n, lines in listening.items():
            for line in lines:
                assert compact(line) in transcripts, (n, line)
        for key, lines in EX.items():
            if key.startswith('listening'):
                for line in lines:
                    assert compact(line) in transcripts, line
        earlier = []
        for level in (1,2):
            for path in sorted(Path(f'../HSK{level}_재배열/output').glob('*문제지.pdf')):
                with fitz.open(path) as pdf:
                    earlier.append(rendered_text(pdf))
        for lines in EX.values():
            for line in lines:
                normalized = compact(line.partition('：')[-1] if '：' in line else line)
                if len(''.join(HAN.findall(normalized))) >= 6:
                    assert all(normalized not in prior for prior in earlier), normalized
        print(f'QR, 70 written items and answers, 30 listening scripts, 15 oral items, and example texts verified against {len(earlier)} prior booklets.')


if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--level', type=int, choices=[3], required=True)
    ap.add_argument('--set', type=int, choices=range(1,11), required=True)
    verify(ap.parse_args().set)
