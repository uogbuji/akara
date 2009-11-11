# -*- coding: iso-8859-1 -*-
# 
"""
@ 2009 by Uche ogbuji <uche@ogbuji.net>

This file is part of the open source Akara project,
provided under the Apache 2.0 license.
See the files LICENSE and NOTICE for details.
Project home, documentation, distributions: http://wiki.xml3k.org/Akara

 Module name:: moinrest

= Defined REST entry points =

http://purl.org/akara/services/builtin/collection (moin)
  - Under there top mount point is oen or more lower points depending on config,
    each of which handles HEAD, GET, POST, PUT

= Configuration =

You'll need a config entry such as:

[moinrest]
target-xml3k=http://wiki.xml3k.org

= Notes on security and authentication =

There are two separate aspects to authentication that moinrest has to
consider and which may need to be configured independently.  First, if
the HTTP server that is running the target wiki is configured with
site-wide basic authentication, you will need to include an
appropriate username and password in the target configuration above.
For example:

[moinrest]
target-xml3k=http://user:password@wiki.xml3k.org

where "user" and "password" are filled in with the appropriate
username and password.  If you're not sure if you need this, try
connecting to the wiki using a browser.  If the browser immediately
displays a pop-up window asking you for a username and password,
you'll need to supply that information in the moinrest configuration
as shown.  If no pop-up window appears, the HTTP server is not using
authentication.

The second form of authentication concerns access to the MoinMoin wiki
itself. In order to modify pages, users may be required to log in to
the wiki first using the wiki's "login" link.  These credentials are
passed to moinrest using HTTP Basic Authentication.  Thus, they need
to be passed in the HTTP headers of requests.  For example, using curl
you would type something like this:

    curl -u me:passwd -p --request PUT --data-binary "@wikicontent.txt" --header "Content-Type: text/plain" "http://localhost:8880/moin/xml3k/FooTest"

Keep in mind that username and password credentials given to moinrest
requests are only for the target wiki.  They are not the same as basic
authentication for the HTTP server hosting the wiki.
"""

#Detailed license and copyright information: http://4suite.org/COPYRIGHT

from __future__ import with_statement

SAMPLE_QUERIES_DOC = '''
Some sample queries:
    curl http://localhost:8880/moin/xml3k/FrontPage
    curl -H "Accept: application/docbook+xml" http://localhost:8880/moin/xml3k/FrontPage
    curl -H "Accept: application/rdf+xml" http://localhost:8880/moin/xml3k/FrontPage
    curl -H "Accept: application/x-moin-attachments+xml" http://localhost:8880/moin/xml3k/FrontPage
    curl --request PUT --data-binary "@wikicontent.txt" --header "Content-Type: text/plain" "http://localhost:8880/moin/xml3k/FooTest"
    curl --request POST --data-binary "@wikicontent.txt" --header "Content-Type: text/plain" "http://localhost:8880/moin/xml3k/FooTest;attachment=wikicontent.txt"

    curl -u me:passwd -p --request PUT --data-binary "@wikicontent.txt" --header "Content-Type: text/plain" "http://localhost:8880/moin/xml3k/FooTest"

    Get an attached page:
    curl "http://localhost:8880/moin/xml3k/FooTest;attachment=wikicontent.txt"
'''

__doc__ += SAMPLE_QUERIES_DOC

import sys
import os
import cgi
#import pprint
import httplib, urllib, urllib2
#from wsgiref.util import shift_path_info, request_uri
from string import Template
from cStringIO import StringIO
import tempfile
from gettext import gettext as _
from functools import wraps
from itertools import *
from contextlib import closing
from wsgiref.util import shift_path_info, request_uri

import amara
from amara import bindery
from amara.lib.iri import absolutize
from amara.bindery.html import parse as htmlparse
from amara.bindery.model import examplotron_model, generate_metadata
from amara.lib.iri import split_fragment, relativize, absolutize, split_uri_ref, split_authority, unsplit_uri_ref
#from amara import inputsource

from akara.util import multipart_post_handler, wsgibase, http_method_handler

