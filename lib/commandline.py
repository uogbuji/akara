"""Deal with the command-line interface

This is an internal module and should not be called from other libraries.

"""

import sys
import os
import signal
import shutil

from akara.thirdparty import argparse
from akara import read_config, run

def get_pid(args):
    try:
        settings, config = read_config.read_config(args.config_filename)
    except read_config.Error, err:
        raise SystemExit(str(err))

    pid_file = settings["pid_file"]
    try:
        f = open(pid_file)
    except IOError, err:
        raise SystemExit("Could not open Akara PID file: %s" % (err,))
    pid = f.readline()
    if not pid:
        raise SystemExit("Empty Akara PID file: %r" % (pid_file,))
    try:
        return int(pid) 
    except ValueError:
        raise SystemExit("Akara PID file %r does not contain a PID (%r)" %
                         (pid_file, pid))

def start(args):
    run.main(args)

def stop(args):
    pid = get_pid(args)
    os.kill(pid, signal.SIGTERM)

def restart(args):
    pid = get_pid(args)
    os.kill(pid, signal.SIGHUP)

def status(args):
    config_filename = read_config.DEFAULT_SERVER_CONFIG_FILE
    if args.config_filename is not None:
        config_filename = args.config_filename

    print "  == Akara status =="
    print "Configuration file:", repr(config_filename)
    try:
        settings, config = read_config.read_config(config_filename)
    except read_config.Error, err:
        print "** ERROR **:", str(err)
        raise SystemExit(1)

    print "Error log file:", repr(settings["error_log"])
    print "Access log file:", repr(settings["access_log"])

    pid_file = settings["pid_file"]
    print "PID file:", repr(pid_file)
    try:
        line = open(pid_file).readline()
    except IOError, err:
        # It's fine if the PID file isn't there
        if not os.path.exists(pid_file):
            print "PID file does not exist"
            print "Akara is not running"
        else:
            print "*** Cannot open PID file:", err
            raise SystemExit(1)
    else:
        try:
            pid = int(line)
        except ValueError, err:
            print "***  Unable to parse the PID from the PID file:", err
            raise SystemExit(1)
        try:
            os.kill(pid, 0)
        except OSError:
            print "PID is", pid, "but no process found with that PID"
            print "Akara is not running"
        else:
            print "PID is", pid, "and there is a process with that PID"
            # XXX try to connect to the server?
            print "Akara is running"


def setup_config_file():
    _setup_config_file(read_config.DEFAULT_SERVER_CONFIG_FILE)

# This function is called by test code.
# It is not part of the external API.
def _setup_config_file(default_file):
    if os.path.exists(default_file):
        print "Configuration file already exists at", repr(default_file)
    else:
        print "Copying reference configuration file to", repr(default_file)
        dirname = os.path.dirname(default_file)
        if not os.path.exists(dirname):
            print "  Creating directory", dirname
            try:
                os.makedirs(dirname)
            except OSError, err:
                raise SystemExit("Cannot make directory: %s" % err)

        # Using 'read_config.__file__' because it was handy
        akara_config = os.path.join(os.path.dirname(read_config.__file__),
                                    "akara.conf")
        try:
            shutil.copy(akara_config, default_file)
        except IOError, err:
            raise SystemExit("Cannot copy file: %s" % err)

def setup_directory_for(what, dirname):
    if os.path.isdir(dirname):
        if what[0] > "Z":
            what = what[0].upper() + what[1:]
        print "%s directory exists: %r" % (what, dirname)
    else:
        try:
            os.makedirs(dirname)
        except OSError, err:
            raise SystemExit("Cannot make %s directory: %s" % (what, err))
        print "Created %s directory: %r" % (what, dirname)

def setup(args):
    if not args.config_filename:
        setup_config_file()
    settings, config = read_config.read_config(args.config_filename)

    dirname = os.path.dirname
    setup_directory_for("error log", dirname(settings["error_log"]))
    setup_directory_for("access log", dirname(settings["access_log"]))
    setup_directory_for("PID file", dirname(settings["pid_file"]))
    setup_directory_for("extension modules", settings["module_dir"])

    print
    print "Akara environment set up. To start Akara use:"
    print "    akara start"


# This function is not multi-process safe. It's meant to be
# called by hand during the development process
def error_log_rotate(args):
    import datetime
    settings, config = read_config.read_config(args.config_filename)
    error_log = settings["error_log"]

    ext  = ""
    i = 0
    timestamp = datetime.datetime.now().isoformat().split(".")[0]
    template = error_log + "." + timestamp
    archived_error_log = template
    while os.path.exists(archived_error_log):
        i += 1
        archived_error_log = template + "_" + str(i)

    try:
        os.rename(error_log, archived_error_log)
    except OSError, err:
        if not os.path.exists(error_log):
            print "No error log found at %r" % error_log
        else:
            raise
    else:
        print "Rotated log file from %r to %r" % (error_log, archived_error_log)
    

######################################################################

# Handle the command-line arguments

parser = argparse.ArgumentParser(prog="akara", add_help=False)

parser.add_argument("-f", "--config-file", metavar="FILE", dest="config_filename",
                    help="read configuration data from FILE")


# I didn't like how argparse put the --help and --version options first.
# I didn't like how it uses -v as a variation of --version.
# So, do it myself.
parser.add_argument("-h", "--help", action="help", default=argparse.SUPPRESS,
                    help=argparse._("show this help message and exit"))

parser.version = "akaractl version 2.0"
parser.add_argument("--version", action="version", default=argparse.SUPPRESS,
                    help=argparse._("show program's version number and exit"))

#### Commands for start, stop, etc.

subparsers = parser.add_subparsers(title="The available server commands are")

parser_start = subparsers.add_parser("start", help="start Akara (use -X for debug mode)")
parser_start.add_argument("-X", dest="debug", action="store_true",
                          help="start in debug mode")
parser_start.add_argument("-f", dest="skip_pid_check", action="store_true",
                          help="do not check for an existing PID file")
parser_start.set_defaults(func=start)

parser_stop = subparsers.add_parser("stop", help="stop an Akara server")
parser_stop.set_defaults(func=stop)

parser_restart = subparsers.add_parser("restart", help="restart an Akara server")
parser_restart.set_defaults(func=restart)

parser_status = subparsers.add_parser("status", help="display a status report")
parser_status.set_defaults(func=status)

parser_setup = subparsers.add_parser("setup", help="set up directories and files for Akara")
parser_setup.set_defaults(func=setup)

# There may be an "akara log rotate" in the future, along perhaps with
# "akara log tail", "akara log filename" and other options. There's
# not yet enough call for those and the following doesn't interfere
# with the possibility (excepting non-orthagonality).

parser_setup = subparsers.add_parser("rotate",
                                     help="rotate out the current Akara error log")
parser_setup.set_defaults(func=error_log_rotate)


def main(argv):
    args = parser.parse_args(argv)
    args.func(args)
