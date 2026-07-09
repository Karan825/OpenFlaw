import hmac
import hashlib

def verify_signature(payload: bytes, signature_header: str, secret: str) -> bool:
    """
    Verifies that the signature in the X-Hub-Signature-256 header matches the
    HMAC-SHA256 digest of the request payload using the specified webhook secret.
    """
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    
    # Extract the hex digest from the header (format: sha256=<digest>)
    expected_signature = signature_header.split("sha256=", 1)[-1]
    
    # Compute HMAC digest of payload
    mac = hmac.new(secret.encode("utf-8"), msg=payload, digestmod=hashlib.sha256)
    actual_signature = mac.hexdigest()
    
    # Prevent timing attacks using constant-time comparison
    return hmac.compare_digest(actual_signature, expected_signature)
