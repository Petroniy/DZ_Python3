import argparse
import shlex
import sys

from prettytable import PrettyTable

from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
)
from valutatrade_hub.core.usecases import TradingService
from valutatrade_hub.logging_config import setup_logging

COMMANDS = {
    "register": "register --username <имя> --password <пароль>",
    "login": "login --username <имя> --password <пароль>",
    "show-portfolio": "show-portfolio [--base USD]",
    "buy": "buy --currency <код> --amount <количество>",
    "sell": "sell --currency <код> --amount <количество>",
    "get-rate": "get-rate --from <код> --to <код>",
    "update-rates": "update-rates [--source coingecko|exchangerate]",
    "show-rates": "show-rates [--currency <код>] [--top <число>] [--base USD]",
    "help": "help [команда]",
    "exit": "exit",
}


class CommandParser(argparse.ArgumentParser):
    """Сообщает об ошибке аргументов без завершения приложения."""

    def error(self, message):
        raise ValueError(f"Ошибка аргументов: {message}")


def positive_int(value):
    """Проверяет количество строк для show-rates."""
    try:
        result = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("--top должен быть целым числом") from error
    if result <= 0:
        raise argparse.ArgumentTypeError("--top должен быть больше нуля")
    return result


def parse_command(tokens):
    """Разбирает одну команду и её флаги."""
    parser = CommandParser(prog="", add_help=False, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("register", "login"):
        command = commands.add_parser(name, add_help=False, allow_abbrev=False)
        command.add_argument("--username", required=True)
        command.add_argument("--password", required=True)
    command = commands.add_parser("show-portfolio", add_help=False, allow_abbrev=False)
    command.add_argument("--base", default="USD")
    for name in ("buy", "sell"):
        command = commands.add_parser(name, add_help=False, allow_abbrev=False)
        command.add_argument("--currency", required=True)
        command.add_argument("--amount", type=float, required=True)
    command = commands.add_parser("get-rate", add_help=False, allow_abbrev=False)
    command.add_argument("--from", dest="from_code", required=True)
    command.add_argument("--to", dest="to_code", required=True)
    command = commands.add_parser("update-rates", add_help=False, allow_abbrev=False)
    command.add_argument("--source", choices=("coingecko", "exchangerate"))
    command = commands.add_parser("show-rates", add_help=False, allow_abbrev=False)
    command.add_argument("--currency")
    command.add_argument("--top", type=positive_int)
    command.add_argument("--base", default="USD")
    command = commands.add_parser("help", add_help=False, allow_abbrev=False)
    command.add_argument("topic", choices=COMMANDS, nargs="?")
    commands.add_parser("exit", add_help=False, allow_abbrev=False)
    return parser.parse_args(tokens)


def number(value):
    """Форматирует суммы и курсы для консоли."""
    text = f"{value:.8f}".rstrip("0").rstrip(".")
    return f"{value:.8g}" if value and text == "0" else text


def show_portfolio(result):
    """Печатает кошельки и итоговую стоимость портфеля."""
    base = result["base"]
    print(f"Портфель пользователя '{result['username']}' (база: {base}):")
    if not result["wallets"]:
        print("Портфель пуст.")
        return
    table = PrettyTable(["Валюта", "Баланс", f"Стоимость, {base}"])
    for wallet in result["wallets"]:
        table.add_row(
            [
                wallet["currency_code"],
                number(wallet["balance"]),
                f"{wallet['value']:.2f}",
            ]
        )
    print(table)
    print(f"ИТОГО: {result['total']:,.2f} {base}")


def show_trade(result, action):
    """Печатает результат покупки или продажи."""
    code = result["currency_code"]
    base = result["base"]
    title = "Покупка" if action == "buy" else "Продажа"
    print(
        f"{title} выполнена: {number(result['amount'])} {code} "
        f"по курсу {number(result['rate'])} {base}/{code}"
    )
    print(f"{code}: было {number(result['before'])} → стало {number(result['after'])}")
    print(f"Оценочная стоимость: {result['cost']:,.2f} {base}")


def show_rates(rows):
    """Печатает сохранённые курсы с датой и источником."""
    if not rows:
        print("Локальный кеш курсов пуст. Выполните 'update-rates'.")
        return
    table = PrettyTable(["Пара", "Курс", "Обновлено", "Источник", "Статус"])
    for row in rows:
        table.add_row(
            [
                row["pair"],
                number(row["rate"]),
                row["updated_at"],
                row["source"],
                "устарел" if row["stale"] else "актуален",
            ]
        )
    print(table)
    if any(row["stale"] for row in rows):
        print("Есть устаревшие курсы. Выполните 'update-rates'.")


def execute_command(service, arguments):
    """Вызывает операцию сервиса и выводит её результат."""
    command = arguments.command
    if command == "exit":
        return False
    if command == "help":
        if arguments.topic:
            print(COMMANDS[arguments.topic])
        else:
            print("Команды:")
            for usage in COMMANDS.values():
                print(f"  {usage}")
    elif command == "register":
        result = service.register(arguments.username, arguments.password)
        print(
            f"Пользователь '{result['username']}' зарегистрирован "
            f"(id={result['user_id']}). Войдите через login."
        )
    elif command == "login":
        result = service.login(arguments.username, arguments.password)
        print(f"Вы вошли как '{result['username']}'")
    elif command == "show-portfolio":
        show_portfolio(service.show_portfolio(arguments.base))
    elif command in ("buy", "sell"):
        operation = service.buy if command == "buy" else service.sell
        show_trade(operation(arguments.currency, arguments.amount), command)
    elif command == "get-rate":
        result = service.get_rate(arguments.from_code, arguments.to_code)
        source, target = arguments.from_code.upper(), arguments.to_code.upper()
        print(
            f"Курс {source}→{target}: {number(result['rate'])} "
            f"(обновлено: {result['updated_at']})"
        )
        print(f"Обратный курс {target}→{source}: {number(1 / result['rate'])}")
    elif command == "update-rates":
        result = service.update_rates(arguments.source)
        print(
            f"Обновлено курсов: {result['count']}. "
            f"Последнее обновление: {result['last_refresh']}"
        )
        for error in result["errors"]:
            print(f"Ошибка источника: {error}")
        if result["errors"]:
            print("Обновление завершено с ошибками. Подробности: logs/parser.log")
    elif command == "show-rates":
        show_rates(
            service.show_rates(arguments.currency, arguments.top, arguments.base)
        )
    return True


def run_command(service, tokens):
    """Обрабатывает ожидаемые ошибки одной команды."""
    if not tokens:
        return True
    try:
        return execute_command(service, parse_command(tokens))
    except InsufficientFundsError as error:
        print(error)
    except CurrencyNotFoundError as error:
        print(error)
        print("Проверьте код валюты. Справка: help get-rate")
    except ApiRequestError as error:
        print(error)
        print("Проверьте подключение к сети и повторите попытку позже.")
    except (ValueError, OSError) as error:
        print(f"Ошибка: {error}")
    return True


def main(argv=None):
    """Запускает интерактивный режим или одну команду из аргументов."""
    tokens = sys.argv[1:] if argv is None else argv
    try:
        setup_logging()
        service = TradingService()
        if tokens:
            run_command(service, tokens)
            return
        print("Валютный кошелёк. Список команд: help. Выход: exit.")
        while True:
            try:
                line = input("> ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            try:
                tokens = shlex.split(line)
            except ValueError as error:
                print(f"Ошибка ввода: {error}")
                continue
            try:
                if not run_command(service, tokens):
                    break
            except KeyboardInterrupt:
                print("\nКоманда прервана.")
    except (ValueError, OSError) as error:
        print(f"Ошибка запуска: {error}")
    except KeyboardInterrupt:
        print("\nРабота завершена.")
