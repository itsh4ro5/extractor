import base64

SECRET_KEY = "GHOST_PROTOCOL_MASTER_KEY" # Secret Key (Dono repo me same honi chahiye)

def encrypt_url(url: str, key: str = SECRET_KEY) -> str:
    """Takes a raw URL and returns a GHOST encrypted string."""
    if not url: return ""
    encrypted_chars = [chr(ord(url[i]) ^ ord(key[i % len(key)])) for i in range(len(url))]
    encoded_bytes = base64.b64encode("".join(encrypted_chars).encode('utf-8'))
    return "GHOST:" + encoded_bytes.decode('utf-8')
