"""Confirm the published player and all four MP3 bodies match the release."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
import time
from urllib.request import Request, urlopen

BASE = 'https://yanchunnu.github.io/-/'

def check(pair):
    resource, local = pair
    url = BASE + resource
    request = Request(url,headers={'User-Agent':'Mozilla/5.0','Cache-Control':'no-cache'})
    with urlopen(request,timeout=30) as response:
        payload = response.read()
        expected = local.read_bytes()
        if local.suffix=='.html':
            payload,expected=(data.replace(b'\r\n',b'\n') for data in (payload,expected))
        assert response.status==200 and sha256(payload).digest()==sha256(expected).digest(), url
        return response.status,len(payload),url

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--level',type=int,choices=[4],required=True)
    parser.add_argument('--set',type=int,choices=range(1,11),required=True)
    parser.add_argument('player',type=Path)
    parser.add_argument('--attempts',type=int,default=1)
    args=parser.parse_args()
    stem=f'HSK3.0_{args.level}급_제{args.set:02}회_'
    pairs=[(f'hsk-listening.html?level={args.level}&set={args.set}',args.player)]
    for remote,local in [('full','전체'),('part1','part1'),('part2','part2'),('part3','part3')]:
        pairs.append((f'hsk{args.level}-set{args.set:02}-{remote}.mp3',Path('output/audio')/(stem+local+'.mp3')))
    with ThreadPoolExecutor(max_workers=len(pairs)) as executor:
        for attempt in range(args.attempts):
            futures=[executor.submit(check,pair) for pair in pairs]
            try:
                results=[future.result() for future in futures]
            except (AssertionError,OSError) as error:
                print(f'배포 대기 {attempt+1}/{args.attempts} {error}',flush=True)
                if attempt+1==args.attempts:
                    raise
                time.sleep(18)
            else:
                for item in results:
                    print(*item)
                return

if __name__=='__main__':
    main()

