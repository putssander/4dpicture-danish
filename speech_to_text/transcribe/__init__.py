"""Local Danish transcription + speaker diarization (faster-whisper + pyannote).

Notebook / one-liner use:

    from transcribe import run
    run("/work/speech/Peter", num_speakers=2)

Command line (inside the ``speech_to_text/`` folder):

    python -m transcribe /path/to/interviews --speakers 2
    python -m transcribe.selftest

Only ``env`` (standard library) is imported eagerly, so this package can be imported
before its dependencies are installed; ``run`` installs and repairs what is missing.
"""
from .env import KernelRestartRequired, bootstrap  # noqa: F401


def run(*args, **kwargs):
    """See :func:`transcribe.pipeline.run`."""
    from .pipeline import run as _run
    return _run(*args, **kwargs)


__all__ = ["run", "bootstrap", "KernelRestartRequired"]
