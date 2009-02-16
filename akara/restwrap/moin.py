# -*- coding: iso-8859-1 -*-
# 
"""
akara.restwrap.moin

A RESTful wrapper for MoinMoin wikis

Copyright 2009 Uche Ogbuji
This file is part of the open source Akara project,
provided under the Apache 2.0 license.
See the files LICENSE and NOTICE for details.
Project home, documentation, distributions: http://wiki.xml3k.org/Akara

@copyright: 2009 by Uche ogbuji <uche@ogbuji.net>

Can be launched from the command line, e.g.:
    python akara/restwrap/moin.py http://mywiki.example.com/
"""
#Detailed license and copyright information: http://4suite.org/COPYRIGHT

import os
import cgi
import pprint
import httplib
import urllib, urllib2, cookielib
from wsgiref.util import shift_path_info, request_uri
from string import Template
from cStringIO import StringIO

import amara
from amara import bindery
from amara.writers.struct import *
from amara.bindery.html import parse as htmlparse

WIKITEXT_IMT = 'text/plain'
DOCBOOK_IMT = 'application/docbook+xml'
RDF_IMT = 'application/rdf+xml'

# Templates
four_oh_four = Template("""
<html><body>
  <h1>404-ed!</h1>
  The requested URL <i>$fronturl</i> was not found (<i>$backurl</i> in the target wiki).
</body></html>""")

def status_response(code):
    return '%i %s'%(code, httplib.responses[code])

class wsgibase(object):
    def __init__(self):
        if not hasattr(self, 'dispatch'):
            self.dispatch = self.dispatch_by_lookup if hasattr(self, '_methods') else self.dispatch_simply
        return

    def __call__(self, environ, start_response):
        self.environ = environ
        self.start_response = start_response
        return self

    def __iter__(self):
        method = self.dispatch()
        if method is None:
            response_headers = [('Content-type','text/plain')]
            self.start_response(response(httplib.METHOD_NOT_ALLOWED), response_headers)
            yield 'Method Not Allowed'
        else:
            yield method(self)

    def dispatch_simply(self):
        method = 'do_%s' % self.environ['REQUEST_METHOD']
        if not hasattr(self, method):
            return None
        else:
            return method

    def dispatch_by_lookup(self):
        return self._methods.get(self.environ['REQUEST_METHOD'])

    def parse_fields(self):
        s = self.environ['wsgi.input'].read(int(self.environ['CONTENT_LENGTH']))
        return cgi.parse_qs(s)

        
