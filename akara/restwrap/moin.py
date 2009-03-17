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

__all__ = [
    "WIKITEXT_IMT", "DOCBOOK_IMT", "RDF_IMT", "ATTACHMENTS_IMT",
    "ORIG_BASE_HEADER", "ATTACHMENTS_MODEL_XML", "ATTACHMENTS_MODEL",
    "MOIN_DOCBOOK_MODEL_XML", "MOIN_DOCBOOK_MODEL",
]

import os
import cgi
import pprint
import httplib
import urllib, urllib2, cookielib
from wsgiref.util import shift_path_info, request_uri
from string import Template
from cStringIO import StringIO
import tempfile
from functools import *
from itertools import *
from operator import *

import amara
from amara import bindery
from amara.writers.struct import *
from amara.bindery.html import parse as htmlparse
from amara.bindery.model import *

from akara.server import serve_forever
from akara.util import multipart_post_handler, wsgibase, http_method_handler

WIKITEXT_IMT = 'text/plain'
DOCBOOK_IMT = 'application/docbook+xml'
RDF_IMT = 'application/rdf+xml'
ATTACHMENTS_IMT = 'application/x-moin-attachments+xml'
ORIG_BASE_HEADER = 'x-akara-wrapped-moin'

# Templates
four_oh_four = Template("""
<html><body>
  <h1>404-ed!</h1>
  The requested URL <i>$fronturl</i> was not found (<i>$backurl</i> in the target wiki).
</body></html>""")

# XML models

ATTACHMENTS_MODEL_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<attachments xmlns:eg="http://examplotron.org/0/" xmlns:ak="http://purl.org/dc/org/xml3k/akara">
  <attachment href="" ak:rel="name()" ak:value="@href"/>
</attachments>
'''

ATTACHMENTS_MODEL = examplotron_model(ATTACHMENTS_MODEL_XML)

MOIN_DOCBOOK_MODEL_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<article xmlns:eg="http://examplotron.org/0/" xmlns:ak="http://purl.org/dc/org/xml3k/akara" ak:resource="">
  <ak:rel name="'ak-type'" ak:value="glosslist[1]/glossentry[glossterm='akara:type']/glossdef//ulink/@url"/>
  <ak:rel name="'ak-updated'" ak:value="articleinfo/revhistory/revision[1]/date"/>
  <articleinfo>
    <title ak:rel="name()" ak:value=".">FrontPage</title>
    <revhistory>
      <revision eg:occurs="*">
        <revnumber>15</revnumber>
        <date>2009-02-22 07:45:22</date>
        <authorinitials>localhost</authorinitials>
      </revision>
    </revhistory>
  </articleinfo>
  <section eg:occurs="*" ak:resource="">
    <title ak:rel="name()" ak:value=".">A page</title>
    <para>
    Using: <ulink url="http://moinmo.in/DesktopEdition"/> set <code>interface = ''</code>)
    </para>
    <itemizedlist>
      <listitem>
        <para>
          <ulink url="http://localhost:8080/Developer#">Developer</ulink> </para>
      </listitem>
    </itemizedlist>
  </section>
</article>
'''

MOIN_DOCBOOK_MODEL = examplotron_model(MOIN_DOCBOOK_MODEL_XML)

def status_response(code):
    return '%i %s'%(code, httplib.responses[code])

