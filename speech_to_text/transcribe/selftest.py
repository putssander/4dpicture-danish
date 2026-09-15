"""Self-test for the transcription pipeline.

Two levels:

* ``smoke_test``: a generated 3 s tone through the whole chain (ffmpeg -> wave -> ASR on
  the GPU without VAD -> pyannote on an in-memory waveform). Catches environment
  breakage in seconds, needs no data files.
* ``clip_test``: the bundled Danish speech clip in ``tests/audio`` (if present) through
  the real pipeline; checks that words come out and how many speakers were found.

Run from the command line (inside ``speech_to_text/``):  python -m transcribe.selftest
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .env import PKG_DIR, log

TEST_AUDIO_DIR = PKG_DIR.parent / "tests" / "audio"


def bundled_test_clips() -> list[Path]:
    if not TEST_AUDIO_DIR.is_dir():
        return []
    return sorted(p for p in TEST_AUDIO_DIR.iterdir()
                  if p.suffix.lower() in {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".wma"})


def smoke_test(transcriber) -> None:
    """3 s 220 Hz tone, written at 44.1 kHz stereo so the ffmpeg conversion has real work.
    VAD is off and the speaker count is not forced, so ASR really hits the GPU and
    pyannote really runs."""
    import numpy as np

    from .pipeline import assign_speakers, load_wav_in_memory, to_wav_16k_mono, write_wav

    with tempfile.TemporaryDirectory() as tmp:
        raw = os.path.join(tmp, "tone.wav")
        sr = 44100
        t = np.arange(3 * sr) / sr
        tone = 0.3 * np.sin(2 * np.pi * 220 * t)
        write_wav(raw, np.column_stack([tone, tone]), sr, channels=2)
        wav = os.path.join(tmp, "audio.wav")
        to_wav_16k_mono(raw, wav, transcriber.env.ffmpeg)
        audio = load_wav_in_memory(wav)
        assert audio["sample_rate"] == 16000
        assert audio["waveform"].shape[0] == 1 and audio["waveform"].shape[1] > 0
        words = transcriber.run_whisper(wav, vad_filter=False)
        turns = transcriber.run_diarization(wav, num_speakers=None)
        assign_speakers(words, turns)
    log(f"Smoke test passed: ffmpeg -> wave -> ASR ({transcriber.asr_device}) -> "
        f"diarization ({transcriber.diar_device}) all work.")


def clip_test(transcriber, clip: Path) -> dict:
    """Run the real pipeline on a bundled clip; the JSON goes to a temp dir, never next
    to the clip. Fails if no words were recognised."""
    with tempfile.TemporaryDirectory() as tmp:
        out = transcriber.transcribe_file(clip, out_json=os.path.join(tmp, "out.json"))
        with open(out, encoding="utf-8") as f:
            data = json.load(f)
    utterances = data["speakers"]
    text = " ".join(u["text"] for u in utterances).strip()
    speakers = sorted({u["speaker"] for u in utterances})
    if not text:
        raise AssertionError(f"No words recognised in {clip.name}")
    log(f"Clip test passed: {clip.name}: {len(utterances)} utterance(s), "
        f"{len(speakers)} speaker(s), text starts with: {text[:80]!r}")
    return data


def main() -> int:
    from .env import bootstrap
    from .pipeline import Transcriber

    env = bootstrap()
    transcriber = Transcriber(env, num_speakers=None)
    smoke_test(transcriber)
    clips = bundled_test_clips()
    if not clips:
        log(f"No bundled clips in {TEST_AUDIO_DIR} - skipping clip test.")
    for clip in clips:
        clip_test(transcriber, clip)
    log("Self-test OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
