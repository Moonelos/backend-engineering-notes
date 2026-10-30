"""Bounded local byte ingestion; never serves or executes untrusted contents."""
from collections.abc import Iterable
from contextlib import contextmanager
import hashlib
from tempfile import TemporaryFile


class UploadTooLarge(ValueError):
    pass


@contextmanager
def quarantine(chunks: Iterable[bytes], *, limit: int):
    """Yield a private temporary file, exact size and SHA-256; always close it."""
    if limit <= 0:
        raise ValueError("limit must be positive")
    with TemporaryFile(mode="w+b") as staged:
        size = 0
        digest = hashlib.sha256()
        for chunk in chunks:
            size += len(chunk)
            if size > limit:
                raise UploadTooLarge("upload exceeds configured byte limit")
            staged.write(chunk)
            digest.update(chunk)
        staged.seek(0)
        yield staged, size, digest.hexdigest()


def main():
    with quarantine([b"abc", b"def"], limit=6) as (staged, size, digest):
        assert staged.read() == b"abcdef"
        assert size == 6
        assert digest == "bef57ec7f53a6d40beb640a780a639c83bc29ac8a9816f1fc6c5c6dcd93c4721"
        print("accepted 6 bytes into quarantine")
    assert staged.closed
    try:
        with quarantine([b"abc", b"def", b"g"], limit=6):
            raise AssertionError("oversize input reached acceptance")
    except UploadTooLarge:
        print("rejected 7 bytes at limit 6")

    def disconnected():
        yield b"abc"
        raise ConnectionError("simulated disconnect")

    try:
        with quarantine(disconnected(), limit=6):
            raise AssertionError("disconnected input reached acceptance")
    except ConnectionError:
        print("disconnect did not publish a result")


if __name__ == "__main__":
    main()
