"""Restart a currently running Akara server"""

import sys
import os
import signal
from optparse import OptionParser

from akara import stop

parser = OptionParser(
    description=("Restart a currently-running Akara server by sending it a "
                 "SIGHUP. Use the PID log file to identify the process."))
parser.add_option("-f", "--config-file", dest="config_filename",
                  help="Read configuration from FILE", metavar="FILE")

def main(argv):
    pid = stop._get_pid(argv, parser)
    os.kill(pid, signal.SIGHUP)

if __name__ == "__main__":
    main(sys.argv)
