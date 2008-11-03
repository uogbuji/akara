#Useful: http://docs.python.org/library/wsgiref.html
#

import httplib
import sqlite3
from datetime import datetime
from wsgiref.util import shift_path_info, request_uri
from string import Template
from cStringIO import StringIO
from akara.resource import *
from akara.resource.repository import driver
from akara.resource.index import simple_xpath_index

# Templates
wrapper = Template("""\
<html><head><title>$title</title></head><body>
$body
</body></html>
""")

four_oh_four = Template("""\
<html><body>
  <h1>404-ed!</h1>
  The requested URL <i>$url</i> was not found.
</body></html>""")


def alias(environ, start_response):
    key = shift_path_info(environ) or 'index'
    if not key in APPS:
        #404 error
        start_response('404 Not Found', [('content-type', 'text/html')])
        response = four_oh_four.substitute(url=request_uri(environ))
        return [response]
    next = APPS[key]
    return next(environ, start_response)


def response(code):
    return '%i %s'%(code, httplib.responses[code])


class store(object):
    def __init__(self, environ, start_response):
        self.environ = environ
        self.start_response = start_response
        return

    def __iter__(self):
        method = self.dispatch.get(self.environ['REQUEST_METHOD'])
        if not method:
            response_headers = [('Content-type','text/plain')]
            self.start_response(response(httplib.METHOD_NOT_ALLOWED), response_headers)
            yield 'Method Not Allowed'
        else:
            yield method(self)

    #def dispatch(self, environ, start_response):
    
    def head_resource(self):
        self.get_resource()
        return ''

    def get_resource(self):
        DBFILE = self.environ['akara.DBFILE']
        key = shift_path_info(self.environ)

        drv = driver(sqlite3.connect(DBFILE))
        content1, metadata = drv.get_resource(key)
        if content1 is None:
            #404 error
            self.start_response('404 Not Found', [('content-type', 'text/html')])
            response = four_oh_four.substitute(url=request_uri(self.environ))
            return response

        self.start_response('200 OK', [('content-type', str(metadata[CONTENT_TYPE]))])
        return content1.encode('utf-8')

        key = shift_path_info(self.environ) or 'index'
        next = APPS[key]

        return next(environ, start_response)

    def post_resource(self):
        ctype = self.environ.get('CONTENT_TYPE', 'application/unknown')
        clen = int(self.environ.get('CONTENT_LENGTH', None))
        if not clen:
            self.start_response("411 Length Required", [('Content-Type','text/plain')])
            return ["Length Required"]
        DBFILE = self.environ['akara.DBFILE']
        key = shift_path_info(self.environ)
        now = datetime.now().isoformat()
        md = {
            CREATED: now,
            UPDATED: now,
            CONTENT_LENGTH: clen,
            CONTENT_TYPE: ctype,
        }
        #md = self.standard_index
        drv = driver(sqlite3.connect(DBFILE))
        content = self.environ['wsgi.input'].read(clen)
        id = drv.create_resource(content, metadata=md)
        msg = 'Adding %i' % id
        new_uri = str(id)

        headers = [('Content-Type', 'text/plain')]
        headers.append(('Location', new_uri))
        headers.append(('Content-Location', new_uri))

        #environ['akara.etag'] = compute_etag(content)
        headers.append(('Content-Length', str(len(msg))))
        self.start_response("201 Created", headers)
        
        return msg

    dispatch = {
        'GET': get_resource,
        'HEAD': head_resource,
        'POST': post_resource,
    }

#store_ = store()

