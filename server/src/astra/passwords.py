"""Password hashing with `hashlib.scrypt`.

A hash is the string `scrypt$N$r$p$salt$digest`: the cost parameters, a
16-byte random salt per user and the 32-byte digest, both URL-safe base64.
The parameters travel with the hash, so raising the cost later does not lock
out existing accounts. docs/auth.md names the values.
"""

import base64
import hashlib
import hmac
import secrets

SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1
SALT_BYTES = 16
DIGEST_BYTES = 32


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii")


def _digest(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode(),
        salt=salt,
        n=n,
        r=r,
        p=p,
        maxmem=2 * 128 * n * r,
        dklen=DIGEST_BYTES,
    )


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    digest = _digest(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt, expected = encoded.split("$")
        if scheme != "scrypt":
            return False
        actual = _digest(
            password, base64.urlsafe_b64decode(salt), int(n), int(r), int(p)
        )
        return hmac.compare_digest(actual, base64.urlsafe_b64decode(expected))
    except ValueError:
        return False
