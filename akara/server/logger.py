########################################################################
# akara/server/logger.py
from __future__ import with_statement

import os
import sys
import time
import operator
import functools
import threading

LOG_EMERG = (0, 'emerg')
LOG_ALERT = (1, 'alert')
LOG_CRIT = (2, 'crit')
LOG_ERROR = LOG_ERR = (3, 'error')
LOG_WARNING = LOG_WARN = (4, 'warn')
LOG_NOTICE = (5, 'notice')
LOG_INFO = (6, 'info')
LOG_DEBUG = (7, 'debug')

class logger(object):

    def __init__(self, ident, stream, level=LOG_INFO, show_header=False,
                 show_pid=False):
        self.ident = ident
        self.stream = stream
        self.level = level
        self.show_header = show_header
        self.show_pid = show_pid

        # Localize for performance
        self._write = stream.write
        self._flush = stream.flush
        return

    def clone(self, ident, level=None):
        # Create a new Logger instance with the given identifier
        if level is None:
            level = self.level
        return self.__class__(ident, self.stream, level, self.show_header,
                              self.show_pid)

    def get_level(self):
        return self._level
    def set_level(self, level):
        self._level = level
        level, priority = level
        if level >= 0:
            wrapper = functools.partial(self._log, LOG_EMERG)
            self.emergency = functools.update_wrapper(wrapper, self.emergency)
        if level >= 1:
            wrapper = functools.partial(self._log, LOG_ALERT)
            self.alert = functools.update_wrapper(wrapper, self.alert)
        if level >= 2:
            wrapper = functools.partial(self._log, LOG_CRIT)
            self.critical = functools.update_wrapper(wrapper, self.critical)
        if level >= 3:
            wrapper = functools.partial(self._log, LOG_ERROR)
            self.error = functools.update_wrapper(wrapper, self.error)
        if level >= 4:
            wrapper = functools.partial(self._log, LOG_WARNING)
            self.warning = functools.update_wrapper(wrapper, self.warning)
        if level >= 5:
            wrapper = functools.partial(self._log, LOG_NOTICE)
            self.notice = functools.update_wrapper(wrapper, self.notice)
        if level >= 6:
            wrapper = functools.partial(self._log, LOG_INFO)
            self.info = functools.update_wrapper(wrapper, self.info)
        if level >= 7:
            wrapper = functools.partial(self._log, LOG_DEBUG)
            self.debug = functools.update_wrapper(wrapper, self.debug)
        return
    level = property(get_level, set_level)
    del get_level, set_level

    _timestamp = functools.partial(time.strftime, "%b %d %H:%M:%S")

    def _log(self, level, message, *args):
        level, priority = level
        # deferred formating (printf-style); only apply replacement if `args`
        # is non-empty to allow for pre-formatted messages that contain '%'.
        if args:
            message %= args

        # create the message header: "mmm dd HH:MM:SS ident[pid]: <message>"
        if self.show_header:
            ident = self.ident
            if self.show_pid:
                ident = "%s[%d]" % (ident, os.getpid())
            format = '%s %s: [%s] %%s' % (self._timestamp(), ident, priority)
            # split `message` into lines, keeping the newline
            lines = [ format % line for line in message.splitlines(True) ]
            message = ''.join(lines)
        # ensure `message` is newline-terminated
        if message[-1:] != '\n':
            message += '\n'
        # emit the now formatted `message`
        self._write(message)
        self._flush()
        return

    def log(self, level, message, *args):
        if self._level >= level:
            self._log(level, message, *args)
        return

    def emergency(self, msg, *args):
        """Log `msg % args` with level`LOG_EMERG`"""
        return

    def alert(self, msg, *args):
        """Log `msg % args` with level `LOG_ALERT`"""
        return

    def critical(self, msg, *args):
        """Log `msg % args` with level `LOG_CRIT`"""
        return

    def error(self, msg, *args):
        """Log `msg % args` with level `LOG_ERROR`"""
        return

    def warning(self, msg, *args):
        """Log `msg % args` with level `LOG_WARNING`"""
        return

    def notice(self, msg, *args):
        """Log `msg % args` with level `LOG_NOTICE`"""
        return

    def info(self, msg, *args):
        """Log `msg % args` with level `LOG_INFO`"""
        return

    def debug(self, msg, *args):
        """Log `msg % args` with level `LOG_DEBUG`"""
        return

    def __str__(self):
        try:
            fname = self.stream.name
        except AttributeError:
            fname = str(self.stream)
        level, priority = self.level
        level = 'LOG_' + priority.upper()
        return "<%s logger, file %r, level %s>" % (self.ident, fname, level)

class loggerstream:
    """
    A wrapper around a Logger instance which allows the log facility
    to be used in place of a stream object.
    """
    def __init__(self, logger, level):
        self.closed = False
        self.softspace = 0
        self._logger = logger
        self._level = level
        self._lock = threading.Lock()
        self._buffer = []

    def close(self):
        if not self.closed:
            self.closed = True
            del self._buffer

    def flush(self):
        if self.closed:
            raise ValueError("I/O operation on closed file")
        if self._buffer:
            with self._lock:
                msg = ''.join(self._buffer)
                del self._buffer[:]
            self._logger.log(self._level, msg)
        return

    def isatty(self):
        if self.closed:
            raise ValueError("I/O operation on closed file")
        return False

    def write(self, bytes):
        if self.closed:
            raise ValueError("I/O operation on closed file")
        self.softspace = 0
        if '\n' in bytes:
            if self._buffer:
                msg, sep, bytes = bytes.partition('\n')
                with self._lock:
                    msg = ''.join(self._buffer) + msg
                    del self._buffer[:]
                self._logger.log(self._level, msg)
            msg, sep, bytes = bytes.rpartition('\n')
            self._logger.log(self._level, msg)
        if bytes:
            with self._lock:
                self._buffer.append(bytes)
        return
