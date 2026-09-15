"""python -m transcribe <audio folder> [--speakers N] [--redo] [--no-docx] [--no-selftest]"""
from __future__ import annotations

import argparse

from .pipeline import DEFAULT_WHISPER_MODEL, run


def main() -> int:
    ap = argparse.ArgumentParser(description="Transcribe + diarize every audio file in a folder.")
    ap.add_argument("folder", help="folder with audio files (not recursive)")
    ap.add_argument("--speakers", type=int, default=2, help="number of speakers, 0 = auto-detect")
    ap.add_argument("--model", default=DEFAULT_WHISPER_MODEL, help="faster-whisper model name")
    ap.add_argument("--redo", action="store_true", help="re-transcribe files that already have a JSON")
    ap.add_argument("--no-docx", action="store_true", help="skip the *_edit.docx export")
    ap.add_argument("--no-selftest", action="store_true", help="skip the 3 s smoke test")
    a = ap.parse_args()
    summary = run(a.folder, num_speakers=a.speakers or None, skip_existing=not a.redo,
                  whisper_model=a.model, selftest=not a.no_selftest, docx=not a.no_docx)
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
