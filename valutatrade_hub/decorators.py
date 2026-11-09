"""Domain action auditing without disclosing passwords."""

import functools
import logging


def log_action(action: str, verbose: bool = False):
    """Log success/failure of a domain operation and re-raise exceptions."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger = logging.getLogger("valutatrade.actions")
            fields = {
                "action": action,
                "user_id": kwargs.get("user_id", args[1] if len(args) > 1 else None),
                "currency_code": kwargs.get("currency_code", args[2] if len(args) > 2 else None),
                "amount": kwargs.get("amount", args[3] if len(args) > 3 else None),
            }
            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                logger.info(
                    "%s result=ERROR error_type=%s error_message=%r",
                    fields,
                    type(exc).__name__,
                    str(exc),
                )
                raise
            details = f" details={result!r}" if verbose else ""
            logger.info("%s result=OK%s", fields, details)
            return result

        return wrapper

    return decorator
