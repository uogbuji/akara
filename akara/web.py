#Useful: http://docs.python.org/library/wsgiref.html
#

import os, sqlite3
from wsgiref.util import shift_path_info, request_uri
from string import Template
from cStringIO import StringIO

from akara.server import serve_forever
from akara.resource import *
from akara.resource.repository import driver
from akara.resource import web as resourceweb
#from akara.services import web as servicesweb

#LOCAL_DIR = os.path.join(os.getcwd(), os.path.dirname(__file__))
print os.path.dirname(__file__)
LOCAL_DIR = os.getcwd()

# Templates
wrapper = Template("""
<html><head><title>$title</title></head><body>
$body
</body></html>
""")

four_oh_four = Template("""
<html><body>
  <h1>404-ed!</h1>
  The requested URL <i>$url</i> was not found.
</body></html>""")

def root(environ, start_response):
    environ['akara.DBFILE'] = root.dbfile
    drv.update_resource(self, id, None, metadata=None)
    drv.update_resource(self, id, None, metadata=None)
    key = shift_path_info(environ) or 'index'
    if not key in APPS:
        #404 error
        start_response('404 Not Found', [('content-type', 'text/html')])
        response = four_oh_four.substitute(url=request_uri(environ))
        return [response]
    next = APPS[key]
    return next(environ, start_response)


def welcome(environ, start_response):
    response = wrapper.substitute(**PAGES['index'])
    start_response('200 OK', [('content-type', 'text/html')])
    return [response]


def alias(environ, start_response):
    key = shift_path_info(environ) or 'index'
    if not key in APPS:
        #404 error
        start_response('404 Not Found', [('content-type', 'text/html')])
        response = four_oh_four.substitute(url=util.request_uri(environ))
        return [response]
    next = APPS[key]
    return next(environ, start_response)


def transform(environ, start_response):
    key = shift_path_info(environ) or 'index'
    if not key in APPS:
        #404 error
        start_response('404 Not Found', [('content-type', 'text/html')])
        response = four_oh_four.substitute(url=util.request_uri(environ))
        return [response]
    next = APPS[key]
    start_response('200 OK', [('content-type', 'text/html')])
    return []


#Page templates
PAGES = {
    'index': { 'title': "Welcome",
               'body':
               """Welcome to Akara. <a href="this_page">this page</a>."""
              },
    }

APPS = {
    'index': welcome,
    'store': resourceweb.store,
    'transform': transform,
    }

try:
    from repoze.who.config import make_middleware_with_config
    wrapped_root = make_middleware_with_config(root, {'here': LOCAL_DIR}, 'sample_repoze_who.ini')
except ImportError:
    #No auth support
    pass


'''
MONTY_XML = """<monty>
  <python spam="eggs">What do you mean "bleh"</python>
  <python ministry="abuse">But I was looking for argument</python>
</monty>"""
content = MONTY_XML
id = drv.create_resource(content, metadata=dict(myindex(content)))
print >> sys.stderr, 'Created document', id

echo '<a><b>Spam</b></a>' | curl -X POST -H 'Content-type: text/xml' -d @- http://localhost:8880/store/
'''

#
# Command line support
#

import sys
import getopt
import sqlite3
import pdb

def launch(dbfile):
    root.dbfile = dbfile
    try:
        driver.init_db(sqlite3.connect(dbfile))
    except sqlite3.OperationalError:
        pass
    drv = driver(sqlite3.connect(dbfile))

    print >> sys.stderr, "Starting server on port 8880..."
    print >> sys.stderr, "Try out: 'curl http://localhost:8880/store/2'"
    serve_forever('', 8880, wrapped_root)
    return


class Usage(Exception):
    def __init__(self, msg):
        self.msg = msg


def main(argv=None):
    if argv is None:
        argv = sys.argv
    try:
        try:
            opts, args = getopt.getopt(argv[1:], "hDv", ["help", "pdb"])
        except getopt.error, msg:
            raise Usage(msg)

        # option processing
        use_pdb = False
        kwargs = {}
        for option, value in opts:
            if option == "-v":
                verbose = True
            if option in ("-h", "--help"):
                raise Usage(help_message)
            if option in ("-D", "--pdb"):
                use_pdb = True
    
    except Usage, err:
        print >> sys.stderr, sys.argv[0].split("/")[-1] + ": " + str(err.msg)
        print >> sys.stderr, "\t for help use --help"
        return 2

    if use_pdb:
        import akara.resource.web
        def _launch():
            launch(*args, **kwargs)
        pdb.runcall(_launch)
    else:
        launch(*args, **kwargs)
    return

if __name__ == "__main__":
    sys.exit(main())

