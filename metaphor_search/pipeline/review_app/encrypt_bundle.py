#!/usr/bin/env python3
"""Encrypt a review bundle with a passphrase so the list can travel by e-mail.

    encrypt_bundle.py --inout list.json --passfile ~/metaphor-private/<bundle>/passphrases.json
    encrypt_bundle.py --decrypt --in list.json --passphrase "..."       (prints the plain bundle)

Format (the app, review_app.js, decrypts it in the browser with WebCrypto):
    {"format": "metaphor-review-bundle-encrypted", "version": 1, "lang", "list_id", "corpus",
     "kdf": {"name": "PBKDF2", "hash": "SHA-256", "iterations": 300000, "salt": b64},
     "cipher": {"name": "AES-GCM", "iv": b64}, "data": b64}
PBKDF2-HMAC-SHA256 → AES-256-GCM. `lang` and `corpus` stay readable so the passphrase prompt
can appear in the reviewer's language; everything else is ciphertext.

The passphrase file maps list_id → passphrase and lives in the PRIVATE store, never in the
repository. A missing entry is generated (four words and a number, easy to read out on the
phone) and written back. Send the passphrase by a different channel than the file.
"""
import argparse
import base64
import json
import os
import secrets
import sys
import unicodedata
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ITER = 300_000
WORDS = ("apple bird boat book bread candle chair cloud coffee copper daisy door eagle field fox garden glass "
         "green hammer harbor honey horse island jacket kettle lake lamp lemon linen lion maple meadow mirror "
         "moon mountain music needle north ocean olive orange otter paper pearl pepper piano pillow pine "
         "planet plum pocket rabbit rain river rope rose salt sand school silver sky snow spoon spring star "
         "stone summer sugar table tiger tower train tree tulip valley velvet violet wagon water wheat "
         "window winter wolf yellow zebra").split()


def norm(p):
    return unicodedata.normalize("NFKC", p).strip()


def new_passphrase():
    return "-".join(secrets.choice(WORDS) for _ in range(4)) + "-" + str(secrets.randbelow(90) + 10)


def key_for(passphrase, salt, iterations=ITER):
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations).derive(
        norm(passphrase).encode("utf-8"))


def encrypt(bundle, passphrase):
    salt, iv = os.urandom(16), os.urandom(12)
    plain = json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    data = AESGCM(key_for(passphrase, salt)).encrypt(iv, plain, None)
    b64 = lambda b: base64.b64encode(b).decode("ascii")
    return {"format": "metaphor-review-bundle-encrypted", "version": 1,
            "lang": bundle.get("lang", "en"), "list_id": bundle.get("list_id", ""), "corpus": bundle.get("corpus", ""),
            "kdf": {"name": "PBKDF2", "hash": "SHA-256", "iterations": ITER, "salt": b64(salt)},
            "cipher": {"name": "AES-GCM", "iv": b64(iv)}, "data": b64(data)}


def decrypt(env, passphrase):
    b64 = base64.b64decode
    key = key_for(passphrase, b64(env["kdf"]["salt"]), env["kdf"]["iterations"])
    return json.loads(AESGCM(key).decrypt(b64(env["cipher"]["iv"]), b64(env["data"]), None).decode("utf-8"))


def load_any(path, passfile=None, passphrase=None):
    """Read a bundle, decrypting with the passphrase file (or given passphrase) if needed."""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    if d.get("format") != "metaphor-review-bundle-encrypted":
        return d
    if passphrase is None:
        passphrase = json.loads(Path(passfile).read_text(encoding="utf-8"))[d["list_id"]]
    return decrypt(d, passphrase)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--inout", help="bundle to encrypt in place")
    ap.add_argument("--in", dest="inp", help="file to read (with --decrypt)")
    ap.add_argument("--passfile", help="JSON {list_id: passphrase}; missing entries are generated and saved")
    ap.add_argument("--passphrase", help="explicit passphrase (else from --passfile)")
    ap.add_argument("--decrypt", action="store_true")
    A = ap.parse_args()
    if A.decrypt:
        print(json.dumps(load_any(A.inp, A.passfile, A.passphrase), ensure_ascii=False))
        sys.exit(0)
    p = Path(A.inout)
    bundle = json.loads(p.read_text(encoding="utf-8"))
    if bundle.get("format") == "metaphor-review-bundle-encrypted":
        print(f"{p.name}: already encrypted"); sys.exit(0)
    assert bundle.get("format") == "metaphor-review-bundle", "not a review bundle"
    if A.passphrase:
        pw = A.passphrase
    else:
        pf = Path(A.passfile)
        table = json.loads(pf.read_text(encoding="utf-8")) if pf.exists() else {}
        pw = table.get(bundle["list_id"]) or new_passphrase()
        table[bundle["list_id"]] = pw
        pf.write_text(json.dumps(table, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    env = encrypt(bundle, pw)
    assert decrypt(env, pw) == bundle
    p.write_text(json.dumps(env, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{p.name}: encrypted ({len(bundle['rows'])} rows) — passphrase: {pw}")
