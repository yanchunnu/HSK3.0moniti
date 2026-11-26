"""Check every option row in the question PDF using Poppler word bounds."""
import argparse
from collections import defaultdict
from os import environ
from pathlib import Path
import re
import subprocess
from xml.etree import ElementTree as ET

def measure(path, tool):
    result = subprocess.run([tool,'-enc','UTF-8','-bbox','-','-'],
                            input=path.read_bytes(),capture_output=True,check=True)
    gaps = []
    count = 0
    for n,page in enumerate(ET.fromstring(result.stdout).findall('.//{*}page'),1):
        rows = defaultdict(list)
        for word in page.findall('{*}word'):
            x,y,right = (float(word.get(attr)) for attr in ('xMin','yMin','xMax'))
            rows[round(y,2)].append((x,right,word.text or ''))
        for words in rows.values():
            words.sort()
            indexes = [i for i,(_,_,token) in enumerate(words) if re.fullmatch('[A-F]',token) and not (i>0 and words[i-1][2].endswith('（'))]
            count += len(indexes)
            for prev,curr in zip(indexes,indexes[1:]):
                assert curr>prev+1,(n,words)
                gap = words[curr][0]-words[curr-1][1]
                assert gap>=20,(n,gap,words)
                gaps.append(gap)
    expected = 32*4+5*4+2*6+2*3+15*4+4+7+3
    assert count == expected,(count,expected)
    return min(gaps),len(gaps),count

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--level',type=int,choices=[4],required=True)
    parser.add_argument('--set',type=int,choices=range(1,11),required=True)
    parser.add_argument('--pdftotext',default=environ.get('PDFTOTEXT','pdftotext'))
    args=parser.parse_args()
    pdf=Path('output')/f'HSK3.0_{args.level}급_제{args.set:02}회_문제지.pdf'
    gap,rows,count=measure(pdf,args.pdftotext)
    print(f'{count}개 선택지, 같은 줄의 인접 간격 {rows}개, 최소 {gap:.3f}pt')

if __name__=='__main__':
    main()


