########################################################################
# akara/server/__init__.py

from __future__ import absolute_import

import os
import sys
#import mmap
import time
#import signal
#import socket
#import functools
import ConfigParser

from akara.server import process, logger, server

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
