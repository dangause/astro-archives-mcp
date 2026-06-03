"""Shim around vcrpy's response stub.

astropy.io.votable.parse calls ``response.read(amt, decode_content=True)``
on the urllib3 HTTPResponse it receives. vcrpy's ``VCRHTTPResponse.read``
forwards ``decode_content`` straight to the underlying ``BytesIO``, which
rejects unknown kwargs. We strip ``decode_content`` so replay matches the
behaviour of a real urllib3 response (which simply ignores it for already-
decoded content).
"""

from io import BytesIO

from vcr.stubs import VCRHTTPResponse


def _read(self, *args, **kwargs):
    kwargs.pop("decode_content", None)
    return self._content.read(*args, **kwargs)


def _read1(self, *args, **kwargs):
    kwargs.pop("decode_content", None)
    return self._content.read1(*args, **kwargs)


VCRHTTPResponse.read = _read  # type: ignore[assignment]
VCRHTTPResponse.read1 = _read1  # type: ignore[assignment]


# Ensure BytesIO is imported so the module is non-empty at import time even
# if the patch is no-op'd by an upstream fix later.
_ = BytesIO
