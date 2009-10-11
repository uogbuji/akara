import sys
import os
import signal
from optparse import OptionParser

from akara import read_config

# The main code uses getopt because of some strange problems on MacOS X
# optparse is so much easier.

parser = OptionParser()
parser.add_option("-f", "--config-file", dest="config_filename",
                  help="Read configuration from FILE", metavar="FILE")



def main(argv):
    (options, args) = parser.parse_args()
    if args:
        parser.error("Arguments %r not accepted" % (args,))

    settings, config = read_config.read_config(options.config_filename)
    pid_file = settings["pid_file"]
    try:
        f = open(pid_file)
    except IOError, err:
        raise SystemExit("Could not open Akara pid file: %s" % (err,))
    pid = f.readline()
    pid = int(pid)

    os.kill(pid, signal.SIGTERM)

if __name__ == "__main__":
    main(sys.argv)
