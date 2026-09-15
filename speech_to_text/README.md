# Transcription of interviews

Local speech-to-text with speaker diarization, producing editable transcripts. One GPU,
nothing leaves the machine: [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
`large-v3` (word-level timestamps, Danish), `pyannote/speaker-diarization-3.1`,
word-to-speaker alignment, export to JSON plus a `*_edit.docx` per interview for manual
correction.

| | |
|---|---|
| **`transcribe_faster_whisper.ipynb`** | The notebook to use: two settings (audio folder, number of speakers), one run cell. |
| **`transcribe/`** | All the code: `env.py` (self-healing environment setup), `pipeline.py` (ffmpeg → Whisper → pyannote → alignment → JSON → docx), `selftest.py`. Also usable from the command line. |
| **`tests/`** | Unit tests and a public, CC-licensed 13-second Danish two-speaker clip used by the self-test. No project data. |
| `convert_m4a_to_wav.ipynb` | Optional: batch-convert recordings to 16 kHz WAV (the pipeline does this itself). |

## Running it (UCloud)

1. Start the **JupyterLab** app, flavor **Base**, version **4.6.3**, machine
   **gpu-nvidia-b200** (1 MIG / fractional GPU is enough). Mount the folder with the
   recordings. *4.6.3 is the image this was verified on (15 Sep 2026). The version selects
   the whole software image, so using the same one avoids most "it worked last month"
   problems; newer images usually work too because the code repairs itself, and it prints
   which version to pick if that ever fails.*
2. Token, once: a Hugging Face token whose account accepted the terms of
   [pyannote/speaker-diarization-3.1](https://hf.co/pyannote/speaker-diarization-3.1) and
   [pyannote/segmentation-3.0](https://hf.co/pyannote/segmentation-3.0). Put `HF_TOKEN=hf_...`
   in a file `.env` in the repo root (git-ignored), or paste it once into the `HF_TOKEN`
   field of the notebook (it is then saved to `.env`; remove it from the notebook again).
3. Open the notebook, set the audio folder, menu **Run → Run All Cells**. Not the toolbar's
   "Restart the kernel and run all cells" button: on this image a kernel *restart* usually
   disconnects the notebook from its kernel (see below).

Output per recording, next to it: `<name>-transcription.json`
(`{"speakers": [{"timestamp": [start, end], "speaker": "SPEAKER_00", "text": "..."}]}`) and
`<name>-transcription_edit.docx`. Recordings that already have a JSON are skipped, so the
notebook can simply be re-run after adding files or after an interruption.

**Model cache.** The image's own `~/.cache` is wiped with every UCloud job, so the ~3 GB of
models (Whisper `large-v3`, pyannote) are cached on persistent storage instead:
`/work/speech/models/huggingface/hub` (standard Hugging Face hub layout, next to the Ollama
models in `/work/speech/models/ollama`). The folder is created on first use and the output
says which models it already holds; a fresh job then loads in seconds instead of
downloading. `HF_HUB_CACHE` or `HF_HOME`, if set, take precedence; without `/work/speech/models`
the default `~/.cache/huggingface/hub` is used (`PERSISTENT_MODEL_ROOTS` in `transcribe/env.py`).

Every output line carries the clock time and the elapsed time. Each file prints its
length, a progress bar during transcription, the diarization steps, the speed, and after
the first file an estimate of the remaining time. On a B200 MIG slice the pipeline runs at
roughly 10–15× realtime: a 30-minute interview takes 2–3 minutes.

From a terminal instead of the notebook:

```sh
cd speech_to_text
python -m transcribe /path/to/interviews --speakers 2   # transcribe a folder (+ docx)
python -m transcribe.selftest                           # environment + pipeline self-test
python -m pytest tests/test_transcribe.py               # unit tests (no GPU needed)
```

## What the setup protects against

The cloud image is rebuilt regularly and package builds drift. `transcribe/env.py` tests
the environment and repairs only what is broken, in this order:

1. NVIDIA pip libraries invisible to the kernel → discovered and preloaded in-process
   (`LD_LIBRARY_PATH` set inside a running kernel does nothing).
2. torch ↔ torchaudio CUDA-build mismatch → torchaudio reinstalled to match torch
   (the notebook then asks for a new kernel).
3. Upstream API churn → `transcribe/requirements.lock` (verified versions) is installed
   first; `transcribe/requirements.in` (unpinned) is the fallback. torch/torchaudio/nvidia-*
   are deliberately unpinned: they must match the machine's CUDA build.
4. faster-whisper/CTranslate2 vs torch CUDA major mismatch (e.g. torch on CUDA 13 while
   CTranslate2 dlopens `libcublas.so.12`) → a **real** GPU decode is run (loading a model is
   not enough, cuBLAS is loaded lazily), the missing `nvidia-*-cuN` wheel is installed side
   by side and preloaded, then retried.
5. No usable GPU at all → CPU `int8` fallback with a loud warning (correct, ~10–30× slower).
6. No `ffmpeg` on the image → static build via pip (`imageio-ffmpeg`).
7. No interactive stdin for the token → env var / `.env` / hub cache lookup, never a prompt
   that can crash.
8. torch imported before numpy exists (bare venv) → numpy installed first, at the locked
   version; if torch got in first, a kernel restart is requested (torch binds NumPy once,
   at import time; otherwise every `torch.from_numpy` fails with "Numpy is not available").
9. Model downloads lost with the cleaned image → persistent model cache (see above).

After a verified-good run on a new image, refresh `transcribe/requirements.lock` and
`VERIFIED_ENV` in `transcribe/env.py`.

## Known JupyterLab problem: "Run All does nothing"

The first output line (`STEP 1/4 ...`) appears within a second or two of starting. If after
a minute there is still no output, whether the cells show `[*]` or not: the notebook is no
longer connected to its kernel. On this image a **kernel restart** usually does that (4 of
5 restarts on 15 Sep 2026, whether from the toolbar button "Restart the kernel and run all
cells" or Kernel → Restart Kernel); a notebook left open and idle can lose the link too. The
`jupyter-server-documents` extension connects the notebook to the kernel at kernel start and
does not reliably reconnect after a restart. The kernel is fine but never receives the cells: the
server log (`/work/stdout-0.log`) shows `Kernel restarted` with no `Connected yroom ... to
kernel` line after it, and `curl -s localhost:8888/api/kernels` reports `"connections": 0`.
Fix: **Kernel → Shut Down Kernel**, then pick **Python 3** again (top-right) and menu
**Run → Run All Cells**. Never restart; shut down and start a new kernel instead.
