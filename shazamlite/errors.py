from typing import Optional


class ShazamError(Exception):
    pass


class NoMatch(ShazamError):
    pass


class BadData(ShazamError):
    pass


class MaxRetriesExceeded(ShazamError):
    pass


class FailedDecodeJson(ShazamError):
    def __init__(self, status_code, body, url):
        self.status_code = status_code
        self.body = body
        self.url = url
        super().__init__(
            "Failed to decode JSON response from %s (status %s): %r"
            % (url, status_code, body[:500])
        )


class HTTPStatusError(ShazamError):
    def __init__(self, status_code, body, url):
        self.status_code = status_code
        self.body = body
        self.url = url
        super().__init__(
            "HTTP %s from %s: %r" % (status_code, url, body[:500])
        )

    @property
    def hint(self) -> Optional[str]:
        """A human-readable hint for common blocking statuses, if any."""
        if self.status_code in (403, 405, 429):
            return (
                "This looks like a network-level block. Shazam/Fastly rejects "
                "VPN, proxy and datacenter exit IPs with 403/405. Disconnect "
                "any VPN or proxy, then retry."
            )
        return None
