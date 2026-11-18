"""VoxCPM2 native CLI adapter for narrate.py; settings stay in ignored runtime JSON."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def run_serial(executable, options, models, requests, required):
    for number, request in enumerate(requests, 1):
        command = [str(executable), '-t', request['text'], '--prompt-wav', request['prompt_wav'],
                   '--prompt-text', request['prompt_text'], '--seed', str(request['seed']),
                   '-o', request['output'], *options, *models]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f"Native synthesis failed on request {number}:\n{result.stderr[-4000:]}")
        if required and required not in result.stderr + result.stdout:
            raise RuntimeError('Expected native backend was not confirmed')
        yield number


def run_batch(executable, options, models, requests, required, tmp):
    batch_path = tmp / 'requests.jsonl'
    with batch_path.open('w', encoding='utf-8') as f:
        for request in requests:
            f.write(json.dumps(request, ensure_ascii=False) + '\n')

    log_path = tmp / 'engine.log'
    command = [str(executable), '--batch', str(batch_path), *options, *models]
    marker = 'voxcpm2-batch-complete '
    with log_path.open('wb') as log, subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=log, text=True, encoding='utf-8', errors='replace'
    ) as process:
        completed = 0
        try:
            for message in process.stdout:
                if not message.startswith(marker):
                    continue
                completed += 1
                if message.strip() != f'{marker}{completed}' or completed > len(requests):
                    raise RuntimeError(f'Unexpected native batch response: {message.strip()}')
                if completed == 1 and required and required not in log_path.read_text(encoding='utf-8', errors='replace'):
                    raise RuntimeError('Expected native backend was not confirmed')
                yield completed
            if process.wait() or completed != len(requests):
                with log_path.open('rb') as f:
                    f.seek(max(0, log_path.stat().st_size - 4000))
                    tail = f.read().decode('utf-8', errors='replace')
                raise RuntimeError(f'Native batch stopped after {completed}/{len(requests)} requests:\n{tail}')
        finally:
            if process.poll() is None:
                process.kill()


def generate(args, root, bank, groups, index):
    import numpy as np
    import soundfile as sf

    config_path = args.native_config.resolve()
    cfg = json.loads(config_path.read_text(encoding='utf-8'))
    use_batch = cfg.get('batch', False)
    if not isinstance(use_batch, bool):
        raise ValueError('Native runtime batch setting must be true or false')
    batch_rows = cfg.get('batch_rows', 1)
    if type(batch_rows) is not int or batch_rows not in (1, 2):
        raise ValueError('Native runtime batch_rows must be 1 or 2')
    if batch_rows == 2 and not use_batch:
        raise ValueError('Native runtime batch_rows=2 requires batch=true')

    def resource(key):
        p = Path(cfg[key]).expanduser()
        p = (config_path.parent / p).resolve() if not p.is_absolute() else p
        if not p.is_file():
            raise ValueError(f'Native runtime resource missing: {key}')
        return p

    executable, base, acoustic = [resource(k) for k in ('executable', 'base_model', 'acoustic_model')]
    model_hashes = {'base': sha(base), 'acoustic': sha(acoustic)}
    executable_hash = sha(executable)
    cap = int(cfg.get('max_steps', 1000))
    steps = int(cfg.get('timesteps', 30))
    guidance = float(cfg.get('cfg', 2.0))
    if cap < 1 or steps < 1:
        raise ValueError('Decode and solver step limits must be positive')
    required = cfg.get('backend_marker')
    options = ['--timesteps', str(steps), '--cfg', str(guidance), '--steps', str(cap)]
    models = [str(base), str(acoustic)]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    provenance = Path(args.provenance) if args.provenance else out / 'provenance.json'
    provenance.parent.mkdir(parents=True, exist_ok=True)
    records = json.loads(provenance.read_text()) if provenance.exists() else {'takes': {}}
    invocation = 'batch' if use_batch else 'per-line CLI'
    print(f'Native continuation cloning ({invocation}).', flush=True)
    with tempfile.TemporaryDirectory(prefix='.native-', dir=out) as temp_dir:
        tmp = Path(temp_dir).resolve()
        requests, takes = [], []
        for mood_number, (mood, lines) in enumerate(groups.items(), 1):
            prompt = (root / bank[mood]['file']).resolve()
            prompt_dir = tmp / f'mood-{mood_number}'
            prompt_dir.mkdir()
            cli_prompt, converted = pcm16_prompt(prompt, prompt_dir, sf)
            prompt_info = {'prompt_mood': mood, 'prompt_file': str(prompt), 'prompt_sha256': sha(prompt),
                           'prompt_cli': converted, 'prompt_text': bank[mood]['text']}
            for line in lines:
                position = index[line['id']]
                seed = args.seed + position - 1
                if use_batch:
                    seed &= 0xffffffff
                filename = f'output_{position:03d}.wav'
                requests.append({'text': line['say'], 'seed': seed,
                                 'output': str(tmp / filename), 'prompt_wav': str(cli_prompt),
                                 'prompt_text': bank[mood]['text']})
                takes.append((line, seed, filename, prompt_info))

        paired_count = len(requests) - len(requests) % 2 if batch_rows == 2 else 0
        if paired_count:
            options.extend(['--batch-rows', '2'])
        outputs = (run_batch(executable, options, models, requests, required, tmp) if use_batch else
                   run_serial(executable, options, models, requests, required))
        with closing(outputs):
            for number in outputs:
                line, seed, filename, prompt_info = takes[number - 1]
                wav, dest = tmp / filename, out / filename
                audio, rate = sf.read(wav, dtype='float32')
                duration = len(audio) / rate
                if not len(audio) or not np.isfinite(audio).all() or not np.any(audio):
                    raise ValueError(f"Native output for {line['id']} is empty, silent or nonfinite")
                # Each acoustic patch represents 0.16 seconds; a capped take needs review.
                if duration >= (cap - 1) * 0.16:
                    raise ValueError(f"Native output for {line['id']} reached the decode cap; increase max_steps")
                os.replace(wav, dest)
                batch_info = {'batch_rows': 1}
                if number <= paired_count:
                    first_in_pair = number % 2 == 1
                    partner_index = number if first_in_pair else number - 2
                    batch_info = {'batch_rows': 2, 'batch_lane': 1 if first_in_pair else 2,
                                  'batch_partner': takes[partner_index][0]['id']}
                records['takes'][line['id']] = {
                    'file': os.path.relpath(dest), 'sha256': sha(dest), 'text': line['say'],
                    'direction': line.get('direction'), 'source': 'narrate.py/native',
                    'generation': {'model': 'VoxCPM2 GGUF', 'model_sha256': model_hashes,
                                   'engine_sha256': executable_hash, 'mode': 'continuation cloning',
                                   'invocation': invocation, **batch_info, 'reference_file': None,
                                   **prompt_info, 'seed': seed,
                                   'inference_timesteps': steps, 'cfg_value': guidance, 'max_steps': cap,
                                   'backend_marker': required, 'seconds': duration}}
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=provenance.parent,
                                                 delete=False) as f:
                    temp = Path(f.name)
                    json.dump(records, f, ensure_ascii=False, indent=1)
                os.replace(temp, provenance)
                print(f"{line['id']} {prompt_info['prompt_mood']}: {duration:.2f}s", flush=True)


def pcm16_prompt(prompt, tmp, sf):
    """The CLI reads only 16-bit PCM WAV prompts; a 24-bit sample corrupts its heap. Returns the file to pass
    and, for a converted copy, what provenance needs to trace it back to the library sample."""
    info = sf.info(str(prompt))
    if info.format == 'WAV' and info.subtype == 'PCM_16':
        return prompt.resolve(), None
    data, rate = sf.read(str(prompt), dtype='float64')
    copy = tmp / 'prompt_pcm16.wav'
    sf.write(str(copy), data, rate, subtype='PCM_16')
    return copy, {'converted_from': info.subtype, 'subtype': 'PCM_16', 'sha256': sha(copy)}
