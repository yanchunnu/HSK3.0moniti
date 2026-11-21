import argparse, re, subprocess
from pathlib import Path
import imageio_ffmpeg, numpy as np, sherpa_onnx

FF = imageio_ffmpeg.get_ffmpeg_exe()
RATE = 16000

def recognizer(model):
    return sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=str(model/'model.onnx'), tokens=str(model/'tokens.txt'),
        language='zh', use_itn=False, num_threads=3)

def recognize(asr, samples):
    stream = asr.create_stream()
    stream.accept_waveform(RATE, np.pad(samples.astype('float32')/32768, (1600,2000)))
    asr.decode_stream(stream)
    return stream.result.text.strip()

def decode(path, filters=None):
    cmd = [FF,'-hide_banner','-i',str(path)]
    if filters:
        cmd += ['-af', filters]
    cmd += ['-ac','1','-ar',str(RATE),'-f','s16le','-']
    result = subprocess.run(cmd,capture_output=True,check=True)
    return np.frombuffer(result.stdout,dtype='<i2'), result.stderr.decode(errors='replace')

def analyze(path, asr, target):
    samples, log = decode(path,'silencedetect=n=-36dB:d=0.45')
    gaps = [(float(end)-float(duration),float(end)) for end,duration in
            re.findall(r'silence_end: ([\d.]+) \| silence_duration: ([\d.]+)',log)]
    with target.open('w',encoding='utf8',buffering=1) as report:
        print('duration',len(samples)/RATE,file=report)
        cursor = 0
        for start, end in gaps+[(len(samples)/RATE,len(samples)/RATE)]:
            if start-cursor > .22:
                for left in np.arange(cursor,start,18):
                    right = min(left+18,start)
                    text = recognize(asr,samples[round(left*RATE):round(right*RATE)])
                    print(f'{left:.3f}\t{right:.3f}\t{end-start:.3f}\t{text}',file=report)
            cursor = end

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('model',type=Path)
    args = parser.parse_args()
    asr = recognizer(args.model)
    for n,path in enumerate(sorted(Path('input').glob('참고*.mp3')),1):
        analyze(path,asr,Path(f'tmp/ref{n}.tsv'))
