"""Unit tests for the pure-Python parts of the transcribe package (no GPU, no models,
no network).

    cd speech_to_text && python -m pytest tests/test_transcribe.py

The full pipeline self-test (GPU, models, HF token) is a separate command:

    cd speech_to_text && python -m transcribe.selftest
"""
import sys
from pathlib import Path

SPEECH_TO_TEXT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SPEECH_TO_TEXT))

from transcribe.env import missing_cuda_library, read_dotenv, resolve_model_cache, save_token_to_dotenv  # noqa: E402
from transcribe.pipeline import assign_speakers, list_audio_files, transcription_json_for  # noqa: E402


def test_missing_cuda_library_parses_ctranslate2_error():
    err = "RuntimeError: Library libcublas.so.12 is not found or cannot be loaded"
    assert missing_cuda_library(err) == ("cublas", "12")
    assert missing_cuda_library("something unrelated") is None


def test_read_dotenv_handles_quotes_export_and_comments(tmp_path):
    env = tmp_path / ".env"
    env.write_text('# comment\nexport HF_TOKEN="hf_abc"\nOTHER=x # trailing\n\nBROKEN\n')
    values = read_dotenv(env)
    assert values["HF_TOKEN"] == "hf_abc"
    assert values["OTHER"] == "x"
    assert "BROKEN" not in values


def test_save_token_to_dotenv_replaces_existing_line_and_keeps_others(tmp_path):
    env = tmp_path / ".env"
    env.write_text("OPENAI_API_KEY=sk-x\nHF_TOKEN=hf_old\n")
    save_token_to_dotenv("hf_new", env)
    values = read_dotenv(env)
    assert values == {"OPENAI_API_KEY": "sk-x", "HF_TOKEN": "hf_new"}
    save_token_to_dotenv("hf_first", tmp_path / "fresh.env")
    assert read_dotenv(tmp_path / "fresh.env") == {"HF_TOKEN": "hf_first"}


def test_assign_speakers_merges_consecutive_words_and_uses_nearest_turn():
    words = [
        {"start": 0.0, "end": 0.5, "text": " Hej"},
        {"start": 0.6, "end": 1.0, "text": " med"},
        {"start": 1.1, "end": 1.4, "text": " dig"},
        {"start": 5.0, "end": 5.5, "text": " Ja"},   # between turns -> nearest (second)
        {"start": 6.0, "end": 6.5, "text": " tak"},
    ]
    turns = [(0.0, 2.0, "SPEAKER_00"), (5.8, 8.0, "SPEAKER_01")]
    out = assign_speakers(words, turns)
    assert [u["speaker"] for u in out] == ["SPEAKER_00", "SPEAKER_01"]
    assert out[0]["text"] == "Hej med dig"
    assert out[0]["timestamp"] == [0.0, 1.4]
    assert out[1]["text"] == "Ja tak"


def test_assign_speakers_without_turns_falls_back_to_single_speaker():
    words = [{"start": 0.0, "end": 0.5, "text": " Hej"}]
    out = assign_speakers(words, [])
    assert out == [{"timestamp": [0.0, 0.5], "speaker": "SPEAKER_00", "text": "Hej"}]


def test_list_audio_files_is_case_insensitive_and_not_recursive(tmp_path):
    for name in ["a.WMA", "b.mp3", "c.txt", "d-transcription.json"]:
        (tmp_path / name).write_bytes(b"")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "e.wav").write_bytes(b"")
    files = [Path(f).name for f in list_audio_files(tmp_path)]
    assert files == ["a.WMA", "b.mp3"]
    assert transcription_json_for(tmp_path / "a.WMA").endswith("a-transcription.json")


def test_resolve_model_cache_prefers_env_then_persistent_root(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_HUB_CACHE", raising=False)
    monkeypatch.delenv("HF_HOME", raising=False)
    # no persistent root -> library default
    assert resolve_model_cache(roots=(str(tmp_path / "missing"),)) is None
    # first existing root -> <root>/huggingface/hub, created
    (tmp_path / "models").mkdir()
    cache = resolve_model_cache(roots=(str(tmp_path / "missing"), str(tmp_path / "models")))
    assert cache == tmp_path / "models" / "huggingface" / "hub" and cache.is_dir()
    # explicit env var wins, nothing created
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "own"))
    assert resolve_model_cache(roots=(str(tmp_path / "models"),)) == tmp_path / "own"
    assert not (tmp_path / "own").exists()
