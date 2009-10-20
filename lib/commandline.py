"Deal with the command-line interface"

import sys
import os
import signal

from akara.thirdparty import argparse
from akara import read_config, run

def get_pid(args):
    settings, config = read_config.read_config(args.config_filename)

    pid_file = settings["pid_file"]
    try:
        f = open(pid_file)
    except IOError, err:
        raise SystemExit("Could not open Akara pid file: %s" % (err,))
    # XXX Perhaps a bit more verbose about error reporting?
    pid = f.readline()
    return int(pid) 

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
        print "** ERROR **:", str(error)
        raise SystemExit(1)
    print "Error log file:", repr(settings["error_log"])

    pid_file = settings["pid_file"]
    print "PID file:", repr(pid_file)
    try:
        line = open(pid_file).readline()
    except IOError, err:
        # It's fine if the PID file isn't there
        if not os.path.exists(pid_file):
            print "PID file does not exist"
        else:
            print "*** Cannot open PID file:", err
    else:
        try:
            pid = int(line)
        except ValueError, err:
            print "***  Unable to parse the PID from the PID file:", err
            raise SystemExit(1)
        try:
            os.kill(pid, 0)
        except OSError:
            print "Process", pid, "does not exist"
        else:
            print "Process", pid, "is running"
    

######################################################################



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
parser_start.set_defaults(func=start)

parser_stop = subparsers.add_parser("stop", help="stop an Akara server")
parser_stop.set_defaults(func=stop)

parser_restart = subparsers.add_parser("restart", help="restart an Akara server")
parser_restart.set_defaults(func=restart)

parser_status = subparsers.add_parser("status", help="display a status report")
parser_status.set_defaults(func=status)

def main(argv):
    args = parser.parse_args()
    args.func(args)
