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

You'll need a config entry such as:

[moinrest]
target=http://wiki.xml3k.org

Can be launched from the command line, e.g.:
    python akara/restwrap/moin.py http://mywiki.example.com/
"""
#Detailed license and copyright information: http://4suite.org/COPYRIGHT

from __future__ import with_statement

__all__ = [
    "WIKITEXT_IMT", "DOCBOOK_IMT", "RDF_IMT", "ATTACHMENTS_IMT",
    "ORIG_BASE_HEADER", "ATTACHMENTS_MODEL_XML", "ATTACHMENTS_MODEL",
    "MOIN_DOCBOOK_MODEL_XML", "MOIN_DOCBOOK_MODEL",
]

MAIN_DOC = '''
Some sample queries:
    curl http://localhost:8880/moin/FrontPage
    curl -H Accept: application/docbook+xml" http://localhost:8880/moin/FrontPage
    curl -H "Accept: application/rdf+xml" http://localhost:8880/moin/FrontPage
    curl -H "Accept: application/x-moin-attachments+xml" http://localhost:8880/moin/FrontPage
    curl --request PUT --data-binary "@wikicontent.txt" --header "Content-Type: text/plain" "http://localhost:8880/moin/FooTest"
    curl --request POST --data-binary "@wikicontent.txt" --header "Content-Type: text/plain" "http://localhost:8880/moin/FooTest;attachment=wikicontent.txt"

    curl -u me:passwd -p --request PUT --data-binary "@wikicontent.txt" --header "Content-Type: text/plain" "http://localhost:8880/moin/FooTest"

    Get an attached page:
    curl "http://localhost:8880/moin/FooTest;attachment=wikicontent.txt"
'''

__doc__ += MAIN_DOC

import sys
import os
import cgi
#import pprint
import httplib, urllib, urllib2, cookielib
#from wsgiref.util import shift_path_info, request_uri
from string import Template
from cStringIO import StringIO
import tempfile
from gettext import gettext as _
from functools import *
from itertools import *
from operator import *
from contextlib import closing

import amara
from amara import bindery
from amara.writers.struct import *
from amara.bindery.html import parse as htmlparse
from amara.bindery.model import *

from akara.util import multipart_post_handler, wsgibase, http_method_handler

from akara.services import *

#AKARA_MODULE_CONFIG is automatically defined at global scope for a module running within Akara
#WIKIBASE = AKARA_MODULE_CONFIG.get('wrapped_wiki')
TARGET_WIKI = AKARA_MODULE_CONFIG['target']

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

OPENER = urllib2.build_opener(
    urllib2.HTTPCookieProcessor(cookielib.CookieJar()),
    multipart_post_handler.MultipartPostHandler)

SERVICE_ID = 'http://purl.org/akara/services/builtin/xslt'
DEFAULT_MOUNT = 'moin'

def check_auth(environ, start_response):
    auth = environ.get('HTTP_AUTHORIZATION')
    if not auth: return
    scheme, data = auth.split(None, 1)
    if scheme.lower() != 'basic':
        raise RuntimeError('Unsupported HTTP auth scheme: %s'%scheme)
    username, password = data.decode('base64').split(':', 1)
    #user = self.user if user is None else user
    #password = self.password if password is None else password
    url = TARGET_WIKI + '?action=login&name=%s&password=%s&login=login'%(username, password)
    request = urllib2.Request(url)
    with closing(OPENER.open(request)) as resp:
        #Don't need to do anything with the response.  The cookies will be captured automatically
        pass
    environ['REMOTE_USER'] = username
    #print "="*60
    #doc = htmlparse(response)
    #amara.xml_print(doc)
    #print 1, response.info()
    #self.cookiejar.extract_cookies(response, request)
    #for c in self.cookiejar:
    #    print c
    return


def _head_page(environ, start_response):
    page = environ['PATH_INFO']
    check_auth(environ, start_response)
    #print page
    upstream_handler = None
    status = httplib.OK
    if DOCBOOK_IMT in environ['HTTP_ACCEPT']:
        url = TARGET_WIKI + page
        request = urllib2.Request(url + "?mimetype=text/docbook")
        ctype = DOCBOOK_IMT
    elif RDF_IMT in environ['HTTP_ACCEPT']:
        #FIXME: Make unique flag optional
        url = TARGET_WIKI + '/RecentChanges?action=rss_rc&unique=1&ddiffs=1'
        request = urllib2.Request(url)
        ctype = RDF_IMT
    elif ATTACHMENTS_IMT in environ['HTTP_ACCEPT']:
        url = TARGET_WIKI + page + '?action=AttachFile'
        request = urllib2.Request(url)
        ctype = ATTACHMENTS_IMT
        def upstream_handler():
            #Sigh.  Sometimes you have to break some Tag soup eggs to make a RESTful omlette
            with closing(OPENER.open(request)) as resp:
                rbody = resp.read()
            doc = htmlparse(rbody)
            attachment_nodes = doc.xml_select(u'//*[contains(@href, "action=AttachFile") and contains(@href, "do=view")]')
            targets = []
            for node in attachment_nodes:
                target = [ param.split('=', 1)[1] for param in node.href.split(u'&') if param.startswith('target=') ][0]
                targets.append(target)
            buf = StringIO()
            structwriter(indent=u"yes", stream=buf).feed(
            ROOT(
                E((u'attachments'),
                    (E(u'attachment', {u'href': unicode(t)}) for t in targets)
                )
            ))
            return buf.getvalue(), ctype
    #Notes on use of URI parameters - http://markmail.org/message/gw6xbbvx4st6bksw
    elif ';attachment=' in page:
        page, attachment = page.split(';attachment=')
        url = TARGET_WIKI + page + '?action=AttachFile&do=get&target=' + attachment
        request = urllib2.Request(url)
        def upstream_handler():
            with closing(OPENER.open(request)) as resp:
                rbody = resp.read()
            return rbody, dict(resp.info())['content-type']
    else:
        url = TARGET_WIKI + page
        request = urllib2.Request(url + "?action=raw")
        ctype = WIKITEXT_IMT
    try:
        if upstream_handler:
            rbody, ctype = upstream_handler()
        else:
            with closing(OPENER.open(request)) as resp:
                rbody = resp.read()
        
        #headers = {ORIG_BASE_HEADER: TARGET_WIKI}
        headers = [(ORIG_BASE_HEADER, TARGET_WIKI)]
        return status, rbody, ctype, headers
    except urllib2.URLError:
        raise
        #404 error
        rbody = four_oh_four.substitute(fronturl=request_uri(environ), backurl=url)
        return httplib.NOT_FOUND, rbody, 'text/html', {}

def fill_page_edit_form(page):
    url = TARGET_WIKI + page + '?action=edit&editor=text'
    with closing(OPENER.open(urllib2.Request(url))) as resp:
        doc = htmlparse(resp)
    form = doc.html.body.xml_select(u'.//*[@id="editor"]')[0]
    form_vars = {}
    #form / fieldset / input
    form_vars["action"] = unicode(form.xml_select(u'string(*/*[@name="action"]/@value)'))
    form_vars["rev"] = unicode(form.xml_select(u'string(*/*[@name="rev"]/@value)'))
    form_vars["ticket"] = unicode(form.xml_select(u'string(*/*[@name="ticket"]/@value)'))
    form_vars["editor"] = unicode(form.xml_select(u'string(*/*[@name="editor"]/@value)'))
    #pprint.pprint(form_vars)
    return form_vars


def fill_attachment_form(page, attachment):
    url = TARGET_WIKI + page + '?action=AttachFile'
    with closing(OPENER.open(urllib2.Request(url))) as resp:
        doc = htmlparse(resp)
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

#def handle_remote_auth(status, headers):
#    if status.startswith('401'):
#        remove_header(headers, 'WWW-Authenticate')
#        headers.append(('WWW-Authenticate', 'Basic realm="%s"' % realm))
    #return start_response(status, headers)
#    return


@service(['HEAD', 'GET', 'PUT', 'POST'], SERVICE_ID, DEFAULT_MOUNT)
def dispatcher(environ, start_response):
    __doc__ = MAIN_DOC
    #print >> sys.stderr, globals()['head_page'], dir(globals()['head_page'])
    return rest_dispatch(environ, start_response, environ['akara.service_id'], globals())


#def akara_xslt(body, ctype, **params):
@method_handler('HEAD', SERVICE_ID)
def head_page(environ, start_response):
    status, rbody, ctype, headers = _head_page(environ, start_response)
    #headers['CONTENT_TYPE'] = ctype
    headers.append(('CONTENT_TYPE', ctype))
    return response('', None, status, headers)


@method_handler('GET', SERVICE_ID)
def get_page(environ, start_response):
    status, rbody, ctype, headers = _head_page(environ, start_response)
    #headers['CONTENT_TYPE'] = ctype
    headers.append(('CONTENT_TYPE', ctype))
    return response(rbody, None, status, headers)


#def check_auth(self, user=None, password=None):
@method_handler('PUT', SERVICE_ID)
def put_page(environ, start_response):
    '''
    '''
    page = environ['PATH_INFO']
    url = TARGET_WIKI + page
    ctype = environ.get('CONTENT_TYPE', 'application/unknown')
    clen = int(environ.get('CONTENT_LENGTH', None))
    if not clen:
        return response('Content length Required', 'text/plain', httplib.LENGTH_REQUIRED)
    content = environ['wsgi.input'].read(clen)

    form_vars = fill_page_edit_form(page)
    form_vars["savetext"] = content

    data = urllib.urlencode(form_vars)
    request = urllib2.Request(url, data)
    try:
        with closing(OPENER.open(request)) as resp:
            doc = htmlparse(resp)
    except urllib2.URLError:
        raise
        rbody = four_oh_four.substitute(fronturl=request_uri(environ), backurl=url)
        return response(rbody, 'text/html', httplib.NOT_FOUND)
    #print "="*60
    #amara.xml_print(doc)

    msg = 'Page updated OK: ' + url
    headers = [('Content-Type', 'text/plain'), ('Content-Location', url)]

    #headers.append(('Content-Length', str(len(msg))))
    return response(msg, None, httplib.CREATED, headers)


@method_handler('POST', SERVICE_ID)
def post_page(environ, start_response):
    #http://groups.google.com/group/comp.lang.python/browse_thread/thread/4662d41aca276d99
    #ctype = environ.get('CONTENT_TYPE', 'application/unknown')
    page = environ['PATH_INFO']
    page, attachment = page.split(';attachment=')
    url = TARGET_WIKI + page
    #print page, attachment
    clen = int(environ.get('CONTENT_LENGTH', None))
    if not clen:
        return response('Content length Required', 'text/plain', httplib.LENGTH_REQUIRED)
    #now = datetime.now().isoformat()
    #Unfortunately because urllib2's data dicts don't give an option for limiting read length, must read into memory and wrap
    #content = StringIO(environ['wsgi.input'].read(clen))

    temp = tempfile.mkstemp(suffix=".dat")
    os.write(temp[0], environ['wsgi.input'].read(clen))

    form_vars = fill_attachment_form(page, attachment)
    form_vars["file"] = open(temp[1], "rb")

    #data = urllib.urlencode(form_vars)
    request = urllib2.Request(url, form_vars)
    try:
        with closing(OPENER.open(request)) as resp:
            doc = htmlparse(resp)
    except urllib2.URLError:
        raise
        rbody = four_oh_four.substitute(fronturl=request_uri(environ), backurl=url)
        return response(rbody, 'text/html', httplib.NOT_FOUND)
    form_vars["file"].close()
    os.close(temp[0])
    os.remove(temp[1])
    #print "="*60
    #amara.xml_print(doc)

    msg = 'Attachment updated OK: %s\n'%(TARGET_WIKI + page)
    headers = [('Content-Type', 'text/plain'), ('Content-Location', url)]

    #headers.append(('Content-Length', str(len(msg))))
    return response(msg, None, httplib.CREATED, headers)


