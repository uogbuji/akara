########################################################################
# akara/server/__init__.py

from __future__ import absolute_import

import os
import sys
import mmap
import time
import signal
import socket
import functools
import ConfigParser

# HACK!
from threading import Lock as proc_mutex

from akara.server import logger, server
from akara.server.application import wsgi_application

SERVER_CONFIG_FILE = os.path.expanduser('~/.config/akara.conf')

SERVER_CONFIG_DEFAULTS = {
    'global': {
        'ServerRoot': '~/.local/lib/akara',
        'PidFile': 'logs/akara.pid',
        'StartServers': '5',
        'MinSpareServers': '5',
        'MaxSpareServers': '10',
        'MaxServers': '150',
        'MaxRequestsPerServer': '10000',
        'ModuleDir': 'modules',
        'ErrorLog': 'logs/error.log',
        'LogLevel': 'notice',
        'AccessLog': '',
        },
    'akara.cache': {
        'DefaultExpire': '3600',
        'LastModifiedFactor': '0.1',
        },
    }

_log_levels = {
    'emerg': logger.LOG_EMERG,
    'alert': logger.LOG_ALERT,
    'crit': logger.LOG_CRIT,
    'error': logger.LOG_ERROR,
    'warn': logger.LOG_WARNING,
    'notice': logger.LOG_NOTICE,
    'info': logger.LOG_INFO,
    'debug': logger.LOG_DEBUG,
    }

# Interval, in seconds, between scoreboard maintenance.  During
# each scoreboard maintenance cycle the parent decides if it needs to
# spawn a new child (to meet MinSpareServers requirements), or kill off
# a child (to meet MaxSpareServers requirements).  It will only spawn or
# kill one child per cycle.  Setting this too low will chew cpu.  The
# default is probably sufficient for everyone.  But some people may want
# to raise this on servers which aren't dedicated to httpd and where they
# don't like the httpd waking up each second to see what's going on.
MAINTENANCE_INTERVAL = 1.0

# This value should prevent resource hogging
MAX_SPAWN_RATE = 32


class dummy_mutex(object):
    def __enter__(self, *args):
        return
    def __exit__(self, *args):
        return


