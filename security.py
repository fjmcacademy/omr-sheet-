import hashlib, hmac, os
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 180000)
    return salt.hex() + "$" + digest.hex()
def verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$", 1)
        check = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 180000).hex()
        return hmac.compare_digest(check, digest)
    except Exception:
        return False
