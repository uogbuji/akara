"""Define the Akara logger and ways to configure it

Akara's logging system is built around its use as a server and not as
a library. It logs everything to a single log file, specified in a
configuration file.

When Akara starts it doesn't know the logging destination. During this
bootstrap phase, any errors (like errors in reading the configuration
file) are sent to sys.stderr. Once the logging file is known, use
set_logfile(f) to start sending log messages to that file _in_
_addition_ to the messages to stderr.

Why? Because the server might be in debug mode, where the messages are
both displayed to stderr and logged to the log file. If this is not
the case then call remove_logging_to_stderr() which does just what it
says it does.

At any time you can call set_logfile(f) again to log the messages to a
different file.

"""

import sys
import logging

from cStringIO import StringIO

__all__ = ("logger", "set_logfile", "remove_logging_to_stderr")

# Create the logger here but mark it as private.
# The other modules can access this as "akara.logger"
_logger = logging.getLogger('akara')

# Make the log messages look like:
# Jul 21 01:39:03 akara[11754]: [error] Traceback (most recent call last):
_default_formatter = logging.Formatter(
    "%(asctime)s %(name)s[%(process)s]: [%(levelname)s] %(message)s",
    "%b %d %H:%M:%S")

# Make special log levels for stdout and stderr.
# Makes the logging messages easier to read.
STDOUT, STDERR = 22, 21
logging.addLevelName(STDERR, "stderr")
logging.addLevelName(STDOUT, "stdout")



# The current output stream for the Akara server.
# Gets initialized in a bit.
_current_handler = None


def set_logfile(f):
    """Direct (or redirect) error logging to a file handle"""
    global _current_handler
    new_handler = logging.FileHandler(f)
    new_handler.setFormatter(_default_formatter)
    _logger.addHandler(new_handler)

    if _current_handler is not None:
        _logger.removeHandler(_current_handler)
    _current_handler = new_handler

## Part of initialization, to log to stderr
# Set the default logger to stderr
def _init_stderr_handler():
    new_handler = logging.StreamHandler(sys.stderr)
    new_handler.setFormatter(_default_formatter)
    _logger.addHandler(new_handler)
    return new_handler

# Save this so I can remove it for later, if requested
_stderr_handler = _init_stderr_handler()

# Then forget about it. It's still registered in the error handler.
_current_handler = None

# At this point there is logging to stderr, and it cannot be clobbered
# by set_logfile.

# Later on it is possible to remove the stderr handler
def remove_logging_to_stderr():
    "Disable logging to stderr. This cannot be re-enabled."
    global _stderr_handler
    if _stderr_handler is not None:
        _logger.removeHandler(_stderr_handler)
        _stderr_handler = None


# This is a simple redirector.
# It fails if none of your prints end with a "\n".
# Don't do that. ;)
class WriteToLogger(object):
    def __init__(self, loglevel):
        self.loglevel = loglevel
        self.chunks = []
    def write(self, s):
        if s.endswith("\n"):
            text = "".join(self.chunks) + s[:-1]
            _logger.log(self.loglevel, text)
        else:
            self.chunks.append(s)


def redirect_stdio():
    sys.stdin = StringIO("")
    sys.stdout = WriteToLogger(STDOUT)
    sys.stderr = WriteToLogger(STDERR)

########  Access logger

# Use the logging mechanism to deal with access logging

# I think this is a bit more cute than I would like.
# Log at the DEBUG level to akara.access.
# That always writes to the _access_logger because of the .setLevel(DEBUG)
# The log event trickles up to the 'akara' logger.
# That only displays in debug mode (most likely with -X)
#  Downside: it displays with the standard Akara log prefix

_access_logger = logging.getLogger("akara.access")
_access_logger.setLevel(logging.DEBUG)
_access_log_formatter = logging.Formatter("%(message)s")

_access_handler = None

def set_access_logfile(f):
    global _access_handler
    new_access_handler = logging.FileHandler(f)
    new_access_handler.setFormatter(_access_log_formatter)
    _access_logger.addHandler(new_access_handler)
    if _access_handler is not None:
        _access_logger.removeHandler(_access_handler)
    _access_handler = new_access_handler