from akara.services import method_dispatcher
from akara.util import status_response
from akara import response
from akara.util.moin import ORIG_BASE_HEADER, WIKITEXT_IMT, DOCBOOK_IMT, RDF_IMT, HTML_IMT, ATTACHMENTS_IMT
from akara.util.moin import ATTACHMENTS_MODEL_XML, ATTACHMENTS_MODEL, MOIN_DOCBOOK_MODEL_XML, MOIN_DOCBOOK_MODEL

# 
# ======================================================================
#                         Module Configruation
# ======================================================================

#AKARA is automatically defined at global scope for a module running within Akara

TARGET_WIKIS = dict(( (k.split('-', 1)[1], AKARA.module_config[k].rstrip('/') + '/') for k in AKARA.module_config if k.startswith('target-')))
TARGET_WIKI_OPENERS = {}
DEFAULT_OPENER = urllib2.build_opener(
    urllib2.HTTPCookieProcessor(),
    multipart_post_handler.MultipartPostHandler)

# Look at each Wiki URL and build an appropriate opener object for retrieving
# pages.   If the URL includes HTTP authentication information such as
# http://user:pass@somedomain.com/mywiki, the opener is built with
# basic authentication enabled.   For details, see:
# 
#     : HTTP basic auth: http://www.voidspace.org.uk/python/articles/urllib2.shtml#id6
for k, v in TARGET_WIKIS.items():
    (scheme, authority, path, query, fragment) = split_uri_ref(v)
    auth, host, port = split_authority(authority)
    authority = host + ':' + port if port else host
    schemeless_url = authority + path
    if auth:
        TARGET_WIKIS[k] = unsplit_uri_ref((scheme, authority, path, query, fragment))
        auth = auth.split(':')
        password_mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
        # Not setting the realm for now, so use None
        password_mgr.add_password(None, scheme+"://"+host+path, auth[0], auth[1])
        password_handler = urllib2.HTTPBasicAuthHandler(password_mgr)
        TARGET_WIKI_OPENERS[k] = urllib2.build_opener(
            password_handler,
            urllib2.HTTPCookieProcessor(),
            multipart_post_handler.MultipartPostHandler)
    else:
        TARGET_WIKI_OPENERS[k] = DEFAULT_OPENER

SERVICE_ID = 'http://purl.org/akara/services/builtin/moinrest'
DEFAULT_MOUNT = 'moin'

# ======================================================================
#                       Exceptions (Used Internally)
# ======================================================================

# Base exception used to indicate errors.  Rather than replicating tons
# of error handling code, these errors are raised instead.  A top-level
# exception handler catches them and then generates some kind of 
# appropriate HTTP response.  Positional arguments (if any)
# are just passed to the Exception base as before.  Keyword arguments
# are saved in a local dictionary.  They will be used to pass parameters
# to the Template strings used when generating error messages.

class MoinRestError(Exception): 
    def __init__(self,*args,**kwargs):
        Exception.__init__(self,*args)
        self.parms = kwargs

class BadTargetError(MoinRestError): pass
class HTTPAuthorizationError(MoinRestError): pass
class MoinAuthorizationError(MoinRestError): pass
class UnexpectedResponseError(MoinRestError): pass
class MoinMustAuthenticateError(MoinRestError): pass
class MoinNotFoundError(MoinRestError): pass
class ContentLengthRequiredError(MoinRestError): pass

# ======================================================================
#                             Response Templates
# ======================================================================
# These template strings contain the output produced for various
# error conditions.

error_badtarget = Template("""\
404 Not Found

The requested URL $fronturl not found.  
Nothing is known about moin target $target.
"""
)

error_httpforbidden = Template("""\
403 Forbidden

Request for URL $url
is being rejected by the Moin HTTP server due to bad HTTP
authentication. Check the Akara's moinrest configuration to make
sure it includes an appropriate HTTP user name and password.
"""
)

error_moinauthforbidden = Template("""\
403 Forbidden

Request for login URL $url
is being rejected by MoinMoin because the username and password
aren't recognized.  Check your request to moinrest to make sure
a valid Moin username and password are being supplied.
"""
)

error_moinmustauthenticateresponse = Template("""\
401 Unauthorized

Request for URL $url
requires a valid Moin username and password.
"""
)

