"""Start up an Akara server on the command-line

This is an internal module not for use by other libraries.

"""
import os
import sys
import socket
import logging
import signal

import akara
from akara import read_config
from akara import logger, logger_config
from akara.multiprocess_http import AkaraPreforkServer, load_modules
from akara import global_config


# Need this in order to install "/" as service.list_services.  I think
# this code is somewhat clunky. There should be no reason to need the
# import here, but something has to install the top-level search
# handler, and doing it via a simple_service just makes things, well,
# simple. But the registry can't import services because services
# needs a fully-loaded registry to register things.
# Threw my hands up in the sky and broke the reference here.
# Caveat emptor.

from akara import services


def save_pid(pid_file):
    "Save the current pid to the given PID filename"
    # One line, newline terminated
    pid_s = str(os.getpid()) + "\n"

    try:
        f = open(pid_file, "w")
    except Exception, error:
        raise Exception("Unable to open PID file: %s" %
                        (error,))
    try:
        try:
            f.write(pid_s)
        except Exception, error:
            raise Exception("Unable to write to PID file %r: %s" %
                            (pid_file, error))
    finally:
        f.close()

def remove_pid(pid_file):
    "Remove the given filename (which should be the PID file)"
    try:
        os.remove(pid_file)
    except Exception, error:
        if not os.path.exists(pid_file):
            logger.error("Unable to remove PID file %r: %s",
                      pid_file, error)
    else:
        logger.info("Removed PID file %r", pid_file)


# There are two ways to run the Akara server, either in debug mode
# (running in the foreground, with the -X option) or in daemon mode
# (running in the background) which is the default. The latter is
# trickier to support.

# In that case the command-line program spawns off a new process,
# which is the master HTTP node ("the flup server"). It manages the
# subprocesses which actually handle the HTTP requests. The flup
# server starts up and either manages to set things up or fails
# because of some problem. The command-line program needs to exit with
# an error code if there was a problem, so there must be some sort of
# communications between the two.

# The solution is simple. Setup a pipe. The child sends either
# "success\n" or "failure\n" as appropriate. The parent (which is the
# command-line program) waits until it gets one of those messages.
class NotifyParent(object):
    def __init__(self):
        self.r_pipe, self.w_pipe = os.pipe()
    def failure(self):
        "Called in the child, when it must abort"
        os.write(self.w_pipe, "failure\n")
    def success(self):
        "Called in the child, when it's ready for HTTP requests"
        os.write(self.w_pipe, "success\n")
    def read_and_close(self):
        "Called in the parent, to wait for the child"
        status = os.read(self.r_pipe, 1000)
        os.close(self.r_pipe)
        os.close(self.w_pipe)
        return status

# Life is much easier in debug mode. There's no need to communicate
# anything to the non-existent parent.
class NoParent(object):
    def failure(self):
        pass
    def success(self):
        pass


def demonize():
    notify_parent = NotifyParent()

    if os.fork():
        # In the command-line parent. Wait for child status.
        status = notify_parent.read_and_close()

        if status.startswith("success"):
            raise SystemExit(0)
        else:
            raise SystemExit(1)

    # In the child, which is the flup server.
    try:
        # Create a new session with this process as the group leader
        try:
            setsid = os.setsid
        except AttributeError:
            os.setpgid(0, 0)
        else:
            setsid()
    except:
        notify_parent.failure()
        raise
    return notify_parent

# Sets up the global_config module contents
def set_global_config(settings):
    for name, value in settings.items():
        setattr(global_config,name,value)

