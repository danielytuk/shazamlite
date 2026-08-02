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
