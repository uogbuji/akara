# Temporary location for the logger. 'logger' is a bad name.
# Want to move under Akara.

import sys
import logging

logger = logging.getLogger('akara')

# Jul 21 01:39:03 akara[11754]: [error] Traceback (most recent call last):
_default_formatter = logging.Formatter(
    "%(asctime)s %(name)s[%(process)s]: [%(levelname)s] %(message)s",
    "%b %d %H:%M:%S")

_current_handler = None

def set_logfile(f):
    global _current_handler
    new_handler = logging.StreamHandler()
    new_handler.setFormatter(_default_formatter)
    logger.addHandler(new_handler)

    if _current_handler is not None:
        logger.removeHandler(_current_handler)
    _current_handler = new_handler

# Set the default logger to stderr
_stderr_handler = _current_handler

# Then forget about it. It's still registered in the error handler.
_current_handler = None

# Later on it's possible to remove the stderr handler
def remove_logging_to_stderr():
    global _stderr_handler
    if _stderr_handler is not None:
        logger.removehander(_stderr_handler)
        _stderr_handler = None
