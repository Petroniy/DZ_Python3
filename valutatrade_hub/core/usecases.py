from valutatrade_hub.core.currencies import CryptoCurrency, get_currency
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
)
from valutatrade_hub.core.models import Portfolio, User
from valutatrade_hub.core.utils import (
    is_rate_fresh,
    parse_timestamp,
    utc_now,
    validate_number,
)
from valutatrade_hub.decorators import log_action
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader


def _extract_pairs(snapshot):
    if "pairs" in snapshot:
        return snapshot["pairs"]
    return {
        pair: record
        for pair, record in snapshot.items()
        if "_" in pair and isinstance(record, dict)
    }


def _usable_record(record, ttl, allow_stale):
    if not isinstance(record, dict):
        return None
    try:
        rate = validate_number(record["rate"], positive=True)
        parse_timestamp(record["updated_at"])
    except (KeyError, ValueError, OverflowError):
        return None
    fresh = is_rate_fresh(record, ttl)
    if not fresh and not allow_stale:
        return None
    return {
        "rate": rate,
        "updated_at": record["updated_at"],
        "source": record.get("source", ""),
        "stale": not fresh,
    }


def _resolve_rate(pairs, from_code, to_code, ttl, *, allow_stale=False):
    if from_code == to_code:
        return {"rate": 1.0, "updated_at": utc_now(), "source": "", "stale": False}
    direct = _usable_record(pairs.get(f"{from_code}_{to_code}"), ttl, allow_stale)
    if direct is not None:
        return direct
    inverse = _usable_record(pairs.get(f"{to_code}_{from_code}"), ttl, allow_stale)
    if inverse is not None:
        try:
            inverse["rate"] = validate_number(1.0 / inverse["rate"], positive=True)
        except (ValueError, OverflowError):
            return None
        return inverse
    if "USD" in (from_code, to_code):
        return None
    from_usd = _resolve_rate(pairs, from_code, "USD", ttl, allow_stale=allow_stale)
    to_usd = _resolve_rate(pairs, to_code, "USD", ttl, allow_stale=allow_stale)
    if from_usd is None or to_usd is None:
        return None
    try:
        rate = validate_number(from_usd["rate"] / to_usd["rate"], positive=True)
    except (ValueError, OverflowError):
        return None
    return {
        "rate": rate,
        "updated_at": min(
            (from_usd["updated_at"], to_usd["updated_at"]), key=parse_timestamp
        ),
        "source": ", ".join(
            dict.fromkeys(
                source for source in (from_usd["source"], to_usd["source"]) if source
            )
        ),
        "stale": from_usd["stale"] or to_usd["stale"],
    }


