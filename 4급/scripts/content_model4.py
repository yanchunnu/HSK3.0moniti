"""Convert the numbered original exam to editable JSON and back."""
import json
from pathlib import Path

import pymupdf as fitz

from source4 import parse

DIRECTORY = Path(__file__).with_name('content4')


def extract(number):
    doc, keys, transcripts, asks, listen, words, fill, reading, sentences, hints, essay, writing, oral, scopes = parse(number)
    items = {n: {'number': n, **({'answer': keys[n]} if n in keys else {})} for n in range(1, 76)}
    for start, end in scopes.items():
        for n in range(start, end + 1):
            items[n].update(scope=[start, end], question=asks[n], options=listen[n])
        items[start]['transcript'] = transcripts[start]
    for n, lines in fill.items():
        items[n].update(lines=lines, bank=0 if n <= 37 else 1)
    for scope, passage, rows in reading:
        start, end = rows[0][0], rows[-1][0]
        for n, question, options in rows:
            items[n].update(scope=[start, end], question=question, options=options)
        items[start].update(scope_label=scope, passage=passage)
    for n in range(58, 65):
        items[n]['bank'] = 0 if n <= 60 else 1
    pics = sorted((info['bbox'] for info in doc[8].get_image_info() if info['width'] > 900),
                  key=lambda r: (round(r[1] / 10), r[0]))
    assert len(pics) == 5
    for n, bbox in zip(range(65, 70), pics):
        items[n].update(hint=hints[n], models=writing[n], image={'page': 8, 'bbox': bbox})
    items[70].update(prompt=essay, models=writing[70])
    for n in oral:
        items[n]['model'] = oral[n][-1]
        if n >= 74:
            items[n]['question'] = oral[n][0]
    bbox, = (info['bbox'] for info in doc[9].get_image_info() if info['width'] > 900)
    items[73]['image_strip'] = {'page': 9, 'bbox': bbox, 'panels': 3}
    return {'set': number, 'source_pdf': doc.name, 'items': list(items.values()),
            'word_banks': words, 'sentence_banks': sentences}


def read_content(number):
    return json.loads((DIRECTORY / f'제{number:02}회.json').read_text(encoding='utf8'))


def write_content(exam):
    DIRECTORY.mkdir(exist_ok=True)
    (DIRECTORY / f"제{exam['set']:02}회.json").write_text(
        json.dumps(exam, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def load(number):
    exam = read_content(number)
    items = {row['number']: row for row in exam['items']}
    assert exam['set'] == number and sorted(items) == list(range(1, 76))
    doc = fitz.open(exam['source_pdf'])
    keys = {n: items[n]['answer'] for n in range(1, 65)}
    transcripts = {n: row['transcript'] for n, row in items.items() if 'transcript' in row}
    scopes = {n: items[n]['scope'][1] for n in transcripts}
    asks = {n: items[n]['question'] for n in range(1, 33)}
    listen = {n: tuple(items[n]['options']) for n in asks}
    words = [tuple(bank) for bank in exam['word_banks']]
    fill = {n: tuple(items[n]['lines']) for n in range(33, 43)}
    reading = [(row['scope_label'], row['passage'],
                [(i, items[i]['question'], tuple(items[i]['options']))
                 for i in range(n, row['scope'][1] + 1)])
               for n, row in items.items() if 'scope_label' in row]
    sentences = [(passage, tuple(options)) for passage, options in exam['sentence_banks']]
    hints = {n: items[n]['hint'] for n in range(65, 70)}
    writing = {n: items[n]['models'] for n in range(65, 71)}
    oral = {n: ([items[n]['question']] if n >= 74 else []) + [items[n]['model']]
            for n in range(71, 76)}
    return (doc, keys, transcripts, asks, listen, words, fill, reading, sentences, hints,
            items[70]['prompt'], writing, oral, scopes)
