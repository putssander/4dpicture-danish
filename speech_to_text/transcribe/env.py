"""Self-healing environment bootstrap for the transcription pipeline.

Only the standard library is imported at module level, so this module can be imported
before any dependency is installed. Everything heavy is imported lazily.

Layers of protection (each one covers a different way a rebuilt cloud image breaks):

1. NVIDIA pip libraries invisible to the kernel  -> discovered + preloaded in-process
2. torch <-> torchaudio CUDA-build mismatch      -> torchaudio reinstalled to match torch
3. Upstream API churn                            -> pinned requirements.lock first,
                                                    unpinned requirements.in as fallback
4. CTranslate2 vs torch CUDA major mismatch      -> real GPU decode probe, missing
                                                    nvidia-*-cuN wheel installed + preloaded
5. No usable GPU at all                          -> CPU int8 fallback (slow, correct)
6. No ffmpeg on the image                        -> static build via pip (imageio-ffmpeg)
7. No interactive stdin for the HF token         -> env var / .env / hub cache lookup
8. Model downloads lost with the cleaned image    -> Hugging Face cache on persistent storage
"""
from __future__ import annotations

import ctypes
import os
import re
import shutil
import site
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
REPO_DIR = PKG_DIR.parents[1]  # <repo>/speech_to_text/transcribe -> <repo>
REQ_IN = PKG_DIR / "requirements.in"
LOCK_FILE = PKG_DIR / "requirements.lock"
TOKEN_ENV_VARS = ("HF_TOKEN", "HUGGINGFACE_AUTH_TOKEN", "HUGGING_FACE_HUB_TOKEN")
GATED_MODELS = ("pyannote/speaker-diarization-3.1", "pyannote/segmentation-3.0")

# Persistent folders that survive a new UCloud job (the image's own ~/.cache does not).
# The first existing, writable one gets <root>/huggingface/hub as the Hugging Face model
# cache (standard hub layout, next to the Ollama models in <root>/ollama), so the ~3 GB of
# models are downloaded once per storage, not once per job. HF_HUB_CACHE / HF_HOME set by
# the user always win.
PERSISTENT_MODEL_ROOTS = ("/work/speech/models",)


# The environment this pipeline was last verified on. On UCloud the JupyterLab app
# *version* selects the whole image (Python, preinstalled packages), so picking the same
# version is the single most effective way to avoid drift. Update after a verified run.
VERIFIED_ENV = {
    "date": "2026-09-15",
    "ucloud": "JupyterLab app, flavor Base, version 4.6.3, machine gpu-nvidia-b200 (1 MIG)",
    "jupyterlab": "4.6.3",
    "python": "3.13",
    "torch": "2.14.0",
}


class KernelRestartRequired(RuntimeError):
    """Raised when a compiled package was replaced and the running process must restart."""


_T0 = None


def fmt_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m" if h else (f"{m}m{s:02d}s" if m else f"{s}s")


def log(msg: str) -> None:
    """Print with wall-clock time and time elapsed since the first message, so the user
    can see that something is happening and how long each step takes."""
    import time
    global _T0
    if _T0 is None:
        _T0 = time.time()
    stamp = time.strftime("%H:%M:%S")
    print(f"[{stamp} +{fmt_duration(time.time() - _T0):>6}] {msg}", flush=True)


def environment_fingerprint() -> dict[str, str]:
    from importlib.metadata import PackageNotFoundError, version

    def ver(dist: str) -> str:
        try:
            return version(dist).split("+")[0]
        except PackageNotFoundError:
            return "not installed"

    return {"jupyterlab": ver("jupyterlab"), "python": f"{sys.version_info.major}.{sys.version_info.minor}",
            "torch": ver("torch")}


