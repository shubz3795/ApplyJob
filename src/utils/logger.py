import logging
import sys
from pathlib import Path
from rich.logging import RichHandler

_LOGGER = None

def get_logger(name: str = "ApplyJob") -> logging.Logger:
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER.getChild(name)

    base_dir = Path(__file__).resolve().parent.parent.parent
    log_file = base_dir / "applyjob.log"

    logger = logging.getLogger("ApplyJob")
    logger.setLevel(logging.DEBUG)

    # Avoid duplicate handlers if re-initialized
    if not logger.handlers:
        # Rich console handler (INFO level)
        c_handler = RichHandler(rich_tracebacks=True, markup=True, show_time=False)
        c_handler.setLevel(logging.INFO)
        c_format = logging.Formatter("%(message)s")
        c_handler.setFormatter(c_format)
        logger.addHandler(c_handler)

        # File handler (DEBUG level for full audit trail)
        f_handler = logging.FileHandler(log_file, encoding="utf-8")
        f_handler.setLevel(logging.DEBUG)
        f_format = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s:%(lineno)d]: %(message)s")
        f_handler.setFormatter(f_format)
        logger.addHandler(f_handler)

    _LOGGER = logger
    return logger.getChild(name)
