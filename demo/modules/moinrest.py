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
from wsgiref.util import shift_path_info, request_uri

import amara
from amara import bindery
from amara.lib.iri import *
from amara.writers.struct import *
from amara.bindery.html import parse as htmlparse
from amara.bindery.model import *
from amara.lib.iri import * #split_fragment, relativize, absolutize

from akara.util import multipart_post_handler, wsgibase, http_method_handler

from akara.services import *
from akara.util.moin import *

#AKARA_MODULE_CONFIG is automatically defined at global scope for a module running within Akara
#WIKIBASE = AKARA_MODULE_CONFIG.get('wrapped_wiki')
TARGET_WIKIS = dict(( (k.split('-', 1)[1], AKARA_MODULE_CONFIG[k].rstrip('/') + '/') for k in AKARA_MODULE_CONFIG if k.startswith('target-')))

#print >> sys.stderr, AKARA_MODULE_CONFIG

TARGET_WIKI_OPENERS = {}
DEFAULT_OPENER = urllib2.build_opener(
    urllib2.HTTPCookieProcessor(cookielib.CookieJar()),
    multipart_post_handler.MultipartPostHandler)

#Re: HTTP basic auth: http://www.voidspace.org.uk/python/articles/urllib2.shtml#id6
for k, v in TARGET_WIKIS.items():
    (scheme, authority, path, query, fragment) = split_uri_ref(v)
    auth, host, port = split_authority(authority)
    #print >> sys.stderr, (scheme, authority, path, query, fragment)
    authority = host + ':' + port if port else host
    schemeless_url = authority + path
    #print >> sys.stderr, schemeless_url

    if auth:
        TARGET_WIKIS[k] = unsplit_uri_ref((scheme, authority, path, query, fragment))
        #print >> sys.stderr, auth, TARGET_WIKIS[k]
        auth = auth.split(':')
        password_mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
        # Not setting the realm for now, so use None
        password_mgr.add_password(None, schemeless_url, auth[0], auth[1])
        password_handler = urllib2.HTTPDigestAuthHandler(password_mgr)
        #password_handler = urllib2.HTTPBasicAuthHandler(password_mgr)

        TARGET_WIKI_OPENERS[k] = urllib2.build_opener(
            password_handler,
            urllib2.HTTPCookieProcessor(cookielib.CookieJar()),
            multipart_post_handler.MultipartPostHandler)
    else:
        TARGET_WIKI_OPENERS[k] = DEFAULT_OPENER

print >> sys.stderr, 'Moin target wiki info', TARGET_WIKIS

# Templates
four_oh_four = Template("""
<html><body>
  <h1>404-ed!</h1>
  The requested URL <i>$fronturl</i> was not found (<i>$backurl</i> in the target wiki).
</body></html>""")

SERVICE_ID = 'http://purl.org/akara/services/builtin/xslt'
DEFAULT_MOUNT = 'moin'

normalize = DEFAULT_RESOLVER.normalize


def target(environ):
    #print >> sys.stderr, 'SCRIPT_NAME', environ['SCRIPT_NAME']
    #print >> sys.stderr, 'PATH_INFO', environ['PATH_INFO']
    wiki_id = shift_path_info(environ)
    return wiki_id, TARGET_WIKIS[wiki_id], TARGET_WIKI_OPENERS.get(wiki_id)


def check_auth(environ, start_response, base, opener):
    '''
    Warning: mutates environ in place
    '''
    #print >> sys.stderr, 'HTTP_AUTHORIZATION: ', environ.get('HTTP_AUTHORIZATION')
    auth = environ.get('HTTP_AUTHORIZATION')
    if not auth: return
    scheme, data = auth.split(None, 1)
    if scheme.lower() != 'basic':
        raise RuntimeError('Unsupported HTTP auth scheme: %s'%scheme)
    username, password = data.decode('base64').split(':', 1)
    #print >> sys.stderr, 'Auth creds: ', username, password
    #user = self.user if user is None else user
    #password = self.password if password is None else password
    url = normalize('?action=login&name=%s&password=%s&login=login'%(username, password), base)
    request = urllib2.Request(url)
    try:
        with closing(opener.open(request)) as resp:
            #Don't need to do anything with the response.  The cookies will be captured automatically
            pass
    except urllib2.URLError:
        print >> sys.stderr, 'Error accessing: ', url
        raise
        rbody = four_oh_four.substitute(fronturl=request_uri(environ), backurl=url)
        return response(rbody, 'text/html', httplib.NOT_FOUND)
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
    wiki_id, base, opener = target(environ)
    page = environ['PATH_INFO'].lstrip('/')
    print >> sys.stderr, (page, wiki_id, base)
    check_auth(environ, start_response, base, opener)
    #print page
    upstream_handler = None
    status = httplib.OK
    params = cgi.parse_qs(environ['QUERY_STRING'])
    if 'search' in params:
        searchq = params['search'][0]
        query = urllib.urlencode({'value' : searchq, 'action': 'fullsearch', 'context': '180', 'fullsearch': 'Text'})
        #?action=fullsearch&context=180&value=foo&=Text
        url = absolutize('?'+query, base)
        request = urllib2.Request(url)
        ctype = RDF_IMT
    elif DOCBOOK_IMT in environ['HTTP_ACCEPT']:
        url = absolutize(page, base)
        request = urllib2.Request(url + "?mimetype=text/docbook")
        ctype = DOCBOOK_IMT
    elif HTML_IMT in environ['HTTP_ACCEPT']:
        url = absolutize(page, base)
        request = urllib2.Request(url)
        ctype = HTML_IMT
    elif RDF_IMT in environ['HTTP_ACCEPT']:
        #FIXME: Make unique flag optional
        #url = base + '/RecentChanges?action=rss_rc&unique=1&ddiffs=1'
        url = absolutize('RecentChanges?action=rss_rc&unique=1&ddiffs=1', base)
        #print >> sys.stderr, (url, base, '/RecentChanges?action=rss_rc&unique=1&ddiffs=1', )
        request = urllib2.Request(url)
        ctype = RDF_IMT
    elif ATTACHMENTS_IMT in environ['HTTP_ACCEPT']:
        url = absolutize(page + '?action=AttachFile', base)
        request = urllib2.Request(url)
        ctype = ATTACHMENTS_IMT
        def upstream_handler():
            #Sigh.  Sometimes you have to break some Tag soup eggs to make a RESTful omlette
            with closing(opener.open(request)) as resp:
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
        url = absolutize(page + '?action=AttachFile&do=get&target=' + attachment, base)
        request = urllib2.Request(url)
        def upstream_handler():
            with closing(opener.open(request)) as resp:
                rbody = resp.read()
            return rbody, dict(resp.info())['content-type']
    else:
        url = absolutize(page, base)
        request = urllib2.Request(url + "?action=raw")
        ctype = WIKITEXT_IMT
    try:
        if upstream_handler:
            rbody, ctype = upstream_handler()
        else:
            with closing(opener.open(request)) as resp:
                rbody = resp.read()
        
        #headers = {ORIG_BASE_HEADER: base}
        headers = [(ORIG_BASE_HEADER, absolutize(wiki_id, base))]
        return status, rbody, ctype, headers
    except urllib2.URLError, e:
        if e.code == 403:
            #send back 401
            #FIXME: L10N
            return httplib.UNAUTHORIZED, 'Unauthorized access.  Please authenticate.', 'text/html', [('WWW-Authenticate', 'Basic realm="%s"'%wiki_id)]
        if e.code == 404:
            rbody = four_oh_four.substitute(fronturl=request_uri(environ), backurl=url)
            return httplib.NOT_FOUND, rbody, 'text/html', []
        else:
            print >> sys.stderr, 'Error accessing: ', (url, e.code)
            raise