error_unexpectedresponse = Template("""\
500 Internal Error

Request for URL $url 
failed because an unexpected HTTP status code $code was received.
$error
"""
)

error_moinnotfoundresponse = Template("""\
404 Not Found

The requested URL $fronturl not found.
The URL $backurl was not found in the target wiki.
"""
)

error_contentlengthrequired = Template("""\
411 Length Required

A POST or PUT request was made, but no data was found.
""")

# ======================================================================
#                      @errorwrapped decorator
# ======================================================================
# This decorator should be wrapped around all WSGI methods implemented
# by the module.   It catches MoinRest specific exceptions and produces
# appropriate error responses if necessary.
#
# The reason for putting this in a decorator is to avoid a lot of 
# excessive code duplication between different HTTP methods.  For example,
# the handlers for each HTTP method are going to have to deal with
# many of the same error conditions, faults, and responses.  This
# decorator allows us to define all of the error handling in just one place.

def errorwrapped(handler):
    status_info = {}          # Dictionary of collected status information

    # Replacement for the WSGI start_response function.  This merely
    # collects data for later use if no errors occur

    def local_start_response(status, headers):
        status_info['status'] = status
        status_info['headers'] = headers

    # Decorated WSGI handler with moinrest error handling
    @wraps(handler)
    def error_handler(environ, start_response):
        try:
            body = handler(environ, local_start_response)
            # If control reaches here, no errors.  Proceed with normal WSGI response
            start_response(status_info['status'],status_info['headers'])
            return body

        # Error handling for specifying an invalid moin target name (i.e., not configured, misspelled)
        except BadTargetError,e:
            start_response(status_response(httplib.NOT_FOUND), [
                    ('Content-Type','text/plain')
                    ])
            return error_badtarget.safe_substitute(e.parms)

        # Error handling for back-end HTTP authorization failure.  For example,
        # if the HTTP server hosting MoinMoin has rejected our requests due to
        # bad HTTP authorization.
        except HTTPAuthorizationError,e:
            start_response(status_response(httplib.FORBIDDEN), [
                    ('Content-Type','text/plain')
                    ])
            return error_httpforbidden.safe_substitute(e.parms)

        # Error handling for MoinMoin authorization failure.  This occurs
        # if the user and password supplied to MoinMoin is rejected.
        except MoinAuthorizationError,e:
            start_response(status_response(httplib.FORBIDDEN), [
                    ('Content-Type','text/plain')
                    ])
            return error_moinauthforbidden.safe_substitute(e.parms)

        # Error handling for unexpected HTTP status codes
        except UnexpectedResponseError,e:
            start_response(status_response(httplib.INTERNAL_SERVER_ERROR), [
                    ('Content-Type','text/plain')
                    ])
            return error_unexpectedresponse.safe_substitute(e.parms)

        # Authentication required by MoinMoin.  This isn't an error, but we
        # have to translate this into a 401 response to send back to the client
        # in order to get them to supply the appropriate username/password
        
        except MoinMustAuthenticateError,e:
            start_response(status_response(httplib.UNAUTHORIZED), [
                    ('Content-Type','text/plain'),
                    ('WWW-Authenticate','Basic realm="%s"' % e.parms.get('target',''))
                    ])
            return error_moinmustauthenticateresponse.safe_substitute(e.parms)
        
        # Page in the target-wiki not found. 404 the client
        except MoinNotFoundError,e:
            start_response(status_response(httplib.NOT_FOUND), [
                    ('Content-Type','text/plain'),
                    ])
            return error_moinnotfoundresponse.safe_substitute(e.parms)

        # Content-length is required for uploaded data
        except ContentLengthRequiredError,e:
            start_response(status_response(httplib.LENGTH_REQUIRED), [
                    ('Content-Type','text/plain')
                    ])
            return error_contentlengthrequired.safe_substitute(e.parms)

    return error_handler

# Utility function for generating status rsponses for WSGI
def status_response(code):
    return '%i %s'%(code, httplib.responses[code])

# Returns information about the target wiki. Raises BadTargetError if nothing
# is known about the target name
def target(environ):
    wiki_id = shift_path_info(environ)
    if wiki_id not in TARGET_WIKIS:
        raise BadTargetError(fronturl=request_uri(environ), target=wiki_id)
    return wiki_id, TARGET_WIKIS[wiki_id], TARGET_WIKI_OPENERS.get(wiki_id)


