"""Start up an Akara server on the command-line"""
from __future__ import absolute_import


import os
import sys

import socket

from akara import read_config
import logging

from akara import logger, logger_config
from akara.module_loader import load_modules
from akara.multiprocess_http import AkaraPreforkServer


def save_pid(pid_file):
    # Newline terminated
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
    try:
        os.remove(pid_file)
    except Exception, error:
        if not os.path.exists(pid_file):
            logger.error("Unable to remove PID file %r: %s",
                      pid_file, error)
    else:
        logger.info("Removed PID file %r", pid_file)


# Used to coordinate between the parent and child processes.
# The child needs to tell the parent if it could start up or not.
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

# Used in the "parent" when there is no child
# and 
class NoParent(object):
    def failure(self):
        pass
    def success(self):
        pass


def demonize():
    notify_parent = NotifyParent()

    if os.fork():
        # In the parent. Wait for child status.
        status = notify_parent.read_and_close()

        if status.startswith("success"):
            raise SystemExit(0)
        else:
            raise SystemExit(1)

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


def main(args):
    config_filename = args.config_filename
    debug = args.debug

    first_time = True
    old_server_address = None
    sock = None
    while 1:
        # XXX comment here
        settings, config = read_config.read_config(config_filename)

        # For now, keep with the old Akara mechanism.
        if debug:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(settings["log_level"])

        # Open this now, so any errors can be reported
        logger_config.set_logfile(settings["error_log"])

        # Compile the modules before spawning the server process
        # If there are any problems, die
        modules = load_modules(settings["module_dir"],
                               settings["server_root"], config)

        # Hopefully helpful check.
        # XXX Should this die if it sees an existing pid?
        pid_file = settings["pid_file"]
        if first_time and os.path.exists(pid_file):
            logger.warning(
                "Existing PID file %r will be overwritten. (Is another instance running?)"
                % (pid_file,))


        if debug or not first_time:
            notify_parent = NoParent()
        else:
            # Spawn off the actual listener.
            # The parent will always raise an exception, and never return.
            try:
                notify_parent = demonize()
            except Exception, err:
                # XXX more comments
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
                # XXX SO_REUSEADDR should be a setting
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    sock.bind(settings["server_address"])
                except socket.error, error:
                    host, port = settings["server_address"]
                    if not host:
                        raise SystemExit("Can not bind to port %r: %s" % (port, error))
                    else:
                        raise SystemExit("Can not bind to interface %r port %r : %s" %
                                         (host, port, error))
                                      
                sock.listen(socket.SOMAXCONN)
                old_server_address = server_address

            # NOTE: StartServers not currently supported and likely won't be.
            # Why? Because the old algorithm would add/cull the server count
            # within a few check intervals (each about 1 second), so it
            # didn't have much long-term effect.
            server = AkaraPreforkServer(
                minSpare = settings["min_spare_servers"],
                maxSpare = settings["max_spare_servers"],
                maxChildren = settings["max_servers"],
                maxRequests = settings["max_requests_per_server"],
                settings = settings,
                config = config,
                modules = modules,
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
        # XXX Reroute sys.std* to the log file?
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
        # XXX Check for other exceptions?

        # XXX Strange. Why didn't flup disable this alarm?
        import signal
        signal.alarm(0)
    
        if not hupReceived:
            logger.info("Shutting down")
            break
        logger.info("Restarting")
        first_time = False
    remove_pid(pid_file)

# This is debugging code I used when with a bug during
# demonization with redirecting stdout/stderr to the logger.
# When enabled, wrap 'main' and dump any exceptions to
# a log file. Defaults to the current terminal.
# NOTE: in normal operation there will be MULTIPLE exits.
#  - one for the command-line program, which forks to
#  - the master process manager, which forks to
#  - each spawned HTTP listener/worker process
if 0:
    def _get_exception_filename():
        # return "/dev/ttyp2"  # Replace this if you want a particular file
        return os.popen("tty").readline().rstrip()

    # Get a useful filename
    _exception_filename = _get_exception_filename()

    # Use a new name for the existing 'main'
    _main = main

    def main(argv):
        try:
            _main(argv)
        except:
            import traceback
            f = open(_exception_filename, "a")
            f.write("Exception trace from %s\n" % (os.getpid(),))
            traceback.print_exc(file=f)
            f.close()
            raise
