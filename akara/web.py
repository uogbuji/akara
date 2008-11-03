#Useful: http://docs.python.org/library/wsgiref.html
#

import sqlite3
from wsgiref.util import shift_path_info, request_uri
from string import Template
from cStringIO import StringIO
from akara.resource import *
from akara.resource.repository import driver

from akara.resource import web as resourceweb
#from akara.services import web as servicesweb


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
    environ['akara.DBFILE'] = DBFILE
    
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

DBFILE = None

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

if __name__ == '__main__':
    import sys
    import sqlite3
    DBFILE = sys.argv[1]
    try:
        driver.init_db(sqlite3.connect(DBFILE))
    except sqlite3.OperationalError:
        pass
    drv = driver(sqlite3.connect(DBFILE))

    from wsgiref import simple_server
    import SocketServer
    class server(simple_server.WSGIServer, SocketServer.ForkingMixIn): pass

    print >> sys.stderr, "Starting server on port 8880..."
    print >> sys.stderr, "Try out: 'curl http://localhost:8880/store/2'"
    try:
        simple_server.make_server('', 8880, root, server).serve_forever()
    except KeyboardInterrupt:
        print >> sys.stderr, "Ctrl-C caught, Server exiting..."

