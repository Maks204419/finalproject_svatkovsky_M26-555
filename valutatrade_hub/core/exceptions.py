"""Domain-specific exceptions with human-readable messages."""


class ValutaTradeError(Exception):
    """Base error for expected application failures."""


class InsufficientFundsError(ValutaTradeError):
    """Raised when a wallet cannot cover a debit."""

    def __init__(self, available: float, required: float, code: str) -> None:
        super().__init__(
            f"Недостаточно средств: доступно {available:.4f} {code}, "
            f"требуется {required:.4f} {code}"
        )


class CurrencyNotFoundError(ValutaTradeError):
    """Raised for a currency absent from the registry."""

    def __init__(self, code: str) -> None:
        super().__init__(f"Неизвестная валюта '{code}'")


class ApiRequestError(ValutaTradeError):
    """Raised for unsuccessful external API requests."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Ошибка при обращении к внешнему API: {reason}")


class ValidationError(ValutaTradeError):
    """Raised for invalid user input."""


class AuthenticationError(ValutaTradeError):
    """Raised when authentication is required or fails."""
