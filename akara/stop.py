"""Stop a currently running Akara server"""

import sys
import os
import signal
from optparse import OptionParser

from akara import read_config

def _get_pid(argv, option_parser):
    options, args = option_parser.parse_args(args=argv[1:])
    if args:
        option_parser.error("The arguments %r are not allowed" % (args,))

    settings, config = read_config.read_config(options.config_filename)

    pid_file = settings["pid_file"]
    try:
        f = open(pid_file)
    except IOError, err:
        raise SystemExit("Could not open Akara pid file: %s" % (err,))
    # XXX Perhaps a bit more verbose about error reporting?
    pid = f.readline()
    return int(pid) 


parser = OptionParser(
    description=("Stop a currently-running Akara server by sending it a "
                 "SIGTERM. Use the PID log file to identify the process."))
parser.add_option("-f", "--config-file", dest="config_filename",
                  help="Read configuration from FILE", metavar="FILE")

def main(argv):
    pid = _get_pid(argv, parser)
    os.kill(pid, signal.SIGTERM)

if __name__ == "__main__":
    main(sys.argv)
