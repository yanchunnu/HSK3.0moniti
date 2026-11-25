"""Check the deployed player and MP3 bodies for one numbered HSK 2 site release."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import time
from urllib.request import Request, urlopen

BASE = 'https://yanchunnu.github.io/-/'
LABELS = ('전체','第一部分','第二部分','第三部分')

def check(pair):
    url,local=pair
    request=Request(BASE+url, headers={'User-Agent':'Mozilla/5.0','Cache-Control':'no-cache'})
    with urlopen(request,timeout=30) as response:
        data=response.read()
        if local.suffix=='.html':
            match=data.replace(b'\r\n',b'\n')==local.read_bytes().replace(b'\r\n',b'\n')
        else:
            match=hashlib.sha256(data).digest()==hashlib.sha256(local.read_bytes()).digest()
        assert response.status==200 and match, (url,response.status,match)
        return url,response.status,len(data)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('set_number',type=int,nargs='?',choices=range(1,11))
    parser.add_argument('--level',type=int,choices=(2,3),default=2)
    parser.add_argument('--set',dest='named_set',type=int,choices=range(1,11))
    parser.add_argument('player',type=Path)
    parser.add_argument('--attempts',type=int,default=1)
    args=parser.parse_args()
    number=args.named_set or args.set_number
    if number is None:
        parser.error('supply --set N')
    stem=f'HSK3.0_{args.level}급_제{number:02}회_'
    pairs=[(f'hsk-listening.html?level={args.level}&set={number}',args.player)]
    names=('full','part1','part2','part3','part4') if args.level==3 else ('full','part1','part2','part3')
    labels=('전체','part1','part2','part3','part4') if args.level==3 else LABELS
    for name,label in zip(names,labels):
        pairs.append((f'hsk{args.level}-set{number:02}-{name}.mp3',Path('output/audio')/(stem+label+'.mp3')))
    with ThreadPoolExecutor(max_workers=len(pairs)) as executor:
        for attempt in range(args.attempts):
            try:
                for item in list(executor.map(check,pairs)):
                    print(*item)
                return
            except (AssertionError,OSError) as error:
                print(error,flush=True)
                if attempt+1==args.attempts:
                    raise
                time.sleep(18)

if __name__=='__main__':
    main()
