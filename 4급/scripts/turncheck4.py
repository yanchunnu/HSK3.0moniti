"""Check the four-turn HSK4 dialogues for questions 8–14 and their shared example."""

import json
from pathlib import Path
import re


SCRIPTS = Path(__file__).resolve().parent
NUMBERS = set(range(8, 15))
LABELS = ('男', '女', '男', '女', '问')
EMBEDDED_LABEL = re.compile(r'[男女问]\s*[：:]')


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def valid_line(line, label):
    if not isinstance(line, str) or not line.startswith(f'{label}：') or line.splitlines() != [line]:
        return False
    body = line[2:]
    return bool(body.strip()) and not EMBEDDED_LABEL.search(body)


def valid_lines(lines, labels):
    return (isinstance(lines, list) and len(lines) == len(labels)
            and all(valid_line(line, label) for line, label in zip(lines, labels)))


def main():
    errors = []
    passed = 0
    for n in range(1, 11):
        label = f'제{n:02d}회'
        exam = read_json(SCRIPTS / 'content4' / f'{label}.json')
        rows = [row for row in exam['items'] if row['number'] in NUMBERS]
        if exam['set'] != n or sorted(row['number'] for row in rows) != sorted(NUMBERS):
            errors.append(f'{label}: expected one item for every number 8–14')
            continue
        for row in rows:
            if (valid_lines(row.get('transcript'), LABELS[:4])
                    and valid_line(row.get('question'), LABELS[4])):
                passed += 1
            else:
                errors.append(f'{label} #{row["number"]}: expected 男 / 女 / 男 / 女 / 问')

    # The booklet and audio use l1b immediately before questions 8–14.
    example = read_json(SCRIPTS / '例01.json')['l1b']
    example_ok = valid_lines(example.get('lines'), LABELS)
    if not example_ok:
        errors.append('例01.json l1b: expected 男 / 女 / 男 / 女 / 问')
    for error in errors:
        print(error)
    print(f'Questions: {passed}/70, shared example: {int(example_ok)}/1')
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
