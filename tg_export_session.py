"""Экспорт сессии Telegram для Railway Variables."""

from telegram.session import export_session_env_lines


def main() -> None:
    try:
        lines = export_session_env_lines()
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc

    print("Вставь в Railway → Variables (или .env):\n")
    for line in lines:
        print(line)
    print(
        "\nПосле этого убери TELEGRAM_CODE и TELEGRAM_DUMP_SESSION, сделай Redeploy."
    )


if __name__ == "__main__":
    main()
