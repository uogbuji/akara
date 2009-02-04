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
    '''
    GET - retrieve the resource with the specified alias
    POST - create a resource with the specified alias
    '''
    key = environ['PATH_INFO']
    print 'key', key
    if not key in :
        #404 error
        start_response('404 Not Found', [('content-type', 'text/html')])
        response = four_oh_four.substitute(url=request_uri(environ))
        return [response]
    next = APPS[key]
    return next(environ, start_response)


def response(code):
    return '%i %s'%(code, httplib.responses[code])


def store(environ, start_response):
    dbfile = environ['akara.DBFILE']
    drv = driver(sqlite3.connect(dbfile))
    def head_resource():
        get_resource()
        return ''

    def get_resource():
        key = shift_path_info(environ)

        content1, metadata = drv.get_resource(key)
        if content1 is None:
            #404 error
            start_response('404 Not Found', [('content-type', 'text/html')])
            response = four_oh_four.substitute(url=request_uri(environ))
            return response

        start_response('200 OK', [('content-type', str(metadata[CONTENT_TYPE]))])
        return content1.encode('utf-8')

    def post_resource():
        ctype = environ.get('CONTENT_TYPE', 'application/unknown')
        clen = int(environ.get('CONTENT_LENGTH', None))
        if not clen:
            start_response("411 Length Required", [('Content-Type','text/plain')])
            return ["Length Required"]
        key = shift_path_info(environ)
        now = datetime.now().isoformat()
        md = {
            CREATED: now,
            UPDATED: now,
            CONTENT_LENGTH: clen,
            CONTENT_TYPE: ctype,
        }
        #md = self.standard_index
        content = environ['wsgi.input'].read(clen)
        id = drv.create_resource(content, metadata=md)
        msg = 'Adding %i' % id
        new_uri = str(id)

        headers = [('Content-Type', 'text/plain')]
        headers.append(('Location', new_uri))
        headers.append(('Content-Location', new_uri))

        #environ['akara.etag'] = compute_etag(content)
        headers.append(('Content-Length', str(len(msg))))
        start_response("201 Created", headers)
        
        return msg

    dispatch = {
        'GET': get_resource,
        'HEAD': head_resource,
        'POST': post_resource,
    }

    method = dispatch.get(environ['REQUEST_METHOD'])
    if not method:
        response_headers = [('Content-type','text/plain')]
        start_response(response(httplib.METHOD_NOT_ALLOWED), response_headers)
        return ['Method Not Allowed']
    else:
        return [method()]

