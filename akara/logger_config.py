"""Define the Akara logger and ways to configure it"""

# Akara is designed as a server and not a library.
# Create the logger, set up a default handler for it to stderr.
# API users have a way to add logging to a file, or to replace that file.
# The log file is IN ADDITION to the stderr logger.
# Once the real logging system is in place, remove the stderr logger.

import sys
import logging


__all__ = ("logger", "set_logfile", "remove_logging_to_stderr")

logger = logging.getLogger('akara')

# Make the log messages look like:
# Jul 21 01:39:03 akara[11754]: [error] Traceback (most recent call last):
_default_formatter = logging.Formatter(
    "%(asctime)s %(name)s[%(process)s]: [%(levelname)s] %(message)s",
    "%b %d %H:%M:%S")

# The current output stream for the Akara server.
# Gets initialized in a bit.
_current_handler = None


def set_logfile(f):
    """Direct (or redirect) error logging to a file handle"""
    global _current_handler
    new_handler = logging.StreamHandler(f)
    new_handler.setFormatter(_default_formatter)
    logger.addHandler(new_handler)

    if _current_handler is not None:
        logger.removeHandler(_current_handler)
    _current_handler = new_handler

## Part of initialization, to log to stderr
# Set the default logger to stderr
set_logfile(sys.stderr)

# Save this so I can remove it for later, if requested
_stderr_handler = _current_handler

# Then forget about it. It's still registered in the error handler.
_current_handler = None

# At this point there is logging to stderr, and it cannot be clobbered
# by set_logfile.

# Later on it is possible to remove the stderr handler
def remove_logging_to_stderr():
    global _stderr_handler
    if _stderr_handler is not None:
        logger.removehander(_stderr_handler)
        _stderr_handler = None
