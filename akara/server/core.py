########################################################################
# $Header: /var/local/cvsroot/4Suite/Ft/Server/Server/Controller.py,v 1.36 2006-08-12 15:56:27 jkloth Exp $
"""
Controller of all repository servers/daemons

Copyright 2003 Fourthought, Inc. (USA).
Detailed license and copyright information: http://4suite.org/COPYRIGHT
Project home, documentation, distributions: http://4suite.org/
"""

import sys, os, signal, socket, time, threading

from Ft import GetConfigVar, MAX_PYTHON_RECURSION_DEPTH
from Ft.Server.Common import Schema
from Ft.Server.Server import Daemon, Ipc, ConfigParser, GlobalConfig
from Ft.Server.Server.Drivers import PathImp, Constants
from Ft.Xml.XPath import Evaluate

# for Versa queries (currently unused)
from Ft.Rdf.Parsers import Versa
from Ft.Rdf.Parsers.Versa import DataTypes
_server_ns = {'ft' : Schema.SCHEMA_NSS + '#',
              'rdf' : 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'}
_server_versa = Versa.Compile('distribute(ft:server<-rdf:type-*, ".",'
                              ' ".-ft:server.running->*",'
                              ' ".-ft:modified_date->*")')

# Interval, in seconds, between scoreboard maintenance.  During
# each scoreboard maintenance cycle the parent decides if it needs to
# spawn a new child (to meet MinSpareServers requirements), or kill off
# a child (to meet MaxSpareServers requirements).  It will only spawn or
# kill one child per cycle.  Setting this too low will chew cpu.  The
# default is probably sufficient for everyone.  But some people may want
# to raise this on servers which aren't dedicated to httpd and where they
# don't like the httpd waking up each second to see what's going on.
MAINTENANCE_INTERVAL = 1

# This value should prevent resource hogging
MAX_SPAWN_RATE = 32

# -- data structures ---------------------------------------------------

class Server:
    def __init__(self, path, lastModified, listeners):
        self.path = path
        self.lastModified = lastModified
        self.listeners = listeners
        return

class Listener:
    def __init__(self, socket, serverConfig):
        self.socket = socket
        self.server = serverConfig

        # Needed for select()
        self.fileno = socket.fileno
        return

class Worker:
    def __init__(self, config, interval, function, name=None):
        self.config = config
        self.interval = interval
        self.function = function
        self.name = name or function.__name__

        self.ticks = 0

        #Run once is handled elsewhere now
        return

    def tick(self):
        if self.ticks == self.interval:
            self.ticks = 0
            self.run()
        else:
            self.ticks += 1
        return

    def run(self):
        self.config.errorLog.info("running worker '%s'" % self.name)
        repo = None
        try:
            repo = self.config.getRepository()
            self.function(repo)
        except:
            if repo:
                repo.txRollback()
            import traceback
            traceback.print_exc()
        else:
            repo.txCommit()
        return

class DBMaintenanceWorker(Worker):
    def __init__(self, config,when):
        self.config = config
        if time.time() > when:
            # Missed the time for today, wait for tommorrow
            when += 86400
        self._when = when
        return

    def tick(self):
        if time.time() > self._when:
            self.run()
            self._when += 60*60*24

    def run(self):
        self.config.errorLog.info("running worker 'DB Maintenance'")
        repo = None
        try:
            repo = self.config.getRepository()
            driverMod = repo._driver._driverMod
            driverProperties = repo._driver._driverProperties
            repo.txRollback()
            repo = None
            driverMod.Maintain(driverProperties)
        except:
            if repo:
                repo.txRollback()
            import traceback
            traceback.print_exc()
        self.config.errorLog.info("'DB Maintenance' worker done")


# -- the controller -----------------------------------------------------

class ControllerBase:

    def __init__(self, config):
        self.config = config

        self.restart_pending = 1
        self.shutdown_pending = 0

        # The active sever configurations
        self.servers = []
        # Wrapped sockets used in the servers
        self.listeners = []

        self.daemons = []
        self._idle_spawn_rate = 1

        # Defined here so all daemons will share the same one
        self.accepting_mutex = threading.Lock()
        return

    # -- main execution ----------------------------------------------

    #@classmethod
    def main(cls):
        # Some functions have *heavy* recursion
        if sys.getrecursionlimit() < MAX_PYTHON_RECURSION_DEPTH:
            sys.setrecursionlimit(MAX_PYTHON_RECURSION_DEPTH)

        # FTSS_ENVIRONMENT is set in the environment by the Launcher class.
        if not os.environ.has_key('FTSS_ENVIRONMENT'):
            # We're running directly from the commandline
            import getpass, sha
            print '*** Running in debug mode ***'
            username = raw_input("4SS Manager Name: ")
            password = getpass.getpass("Password for %s: " % username)
            password = sha.new(password).hexdigest()
            core = os.environ.get('FTSS_CORE_ID', 'Core')
            debug = 1
        else:
            username, password, core = eval(os.environ['FTSS_ENVIRONMENT'])
            del os.environ['FTSS_ENVIRONMENT']
            debug = 0
        # The default location of the config file.
        conffile = os.path.join(GetConfigVar('SYSCONFDIR'), '4ss.conf')
        # User overridden location of the config file.
        conffile = os.environ.get('FTSERVER_CONFIG_FILE', conffile)
        config = GlobalConfig.GlobalConfig(username, password, core,
                                           conffile, debug)
        controller = cls(config)
        return controller.run()
    main = classmethod(main)

    def run(self):
        # Setup hooks for controlling within the OS
        self.setSignals()

        # Read the configuration
        self.config.readConfig()

        # Open log files
        self.config.openLogs()

        # Let the controlling process know we're going to live
        self.config.savePid()

        if self.config.debug:
            # Let Control-C do a clean shutdown
            signal.signal(signal.SIGINT, self.shutdown)
        else:
            Ipc.DetachProcess()

        while self.restart_pending:

            self.errorLog = self.config.errorLog

            # Get the active worker list (always runs them once)
            workers = self.getWorkers()

            for slot in range(self.config.daemons_to_start):
                daemon = Daemon.Daemon(self.accepting_mutex, self.listeners,
                                       self.errorLog)
                daemon.start()
                self.daemons.append(daemon)

            self.errorLog.notice("%s configured -- resuming normal "
                                 "operations" % self.config.ident)

            self.restart_pending = self.shutdown_pending = 0

            while not self.restart_pending and not self.shutdown_pending:
                self.waitOrTimeout(MAINTENANCE_INTERVAL)
                self.idleMaintenance()

                # Update the workers internal counters; this might cause
                # them to execute as well
                for worker in workers:
                    worker.tick()

            if self.shutdown_pending:
                self.errorLog.notice('shutting down')

            self.reclaimChildren()

            # debug mode doesn't have the concept of restarting
            if self.shutdown_pending or self.config.debug:
                # Cleanup pid file on normal shutdown
                self.config.removePid()
                break

            # We've been told to restart so we need to cleanup our lists.
            # Note: empty the list, not replace it, because the list is
            #       shared across threads.
            self.daemons[:] = []
            self.listeners[:] = []
            self.servers[:] = []

            self.errorLog.notice('Graceful restart...')

            # Redo configuration process
            self.config.readConfig()
            self.config.openLogs()
            continue

        self.errorLog.notice('process %d exiting' % os.getpid())
        return 0

    # -- signal handling ---------------------------------------------

    def waitOrTimeout(self, timeout):
        raise NotImplementedError

    def shutdown(self, *ignored):
        # the varargs is to allow this as a signal handler
        self.shutdown_pending = 1
        return

    def restart(self, *ignored):
        # the varargs is to allow this as a signal handler
        self.restart_pending = 1
        return

    # -- connection structures and accouting -------------------------

    def addServer(self, config):
        listeners = []
        self.errorLog.debug('Adding server definition %s' % config.path)
        for address in self.config.addresses:
            try:
                socket = self.makeSocket(address, config.port)
            except Exception, error:
                self.errorLog.critical(str(error))
            else:
                config.openLogs(self.config)
                listener = Listener(socket, config)
                listeners.append(listener)

        if listeners:
            server = Server(config.path, config.modifiedDate, listeners)
            self.servers.append(server)
            self.listeners.extend(listeners)
        else:
            self.errorLog.error('No listeners for server %s' % config.path)
        return

    def removeServer(self, server):
        self.servers.remove(server)
        for listener in server.listeners:
            self.listeners.remove(listener)
        return

    def makeSocket(self, host, port):
        """
        Creates the socket for this address.
        """
        # Create a human readable version of the address for errors
        # and a tuple for use with bind()

        if host == '*':
            # INADDR_ANY, bind to all interfaces
            host = ''
            address = 'port %d' % port
        else:
            address = 'address %s port %d' % (host, port)

        self.errorLog.debug('creating socket for %s' % address)
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
            self.errorLog.warning(msg)

        try:
            sock.bind((host, port))
        except:
            raise Exception('could not bind to %s' % address)

        try:
            sock.listen(socket.SOMAXCONN)
        except:
            raise Exception('unable to listen for connections on %s' % address)

        return sock

    # -- daemon control ----------------------------------------------

    def reclaimChildren(self):
        for daemon in self.daemons:
            # Prevent processing any more requests
            daemon.active = 0

        self.errorLog.info('waiting for daemons to exit...')

        waittime = 0.016
        for tries in xrange(9):
            # don't want to hold up progess any more than
            # necessary, but we need to allow children a few moments
            # to exit. Set delay with an exponential backoff.
            time.sleep(waittime)
            waittime *= 4

            not_dead_yet = 0
            for daemon in self.daemons:
                if daemon.isAlive():
                    not_dead_yet += 1
                    if tries == 2: # after 1.4s
                        # perhaps it missed the first attempt
                        daemon.active = 0
                        waittime = 0.016
                    elif tries == 6: # after 2.7s
                        # ok, now it's being annoying
                        self.errorLog.warning("%s did not exit, sending "
                                              "interrupt" % daemon)
                        # There is no way to kill a thread in Python
                    elif tries == 7: # after 6.8s
                        # die child scum
                        self.errorLog.error("%s still did not exit, sending "
                                            "termination" % daemon)
                        # There is no way to kill a thread in Python
                        waittime /= 4
                    elif tries == 8: # after 10.9s
                        # gave it our best shot, but alas...
                        self.errorLog.error("could not make %s exit, attempting"
                                            " to continue anyway" % daemon)

            if not not_dead_yet:
                # nothing left to wait for
                break
        return

    def idleMaintenance(self):
        inactive = []
        idle_count = 0

        for daemon in self.daemons:
            if not daemon.active:
                inactive.append(daemon)
            elif daemon.ready:
                idle_count += 1

        # Remove any dead threads:
        if inactive:
            self.errorLog.notice('Purging %d unused daemons' % len(inactive))
            for daemon in inactive:
                self.daemons.remove(daemon)

        if idle_count > self.config.daemons_max_free:
            # kill off one child...let it die gracefully
            # always kill the highest numbered child if we have to...
            # no really well thought out reason ... other than observing
            # the server behaviour under linux where lower numbered children
            # tend to service more hits (and hence are more likely to have
            # their data in cpu caches).
            if self.daemons:
                # We might not have any current children
                self.daemons[-1].active = 0
            self._idle_spawn_rate = 1

        elif idle_count < self.config.daemons_min_free:
            if len(self.daemons) > self.config.max_daemons:
                logger.error('reached MaxClients setting')
                self._idle_spawn_rate = 1
            else:
                if self._idle_spawn_rate >= 8:
                    self.errorLog.info(
                        'server seems busy, (you may need to increase '
                        'Min/MaxSpareServers), creating %d children, there '
                        '%s %d idle, and %d total child%s' % (
                        self._idle_spawn_rate,
                        ('are','is')[idle_count == 1], idle_count,
                        len(self.daemons),
                        ('ren','')[len(self.daemons) == 1],
                        ))

                self.errorLog.notice('spawning %d new child%s' % (
                                     self._idle_spawn_rate,
                                     ('ren','')[self._idle_spawn_rate == 1]))
                for slot in range(self._idle_spawn_rate):
                    daemon = Daemon.Daemon(self.accepting_mutex, self.listeners,
                                           self.errorLog)
                    daemon.start()
                    self.daemons.append(daemon)

                # the next time around we want to spawn twice as many if this
                # wasn't good enough
                if self._idle_spawn_rate < MAX_SPAWN_RATE:
                    self._idle_spawn_rate *= 2
        else:
            self._idle_spawn_rate = 1
        return

    # -- worker threads ----------------------------------------------

    def getWorkers(self):
        workers = []

        # Dynamic configuration update
        interval = self.config.properties['DynamicReloadInterval']
        worker = Worker(self.config, interval, self._check_config)
        worker.run()
        if interval > 0:
            workers.append(worker)


        # Temporary file purge thread
        interval = self.config.properties['TemporaryReapInterval']
        worker = Worker(self.config, interval, self._purge_temp)
        worker.run()
        if interval > 0:
            workers.append(worker)

        # XSLT Cron
        interval = self.config.properties['XsltStrobeInterval']
        worker = Worker(self.config, interval, self._xslt_strobe)
        worker.run()
        if interval > 0:
            workers.append(worker)

        # DB Maint.
        interval = self.config.properties['DBMaintenanceTime']
        if interval > 0:
            worker = DBMaintenanceWorker(self.config, interval)
            workers.append(worker)

        return workers

    def _check_config(self, repo):
        # Determine all available servers (via schema) and the
        # "running" and "last-modified-date" for them

        # Versa is waaaaaaaayyyyyyyyyy to slow when there are lots of
        # statements in the model.  Hopefully can be used again soon.
        #context = Versa.CreateContext(model=repo.getModel(),
        #                              nsMapping=_server_ns)
        #result = _server_versa.evaluate(context)
        #status = {}
        #for name, running, modified in result:
        #    running = len(running) and int(min(DataTypes.ToList(running)))
        #    modified = max(DataTypes.ToList(modified))
        #    status[str(name)] = (running, modified)
        model = repo.getModel()
        statements = model.complete(None,
                                    'http://www.w3.org/1999/02/22-rdf-syntax-ns#type',
                                    Schema.SCHEMA_NSS + '#server')
        status = {}
        for statement in statements:
            serverPath = PathImp.QuickCreate(statement.subject)
            con = repo._driver.getContext(serverPath)
            running = Evaluate(Constants.SERVER_STATUS_XPATH,context=con)
            con = repo._driver.getContext(serverPath.normalize('.;metadata;no-traverse'))
            modified = Evaluate(Constants.LAST_MODIFIED_DATE_XPATH,context=con)
            status[statement.subject] = (running, modified)

        unused = []
        # Process currently running servers
        for server in self.servers:
            if not status.has_key(server.path):
                # The configuration file has been removed
                unused.append(server)
                continue

            running, modified_date = status[server.path]
            if not running:
                # The server should be stopped
                unused.append(server)
                del status[server.path]
            elif modified_date > server.lastModified:
                # The configuration file has changed
                # Remove the current server and recreate it with
                # the new configuration
                unused.append(server)
            else:
                # By removing it from status, no changes will be made
                del status[server.path]

        for server in unused:
            self.removeServer(server)

        # Servers remaining in status are considered to be new
        if status:
            items = status.items()
            items = [ (path, date) for path, (start, date) in items if start ]

            parser = ConfigParser.ConfigParser(self.errorLog)
            try:
                repo = self.config.getRepository()
            except:
                # This is an extremely critical error, just die
                self.errorLog.emergency('Unable to connect to repository')
                self.shutdown()
                return

            try:
                for path, date in items:
                    try:
                        resource = repo.fetchResource(path)
                        config = parser.readConfig(path, resource.getContent())
                        config.finalize(date, self.config)
                    except Exception, error:
                        self.errorLog.error('Unable to read configuration '
                                            'resource %s: %s' % (path, error))
                        continue
                    self.addServer(config)
            finally:
                repo.txCommit()
        return

    def _purge_temp(self, repo):
        repo.purgeTemporaryResources()
        return

    def _xslt_strobe(self, repo):
        repo.runXsltStrobe()
        return


class PosixController(ControllerBase):

    def setSignals(self):
        signal.signal(signal.SIGTERM, self.shutdown)
        signal.signal(signal.SIGHUP, self.restart)
        return

    def waitOrTimeout(self, timeout):
        time.sleep(timeout)
        return


class WindowsController(ControllerBase):

    def setSignals(self):
        # Windows doesn't really use signals, therefore we'll use events
        # that mimic how signals are used
        shutdown = Ipc.Event('ap%dshutdown' % os.getpid())
        shutdown.handle = self.shutdown
        restart = Ipc.Event('ap%drestart' % os.getpid())
        restart.handle = self.restart
        self._signals = (shutdown, restart)
        return

    def waitOrTimeout(self, timeout):
        set = Ipc.WaitEvents(self._signals, timeout)
        for event in set:
            event.clear()
            event.handle()
        return


if sys.platform == 'win32':
    Controller = WindowsController

elif os.name == 'posix':
    Controller = PosixController

else:
    raise ImportError("I don't know how to control servers on this platform!")


if __name__ == '__main__':
    sys.exit(Controller.main())

