# Transcription of interviews

Local speech-to-text with speaker diarization, producing editable transcripts.

1. **`convert_m4a_to_wav.ipynb`** — batch-convert recordings to 16 kHz WAV with `ffmpeg`.
2. **`transcribe_faster_whisper.ipynb`** — one GPU, nothing leaves the machine:
   [faster-whisper](https://github.com/SYSTRAN/faster-whisper) `large-v3` (word-level
   timestamps, Danish), `pyannote/speaker-diarization-3.1`, word-to-speaker alignment,
   export to JSON plus a `*_edit.docx` per interview for manual correction. Includes a
   synthetic-audio smoke test, so the pipeline can be verified without any interview data.

Dependencies are pinned in `transcribe_faster_whisper.requirements.in`; torch/torchaudio
are left unpinned so the installed CUDA build is reused. Pyannote requires accepting the
model licence on HuggingFace and an `HF_TOKEN` in the environment.
