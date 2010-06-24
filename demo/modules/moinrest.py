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

http://purl.org/akara/services/demo/collection (moin)
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

    Get a page's history:
    curl http://localhost:8880/moin/xml3k/FrontPage;history
'''

__doc__ += SAMPLE_QUERIES_DOC

# Standard library imports
import sys     # Used only from sys.stderr
import os
import cgi
import httplib, urllib, urllib2
from string import Template
from cStringIO import StringIO
import tempfile
from contextlib import closing
from wsgiref.util import shift_path_info, request_uri
from functools import wraps
from itertools import dropwhile

# Amara Imports
import amara
from amara import bindery
from amara.lib.util import first_item
from amara.lib.iri import absolutize, relativize
from amara.writers.struct import structencoder, E, NS, ROOT, RAW
from amara.bindery.html import parse as htmlparse
from amara.bindery.model import examplotron_model, generate_metadata
from amara.lib.iri import split_fragment, relativize, absolutize, split_uri_ref, split_authority, unsplit_uri_ref
from amara.lib.iri import split_uri_ref, unsplit_uri_ref, split_authority, absolutize
#from amara import inputsource

# Akara Imports
from akara.util import multipart_post_handler, wsgibase, http_method_handler
from akara.services import method_dispatcher
from akara.util import status_response, read_http_body_to_temp
from akara.util import BadTargetError, HTTPAuthorizationError, MoinAuthorizationError, UnexpectedResponseError, MoinMustAuthenticateError, MoinNotFoundError, ContentLengthRequiredError
import akara.util.moin as moin
from akara import response
from akara import logger

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

SERVICE_ID = 'http://purl.org/xml3k/akara/services/demo/moinrest'
DEFAULT_MOUNT = 'moin'

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
#                          moin_error_handler
# ======================================================================
# This error handling function is what actually runs all of the WSGI
# functions implemented by the modules. It catches MoinRest specific exceptions 
# and produces appropriate error responses as needed.
#
# The reason for putting this functionality in a single function is to avoid a lot
# excessive code duplication between different HTTP methods.  For example,
# the handlers for each HTTP method are going to have to deal with
# many of the same error conditions, faults, and responses.  Centralizing
# the handling makes it possible to deal all of the errors in just one place.

def moin_error_wrapper(wsgiapp):
    @wraps(wsgiapp)
    def handler(environ, start_response):
        status_info = {}          # Dictionary of collected status information

        # Replacement for the WSGI start_response function.  This merely
        # collects response data in a dictionary for later use if no errors occur
        def local_start_response(status, headers):
            status_info['status'] = status
            status_info['headers'] = headers

        # Try to run the supplied WSGI handler
        try:
            body = wsgiapp(environ, local_start_response)
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

    return handler


# ----------------------------------------------------------------------
#                   Support functions used by handlers
# ----------------------------------------------------------------------

# Utility function for generating status rsponses for WSGI
def status_response(code):
    return '%i %s'%(code, httplib.responses[code])


# Returns information about the target wiki. Raises BadTargetError if nothing
# is known about the target name
def target(environ):
    wiki_id = shift_path_info(environ)
    full_incoming_request = request_uri(environ)
    original_page = absolutize(environ['PATH_INFO'], TARGET_WIKIS[wiki_id])
    #relative_to_wrapped = relativize(, full_incoming_request)
    wrapped_wiki_base = full_incoming_request[:-len(environ['PATH_INFO'])]
    if wiki_id not in TARGET_WIKIS:
        raise BadTargetError(fronturl=request_uri(environ), target=wiki_id)
    return wiki_id, TARGET_WIKIS[wiki_id], TARGET_WIKI_OPENERS.get(wiki_id), original_page, wrapped_wiki_base


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


def fill_page_edit_form(page, wiki_id, base, opener):
    url = absolutize(page, base)
    request = urllib2.Request(url+"?action=edit&editor=text")
    try:
        with closing(opener.open(request)) as resp:
            x = resp.read(); resp = x
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

    try:
        form = doc.html.body.xml_select(u'.//*[@id="editor"]')[0]
    except Exception as ex:
        #XXX There seems to be a crazy XPath bug that only manifests here
        #Use non-XPath as a hack-around :(
        #open('/tmp/foo.html', 'w').write(x)
        logger.debug('Stupid XPath bug.  Working around... ' + repr(ex))
        from amara.lib.util import element_subtree_iter
        form = [ e for e in element_subtree_iter(doc.html.body) if e.xml_attributes.get(u'id') == u'editor' ][0]
        #logger.debug('GRIPPO ' + repr(doc.html.body.xml_select(u'.//form')))
        #logger.debug('GRIPPO ' + repr((form.xml_namespace, form.xml_local, form.xml_qname, form.xml_name, dict(form.xml_attributes))))
        form_vars = {}
        #form / fieldset / input
        form_vars["action"] = [ e for e in element_subtree_iter(form) if e.xml_attributes.get(u'name') == u'action' ][0].xml_attributes[u'value']
        form_vars["rev"] = [ e for e in element_subtree_iter(form) if e.xml_attributes.get(u'name') == u'rev' ][0].xml_attributes[u'value']
        form_vars["ticket"] = [ e for e in element_subtree_iter(form) if e.xml_attributes.get(u'name') == u'ticket' ][0].xml_attributes[u'value']
        form_vars["editor"] = [ e for e in element_subtree_iter(form) if e.xml_attributes.get(u'name') == u'editor' ][0].xml_attributes[u'value']
        #logger.debug('Edit form vars ' + repr(form_vars))
        return form_vars
    form_vars = {}
    #form / fieldset / input
    form_vars["action"] = unicode(form.xml_select(u'string(*/*[@name="action"]/@value)'))
    form_vars["rev"] = unicode(form.xml_select(u'string(*/*[@name="rev"]/@value)'))
    form_vars["ticket"] = unicode(form.xml_select(u'string(*/*[@name="ticket"]/@value)'))
    form_vars["editor"] = unicode(form.xml_select(u'string(*/*[@name="editor"]/@value)'))
    #logger.debug('Edit form vars ' + repr(form_vars))
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
    #Was called rename in 1.8.x, target in 1.9.x
    form_vars["rename"] = unicode(attachment)
    form_vars["target"] = unicode(attachment)
    #FIXME: parameterize
    form_vars["overwrite"] = u'1'
    form_vars["action"] = unicode(form.xml_select(u'string(*/*[@name="action"]/@value)'))
    form_vars["do"] = unicode(form.xml_select(u'string(*/*[@name="do"]/@value)'))
    form_vars["ticket"] = unicode(form.xml_select(u'string(*/*[@name="ticket"]/@value)'))
    form_vars["submit"] = unicode(form.xml_select(u'string(*/*[@type="submit"]/@value)'))
    #pprint.pprint(form_vars)
    return form_vars


def scrape_page_history(page, base, opener):
    url = absolutize(page, base)
    request = urllib2.Request(url+"?action=info")
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

    info = []
    try:
        table = doc.html.body.xml_select(u'.//table[@id="dbw.table"]')[0]
    except Exception as ex:
        #XXX Seems to be a crazy XPath bug that only manifests here
        #Use non-XPath as a hack-around :(
        logger.debug('Stupid XPath bug.  Working around... ' + repr(ex))
        from amara.lib.util import element_subtree_iter
        table = [ e for e in element_subtree_iter(doc.html.body) if e.xml_attributes.get(u'id') == u'dbw.table' ]
        if not table:
            #"Revision History... No log entries found." i.e. page not even yet created
            return info
    info = [
        dict(rev=tr.td[0], date=tr.td[1], editor=tr.td[4])
        for tr in table[0].xml_select(u'.//tr[td[@class="column1"]]')
        #for tr in table.tbody.tr if tr.xml_select(u'td[@class="column1"]')
    ]
    return info


# ----------------------------------------------------------------------
#                       HTTP Method Handlers
# ----------------------------------------------------------------------
# The following functions implement versions of the various HTTP methods 
# (GET, HEAD, POST, PUT).  Each method is actually implemented as a
# a pair of functions.  One is a private implementation (e.g., _get_page).  
# The other function is a wrapper that encloses each handler with the error 
# handling function above (moin_error_handler).   Again, this is to avoid
# excessive duplication of error handling code.

@method_dispatcher(SERVICE_ID, DEFAULT_MOUNT, wsgi_wrapper=moin_error_wrapper)
def dispatcher():
    __doc__ = SAMPLE_QUERIES_DOC
    return

@dispatcher.method("GET")
def get_page(environ, start_response):
    wiki_id, base, opener, original_page, wrapped_wiki_base = target(environ)
    page = environ['PATH_INFO'].lstrip('/')
    check_auth(environ, start_response, base, opener)
    upstream_handler = None
    status = httplib.OK
    params = cgi.parse_qs(environ['QUERY_STRING'])
    #Note: probably a better solution here: http://code.google.com/p/mimeparse/
    accepted_imts = environ.get('HTTP_ACCEPT', '').split(',')
    #logger.debug('accepted_imts: ' + repr(accepted_imts))
    imt = first_item(dropwhile(lambda x: '*' in x, accepted_imts))
    #logger.debug('imt: ' + repr(imt))
    params_for_moin = {}
    if 'rev' in params:
        #XXX: Not compatible with search
        #params_for_moin = {'rev' : params['rev'][0], 'action': 'recall'}
        params_for_moin = {'rev' : params['rev'][0]}
    if 'search' in params:
        searchq = params['search'][0]
        query = urllib.urlencode({'value' : searchq, 'action': 'fullsearch', 'context': '180', 'fullsearch': 'Text'})
        #?action=fullsearch&context=180&value=foo&=Text
        url = absolutize('?'+query, base)
        request = urllib2.Request(url)
        ctype = moin.RDF_IMT
    #elif 'action' in params and params['action'][0] == 'recall':
    elif moin.HTML_IMT in environ.get('HTTP_ACCEPT', ''):
        params = urllib.urlencode(params_for_moin)
        url = absolutize(page+'?'+params, base)
        request = urllib2.Request(url)
        ctype = moin.HTML_IMT
    elif moin.RDF_IMT in environ.get('HTTP_ACCEPT', ''):
        #FIXME: Make unique flag optional
        #url = base + '/RecentChanges?action=rss_rc&unique=1&ddiffs=1'
        url = absolutize('RecentChanges?action=rss_rc&unique=1&ddiffs=1', base)
        #print >> sys.stderr, (url, base, '/RecentChanges?action=rss_rc&unique=1&ddiffs=1', )
        request = urllib2.Request(url)
        ctype = moin.RDF_IMT
    elif moin.ATTACHMENTS_IMT in environ.get('HTTP_ACCEPT', ''):
        url = absolutize(page + '?action=AttachFile', base)
        request = urllib2.Request(url)
        ctype = moin.ATTACHMENTS_IMT
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
            output = structencoder(indent=u"yes")
            output.feed(
            ROOT(
                E((u'attachments'),
                    (E(u'attachment', {u'href': unicode(t)}) for t in targets)
                )
            ))
            return output.read(), ctype
    #Notes on use of URI parameters - http://markmail.org/message/gw6xbbvx4st6bksw
    elif ';attachment=' in page:
        page, attachment = page.split(';attachment=', 1)
        url = absolutize(page + '?action=AttachFile&do=get&target=' + attachment, base)
        request = urllib2.Request(url)
        def upstream_handler():
            with closing(opener.open(request)) as resp:
                rbody = resp.read()
            return rbody, dict(resp.info())['content-type']
    #
    elif ';history' in page:
        ctype = moin.XML_IMT
        page, discard = page.split(';history', 1)
        def upstream_handler():
            revs = scrape_page_history(page, base, opener)
            output = structencoder(indent=u"yes")
            output.feed(
            ROOT(
                E((u'history'),
                    (E(u'rev', {u'id': unicode(r['rev']), u'editor': unicode(r['editor']), u'date': unicode(r['date']).replace(' ', 'T')}) for r in revs)
                )
            ))
            return output.read(), ctype
    elif imt:
        params_for_moin.update({'mimetype': imt})
        params = urllib.urlencode(params_for_moin)
        url = absolutize(page, base) + '?' + params
        request = urllib2.Request(url)
        ctype = moin.DOCBOOK_IMT
    else:
        params_for_moin.update({'action': 'raw'})
        params = urllib.urlencode(params_for_moin)
        url = absolutize(page, base) + '?' + params
        request = urllib2.Request(url)
        ctype = moin.WIKITEXT_IMT
    try:
        if upstream_handler:
            rbody, ctype = upstream_handler()
        else:
            with closing(opener.open(request)) as resp:
                rbody = resp.read()
        
        #headers = {moin.ORIG_BASE_HEADER: base}
        #moin_base = absolutize(wiki_id, base)
        moin_base_info = base + ' ' + wrapped_wiki_base + ' ' + original_page
        start_response(status_response(status), [("Content-Type", ctype), (moin.ORIG_BASE_HEADER, moin_base_info)])
        return rbody
    except urllib2.URLError, e:
        if e.code == 401:
            raise HTTPAuthorizationError(url=request.get_full_url())
        if e.code == 403:
            raise MoinMustAuthenticateError(url=request.get_full_url(),target=wiki_id)
        if e.code == 404:
            raise MoinNotFoundError(fronturl=request_uri(environ),backurl=url)
        else:
            raise UnexpectedResponseError(url=url,code=e.code,error=str(e))


# PUT handler
@dispatcher.method("PUT")
def _put_page(environ, start_response):
    '''
    '''
    wiki_id, base, opener, original_page, wrapped_wiki_base = target(environ)
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
        logger.debug('Prior to urllib2.opener')
        with closing(opener.open(request)) as resp:
            logger.debug('Return from urllib2.opener')
            doc = htmlparse(resp)
            logger.debug('HTML parse complete post urllib2.opener')
    except urllib2.URLError,e:
        raise UnexpectedResponseError(url=url,code=e.code,error=str(e))

    msg = 'Page updated OK: ' + url
    #response.add_header("Content-Length", str(len(msg)))
    start_response(status_response(httplib.CREATED), [("Content-Type", "text/plain"), ("Content-Location", url), (moin.ORIG_BASE_HEADER, base)])
    return [msg]


# POST handler
@dispatcher.method("POST")
def post_page(environ, start_response):
    '''
    Attachments use URI path params
    (for a bit of discussion see http://groups.google.com/group/comp.lang.python/browse_thread/thread/4662d41aca276d99)
    '''
    #ctype = environ.get('CONTENT_TYPE', 'application/unknown')

    wiki_id, base, opener, original_page, wrapped_wiki_base = target(environ)
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
            #logger.debug('POST for attachment page response... ' + doc.xml_encode())
    except urllib2.URLError,e:
        if e.code == 404:
            raise MoinNotFoundError(fronturl=request_uri(environ), backurl=url)
        else:
            raise UnexpectedResponseError(url=url,code=e.code,error=str(e))

    form_vars["file"].close()
    os.remove(temp_fpath)

    msg = 'Attachment updated OK: %s\n'%(url)

    #response.add_header("Content-Length", str(len(msg)))
    start_response(status_response(httplib.CREATED), [("Content-Type", "text/plain"), ("Content-Location", url), (moin.ORIG_BASE_HEADER, base)])
    return msg