class wikiwrapper(wsgibase):
    def __init__(self, wikibase):
        wsgibase.__init__(self)
        #wikibase = environ['moinrestwrapper.wikibase']
        self.wikibase = wikibase
        self.cookiejar = cookielib.CookieJar()
        self.opener = urllib2.build_opener(
            urllib2.HTTPCookieProcessor(self.cookiejar),
            multipart_post_handler.MultipartPostHandler)
        return

    def __call__(self, environ, start_response):
        wsgibase.__call__(self, environ, start_response)
        self.page = environ['PATH_INFO']
        #pprint.pprint(environ)
        self.check_auth()
        return self

    @http_method_handler('HEAD')
    def head_page(self):
        #print self.page
        upstream_handler = None
        if DOCBOOK_IMT in self.environ['HTTP_ACCEPT']:
            url = self.wikibase + self.page
            request = urllib2.Request(url + "?mimetype=text/docbook")
            self.headers = [('content-type', DOCBOOK_IMT)]
        elif RDF_IMT in self.environ['HTTP_ACCEPT']:
            #FIXME: Make unique flag optional
            url = self.wikibase + '/RecentChanges?action=rss_rc&unique=1&ddiffs=1'
            request = urllib2.Request(url)
            self.headers = [('content-type', RDF_IMT)]
        elif ATTACHMENTS_IMT in self.environ['HTTP_ACCEPT']:
            url = self.wikibase + self.page + '?action=AttachFile'
            request = urllib2.Request(url)
            self.headers = [('content-type', ATTACHMENTS_IMT)]
            def upstream_handler():
                buf = StringIO()
                #Sigh.  Sometimes you have to break some Tag soup eggs to make a RESTful omlette
                response = self.opener.open(request)
                self.response = response.read()
                response.close()
                doc = htmlparse(self.response)
                attachment_nodes = doc.xml_select(u'//*[contains(@href, "action=AttachFile") and contains(@href, "do=view")]')
                targets = []
                for node in attachment_nodes:
                    target = [ param.split('=', 1)[1] for param in node.href.split(u'&') if param.startswith('target=') ][0]
                    targets.append(target)
                structwriter(indent=u"yes", stream=buf).feed(
                ROOT(
                    E((u'attachments'),
                        (E(u'attachment', {u'href': unicode(t)}) for t in targets)
                    )
                ))
                self.response = buf.getvalue()
                return
        elif ';attachment=' in self.page:
            page, attachment = self.page.split(';attachment=')
            url = self.wikibase + page + '?action=AttachFile&do=get&target=' + attachment
            request = urllib2.Request(url)
            def upstream_handler():
                response = self.opener.open(request)
                self.response = response.read()
                response.close()
                self.headers = [('content-type', dict(response.info())['content-type'])]
                return
        else:
            url = self.wikibase + self.page
            request = urllib2.Request(url + "?action=raw")
            self.headers = [('content-type', WIKITEXT_IMT)]

        try:
            if upstream_handler:
                upstream_handler()
            else:
                response = self.opener.open(request)
                self.response = response.read()
                response.close()
            self.headers = [(ORIG_BASE_HEADER, self.wikibase)]
            self.start_response(status_response(httplib.OK), self.headers)
            return ''
        except urllib2.URLError:
            raise
            #404 error
            self.start_response(status_response(httplib.NOT_FOUND), [('content-type', 'text/html')])
            response = four_oh_four.substitute(fronturl=request_uri(self.environ), backurl=url)
            return response

    @http_method_handler('GET')
    def get_page(self):
        self.head_page()
        return self.response

    def fill_page_edit_form(self, page=None):
        page = page or self.page
        url = self.wikibase + page + '?action=edit&editor=text'
        response = self.opener.open(urllib2.Request(url))
        doc = htmlparse(response)
        response.close()
        form = doc.html.body.xml_select(u'.//*[@id="editor"]')[0]
        form_vars = {}
        #form / fieldset / input
        form_vars["action"] = unicode(form.xml_select(u'string(*/*[@name="action"]/@value)'))
        form_vars["rev"] = unicode(form.xml_select(u'string(*/*[@name="rev"]/@value)'))
        form_vars["ticket"] = unicode(form.xml_select(u'string(*/*[@name="ticket"]/@value)'))
        form_vars["editor"] = unicode(form.xml_select(u'string(*/*[@name="editor"]/@value)'))
        #pprint.pprint(form_vars)
        return form_vars

    def fill_attachment_form(self, page, attachment):
        url = self.wikibase + page + '?action=AttachFile'
        response = self.opener.open(urllib2.Request(url))
        doc = htmlparse(response)
        response.close()
        form = doc.html.body.xml_select(u'.//*[@id="content"]/form')[0]
        form_vars = {}
        #form / dl / ... dd
        form_vars["rename"] = unicode(attachment)
        #FIXME: parameterize
        form_vars["overwrite"] = u'1'
        form_vars["action"] = unicode(form.xml_select(u'string(*/*[@name="action"]/@value)'))
        form_vars["do"] = unicode(form.xml_select(u'string(*/*[@name="do"]/@value)'))
        form_vars["submit"] = unicode(form.xml_select(u'string(*/*[@type="submit"]/@value)'))
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
        response.close()
        self.environ['REMOTE_USER'] = username
        #print "="*60
        #doc = htmlparse(response)
        #amara.xml_print(doc)
        #print 1, response.info()
        #self.cookiejar.extract_cookies(response, request)
        #for c in self.cookiejar:
        #    print c
        return

    @http_method_handler('PUT')
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
        except urllib2.URLError:
            raise
            #404 error
            self.start_response(status_response(httplib.NOT_FOUND), [('content-type', 'text/html')])
            response = four_oh_four.substitute(fronturl=request_uri(self.environ), backurl=url)
            return response
        doc = htmlparse(response)
        response.close()
        #print "="*60
        #amara.xml_print(doc)

        msg = 'Page updated OK: ' + url
        headers = [('Content-Type', 'text/plain')]
        headers.append(('Content-Location', url))

        headers.append(('Content-Length', str(len(msg))))
        self.start_response(status_response(httplib.CREATED), headers)
        
        return msg

    @http_method_handler('POST')
    def post_page(self):
        #http://groups.google.com/group/comp.lang.python/browse_thread/thread/4662d41aca276d99
        #ctype = self.environ.get('CONTENT_TYPE', 'application/unknown')
        page, attachment = self.page.split(';attachment=')
        url = self.wikibase + page
        #print page, attachment
        clen = int(self.environ.get('CONTENT_LENGTH', None))
        if not clen:
            self.start_response(status_response(httplib.LENGTH_REQUIRED), [('Content-Type','text/plain')])
            return ["Content length Required"]
        #now = datetime.now().isoformat()
        #Unfortunately because urllib2's data dicts don't give an option for limiting read length, must read into memory and wrap
        #content = StringIO(self.environ['wsgi.input'].read(clen))

        temp = tempfile.mkstemp(suffix=".dat")
        os.write(temp[0], self.environ['wsgi.input'].read(clen))

        form_vars = self.fill_attachment_form(page, attachment)
        form_vars["file"] = open(temp[1], "rb")

        #data = urllib.urlencode(form_vars)
        request = urllib2.Request(url, form_vars)
        try:
            response = self.opener.open(request)
        except urllib2.URLError:
            raise
            #404 error
            self.start_response(status_response(httplib.NOT_FOUND), [('content-type', 'text/html')])
            response = four_oh_four.substitute(fronturl=request_uri(self.environ), backurl=url)
            return response
        form_vars["file"].close()
        os.close(temp[0])
        os.remove(temp[1])
        doc = htmlparse(response)
        response.close()
        #print "="*60
        #amara.xml_print(doc)

        msg = 'Attachment updated OK: %s\n'%(self.wikibase + self.page)
        headers = [('Content-Type', 'text/plain')]
        headers.append(('Content-Location', url))

        headers.append(('Content-Length', str(len(msg))))
        self.start_response(status_response(httplib.CREATED), headers)
        
        return msg


