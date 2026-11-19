import argparse
import json
import re
import subprocess
from pathlib import Path

import numpy as np
import sherpa_onnx

ROOT = Path(__file__).resolve().parent
VOICES = {'female': 5, 'male': 59}
DIGITS = '零一二三四五六七八九'
ANSWER_TIME = 13.73
TARGET_RATE = 2.8


def question_number(number):
    if number < 10:
        return DIGITS[number]
    if number == 20:
        return '二十'
    return '十' + (DIGITS[number % 10] if number % 10 else '')


def load_voice(model):
    config = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(
                model=str(model / 'model.onnx'),
                voices=str(model / 'voices.bin'),
                tokens=str(model / 'tokens.txt'),
                lexicon=str(model / 'lexicon-zh.txt'),
                data_dir=str(model / 'espeak-ng-data'),
            ),
            num_threads=2,
            provider='cpu',
        ),
        rule_fsts=','.join(str(model / name) for name in ('date-zh.fst', 'phone-zh.fst')),
    )
    return sherpa_onnx.OfflineTts(config)


def render(engine, text, role):
    config = sherpa_onnx.GenerationConfig()
    config.sid = VOICES[role]
    config.speed = 1.0
    raw = np.asarray(engine.generate(text, config).samples, dtype=np.float32)
    signal = np.flatnonzero(np.abs(raw) > 0.004)
    if not len(signal):
        raise ValueError(f'No speech was generated for {text}')
    padding = round(engine.sample_rate * 0.05)
    return raw[max(0, signal[0] - padding):signal[-1] + padding + 1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('model', type=Path, help='Extracted kokoro-multi-lang-v1_1 model')
    args = parser.parse_args()
    engine = load_voice(args.model)
    rate = engine.sample_rate
    data = json.loads((ROOT / 'listening-script.json').read_text())
    sections = data['sections']
    if [len(section) for section in sections] != [5] * 4:
        raise ValueError('Expected four sections of five questions.')
    lines = {('female', '例如。')}
    for section in [*sections, list(data['examples'].values())]:
        lines.update((item['role'], item['text']) for group in section for item in group)
    lines.update(('female', f'第{question_number(n)}题。') for n in range(1, 21))
    audio = {(role, text): render(engine, text, role) for role, text in sorted(lines)}
    character_count = sum(len(re.findall(r'[\u3400-\u9fff]', text)) for _, text in lines)
    native_rate = character_count * rate / sum(map(len, audio.values()))
    tempo = min(1.15, max(0.72, TARGET_RATE / native_rate))
    print(f'Native {native_rate:.2f} characters/s, tempo {tempo:.3f}', flush=True)

    for key, samples in audio.items():
        result = subprocess.check_output([
            'ffmpeg', '-v', 'error', '-f', 'f32le', '-ar', str(rate), '-ac', '1',
            '-i', 'pipe:0', '-af', f'atempo={tempo:.6f}', '-f', 'f32le', 'pipe:1',
        ], input=samples.astype('<f4').tobytes())
        if not result:
            raise ValueError(f'Tempo filter returned no samples for {key}')
        audio[key] = np.frombuffer(result, dtype='<f4')

    output = ROOT / 'hsk1-set01-examples'
    output.mkdir(exist_ok=True)

    def gap(seconds):
        return np.zeros(round(seconds * rate), dtype=np.float32)

    def repeated(chunks, lines, final_gap):
        for pause in (2.0, final_gap):
            for index, line in enumerate(lines):
                if index:
                    chunks.append(gap(0.85))
                chunks.append(audio[line['role'], line['text']])
            chunks.append(gap(pause))

    def save(name, chunks):
        destination = output / f'hsk1-set01-{name}-mandarin.mp3'
        samples = np.concatenate(chunks).astype('<f4')
        subprocess.run([
            'ffmpeg', '-v', 'error', '-y', '-f', 'f32le', '-ar', str(rate),
            '-ac', '1', '-i', 'pipe:0', '-af', 'loudnorm=I=-19:TP=-2:LRA=7',
            '-ar', '44100', '-c:a', 'libmp3lame', '-b:a', '96k', str(destination),
        ], input=samples.tobytes(), check=True)
        print(f'{destination.name} {len(samples) / rate:.2f}s', flush=True)

    for part, questions in enumerate(sections, start=1):
        chunks = [gap(0.4), audio['female', '例如。'], gap(0.85)]
        repeated(chunks, data['examples'][str(part)], 1.0)
        save(f'example{part}', chunks)
        for number, lines in enumerate(questions, start=(part - 1) * 5 + 1):
            chunks.extend((audio['female', f'第{question_number(number)}题。'], gap(0.85)))
            repeated(chunks, lines, ANSWER_TIME)
        save(f'part{part}', chunks)


if __name__ == '__main__':
    main()