# Check authentication of the user on the MoinMoin wiki
def check_auth(environ, start_response, base, opener):
    '''
    Warning: mutates environ in place
    '''
    auth = environ.get('HTTP_AUTHORIZATION')
    if not auth: 
        return False

    scheme, data = auth.split(None, 1)
    if scheme.lower() != 'basic':
        raise RuntimeError('Unsupported HTTP auth scheme: %s'%scheme)
    username, password = data.decode('base64').split(':', 1)
    url = absolutize('?action=login&name=%s&password=%s&login=login'%(username, password), base)
    request = urllib2.Request(url)
    try:
        with closing(opener.open(request)) as resp:
            #Don't need to do anything with the response.  The cookies will be captured automatically
            pass
    except urllib2.URLError,e:
        if e.code == 401:
            # If we're here, the backend HTTP server has likely rejected our request due to HTTP auth
            raise HTTPAuthorizationError(url=url)
        elif e.code == 403:
            # If we get a forbidden response, we made it to MoinMoin but the user name/pass was rejected
            raise MoinAuthorizationError(url=url)
        else:
            raise UnexpectedResponseError(url=url,code=e.code,error=str(e))

    environ['REMOTE_USER'] = username
    return True


def _get_page(environ, start_response):
    wiki_id, base, opener = target(environ)
    page = environ['PATH_INFO'].lstrip('/')
    check_auth(environ, start_response, base, opener)
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
        start_response(status_response(status), [("Content-Type", ctype), (ORIG_BASE_HEADER, base)])
        return rbody
    except urllib2.URLError, e:
        if e.code == 403:
            raise MoinMustAuthenticateError(url=request.get_full_url(),target=wiki_id)
        if e.code == 404:
            raise MoinNotFoundError(fronturl=request_uri(environ),backurl=url)
        else:
            raise UnexpectedResponseError(url=url,code=e.code,error=str(e))

def fill_page_edit_form(page, wiki_id, base, opener):
    url = absolutize(page, base)
    request = urllib2.Request(url+"?action=edit&editor=text")
    try:
        with closing(opener.open(request)) as resp:
            doc = htmlparse(resp)

    except urllib2.URLError,e:
        # Comment concerning the behavior of MoinMoin.  If an attempt is made to edit a page 
        # and the user is not authenticated, you will either get a 403 or 404 error depending
        # on whether or not the page being edited exists or not.   If it doesn't exist, 
        # MoinMoin sends back a 404 which is misleading.   We raise MoinMustAuthenticateError
        # to signal the error wrapper to issue a 401 back to the client
        if e.code == 403 or e.code == 404:
            raise MoinMustAuthenticateError(url=request.get_full_url(),target=wiki_id)
        else:
            raise UnexpectedResponseError(url=request.get_full_url(),code=e.code,error=str(e))
        
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
    request = urllib2.Request(url + '?action=AttachFile')
    try:
        with closing(opener.open(request)) as resp:
            doc = htmlparse(resp)

    except urllib2.URLError,e:
        # Comment concerning the behavior of MoinMoin.  If an attempt is made to post to a page 
        # and the user is not authenticated, you will either get a 403 or 404 error depending
        # on whether or not the page being edited exists or not.   If it doesn't exist, 
        # MoinMoin sends back a 404 which is misleading.   We raise MoinMustAuthenticateError
        # to signal the error wrapper to issue a 401 back to the client
        if e.code == 403 or e.code == 404:
            raise MoinMustAuthenticateError(url=request.get_full_url(),target=wiki_id)
        else:
            raise UnexpectedResponse(url=request.get_full_url(),code=e.code,error=str(e))

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

@method_dispatcher(SERVICE_ID, DEFAULT_MOUNT)
def dispatcher():
    __doc__ = SAMPLE_QUERIES_DOC
    return


#def akara_xslt(body, ctype, **params):
@dispatcher.method("HEAD")
@errorwrapped
def head_page(environ, start_response):
    rbody = _get_page(environ, start_response)
    return ''