class TradingService:
    def __init__(self, database=None):
        self.database = database if database is not None else DatabaseManager()
        self.settings = SettingsLoader()
        self.current_user = None

    def register(self, username, password):
        """Создаёт пользователя и его пустой портфель."""
        with self.database.transaction():
            users = self.database.load_users()
            portfolios = self.database.load_portfolios()
            user_id = max((item["user_id"] for item in users), default=0) + 1
            user = User.create(user_id, username, password)
            if any(item["username"] == user.username for item in users):
                raise ValueError(f"Имя пользователя '{user.username}' уже занято")
            self.database.save_users([*users, user.to_dict()])
            try:
                self.database.save_portfolios(
                    [*portfolios, {"user_id": user_id, "wallets": {}}]
                )
            except (OSError, ValueError):
                self.database.save_users(users)
                raise
        return user.get_user_info()

    def login(self, username, password):
        """Проверяет пароль и сохраняет пользователя текущей сессии."""
        if not isinstance(username, str) or not username.strip():
            raise ValueError("Имя пользователя не может быть пустым")
        username = username.strip()
        users = self.database.load_users()
        record = next((item for item in users if item["username"] == username), None)
        if record is None:
            raise ValueError(f"Пользователь '{username}' не найден")
        user = User(**record)
        if not user.verify_password(password):
            raise ValueError("Неверный пароль")
        self.current_user = user
        return user.get_user_info()

    def _require_user(self):
        if self.current_user is None:
            raise ValueError("Сначала выполните login")
        return self.current_user

    def _load_portfolio(self, portfolios):
        user = self._require_user()
        for index, record in enumerate(portfolios):
            if record["user_id"] == user.user_id:
                return index, Portfolio(user, record["wallets"])
        raise ValueError("Портфель пользователя не найден")

    def show_portfolio(self, base="USD"):
        user = self._require_user()
        try:
            base = get_currency(base).code
        except CurrencyNotFoundError as error:
            raise ValueError(f"Неизвестная базовая валюта '{base}'") from error
        portfolios = self.database.load_portfolios()
        _, portfolio = self._load_portfolio(portfolios)
        wallets = []
        total = 0.0
        for code, wallet in portfolio.wallets.items():
            value = (
                wallet.balance * self.get_rate(code, base)["rate"]
                if wallet.balance
                else 0.0
            )
            value = validate_number(value)
            total += value
            wallets.append(
                {"currency_code": code, "balance": wallet.balance, "value": value}
            )
        return {
            "username": user.username,
            "base": base,
            "wallets": wallets,
            "total": validate_number(total),
        }

    @log_action("BUY", verbose=True)
    def buy(self, currency_code, amount):
        return self._trade(currency_code, amount, buying=True)

    @log_action("SELL", verbose=True)
    def sell(self, currency_code, amount):
        return self._trade(currency_code, amount, buying=False)

    def _trade(self, currency_code, amount, *, buying):
        user = self._require_user()
        code = get_currency(currency_code).code
        amount = validate_number(amount, positive=True)
        with self.database.transaction():
            portfolios = self.database.load_portfolios()
            index, portfolio = self._load_portfolio(portfolios)
            wallets = portfolio.wallets
            if not buying:
                wallet = portfolio.get_wallet(code)
                if amount > wallet.balance:
                    raise InsufficientFundsError(wallet.balance, amount, code)
            else:
                wallet = wallets.get(code)
                if wallet is None:
                    wallet = portfolio.add_currency(code)
            before = wallet.balance
            rate = self.get_rate(code, "USD")["rate"]
            cost = validate_number(amount * rate, positive=True)
            if buying:
                wallet.deposit(amount)
            else:
                wallet.withdraw(amount)
            portfolios[index] = portfolio.to_dict()
            self.database.save_portfolios(portfolios)
        return {
            "username": user.username,
            "currency_code": code,
            "amount": amount,
            "rate": rate,
            "base": "USD",
            "before": before,
            "after": wallet.balance,
            "cost": cost,
        }

    def get_rate(self, from_code, to_code):
        """Возвращает свежий прямой, обратный или кросс-курс через USD."""
        from_currency = get_currency(from_code)
        to_currency = get_currency(to_code)
        from_code, to_code = from_currency.code, to_currency.code
        if from_code == to_code:
            return {"rate": 1.0, "updated_at": utc_now()}
        ttl = self.settings.get("rates_ttl_seconds", 300)
        pairs = _extract_pairs(self.database.load_rates())
        result = _resolve_rate(pairs, from_code, to_code, ttl)
        if result is not None:
            return {"rate": result["rate"], "updated_at": result["updated_at"]}
        non_usd = [
            currency
            for currency in (from_currency, to_currency)
            if currency.code != "USD"
        ]
        if all(isinstance(currency, CryptoCurrency) for currency in non_usd):
            source = "coingecko"
        elif all(not isinstance(currency, CryptoCurrency) for currency in non_usd):
            source = "exchangerate"
        else:
            source = None
        try:
            report = self.update_rates(source)
        except ApiRequestError as error:
            raise ApiRequestError(
                f"Курс {from_code}→{to_code} недоступен. {error.reason}"
            ) from error
        pairs = _extract_pairs(self.database.load_rates())
        result = _resolve_rate(pairs, from_code, to_code, ttl)
        if result is None:
            details = "; ".join(report.get("errors", []))
            raise ApiRequestError(
                f"Курс {from_code}→{to_code} недоступен. "
                f"{details or 'Повторите попытку позже.'}"
            )
        return {"rate": result["rate"], "updated_at": result["updated_at"]}

    def update_rates(self, source=None):
        from valutatrade_hub.parser_service.storage import RatesStorage
        from valutatrade_hub.parser_service.updater import RatesUpdater

        return RatesUpdater(storage=RatesStorage(self.database)).run_update(
            source=source
        )

    def show_rates(self, currency=None, top=None, base="USD"):
        """Читает локальный снимок без сетевых запросов."""
        base = get_currency(base).code
        if currency is not None:
            currency = get_currency(currency).code
        if top is not None and (
            isinstance(top, bool) or not isinstance(top, int) or top <= 0
        ):
            raise ValueError("'top' должен быть положительным целым числом")
        pairs = _extract_pairs(self.database.load_rates())
        if not pairs:
            raise ValueError(
                "Локальный кеш курсов пуст. Выполните 'update-rates', "
                "чтобы загрузить данные."
            )
        codes = set()
        for pair in pairs:
            parts = pair.split("_")
            if len(parts) != 2:
                continue
            for code in parts:
                if code != base:
                    codes.add(code)
        if currency is not None:
            codes = {currency}
        ttl = self.settings.get("rates_ttl_seconds", 300)
        result = []
        for code in sorted(codes):
            try:
                currency_object = get_currency(code)
            except CurrencyNotFoundError:
                continue
            if top is not None and not isinstance(currency_object, CryptoCurrency):
                continue
            record = _resolve_rate(pairs, code, base, ttl, allow_stale=True)
            if record is not None:
                result.append({"pair": f"{code}_{base}", **record})
        if currency is not None and not result:
            raise ValueError(f"Курс для '{currency}' не найден в кеше.")
        if top is not None:
            result.sort(key=lambda item: item["rate"], reverse=True)
            result = result[:top]
        return result


def get_rate(from_code, to_code, database=None):
    return TradingService(database).get_rate(from_code, to_code)
