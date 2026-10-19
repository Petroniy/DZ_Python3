class InsufficientFundsError(Exception):
    """На кошельке не хватает средств для операции."""

    def __init__(self, available, required, code):
        self.available = available
        self.required = required
        self.code = code
        super().__init__(
            f"Недостаточно средств: доступно {available} {code}, "
            f"требуется {required} {code}"
        )


class CurrencyNotFoundError(Exception):
    """Код отсутствует в реестре валют."""

    def __init__(self, code):
        self.code = code
        super().__init__(f"Неизвестная валюта '{code}'")


class ApiRequestError(Exception):
    """Внешний источник не предоставил пригодный курс."""

    def __init__(self, reason):
        self.reason = str(reason)
        super().__init__(f"Ошибка при обращении к внешнему API: {self.reason}")