class process(object):

    ident = 'akara'
    config_file = SERVER_CONFIG_FILE
    log_level = logger.LOG_WARN

    current_pid = 0

    def __init__(self, config_file=None, log_level=None, debug=None):
        if config_file is not None:
            self.config_file = config_file
        if log_level is not None:
            log_level = logger.LOG_WARN
        self.debug = not not debug
        # Force debug level logging for "one process" debug mode
        if debug:
            log_level = logger.LOG_DEBUG
        # setup stderr logging for startup logging
        self.log = logger.logger(self.ident, sys.stderr, log_level, False)

    def set_signals(self):
        def shutdown_callback(signum, frame, server=self):
            server.shutdown_pending = True
        def restart_callback(signum, frame, server=self):
            server.restart_pending = True

        signal.signal(signal.SIGTERM, shutdown_callback)
        if self.debug:
            signal.signal(signal.SIGHUP, shutdown_callback)
            signal.signal(signal.SIGINT, shutdown_callback)
        else:
            signal.signal(signal.SIGHUP, restart_callback)
        return

    def read_config(self):
        config = ConfigParser.ConfigParser()
        for section, defaults in SERVER_CONFIG_DEFAULTS.iteritems():
            config.add_section(section)
            for name, value in defaults.iteritems():
                config.set(section, name, value)
        if not os.path.exists(self.config_file):
            self.log.info('configuration file %r not found, using defaults',
                           self.config_file)
        else:
            config.read(self.config_file)

        try:
            addr = config.get('global', 'Listen')
        except ConfigParser.NoOptionError:
            self.log.alert("no listening sockets available, shutting down")
            raise SystemExit(1)

        if ':' in addr:
            host, port = addr.rsplit(':', 1)
        else:
            host, port = '', addr
        self.server_addr = host, int(port)
        self.server_name = socket.getfqdn(host)
        self.server_port = int(port)

        self.server_root = config.get('global', 'ServerRoot')
        self.server_root = os.path.expanduser(self.server_root)
        self.server_root = os.path.abspath(self.server_root)

        self.pid_file = config.get('global', 'PidFile')
        self.pid_file = os.path.join(self.server_root, self.pid_file)

        self.error_log = config.get('global', 'ErrorLog')
        self.error_log = os.path.join(self.server_root, self.error_log)
        self.log_level = config.get('global', 'LogLevel')
        try:
            logf = open(self.error_log, 'a+')
        except OSError, e:
            self.log.alert("could not open error log file '%s': %s\n",
                           self.error_log, str(e))
            raise SystemExit(1)
        try:
            self.log_level = _log_levels[self.log_level.lower()]
        except:
            self.log.crit('LogLevel requires level keyword; one of %s',
                          ' | '.join(_log_levels))
        if self.debug:
            self.log = logger.logger(self.ident, sys.stderr, logger.LOG_DEBUG,
                                     True, False)
        else:
            self.log = logger.logger(self.ident, logf, self.log_level,
                                     True, True)
            sys.stderr = logger.loggerstream(self.log, logger.LOG_ERROR)
            sys.stdout = logger.loggerstream(self.log, logger.LOG_DEBUG)

        self.server_type = server.wsgi_server_process
        self.start_servers = config.getint('global', 'StartServers')
        self.max_servers = config.getint('global', 'MaxServers')
        self.min_free_servers = config.getint('global', 'MinSpareServers')
        self.max_free_servers = config.getint('global', 'MaxSpareServers')
        self.max_requests = config.getint('global', 'MaxRequestsPerServer')

        self.application = wsgi_application(self, config)
        return

    def detach_process(self):
        if os.fork():
            raise SystemExit(0)
        # create a new session with this process as the group leader
        try:
            setsid = os.setsid
        except AttributeError:
            os.setpgid(0, 0)
        else:
            setsid()
        # close the standard file descriptors
        for stream in (sys.stdin, sys.stdout, sys.stderr):
            if stream.isatty():
                stream.close()
        return

    def save_pid(self):
        pid = os.getpid()
        if os.path.exists(self.pid_file) and self.current_pid != pid:
            self.log.warning('PID file %s overwritten -- unclean '
                             'shutdown of previous run?', self.pid_file)
        try:
            fd = open(self.pid_file, 'w')
        except Exception, error:
            self.log.critical("Unable to open pid file '%s': %s\n",
                              self.pid_file, str(error))
            sys.exit(1)

        try:
            fd.write(str(pid))
        except Exception, error:
            self.log.critical("Unable to write to pid file '%s': %s\n",
                              self.pid_file, str(error))
            try:
                fd.close()
            except:
                self.log.error("Error closing file descriptor\n")
            sys.exit(1)

        try:
            fd.close()
        except:
            self.log.error("Error closing file descriptor\n")
            sys.exit(1)

        self.current_pid = pid
        return

    def remove_pid(self):
        if os.path.exists(self.pid_file):
            try:
                os.remove(self.pid_file)
            except Exception, error:
                self.log.debug("Unable to remove file '%s': %s\n",
                               self.pid_file, str(error))
            else:
                self.log.info('removed PID file %s\n', self.pid_file)
        return

    wait_or_timeout = functools.partial(time.sleep, MAINTENANCE_INTERVAL)

    def idle_maintenance(self):
        inactive, idle = [], []
        for slot, server in enumerate(self.servers):
            if server:
                if not server.active:
                    inactive.append(slot)
                elif server.ready:
                    idle.append(server)

        # Remove any dead servers
        if inactive:
            self.log.notice('purging %d unused servers', len(inactive))
            for slot in inactive:
                self.servers[slot] = None

        idle_count = len(idle)
        if idle_count > self.max_free_servers:
            # kill off one child...let it die gracefully
            # always kill the highest numbered child if we have to...
            # no really well thought out reason ... other than observing
            # the server behaviour under linux where lower numbered children
            # tend to service more hits (and hence are more likely to have
            # their data in cpu caches).
            idle[-1].stop()
            self._idle_spawn_rate = 1

        elif idle_count < self.min_free_servers:
            free_slots = [ slot for slot, server in enumerate(self.servers)
                           if not server ]
            if not free_slots:
                self.log.error('reached MaxServers setting')
                self._idle_spawn_rate = 1
            else:
                if self._idle_spawn_rate >= 8:
                    self.log.info(
                        'server seems busy, (you may need to increase '
                        'StartServers or Min/MaxSpareServers)')
                total_count = self.max_servers - len(free_slots)
                self.log.notice('there are %d idle and %d total servers',
                                idle_count, total_count)
                self.spawn_servers(free_slots[:self._idle_spawn_rate])
                # the next time around we want to spawn twice as many if this
                # wasn't good enough
                if self._idle_spawn_rate < MAX_SPAWN_RATE:
                    self._idle_spawn_rate *= 2
        else:
            self._idle_spawn_rate = 1
        return

    def make_socket(self, host, port):
        """
        Creates the socket for this address.
        """
        # Create a human readable version of the address for errors
        # and a tuple for use with bind()

        if host in ('', '*', '0.0.0.0'):
            # INADDR_ANY, bind to all interfaces
            host = ''
            address = 'port %d' % port
        else:
            address = 'address %s port %d' % (host, port)

        self.log.debug('creating socket for %s' % address)
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        except:
            raise Exception('failed to get a socket for %s' % address)

        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except:
            raise Exception('for %s, setsockopt: SO_REUSEADDR' % address)

        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except:
            raise Exception('for %s, setsockopt: SO_KEEPALIVE' % address)

        # The Nagle algorithm says that we should delay sending partial
        # packets in hopes of getting more data.  We don't want to do
        # this; we are not telnet.  There are bad interactions between
        # persistent connections and Nagle's algorithm that have very
        # severe performance penalties.  (Failing to disable Nagle is not
        # much of a problem with simple HTTP.)
        #
        # In spite of these problems, failure here is not a big offense.
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except:
            msg = 'for %s, setsockopt: TCP_NODELAY' % address
            self.log.warning(msg)

        try:
            sock.bind((host, port))
        except:
            raise Exception('could not bind to %s' % address)

        try:
            sock.listen(socket.SOMAXCONN)
        except:
            raise Exception('unable to listen for connections on %s' % address)

        return sock

    def spawn_servers(self, slots):
        self.log.notice('creating %d new servers', len(slots))
        for slot in slots:
            server = self.server_type(slot, self)
            server.start()
            self.servers[slot] = server
        return

    def reclaim_servers(self, _time=time.time, _sleep=time.sleep):
        self.log.info('waiting for servers to exit...')
        # Begin with the set of servers that are alive
        servers = [ server for server in self.servers if server ]
        # Continue trying each each `action` for the given `duration`.
        waittime = 1.0 / 64
        for action, duration in (('stop', 3.0), ('term', 6.0),
                                 # A `duration` <1 ensures one iteration
                                 ('kill', 0.5), ('cont', 0.5)):
            endtime = _time() + duration
            while servers and _time() < endtime:
                _sleep(waittime)
                # Don't let `waittime` exceed 1 second, to ensure reasonable
                # response time.
                if waittime < 1.0: waittime *= 4
                # Process the servers which are still serving requests
                servers = [ server for server in servers if server.active ]
                for server in servers:
                    if action == 'stop':
                        server.stop()
                    elif action == 'term':
                        self.log.warning(
                            "server '%s' still did not exit, terminating",
                            server.name)
                        server.terminate()
                    elif action == 'kill':
                        self.log.error(
                            "server '%s' still did not exit, killing",
                            server.name)
                        server.kill()
                    elif action == 'cont':
                        self.log.error(
                            "could not make server '%s' exit, "
                            "attempting to continue anyway", server.name)
            # Everyone has finished!
            if not servers:
                break
        del self.listeners, self.servers
        return

    def run(self):
        # Setup hooks for controlling within the OS
        self.set_signals()

        # Read the configuration
        self.read_config()

        if not self.debug:
            self.detach_process()

        # Let the controlling process know we're going to live
        self.save_pid()

        # Force once through the loop
        self.restart_pending = self.shutdown_pending = True

        while self.restart_pending:
            self.listeners = [self.make_socket(*self.server_addr)]

            # Initialize cross-process accept lock */
            if len(self.listeners) > 1:
                mutex_class = proc_mutex
            else:
                mutex_class = dummy_mutex
            try:
                self.accepting_mutex = mutex_class()
            except:
                self.log.emerg('Could not create accept lock')
                return 1

            self.scoreboard = mmap.mmap(-1, self.max_servers)
            self.servers = [None]*self.max_servers
            self.spawn_servers(range(self.start_servers))

            self.log.notice("started akara server (pid=%d) for %s:%d",
                            self.current_pid, self.server_name,
                            self.server_port)

            self.restart_pending = self.shutdown_pending = False
            self._idle_spawn_rate = 1
            while not self.restart_pending and not self.shutdown_pending:
                self.wait_or_timeout()
                self.idle_maintenance()

            if self.shutdown_pending:
                self.log.notice("shutting down")

            self.reclaim_servers()

            # debug mode doesn't have the concept of restarting
            if self.shutdown_pending or self.debug:
                # Cleanup pid file on normal shutdown
                self.remove_pid()
                break

            self.log.notice("graceful restart...")

            self.read_config()
            continue

        self.log.notice('process %d exiting' % self.current_pid)
        return 0

