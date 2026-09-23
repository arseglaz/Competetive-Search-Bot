class ProviderError(Exception):
    def __init__(
            self,
            message: str,
            *,
            kind: str,
            status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.status_code = status_code