class wikiwrapper(wsgibase):
    def __init__(self, wikibase):
        wsgibase.__init__(self)
        #wikibase = environ['moinrestwrapper.wikibase']
        self.wikibase = wikibase
        self.cookiejar = cookielib.CookieJar()
        self.opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(self.cookiejar))
        return

    def __call__(self, environ, start_response):
        wsgibase.__call__(self, environ, start_response)
        self.page = environ['PATH_INFO']
        #pprint.pprint(environ)
        self.check_auth()
        return self

    def head_page(self):
        url = self.wikibase + self.page
        transform = None
        if DOCBOOK_IMT in self.environ['HTTP_ACCEPT']:
            request = urllib2.Request(url + "?mimetype=text/docbook")
        elif RDF_IMT in self.environ['HTTP_ACCEPT']:
            #FIXME: Make unique flag optional
            url = self.wikibase + '/RecentChanges?action=rss_rc&unique=1&ddiffs=1'
            request = urllib2.Request(url)
        else:
            request = urllib2.Request(url + "?action=raw")
        try:
            response = self.opener.open(request)
        except:
            raise
            #404 error
            self.start_response(status_response(httplib.NOT_FOUND), [('content-type', 'text/html')])
            response = four_oh_four.substitute(fronturl=request_uri(self.environ), backurl=url)
            return response
        #response["Set-Cookie"] = "name=tom"
        #self.cookiejar.extract_cookies(response, request)
        
        self.start_response(status_response(httplib.OK), [('content-type', WIKITEXT_IMT)])
        self.response = response.read()
        return ''

    def get_page(self):
        self.head_page()
        return self.response

    def fill_page_edit_form(self, page=None):
        page = page or self.page
        url = self.wikibase + page + '?action=edit&editor=text'
        doc = htmlparse(self.opener.open(urllib2.Request(url)))
        form = doc.html.body.xml_select(u'.//*[@id="editor"]')[0]
        form_vars = {}
        #form / fieldset / input
        form_vars["action"] = unicode(form.xml_select(u'string(*/*[@name="action"]/@value)'))
        form_vars["rev"] = unicode(form.xml_select(u'string(*/*[@name="rev"]/@value)'))
        form_vars["ticket"] = unicode(form.xml_select(u'string(*/*[@name="ticket"]/@value)'))
        form_vars["editor"] = unicode(form.xml_select(u'string(*/*[@name="editor"]/@value)'))
        #pprint.pprint(form_vars)
        return form_vars

    def handle_remote_auth(self, status, headers):
        if status.startswith('401'):
            remove_header(headers, 'WWW-Authenticate')
            headers.append(('WWW-Authenticate', 'Basic realm="%s"' % self.realm))
        return start_response(status, headers)

    #def check_auth(self, user=None, password=None):
    def check_auth(self):
        auth = self.environ.get('HTTP_AUTHORIZATION')
        if not auth: return
        scheme, data = auth.split(None, 1)
        if scheme.lower() != 'basic':
            raise RuntimeError('Unsupported HTTP auth scheme: %s'%scheme)
        username, password = data.decode('base64').split(':', 1)
        #user = self.user if user is None else user
        #password = self.password if password is None else password
        url = self.wikibase + '?action=login&name=%s&password=%s&login=login'%(username, password)
        request = urllib2.Request(url)
        response = self.opener.open(request)
        self.environ['REMOTE_USER'] = username
        #print "="*60
        #doc = htmlparse(response)
        #amara.xml_print(doc)
        #print 1, response.info()
        #self.cookiejar.extract_cookies(response, request)
        #for c in self.cookiejar:
        #    print c
        return

    def put_page(self):
        '''
        '''
        url = self.wikibase + self.page
        ctype = self.environ.get('CONTENT_TYPE', 'application/unknown')
        clen = int(self.environ.get('CONTENT_LENGTH', None))
        if not clen:
            self.start_response(status_response(httplib.LENGTH_REQUIRED), [('Content-Type','text/plain')])
            return "Content length Required"
        content = self.environ['wsgi.input'].read(clen)

        form_vars = self.fill_page_edit_form()
        form_vars["savetext"] = content

        data = urllib.urlencode(form_vars)
        request = urllib2.Request(url, data)
        try:
            response = self.opener.open(request)
        except:
            raise
            #404 error
            self.start_response(status_response(httplib.NOT_FOUND), [('content-type', 'text/html')])
            response = four_oh_four.substitute(fronturl=request_uri(self.environ), backurl=url)
            return response
        doc = htmlparse(response)
        #print "="*60
        #amara.xml_print(doc)

        msg = 'Page updated OK: ' + url
        headers = [('Content-Type', 'text/plain')]
        headers.append(('Content-Location', url))

        headers.append(('Content-Length', str(len(msg))))
        self.start_response(status_response(httplib.OK), headers)
        
        return msg

    def post_page(self):
        ctype = self.environ.get('CONTENT_TYPE', 'application/unknown')
        clen = int(self.environ.get('CONTENT_LENGTH', None))
        if not clen:
            self.start_response(status_response(httplib.LENGTH_REQUIRED), [('Content-Type','text/plain')])
            return ["Content length Required"]
        key = shift_path_info(environ)
        now = datetime.now().isoformat()
        content = environ['wsgi.input'].read(clen)
        id = drv.create_resource(content, metadata=md)
        msg = 'Adding %i' % id
        new_uri = str(id)

        headers = [('Content-Type', 'text/plain')]
        headers.append(('Location', new_uri))
        headers.append(('Content-Location', new_uri))

        #environ['akara.etag'] = compute_etag(content)
        headers.append(('Content-Length', str(len(msg))))
        self.start_response(status_response(httplib.CREATED), headers)
        
        return msg

    _methods = {
        'GET': get_page,
        'HEAD': head_page,
        'POST': post_page,
        'PUT': put_page,
    }


import sys
import SocketServer
from wsgiref import simple_server

def moinrestwrapper(wikibase):
    class server(simple_server.WSGIServer, SocketServer.ForkingMixIn): pass

    print >> sys.stderr, "Starting server on port 8880..."
    print >> sys.stderr, "Try out:"
    print >> sys.stderr, "\tcurl http://localhost:8880/FrontPage"
    print >> sys.stderr, "\tcurl -H \"Accept: application/docbook+xml\" http://localhost:8880/FrontPage"
    print >> sys.stderr, "\tcurl -H \"Accept: application/rdf+xml\" http://localhost:8880/FrontPage"
    print >> sys.stderr, '\tcurl --request PUT --data-binary "@wikicontent.txt" --header "Content-Type: %s" "http://localhost:8880/FooTest"'%WIKITEXT_IMT
    print >> sys.stderr, '\tcurl -u me:passwd -p --request PUT --data-binary "@wikicontent.txt" --header "Content-Type: %s" "http://localhost:8880/FooTest"'%WIKITEXT_IMT
    try:
        simple_server.make_server('', 8880, wikiwrapper(wikibase), server).serve_forever(
)
    except KeyboardInterrupt:
        print >> sys.stderr, "Ctrl-C caught, Server exiting..."

    return

#Ideas borrowed from
# http://www.artima.com/forums/flat.jsp?forum=106&thread=4829

def command_line_prep():
    from optparse import OptionParser
    usage = "%prog [options] source cmd"
    parser = OptionParser(usage=usage)
    return parser


def main(argv=None):
    #But with better integration of entry points
    if argv is None:
        argv = sys.argv
    # By default, optparse usage errors are terminated by SystemExit
    try:
        optparser = command_line_prep()
        options, args = optparser.parse_args(argv[1:])
        # Process mandatory arguments with IndexError try...except blocks
        try:
            #FIXME: Things seem to break with a trailing slash
            wikibase = args[0]
        except IndexError:
            optparser.error("Missing Wiki base URL")
        rewrite = args[1] if len(args) > 1 else None
    except SystemExit, status:
        return status

    # Perform additional setup work here before dispatching to run()
    # Detectable errors encountered here should be handled and a status
    # code of 1 should be returned. Note, this would be the default code
    # for a SystemExit exception with a string message.

    moinrestwrapper(wikibase)
    return


if __name__ == "__main__":
    sys.exit(main(sys.argv))


