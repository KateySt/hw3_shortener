import logging

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"
NOISY_LOGGERS = ("boto3", "botocore", "urllib3")
NOISY_LOGGERS_LEVEL = logging.WARNING


def configure_logging(level: str) -> None:
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(NOISY_LOGGERS_LEVEL)
    if logging.getLogger().handlers:
        return
    logging.basicConfig(level=level, format=LOG_FORMAT, datefmt=DATE_FORMAT)


def get_logger(name: str, level: str = "INFO") -> logging.Logger:
    configure_logging(level)
    return logging.getLogger(name)