@dispatcher.method("GET")
@errorwrapped
def get_page(environ, start_response):
    return _get_page(environ, start_response)


@dispatcher.method("PUT")
@errorwrapped
def put_page(environ, start_response):
    '''
    '''
    wiki_id, base, opener = target(environ)
    page = environ['PATH_INFO'].lstrip('/')
    check_auth(environ, start_response, base, opener)

    ctype = environ.get('CONTENT_TYPE', 'application/unknown')
    temp_fpath = read_http_body_to_temp(environ, start_response)
    form_vars = fill_page_edit_form(page, wiki_id, base, opener)
    form_vars["savetext"] = open(temp_fpath, "r").read()

    url = absolutize(page, base)
    data = urllib.urlencode(form_vars)
    request = urllib2.Request(url, data)
    try:
        with closing(opener.open(request)) as resp:
            doc = htmlparse(resp)
    except urllib2.URLError,e:
        raise UnexpectedResponseError(url=url,code=e.code,error=str(e))

    msg = 'Page updated OK: ' + url
    #response.add_header("Content-Length", str(len(msg)))
    start_response(status_response(httplib.CREATED), [("Content-Type", "text/plain"), ("Content-Location", url), (ORIG_BASE_HEADER, base)])
    return [msg]


@dispatcher.method("POST")
@errorwrapped
def post_page(environ, start_response):
    '''
    Attachments use URI path params
    (for a bit of discussion see http://groups.google.com/group/comp.lang.python/browse_thread/thread/4662d41aca276d99)
    '''
    #ctype = environ.get('CONTENT_TYPE', 'application/unknown')

    wiki_id, base, opener = target(environ)
    check_auth(environ, start_response, base, opener)

    page = environ['PATH_INFO'].lstrip('/')
    page, chaff, attachment = page.partition(';attachment=')
#    print >> sys.stderr, page, attachment
    #now = datetime.now().isoformat()
    #Unfortunately because urllib2's data dicts don't give an option for limiting read length, must read into memory and wrap
    #content = StringIO(environ['wsgi.input'].read(clen))
    temp_fpath = read_http_body_to_temp(environ, start_response)
    form_vars = fill_attachment_form(page, attachment, wiki_id, base, opener)
    form_vars["file"] = open(temp_fpath, "rb")

    url = absolutize(page, base)
    #print >> sys.stderr, url, temp_fpath
    #data = urllib.urlencode(form_vars)
    request = urllib2.Request(url, form_vars)
    try:
        with closing(opener.open(request)) as resp:
            doc = htmlparse(resp)
            #amara.xml_write(doc, stream=sys.stderr, indent=True)
    except urllib2.URLError,e:
        if e.code == 404:
            raise MoinNotFoundError(fronturl=request_uri(environ), backurl=url)
        else:
            raise UnexpectedResponseError(url=url,code=e.code,error=str(e))

    form_vars["file"].close()
    os.remove(temp_fpath)

    msg = 'Attachment updated OK: %s\n'%(url)

    #response.add_header("Content-Length", str(len(msg)))
    start_response(status_response(httplib.CREATED), [("Content-Type", "text/plain"), ("Content-Location", url), (ORIG_BASE_HEADER, base)])
    return msg

CHUNKLEN = 4096
def read_http_body_to_temp(environ, start_response):
    '''
    Handle the reading of a file from an HTTP message body (file pointer from wsgi.input)
    in chunks to a temporary file
    Returns the file path of the resulting temp file
    '''
    clen = int(environ.get('CONTENT_LENGTH', None))
    if not clen:
        raise ContentLengthRequiredError()
    http_body = environ['wsgi.input']
    temp = tempfile.mkstemp(suffix=".dat")
    while clen != 0:
        chunk_len = min(CHUNKLEN, clen)
        data = http_body.read(chunk_len)
        if data:
            #assert chunk_len == os.write(temp[0], data)
            written = os.write(temp[0], data)
            #print >> sys.stderr, "Bytes written to file in this chunk", written
            clen -= len(data)
        else:
            clen = 0
    os.fsync(temp[0]) #is this needed with the close below?
    os.close(temp[0])
    return temp[1]