def warn_if_unverified_environment() -> list[str]:
    """Log a warning when this environment differs from the verified one, and say which
    UCloud app version to pick if the self-healing below is not enough."""
    fp = environment_fingerprint()
    diffs = [f"{k}: {fp[k]} (verified: {VERIFIED_ENV[k]})" for k in ("python", "jupyterlab", "torch")
             if fp[k] != VERIFIED_ENV[k] and fp[k] != "not installed"]
    if diffs:
        log("NOTE: this environment differs from the one verified on " + VERIFIED_ENV["date"] + ": "
            + "; ".join(diffs) + ". The pipeline will try to adapt. If it fails, start UCloud with: "
            + VERIFIED_ENV["ucloud"] + ".")
    return diffs


# --------------------------------------------------------------------------- pip
def pip_install(*args: str) -> bool:
    """pip install into *this* interpreter. Returns False (and prints pip's stderr tail)
    instead of raising, so self-healing can continue."""
    cmd = [sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", *args]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        log(f"  pip install {' '.join(args)} failed:\n" + r.stderr.strip()[-1500:])
        return False
    return True


def install_dependencies() -> None:
    """Pinned, verified versions first; unpinned fallback if they cannot be installed
    on this Python/platform (e.g. a newer Python without wheels)."""
    if LOCK_FILE.exists():
        log(f"Installing pinned, verified dependency versions from {LOCK_FILE.name} "
            "(seconds if already installed, a few minutes on a fresh machine) ...")
        if pip_install("-r", str(LOCK_FILE)):
            return
        log("!! Pinned versions could not be installed here - falling back to unpinned requirements.")
    log(f"Installing dependencies from {REQ_IN.name}")
    if not pip_install("-r", str(REQ_IN)):
        raise RuntimeError(f"Could not install dependencies from {REQ_IN}")


# --------------------------------------------------------------------------- CUDA libs
def python_site_roots() -> list[Path]:
    roots: list = []
    for getter in (site.getsitepackages, lambda: [site.getusersitepackages()]):
        try:
            roots.extend(getter())
        except Exception:
            pass
    roots.extend(p for p in sys.path if "site-packages" in str(p))
    out, seen = [], set()
    for r in roots:
        p = Path(r)
        if p.exists() and p.resolve() not in seen:
            seen.add(p.resolve())
            out.append(p.resolve())
    return out


def nvidia_cuda_lib_dirs() -> list[Path]:
    dirs, seen = [], set()
    for root in python_site_roots():
        nvidia = root / "nvidia"
        if nvidia.exists():
            for p in nvidia.rglob("lib"):
                if any(p.glob("*.so*")) and p not in seen:
                    seen.add(p)
                    dirs.append(p)
    return dirs


# Order matters: dependencies first (nvJitLink < cublasLt < cublas), then cuDNN.
PRELOAD_PATTERNS = [
    "libnvJitLink.so*", "libcudart.so*", "libnvrtc.so*",
    "libcublasLt.so*", "libcublas.so*", "libcudnn.so*", "libcudnn_*.so*",
]


def preload_shared_libraries(lib_dirs: list[Path]) -> list[str]:
    """dlopen every NVIDIA lib by absolute path with RTLD_GLOBAL.

    LD_LIBRARY_PATH is read by the dynamic loader only at process start, so setting it
    inside a running kernel does nothing for this process. But once a library is loaded,
    a later dlopen("libcublas.so.N") by CTranslate2/torchaudio resolves to the loaded
    copy by soname. That is what makes the GPU work with no shell setup at all.
    """
    loaded = []
    for pattern in PRELOAD_PATTERNS:
        for lib_dir in lib_dirs:
            for lib in sorted(lib_dir.glob(pattern)):
                if lib.is_file():
                    try:
                        ctypes.CDLL(str(lib), mode=ctypes.RTLD_GLOBAL)
                        loaded.append(lib.name)
                    except OSError:
                        pass
    return loaded


def bootstrap_cuda_library_path(verbose: bool = True) -> list[Path]:
    lib_dirs = nvidia_cuda_lib_dirs()
    if not lib_dirs:
        if verbose:
            log("No NVIDIA pip CUDA library directories found in this environment (yet).")
        return []
    existing = [p for p in os.environ.get("LD_LIBRARY_PATH", "").split(os.pathsep) if p]
    strings = [str(p) for p in lib_dirs]
    os.environ["LD_LIBRARY_PATH"] = os.pathsep.join(strings + [p for p in existing if p not in strings])
    loaded = sorted(set(preload_shared_libraries(lib_dirs)))
    if verbose:
        log(f"CUDA: {len(lib_dirs)} NVIDIA library folder(s), preloaded {len(loaded)} libs.")
    return lib_dirs


# --------------------------------------------------------------------------- numpy
def ensure_numpy_before_torch() -> None:
    """torch binds to NumPy once, when it is imported. If numpy is missing at that moment,
    every torch<->numpy conversion fails for the rest of the process ("Numpy is not
    available"), even after numpy has been installed. So on a machine that has torch but
    no numpy (a bare venv), install numpy (at the lock's pinned version) *before* anything
    imports torch, and demand a restart if torch got in first."""
    try:
        import numpy  # noqa: F401
        return
    except ImportError:
        pass
    spec = "numpy"
    if LOCK_FILE.exists():
        m = re.search(r"^numpy==\S+", LOCK_FILE.read_text(encoding="utf-8"), re.MULTILINE)
        spec = m.group(0) if m else spec
    log(f"numpy is not installed - installing {spec} before torch is imported.")
    pip_install(spec)
    if "torch" in sys.modules:
        raise KernelRestartRequired(
            "torch was imported while numpy was missing; numpy is installed now. RESTART THE "
            "KERNEL (Kernel -> Restart) and run the cell again.")


# --------------------------------------------------------------------------- torchaudio
def torchaudio_imports() -> bool:
    try:
        import torchaudio  # noqa: F401
        return True
    except Exception as e:
        log(f"torchaudio import failed: {type(e).__name__}: {str(e)[:200]}")
        return False


def torch_build_tag() -> str | None:
    """'cu130' / 'cu128' / 'cpu' from torch.version.cuda (NOT nvidia-smi, which reports
    the driver's maximum CUDA version, for which no wheel index may exist)."""
    try:
        import torch
    except Exception:
        return None
    cu = getattr(torch.version, "cuda", None)
    if not cu:
        return "cpu"
    major, minor = (cu.split(".") + ["0"])[:2]
    return f"cu{major}{minor}"


def reconcile_torchaudio() -> bool:
    """Reinstall torchaudio to match torch's build if (and only if) it fails to import.
    Returns True when a reinstall happened (the process must then restart)."""
    if torchaudio_imports():
        return False
    tag = torch_build_tag()
    if tag is None:
        log("torch is not installed yet - the dependency install will pull torch + torchaudio.")
        return False
    index = f"https://download.pytorch.org/whl/{tag}"
    log(f"Reinstalling torchaudio to match torch build '{tag}' via {index}")
    return pip_install("--force-reinstall", "--no-deps", "--index-url", index, "torchaudio")


# --------------------------------------------------------------------------- GPU probe
NVIDIA_PIP_STEMS = {
    "cublas": "cublas", "cublasLt": "cublas", "cudart": "cuda-runtime", "nvrtc": "cuda-nvrtc",
    "nvJitLink": "nvjitlink", "cudnn": "cudnn", "cufft": "cufft", "curand": "curand",
    "cusolver": "cusolver", "cusparse": "cusparse",
}


def missing_cuda_library(error_text: str) -> tuple[str, str] | None:
    """('cublas', '12') from 'Library libcublas.so.12 is not found or cannot be loaded'."""
    m = re.search(r"lib([A-Za-z_]+?)\.so\.(\d+)", str(error_text))
    return (m.group(1), m.group(2)) if m else None


def probe_ctranslate2_gpu(download_root: str | None = None) -> str | None:
    """Run a REAL 1 s GPU decode with the public 'tiny' model. Returns None on success or
    the error text. Constructing a model is not enough: CTranslate2 dlopens cuBLAS lazily
    on the first matmul, and VAD-filtered silence never reaches the GPU either."""
    try:
        import numpy as np
        from faster_whisper import WhisperModel
        model = WhisperModel("tiny", device="cuda", compute_type="float16", download_root=download_root)
        noise = (np.random.default_rng(0).standard_normal(16000) * 0.01).astype(np.float32)
        segments, _ = model.transcribe(noise, language="da", vad_filter=False,
                                       beam_size=1, without_timestamps=True)
        list(segments)
        del model
        return None
    except Exception as e:
        return f"{type(e).__name__}: {e}"


def install_missing_cuda_library(name: str, major: str) -> bool:
    stem = NVIDIA_PIP_STEMS.get(name, name.lower())
    if stem == "cudnn":
        # cu12 and cu13 cuDNN builds share nvidia/cudnn/lib; reinstalling the same major
        # would clobber torch's copy. Only install if that major is absent entirely.
        for d in nvidia_cuda_lib_dirs():
            if any(d.glob(f"libcudnn.so.{major}")):
                log(f"  libcudnn.so.{major} exists at {d} but could not be loaded - "
                    "not reinstalling (would break torch).")
                return False
    # CUDA 12 wheels are suffixed (nvidia-cublas-cu12); CUDA 13 core libs are not
    # (nvidia-cublas==13.*) while cudnn/nccl keep the suffix. Try both.
    for spec in (f"nvidia-{stem}-cu{major}", f"nvidia-{stem}=={major}.*"):
        log(f"  pip install {spec}")
        if pip_install(spec):
            return True
    return False


def ensure_asr_gpu(max_rounds: int = 3, download_root: str | None = None) -> tuple[str, str]:
    """Return (device, compute_type) for faster-whisper, repairing CUDA libs on the way."""
    try:
        import torch
        cuda_ok = torch.cuda.is_available()
    except Exception as e:
        log(f"torch import failed ({e}) - ASR will run on CPU.")
        cuda_ok = False
    if not cuda_ok:
        log("torch reports no usable CUDA device - ASR will run on CPU (int8).")
        return "cpu", "int8"

    log("GPU check: running a real test decode (downloads the small 'tiny' model once) ...")
    for round_no in range(max_rounds + 1):
        err = probe_ctranslate2_gpu(download_root)
        if err is None:
            log("GPU check: faster-whisper real decode on cuda/float16 OK.")
            return "cuda", "float16"
        log(f"GPU check failed: {err[:300]}")
        missing = missing_cuda_library(err)
        if missing is None or round_no == max_rounds:
            break
        name, major = missing
        log(f"Missing lib{name}.so.{major} - installing the matching NVIDIA pip package "
            "side by side with torch's CUDA libraries.")
        if not install_missing_cuda_library(name, major):
            break
        bootstrap_cuda_library_path(verbose=False)  # picks up + preloads the new folder

    log("!! GPU ASR is unavailable. Falling back to CPU int8 - correct output, but roughly "
        "10-30x slower. Fix the CUDA error above to get the GPU back.")
    return "cpu", "int8"


# --------------------------------------------------------------------------- ffmpeg
def find_ffmpeg() -> str:
    """System ffmpeg if present; otherwise a static build installed via pip."""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    log("ffmpeg not on PATH - installing a static build via pip (imageio-ffmpeg).")
    if pip_install("imageio-ffmpeg"):
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception as e:
            log(f"  imageio-ffmpeg unusable: {e}")
    raise RuntimeError("ffmpeg not found and the pip fallback failed - run: sudo apt install ffmpeg")


# --------------------------------------------------------------------------- model cache
def resolve_model_cache(roots=PERSISTENT_MODEL_ROOTS) -> Path | None:
    """Where Hugging Face downloads (Whisper, pyannote) are stored.

    Explicit HF_HUB_CACHE / HF_HOME -> respected untouched. Otherwise the first existing,
    writable persistent root gets ``<root>/huggingface/hub`` (created). None means the
    library default (~/.cache/huggingface/hub), which on UCloud is wiped with the image.
    """
    if os.environ.get("HF_HUB_CACHE"):
        log(f"Model cache: {os.environ['HF_HUB_CACHE']} (from $HF_HUB_CACHE)")
        return Path(os.environ["HF_HUB_CACHE"])
    if os.environ.get("HF_HOME"):
        log(f"Model cache: {os.environ['HF_HOME']}/hub (from $HF_HOME)")
        return Path(os.environ["HF_HOME"]) / "hub"
    for root in roots:
        root = Path(root)
        if not (root.is_dir() and os.access(root, os.W_OK)):
            continue
        cache = root / "huggingface" / "hub"
        try:
            cache.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            log(f"  could not create {cache} ({e}); trying the next location")
            continue
        cached = sorted(p.name.removeprefix("models--").replace("--", "/") for p in cache.glob("models--*"))
        log(f"Model cache: {cache} (persistent; " + (f"already holds {', '.join(cached)})" if cached
            else "empty, models will be downloaded into it once)"))
        return cache
    log("Model cache: default ~/.cache/huggingface/hub (no persistent folder found: "
        + ", ".join(roots) + "). Models are re-downloaded on a fresh machine.")
    return None


def activate_model_cache(cache: Path | None) -> None:
    """Point every huggingface_hub download at ``cache``. The env var must be set before
    huggingface_hub is imported (it reads it once); the pipeline additionally passes the
    folder explicitly, so the cache is honoured even if the import already happened."""
    if cache is None:
        return
    os.environ["HF_HUB_CACHE"] = str(cache)
    hub = sys.modules.get("huggingface_hub")
    if hub is not None:
        try:
            import huggingface_hub.constants as c
            if Path(c.HF_HUB_CACHE).resolve() != cache.resolve():
                log("  NOTE: huggingface_hub was imported before the cache was chosen; downloads "
                    "outside the transcribe package may still use " + c.HF_HUB_CACHE)
        except Exception:
            pass


# --------------------------------------------------------------------------- HF token
def read_dotenv(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE parser (quotes, `export`, comments). No extra dependency."""
    values: dict[str, str] = {}
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip().removeprefix("export ").strip()
            val = val.strip().split(" #")[0].strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                val = val[1:-1]
            values[key] = val
    except Exception:
        pass
    return values


def dotenv_candidates() -> list[Path]:
    cwd = Path.cwd()
    roots = [REPO_DIR, cwd, *cwd.parents, Path.home()]
    seen, out = set(), []
    for r in roots:
        p = (r / ".env").resolve()
        if p.is_file() and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def save_token_to_dotenv(token: str, env_file: Path | None = None) -> Path:
    """Write/replace the HF_TOKEN line in the repo .env so the token is found next time
    and does not have to stay in the notebook."""
    env_file = env_file or (REPO_DIR / ".env")
    lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
    lines = [l for l in lines if not re.match(r"\s*(export\s+)?(HF_TOKEN|HUGGINGFACE_AUTH_TOKEN)\s*=", l)]
    lines.append(f"HF_TOKEN={token}")
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(env_file, 0o600)
    except Exception:
        pass
    return env_file


def resolve_hf_token(interactive: bool = True, explicit: str | None = None) -> str:
    """Explicit value (from the notebook) -> env var -> .env files -> huggingface_hub
    login cache -> prompt (if possible). Never crashes on a frontend without stdin;
    explains where to put the token instead. An explicit token is saved to the repo
    .env so it can be removed from the notebook afterwards."""
    if explicit and explicit.strip():
        token = explicit.strip()
        if not token.startswith("hf_"):
            log("!! The token given in the notebook does not start with 'hf_' - is it really a Hugging Face token?")
        saved = save_token_to_dotenv(token)
        log(f"HF token: from the notebook; saved to {saved} so you can clear it from the notebook now.")
        return token
    for var in TOKEN_ENV_VARS:
        if os.environ.get(var, "").strip():
            log(f"HF token: from ${var}")
            return os.environ[var].strip()
    for env_file in dotenv_candidates():
        values = read_dotenv(env_file)
        for var in TOKEN_ENV_VARS:
            if values.get(var, "").strip():
                log(f"HF token: from {env_file}")
                return values[var].strip()
    try:
        from huggingface_hub import get_token
        token = get_token()
        if token:
            log("HF token: from huggingface_hub login cache")
            return token
    except Exception:
        pass
    if interactive:
        try:
            import getpass
            token = getpass.getpass("Hugging Face token (hf_...): ").strip()
            if token:
                return token
        except Exception:
            pass  # e.g. StdinNotImplementedError on frontends without input support
    raise RuntimeError(
        "No Hugging Face token found. Put a line  HF_TOKEN=hf_...  into "
        f"{REPO_DIR / '.env'} (or export HF_TOKEN before starting Jupyter). Create a token "
        "at https://huggingface.co/settings/tokens and accept the terms of "
        + " and ".join(f"https://hf.co/{m}" for m in GATED_MODELS) + "."
    )


# --------------------------------------------------------------------------- bootstrap
@dataclass
class Env:
    asr_device: str
    asr_compute_type: str
    diar_device: str
    ffmpeg: str
    hf_token: str | None
    gpu_name: str
    model_cache: Path | None = None  # None = huggingface_hub default

    @property
    def model_cache_str(self) -> str | None:
        return str(self.model_cache) if self.model_cache else None

    def summary(self) -> str:
        return (f"ASR on {self.asr_device}/{self.asr_compute_type}, diarization on "
                f"{self.diar_device}, GPU: {self.gpu_name}, ffmpeg: {self.ffmpeg}, "
                f"model cache: {self.model_cache or 'default (~/.cache/huggingface/hub)'}")


_ENV: Env | None = None


def bootstrap(install: bool = True, need_token: bool = True, verbose: bool = True,
              hf_token: str | None = None) -> Env:
    """Prepare this process to run the pipeline. Idempotent: the result is cached, so
    calling it twice in one kernel is free. ``hf_token`` is an optional explicit token
    (e.g. pasted into the notebook); it is saved to the repo .env for next time."""
    global _ENV
    if _ENV is not None and (_ENV.hf_token or not need_token) and not hf_token:
        return _ENV

    if verbose:
        warn_if_unverified_environment()
    model_cache = resolve_model_cache()
    activate_model_cache(model_cache)
    bootstrap_cuda_library_path(verbose=verbose)
    if install:
        ensure_numpy_before_torch()
        if reconcile_torchaudio():
            raise KernelRestartRequired(
                "torchaudio was reinstalled to match torch. RESTART THE KERNEL "
                "(Kernel -> Restart) and run the cell again.")
        install_dependencies()
        bootstrap_cuda_library_path(verbose=False)  # deps may have added NVIDIA packages
    asr_device, asr_compute_type = ensure_asr_gpu(download_root=str(model_cache) if model_cache else None)

    try:
        import torch
        diar_device = "cuda" if torch.cuda.is_available() else "cpu"
        gpu_name = torch.cuda.get_device_name(0) if diar_device == "cuda" else "-"
    except Exception:
        diar_device, gpu_name = "cpu", "-"

    ffmpeg = find_ffmpeg()
    token = resolve_hf_token(explicit=hf_token) if need_token else None
    if token:
        for var in TOKEN_ENV_VARS:  # so every huggingface_hub download authenticates
            os.environ[var] = token

    _ENV = Env(asr_device, asr_compute_type, diar_device, ffmpeg, token, gpu_name, model_cache)
    if verbose:
        log("Environment ready: " + _ENV.summary())
    return _ENV
