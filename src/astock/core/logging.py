import logging
from pathlib import Path


def setup_logging(cfg):
    log_path = Path(cfg.file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("astock")
    logger.setLevel(getattr(logging, cfg.level.upper(), logging.INFO))

    if not logger.handlers:
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
        logger.addHandler(fh)

        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(ch)

    return logger
