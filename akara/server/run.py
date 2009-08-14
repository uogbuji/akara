########################################################################
# akara/server/__init__.py

from __future__ import absolute_import

import os
import sys
import time
import ConfigParser

from akara.server import process, logger

# COMMAND-LINE --------------------------------------------------------

import getopt

# This function exists to simplify command-line parsing.
# It is not part of the external API.

def _create_process(argv):
    ##OptionParser commented out in changeset 54:0cc733983ad4 because
    ## of some _locale interaction with CoreFoundation on Mac OSX 10.5.
    #from optparse import OptionParser
    #parser = OptionParser(prog=os.path.basename(argv[0]))
    #parser.add_option('-X', '--debug', action='store_true')
    #parser.add_option('-f', '--config-file')

    # Parse the command-line
    debug = False
    config_file = None
    try:
        options, args = getopt.getopt(argv[1:], 'hf:X',
                                      ('help', 
                                       'config-file='))
    except getopt.GetoptError, e:
        print >> sys.stderr, e.msg
        raise SystemExit(2)

    for opt, val in options:
        if opt in ('-h', '--help'):
            print >> sys.stderr, 'usage: '
            raise SystemExit(1)
        elif opt in ('-f', '--config-file'):
            config_file = val
        elif opt == '-X':
            debug = True

    # Process/validate mandatory arguments
    #try:
    #    arg = args[0]
    #except IndexError:
    #    parser.error("Missing required argument")

    return process(config_file, debug)


def main(argv=None):
    if argv is None:
        argv = sys.argv
    new_process = _create_process(argv)
    new_process.run()

if __name__ == "__main__":
    sys.exit(main())