def main(args):
    config_filename = args.config_filename
    debug = args.debug
    skip_pid_check = args.skip_pid_check

    first_time = True
    old_server_address = None
    sock = None
    while 1:
        # This is the main loop for the flup server.

        # Why is it a loop? A SIGHUP sent to the server
        # will shut down flup then reread the configuration
        # file, reload the extension modules, and start
        # the flup server again.

        try:
            settings, config = read_config.read_config(config_filename)
        except read_config.Error, err:
            logger.fatal(str(err))
            if first_time:
                raise SystemExit("Cannot start Akara. Exiting.")
            else:
                raise SystemExit("Cannot restart Akara. Exiting.")

        akara.config = config

        # Establish the global configuration module
        set_global_config(settings, config)

        # In debug mode (-X), display all log messages.
        # Otherwise, use the configuration level
        if debug:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(settings["log_level"])

        # Open this now, so any errors can be reported
        try:
            logger_config.set_logfile(settings["error_log"])
        except IOError, err:
            # Only give the 'akara setup' text here because it's where
            # we get to with an empty/nonexistant configuration file.
            logger.fatal("""\
Could not open the Akara error log:
   %s
Does that directory exist and is it writeable?
You may want to use 'akara setup' to set up the directory structure.""" % err)
            sys.exit(1)

        # Configure the access log
        try:
            logger_config.set_access_logfile(settings["access_log"])
        except IOError, err:
            logger.fatal("""\
Could not open the Akara access log:
   %s
Does that directory exist and is it writeable?""" % err)
            sys.exit(1)


        # Don't start if the PID file already exists.
        pid_file = settings["pid_file"]

        if first_time and (not skip_pid_check) and os.path.exists(pid_file):
            msg = ("Akara PID file %r already exists. Is another Akara instance running?\n"
                   "If not, remove the file or use the '-f' option to skip this check")
            logger.fatal(msg % (pid_file,))
            raise SystemExit(1)

        if debug or not first_time:
            notify_parent = NoParent()
        else:
            # Spawn off the actual listener.
            # The parent will always raise an exception, and never return.
            try:
                notify_parent = demonize()
            except Exception, err:
                # This can come from the parent or the child.
                logger.critical("Cannot spawn HTTP server", exc_info=True)
                raise SystemExit("Exiting - check the log file for details")


        # At this point we are in the child. Set things up as
        # far as we can go, then tell the parent that we're ready.
        try:
            server_address = settings["server_address"]
            if server_address != old_server_address:
                if sock is not None:
                    sock.close()
                sock = socket.socket()
                # XXX Should SO_REUSEADDR be a configuration setting?
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                # Disable Nagle's algorithm, which causes problems with
                # keep-alive. See:
                #     http://stackoverflow.com/questions/1781766/
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                host, port = settings["server_address"]
                if host:
                    description = "interface %r port %r" % (host, port)
                else:
                    description = "port %r" % (port,)
                try:
                    sock.bind(settings["server_address"])
                except socket.error, error:
                    raise SystemExit("Can not bind to " + description)
                logger.info("Listening to " + description)
                                      
                sock.listen(socket.SOMAXCONN)
                old_server_address = server_address

            # NOTE: StartServers not currently supported and likely won't be.
            # Why? Because the old algorithm would add/cull the server count
            # within a few check intervals (each about 1 second), so it
            # didn't have much long-term effect.
            logger.info("Akara server is running")
            server = AkaraPreforkServer(
                minSpare = settings["min_spare_servers"],
                maxSpare = settings["max_spare_servers"],
                maxChildren = settings["max_servers"],
                maxRequests = settings["max_requests_per_server"],
                settings = settings,
                config = config,
                )

            # Everything is ready to go, except for saving the PID file
            if first_time:
                save_pid(pid_file)
        except:
            notify_parent.failure()
            logger.critical("Could not set up the Akara HTTP server", exc_info=True)
            raise SystemExit("Akara HTTP server exiting - check the log file for details")

        else:
            notify_parent.success()

        # Fully demonize - no more logging to sys.std*
        # Close the standard file descriptors.
        # Redirect sys.std* to the log file
        if first_time and not debug:
            logger_config.remove_logging_to_stderr()
            logger_config.redirect_stdio()

        try:
            hupReceived = server.run(sock)
        except SystemExit:
            # Propogate the SystemExit through the system.  Remember,
            # this is also the root of the call tree for the child
            # which handles the request. The child exits at some point.
            raise

        # Strange. Why didn't flup disable this alarm?
        signal.alarm(0)
    
        if not hupReceived:
            logger.info("Akara server shutting down.")
            break
        logger.info("Akara server is restarting.")
        first_time = False
    remove_pid(pid_file)
