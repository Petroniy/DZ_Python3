import hashlib
import hmac
import secrets
from datetime import datetime, timezone

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import InsufficientFundsError
from valutatrade_hub.core.utils import validate_number


class User:
    def __init__(self, user_id, username, hashed_password, salt, registration_date):
        if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
            raise ValueError(
                "Идентификатор пользователя должен быть положительным целым"
            )
        if not isinstance(hashed_password, str) or not hashed_password:
            raise ValueError("Хеш пароля не может быть пустым")
        if not isinstance(salt, str) or not salt:
            raise ValueError("Соль не может быть пустой")
        if isinstance(registration_date, str):
            registration_date = datetime.fromisoformat(
                registration_date.replace("Z", "+00:00")
            )
        if not isinstance(registration_date, datetime):
            raise ValueError("Некорректная дата регистрации")
        self._user_id = user_id
        self.username = username
        self._hashed_password = hashed_password
        self._salt = salt
        self._registration_date = registration_date

    @classmethod
    def create(cls, user_id, username, password):
        cls._validate_password(password)
        salt = secrets.token_hex(16)
        hashed_password = hashlib.sha256((password + salt).encode("utf-8")).hexdigest()
        return cls(user_id, username, hashed_password, salt, datetime.now(timezone.utc))

    @staticmethod
    def _validate_password(password):
        if not isinstance(password, str) or len(password) < 4:
            raise ValueError("Пароль должен быть не короче 4 символов")

    @property
    def user_id(self):
        return self._user_id

    @property
    def username(self):
        return self._username

    @username.setter
    def username(self, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Имя пользователя не может быть пустым")
        self._username = value.strip()

    @property
    def hashed_password(self):
        return self._hashed_password

    @property
    def salt(self):
        return self._salt

    @property
    def registration_date(self):
        return self._registration_date

    def get_user_info(self):
        """Возвращает сведения, которые можно показать пользователю."""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "registration_date": self.registration_date.isoformat(),
        }

    def change_password(self, new_password):
        self._validate_password(new_password)
        self._salt = secrets.token_hex(16)
        self._hashed_password = hashlib.sha256(
            (new_password + self.salt).encode("utf-8")
        ).hexdigest()

    def verify_password(self, password):
        if not isinstance(password, str):
            return False
        candidate = hashlib.sha256((password + self.salt).encode("utf-8")).hexdigest()
        return hmac.compare_digest(self.hashed_password, candidate)

    def to_dict(self):
        return {
            **self.get_user_info(),
            "hashed_password": self.hashed_password,
            "salt": self.salt,
        }


class Wallet:
    def __init__(self, currency_code, balance=0.0):
        self.currency_code = get_currency(currency_code).code
        self.balance = balance

    @property
    def balance(self):
        return self._balance

    @balance.setter
    def balance(self, value):
        self._balance = validate_number(value)

    def deposit(self, amount):
        amount = validate_number(amount, positive=True)
        self.balance = self.balance + amount

    def withdraw(self, amount):
        amount = validate_number(amount, positive=True)
        if amount > self.balance:
            raise InsufficientFundsError(self.balance, amount, self.currency_code)
        self.balance = self.balance - amount

    def get_balance_info(self):
        return f"{self.currency_code}: {self.balance:.4f}"


class Portfolio:
    def __init__(self, user_id, wallets=None, user=None):
        if isinstance(user_id, User):
            user = user_id
            user_id = user.user_id
        if user is None:
            from valutatrade_hub.infra.database import DatabaseManager

            stored = next(
                (
                    item
                    for item in DatabaseManager().load_users()
                    if item["user_id"] == user_id
                ),
                None,
            )
            if stored is None:
                raise ValueError(f"Пользователь с id={user_id} не найден")
            user = User(**stored)
        if not isinstance(user, User) or user.user_id != user_id:
            raise ValueError("Пользователь не соответствует портфелю")
        self._user_id = user_id
        self._user = user
        self._wallets = {}
        for code, value in (wallets or {}).items():
            normalized = get_currency(code).code
            if normalized in self._wallets:
                raise ValueError(f"Кошелёк '{normalized}' уже существует")
            if isinstance(value, Wallet):
                if value.currency_code != normalized:
                    raise ValueError("Код кошелька не соответствует ключу")
                self._wallets[normalized] = value
            else:
                self._wallets[normalized] = Wallet(normalized, value["balance"])

    @property
    def user(self):
        return self._user

    @property
    def wallets(self):
        return self._wallets.copy()

    def add_currency(self, currency_code):
        normalized = get_currency(currency_code).code
        if normalized in self._wallets:
            raise ValueError(f"Кошелёк '{normalized}' уже существует")
        self._wallets[normalized] = Wallet(normalized)
        return self._wallets[normalized]

    def get_wallet(self, currency_code):
        normalized = get_currency(currency_code).code
        if normalized not in self._wallets:
            raise ValueError(
                f"У вас нет кошелька '{normalized}'. Добавьте валюту: "
                "она создаётся автоматически при первой покупке."
            )
        return self._wallets[normalized]

    def get_total_value(self, base_currency="USD"):
        from valutatrade_hub.core.usecases import get_rate

        base = get_currency(base_currency).code
        total = 0.0
        for code, wallet in self._wallets.items():
            if wallet.balance:
                total += wallet.balance * get_rate(code, base)["rate"]
        return validate_number(total)

    def to_dict(self):
        return {
            "user_id": self._user_id,
            "wallets": {
                code: {"balance": wallet.balance}
                for code, wallet in self._wallets.items()
            },
        }