# COMMAND-LINE --------------------------------------------------------

import getopt

def main(argv=None):
    if argv is None:
        argv = sys.argv
    #from optparse import OptionParser
    #parser = OptionParser(prog=os.path.basename(argv[0]))
    #parser.add_option('-X', '--debug', action='store_true')
    #parser.add_option('-v', '--verbose', action='count', default=0)
    #parser.add_option('-f', '--config-file')

    # Parse the command-line
    debug = False
    verbosity = 0
    config_file = None
    try:
        options, args = getopt.getopt(argv[1:], 'hqvf:X',
                                      ('help', 'quiet', 'verbose',
                                       'config-file='))
    except getopt.GetoptError, e:
        print >> sys.stderr, e.msg
        return 2

    for opt, val in options:
        if opt in ('-h', '--help'):
            print >> sys.stderr, 'usage: '
            return 1
        elif opt in ('-q', '--quiet'):
            verbosity -= 1
        elif opt in ('-v', '--verbose'):
            verbosity += 1
        elif opt in ('-f', '--config-file'):
            config_file = val
        elif opt == '-X':
            debug = True

    # Process/validate mandatory arguments
    #try:
    #    arg = args[0]
    #except IndexError:
    #    parser.error("Missing required argument")

    # Setup initial logging levels
    if verbosity > 2:
        log_level = logger.LOG_DEBUG
    elif verbosity > 1:
        log_level = logger.LOG_INFO
    elif verbosity > 0:
        log_level = logger.LOG_NOTICE
    else:
        log_level = logger.LOG_WARN

    return process(config_file, log_level, debug).run()

if __name__ == "__main__":
    sys.exit(main())