import sys

def moinrestwrapper(wikibase):
    print >> sys.stderr, "Starting server on port 8880..."
    print >> sys.stderr, "Try out:"
    print >> sys.stderr, "\tcurl http://localhost:8880/FrontPage"
    print >> sys.stderr, "\tcurl -H \"Accept: application/docbook+xml\" http://localhost:8880/FrontPage"
    print >> sys.stderr, "\tcurl -H \"Accept: application/rdf+xml\" http://localhost:8880/FrontPage"
    print >> sys.stderr, "\tcurl -H \"Accept: application/x-moin-attachments+xml\" http://localhost:8880/FrontPage"
    print >> sys.stderr, '\tcurl --request PUT --data-binary "@wikicontent.txt" --header "Content-Type: %s" "http://localhost:8880/FooTest"'%WIKITEXT_IMT
    print >> sys.stderr, '\tcurl --request POST --data-binary "@wikicontent.txt" --header "Content-Type: %s" "http://localhost:8880/FooTest;attachment=wikicontent.txt"'%WIKITEXT_IMT
    print >> sys.stderr, '\tcurl -u me:passwd -p --request PUT --data-binary "@wikicontent.txt" --header "Content-Type: %s" "http://localhost:8880/FooTest"'%WIKITEXT_IMT
    serve_forever('', 8880, wikiwrapper(wikibase)
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


