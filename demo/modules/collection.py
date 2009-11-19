# -*- coding: iso-8859-1 -*-
# 
"""
@ 2009 by Uche ogbuji <uche@ogbuji.net>

This file is part of the open source Akara project,
provided under the Apache 2.0 license.
See the files LICENSE and NOTICE for details.
Project home, documentation, distributions: http://wiki.xml3k.org/Akara

 Module name:: collection

= Defined REST entry points =

http://purl.org/akara/services/demo/collection (akara.collection) Handles HEAD, GET, POST, PUT

= Configuration =

You'll need a config entry such as:

[collection]
folder = /tmp/collection

= Notes on security =

This module is a very simple demo, and does not pay much attention to security at all.
The directory you expose to the Web will be exposed to the URL, although
measures are taken to prevent obvious hierarchical manipulation to access
outside that folder

Use this with care.

"""
#Detailed license and copyright information: http://4suite.org/COPYRIGHT

from __future__ import with_statement

SAMPLE_QUERIES_DOC = '''
= Some sample queries =

Get a list of files:

    curl http://localhost:8880/collection

Add a file:

    curl --request POST --data-binary "@foo.txt" --header "Content-Type: text/plain" "http://localhost:8880/collection"
    Note: You might want to see the response headers.  Add "-i" right after "curl" (works with any of these commands)

Get a file:

    curl http://localhost:8880/collection/1

Update file content

    curl --request PUT --data-binary "@foo1.txt" --header "Content-Type: text/plain" "http://localhost:8880/collection/1"
'''

__doc__ += SAMPLE_QUERIES_DOC

import sys
import os
import time
import httplib
from string import Template
from gettext import gettext as _
from contextlib import closing
from wsgiref.util import shift_path_info, request_uri

from akara.util import multipart_post_handler, wsgibase, http_method_handler

from akara.services import method_dispatcher
from akara import response

#AKARA is automatically defined at global scope for a module running within Akara
BASE = AKARA.module_config['folder']

# Templates
four_oh_four = Template("""
<html><body>
  <h1>404-ed!</h1>
  The requested URL <i>$fronturl</i> was not found (<i>$backurl</i> in the target wiki).
</body></html>""")

SERVICE_ID = 'http://purl.org/akara/services/demo/collection'
DEFAULT_MOUNT = 'akara.collection'

def status_response(code):
    return '%i %s'%(code, httplib.responses[code])

#
@method_dispatcher(SERVICE_ID, DEFAULT_MOUNT)
def collection_resource():
    __doc__ = SAMPLE_QUERIES_DOC
    return


@collection_resource.method("GET")
def get_file(environ, start_response):
    '''
    GETting the collection resource itself returns a simple file listing.
    
    GETting a subsidiary resource returns the file
    '''
    print >> sys.stderr, 'GRIPPO', environ['PATH_INFO']
    if environ['PATH_INFO'] == '/':
        #Get index
        start_response(status_response(httplib.OK), [("Content-Type", "text/plain")])
        return '\n'.join(os.listdir(BASE)) + '\n'
    resource_fname = shift_path_info(environ)
    #Not needed because the shift_path_info will ignore anything after the '/' and they'll probably get a 404
    #'..' will not be expanded by os.path.join
    #if "/" in resource_fname:
    #    start_response(status_response(httplib.BAD_REQUEST), [("Content-Type", "text/plain")])
    #    return 'You must not include forward slashes in your request (%s)'%resource_fname
    resource_path = os.path.join(BASE, resource_fname)
    print >> sys.stderr, 'Getting the file at: ', resource_fname
    try:
        f = open(resource_path, 'rb')
        #FIXME: do it chunk by chunk
        rbody = f.read()
        #FIXME: work out content type mappings (perhaps by file extension)
        start_response(status_response(httplib.OK), [("Content-Type", "text/plain")])
        return rbody
    except IOError:
        rbody = four_oh_four.substitute(fronturl=request_uri(environ), backurl=resource_fname)
        start_response(status_response(httplib.NOT_FOUND), [("Content-Type", "text/html")])
        return rbody

#
@collection_resource.method("POST")
def post_file(environ, start_response):
    '''
    Add a new file to the collection
    '''
    #Not needed because the shift_path_info will ignore anything after the '/' and they'll probably get a 404
    #'..' will not be expanded by os.path.join
    #if "/" in resource_fname:
    #    start_response(status_response(httplib.BAD_REQUEST), [("Content-Type", "text/plain")])
    #    return 'You must not include forward slashes in your request (%s)'%resource_fname
    fname = str(int(time.time()))
    #resource_fname = shift_path_info(environ)
    resource_path = os.path.join(BASE, fname)
    fp = open(resource_path, 'wb')

    if not read_http_body_to_file(environ, start_response, fp):
        return 'Content length Required'

    msg = 'File created OK: %s\n'%(fname)
    print >> sys.stderr, 'Creating a file at: ', resource_path

    #response.add_header("Content-Length", str(len(msg)))
    #FIXME: use the full URI for Location header
    start_response(status_response(httplib.CREATED), [("Content-Type", "text/plain"), ("Content-Location", fname)])
    return msg


#def check_auth(self, user=None, password=None):
@collection_resource.method("PUT")
def put_page(environ, start_response):
    '''
    '''
    raise NotImplementedErr


#
CHUNKLEN = 4096
def read_http_body_to_file(environ, start_response, fp):
    '''
    Handle the reading of a file from an HTTP message body (file pointer from wsgi.input)
    in chunks to a temporary file
    Returns the file path of the resulting temp file
    '''
    clen = int(environ.get('CONTENT_LENGTH', None))
    if not clen:
        start_response(status_response(httplib.LENGTH_REQUIRED), [("Content-Type", "text/plain")])
        return False
    http_body = environ['wsgi.input']
    while clen != 0:
        chunk_len = min(CHUNKLEN, clen)
        data = http_body.read(chunk_len)
        if data:
            fp.write(data)
            clen -= chunk_len
        else:
            clen = 0
    fp.close()
    return True