def fill_page_edit_form(page, wiki_id, base, opener):
    url = absolutize(page, base)
    with closing(opener.open(urllib2.Request(url + '?action=edit&editor=text'))) as resp:
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


def fill_attachment_form(page, attachment, wiki_id, base, opener):
    url = absolutize(page, base)
    with closing(opener.open(urllib2.Request(url + '?action=AttachFile'))) as resp:
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
    #print >> sys.stderr, headers
    return response('', None, status, headers)


@method_handler('GET', SERVICE_ID)
def get_page(environ, start_response):
    status, rbody, ctype, headers = _head_page(environ, start_response)
    #headers['CONTENT_TYPE'] = ctype
    headers.append(('CONTENT_TYPE', ctype))
    #print >> sys.stderr, headers
    return response(rbody, None, status, headers)


#def check_auth(self, user=None, password=None):
@method_handler('PUT', SERVICE_ID)
def put_page(environ, start_response):
    '''
    '''
    wiki_id, base, opener = target(environ)
    page = environ['PATH_INFO'].lstrip('/')
    check_auth(environ, start_response, base, opener)
    ctype = environ.get('CONTENT_TYPE', 'application/unknown')
    clen = int(environ.get('CONTENT_LENGTH', None))
    if not clen:
        return response('Content length Required', 'text/plain', httplib.LENGTH_REQUIRED)
    content = environ['wsgi.input'].read(clen)

    form_vars = fill_page_edit_form(page, wiki_id, base, opener)
    form_vars["savetext"] = content

    url = absolutize(page, base)
    data = urllib.urlencode(form_vars)
    request = urllib2.Request(url, data)
    try:
        with closing(opener.open(request)) as resp:
            doc = htmlparse(resp)
    except urllib2.URLError:
        print >> sys.stderr, 'Error accessing: ', url
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
    wiki_id, base, opener = target(environ)
    check_auth(environ, start_response, base, opener)
    page = environ['PATH_INFO'].lstrip('/')
    page, chaff, attachment = page.partition(';attachment=')
    print >> sys.stderr, page, attachment
    clen = int(environ.get('CONTENT_LENGTH', None))
    if not clen:
        return response('Content length Required', 'text/plain', httplib.LENGTH_REQUIRED)
    #now = datetime.now().isoformat()
    #Unfortunately because urllib2's data dicts don't give an option for limiting read length, must read into memory and wrap
    #content = StringIO(environ['wsgi.input'].read(clen))

    temp = tempfile.mkstemp(suffix=".dat")
    os.write(temp[0], environ['wsgi.input'].read(clen))

    form_vars = fill_attachment_form(page, attachment, wiki_id, base, opener)
    form_vars["file"] = open(temp[1], "rb")

    url = absolutize(page, base)
    print >> sys.stderr, url, 
    #data = urllib.urlencode(form_vars)
    request = urllib2.Request(url, form_vars)
    try:
        with closing(opener.open(request)) as resp:
            doc = htmlparse(resp)
            amara.xml_print(doc, stream=sys.stderr, indent=True)
    except urllib2.URLError:
        print >> sys.stderr, 'Error accessing: ', url
        raise
        rbody = four_oh_four.substitute(fronturl=request_uri(environ), backurl=url)
        return response(rbody, 'text/html', httplib.NOT_FOUND)
    form_vars["file"].close()
    os.close(temp[0])
    os.remove(temp[1])
    #print "="*60
    #amara.xml_print(doc)

    msg = 'Attachment updated OK: %s\n'%(url)
    headers = [('Content-Type', 'text/plain'), ('Content-Location', url)]

    #headers.append(('Content-Length', str(len(msg))))
    return response(msg, None, httplib.CREATED, headers)


