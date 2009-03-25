########################################################################
# akara/server/logger.py

import os
import sys
import time
import threading

LOG_EMERG = (0, 'emerg')
LOG_ALERT = (1, 'alert')
LOG_CRIT = (2, 'crit')
LOG_ERROR = LOG_ERR = (3, 'error')
LOG_WARNING = LOG_WARN = (4, 'warn')
LOG_NOTICE = (5, 'notice')
LOG_INFO = (6, 'info')
LOG_DEBUG = (7, 'debug')

_levels = {
    'emerg': LOG_EMERG,
    'alert': LOG_ALERT,
    'crit': LOG_CRIT,
    'error': LOG_ERROR,
    'warn': LOG_WARN,
    'warning': LOG_WARN,
    'notice': LOG_NOTICE,
    'info': LOG_INFO,
    'debug': LOG_DEBUG,
    }
_file_locks_lock = threading.Lock()
_file_locks = {}

class threadsafefile:

    def __init__(self, name):
        name = os.path.abspath(name)
        _file_locks_lock.acquire()
        try:
            if not _file_locks.has_key(name):
                _file_locks[name] = threading.Lock()
        finally:
            _file_locks_lock.release()
        self.name = name
        self._lock = _file_locks[name]
        return

    def __str__(self):
        return 'threadsafefile(%s)' % self.name

    def write(self, data):
        self._lock.acquire()
        try:
            fd = open(self.name, 'a')
            fd.write(data)
            fd.close()
        finally:
            self._lock.release()
        return


class logger:
    def __init__(self, ident, logFile, maxLevel=LOG_INFO, showPid=0):
        self.buffer = []
        self.buffer_maxsize = 600 # lines
        self.bufferIsFull = False
        self.ident = ident
        if isinstance(logFile, (file, threadsafefile)):
            # An existing file-like object
            self.logFile = logFile.name
            self.stream = logFile
        else:
            # Assume it is a filename
            self.logFile = logFile
            self.stream = threadsafefile(logFile)
        self.maxLevel, self.maxPriority = self.logLevel = maxLevel
        self.showPid = showPid
        return

    def __str__(self):
        level = 'LOG_' + self.maxPriority.upper()
        return "<Logger %s, file %s, maxlevel %s>" % (self.ident,
                                                      self.logFile,
                                                      level)

    def clone(self, ident, logLevel=None, showPid=None):
        # Create a new Logger instance with the given identifier
        if logLevel is None:
            logLevel = self.logLevel
        if showPid is None:
            showPid = self.showPid
        return self.__class__(ident, self.stream, logLevel, showPid)

    def _log(self, (level, priority), message, *args):
        # deferred formating (printf-style)
        if args:
            # only apply replacement if args are non-empty to allow for
            # pre-formatted messages that contain '%'.
            message = message % args

        # Create the message header: "mmm dd HH:MM:SS ident[pid]: <message>"
        strtime = time.strftime('%b %d %H:%M:%S', time.localtime(time.time()))
        if self.showPid:
            ident = '%s[%d]' % (self.ident, os.getpid())
        else:
            ident = self.ident
        header = '%s %s: [%s]' % (strtime, ident, priority)

        if message.endswith('\n'):
            # strip single trailing newline
            message = message[:-1]

        # Map the header to each line of the message
        data = reduce(lambda data, line, header=header:
                      data + '%s %s\n' % (header, line),
                      message.split('\n'), '')

        # attempt to write buffered messages
        if self.buffer:
            try:
                self.stream.write(''.join(self.buffer))
                self.buffer = []
                self.bufferIsFull = False
            except IOError:
                pass

        # Write it out
        try:
            self.stream.write(data)
        except IOError:
            # if log temporarily unwritable, buffer the data
            if self.bufferIsFull:
                pass
            else:
                lines = data.split('\n')
                if len(self.buffer) + len(lines) > self.buffer_maxsize:
                    self.bufferIsFull = True
                    self.buffer.append('%s Additional messages exist but were not logged (buffer full)\n' % header)
                else:
                    self.buffer += lines
        return

    def log(self, (level, priority), message, *args):
        if level > self.maxLevel:
            # Ignore this message, more detail than we want to display
            return
        return self._log((level, priority), message, *args)

    def emergency(self, msg, *args):
        if self.maxLevel >= 0:
            self._log(LOG_EMERG, msg, *args)
        return

    def alert(self, msg, *args):
        if self.maxLevel >= 1:
            self._log(LOG_ALERT, msg, *args)
        return

    def critical(self, msg, *args):
        if self.maxLevel >= 2:
            self._log(LOG_CRIT, msg, *args)
        return

    def error(self, msg, *args):
        if self.maxLevel >= 3:
            self._log(LOG_ERR, msg, *args)
        return

    def warning(self, msg, *args):
        if self.maxLevel >= 4:
            self._log(LOG_WARNING, msg, *args)
        return

    def notice(self, msg, *args):
        if self.maxLevel >= 5:
            self._log(LOG_NOTICE, msg, *args)
        return

    def info(self, msg, *args):
        if self.maxLevel >= 6:
            self._log(LOG_INFO, msg, *args)
        return

    def debug(self, msg, *args):
        if self.maxLevel >= 7:
            self._log(LOG_DEBUG, msg, *args)
        return


class loggerstream:
    """
    A wrapper around a Logger instance which allows the log facility
    to be used in place of a stream object.
    """
    def __init__(self, logger, priority):
        self._logger = logger
        self._priority = priority
        self._lock = threading.Lock()
        self._buffer = []

    def flush(self):
        if self._buffer:
            self._lock.acquire()
            try:
                msg = ''.join(self._buffer)
                self._buffer = self._buffer[:0]
            finally:
                self._lock.release()
            self._logger.log(self._priority, msg)
        return

    def write(self, str):
        if '\n' in str:
            parts = str.split('\n')
            self._lock.acquire()
            try:
                parts[0] = ''.join(self._buffer) + parts[0]
                self._buffer = parts[-1:]
            finally:
                self._lock.release()
            for msg in parts[:-1]:
                self._logger.log(self._priority, msg)
        else:
            self._buffer.append(str)
        return

    def isatty(self):
        return False
