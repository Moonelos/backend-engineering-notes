"""A local diagnostic test; the marker is fake and grants no authority."""
import io
import logging

fake_secret = "FAKE_KEY_FOR_LOCAL_ASSERTION_ONLY"
stream = io.StringIO()
handler = logging.StreamHandler(stream)
handler.setFormatter(logging.Formatter("%(message)s"))
logger = logging.getLogger("notes.secret-boundary")
logger.handlers = [handler]
logger.propagate = False
logger.setLevel(logging.INFO)
try:
    raise RuntimeError(f"provider rejected {fake_secret}")
except RuntimeError:
    # Do not log the exception text: an upstream library may embed a credential.
    logger.warning("provider_auth_failed version=%s", "v8")
output = stream.getvalue().strip()
assert fake_secret not in output
assert output == "provider_auth_failed version=v8"
print("safe diagnostic:", output)
