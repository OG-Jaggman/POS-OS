import hashlib
import hmac
import os


def hash_pin(pin: str) -> str:
    if not pin.isdigit() or not (4 <= len(pin) <= 12):
        raise ValueError("PIN must contain 4 to 12 digits")
    salt = os.urandom(16)
    digest = hashlib.scrypt(pin.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_pin(pin: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$", 2)
        if scheme != "scrypt":
            return False
        actual = hashlib.scrypt(pin.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(actual.hex(), digest_hex)
    except Exception:
        return False
