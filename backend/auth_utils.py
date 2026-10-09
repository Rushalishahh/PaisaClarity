import bcrypt

def hash_password(plain_password: str) -> str:
    """
    Hash a plain-text password for safe storage.
    bcrypt automatically generates a random 'salt' each time,
    so the same password hashed twice produces different results -
    this protects against precomputed 'rainbow table' attacks.
    """
    password_bytes = plain_password.encode("utf-8")
    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    return hashed.decode("utf-8")  # store as a string in the database


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Check a login attempt's password against the stored hash.
    We never decrypt the hash - we hash the attempt and let bcrypt
    compare it internally against the stored hash.
    """
    password_bytes = plain_password.encode("utf-8")
    hashed_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(password_bytes, hashed_bytes)