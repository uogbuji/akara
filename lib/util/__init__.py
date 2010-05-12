import os
import tempfile
import httplib
import urllib, urllib2
import base64
from functools import wraps
from string import Template

from amara.lib.iri import *

from akara import logger

def status_response(code):
    return '%i %s'%(code, httplib.responses[code])

class iterwrapper:
    """
    Wraps the response body iterator from the application to meet WSGI
    requirements.
    """
    def __init__(self, wrapped, responder):
        """
        wrapped - the iterator coming from the application
        response_chunk_handler - a callable for any processing of a
            response body chunk before passing it on to the server.
        """
        self._wrapped = iter(wrapped)
        self._responder = responder(self._wrapped)
        if hasattr(wrapped, 'close'):
            self.close = self._wrapped.close

    def __iter__(self):
        return self

    def next(self):
        return self._responder.next()


def geturl(environ, relative=''):
    """
    Constructs a portable URL for your application.  If relative is omitted or '',
    Just return the current base URL. Otherwise resolve the relative portion against
    the present base and return the resulting URL.

    (Inspired by url functions in CherryPy and Pylons, and Ian Bicking's code in PEP 333)

    If you have a proxy that forwards the HOST but not the original HTTP request path
    you might have to set akara.proxy-base in environ (e.g. through .ini)  See

    http://wiki.xml3k.org/Akara/Configuration
    """

    #Manually set proxy base URI for non-well-behaved proxies, such as Apache < 1.3.33,
    #Or for cases where the proxy is not mounted at the root of a host, and thus the original
    #request path info is lost
    if environ.get('akara.proxy-base'):
        url = environ['akara.proxy-base']
        if relative: url = Uri.Absolutize(relative, url)
        return url

    url = environ['wsgi.url_scheme']+'://'
    #Apache 1.3.33 and later mod_proxy uses X-Forwarded-Host
    if environ.get('HTTP_X_FORWARDED_HOST'):
        url += environ['HTTP_X_FORWARDED_HOST']
    #Lighttpd uses X-Host
    elif environ.get('HTTP_X_HOST'):
        url += environ['HTTP_X_HOST']
    elif environ.get('HTTP_HOST'):
        url += environ['HTTP_HOST']
    else:
        url += environ['SERVER_NAME']

        if environ['wsgi.url_scheme'] == 'https':
            if environ['SERVER_PORT'] != '443':
               url += ':' + environ['SERVER_PORT']
        else:
            if environ['SERVER_PORT'] != '80':
               url += ':' + environ['SERVER_PORT']

    #Can't use the more strict Uri.PercentEncode because it would quote the '/'
    url += urllib.quote(environ.get('SCRIPT_NAME', '').rstrip('/')) + '/'
    if relative: url = Uri.Absolutize(relative, url)
    return url


def http_method_handler(method):
    '''
    A decorator maker to flag a function as suitable for a given HTTP method
    '''
    def wrap(f):
        #@wraps(f)
        #def wrapper(*args, **kwargs):
        #    return f()
        f.method = method
        return f
    return wrap


class wsgibase(object):
    def __init__(self):
        self._method_handlers = {}
        if not hasattr(self, 'dispatch'):
            self.dispatch = self.dispatch_by_lookup
        #if not hasattr(self, 'dispatch'):
        #    self.dispatch = self.dispatch_by_lookup if hasattr(self, '_methods') else self.dispatch_simply
        for obj in ( getattr(self, name) for name in dir(self) ):
            method = getattr(obj, 'method', None)
            if method:
                self._method_handlers[method] = obj
        return

    def __call__(self, environ, start_response):
        self.environ = environ
        self.start_response = start_response
        return self

    def __iter__(self):
        func = self.dispatch()
        if func is None:
            response_headers = [('Content-type','text/plain')]
            self.start_response(response(httplib.METHOD_NOT_ALLOWED), response_headers)
            yield 'HTTP method Not Allowed'
        else:
            yield func()

    def dispatch_simply(self):
        func = 'do_%s' % self.environ['REQUEST_METHOD']
        if not hasattr(self, func):
            return None
        else:
            return func

    def dispatch_by_lookup(self):
        return self._method_handlers.get(self.environ['REQUEST_METHOD'])

    def parse_fields(self):
        s = self.environ['wsgi.input'].read(int(self.environ['CONTENT_LENGTH']))
        return cgi.parse_qs(s)


def extract_auth(environ):
    '''
    Extract auth creds (HTTP basic only, for now) from the incoming request and return the
    (username, password)

    environ - The usual WSGI structure. Note: if you are using simple_service,
    in Akara services available as akara.request.environ, or perhaps passed right
    into the handler
    top - top URL to be used for this auth.
    '''
    #Useful: http://www.voidspace.org.uk/python/articles/authentication.shtml
    auth = environ.get('HTTP_AUTHORIZATION')
    if not auth: return None
    scheme, data = auth.split(None, 1)
    if scheme.lower() != 'basic':
        raise RuntimeError('Unsupported HTTP auth scheme: %s'%scheme)
    username, password = data.decode('base64').split(':', 1)
    return username, password


def copy_auth(environ, top, realm=None):
    '''
    Get auth creds (HTTP basic only, for now) from the incoming request and return an
    HTTP auth handler for urllib2.  This handler allows you to "forward" this auth to
    remote services

    environ - The usual WSGI structure. Note: if you are using simple_service,
    in Akara services available as akara.request.environ, or perhaps passed right
    into the handler
    top - top URL to be used for this auth.
    '''
    #Useful: http://www.voidspace.org.uk/python/articles/authentication.shtml
    creds = extract_auth(environ)
    if creds:
        username, password = creds
    else:
        return None
    
    password_mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
    # HTTPPasswordMgr top must omit any URL components before the host (i.e. no scheme and no auth info in the authority section)
    #(scheme, authority, path, query, fragment) = split_uri_ref(top)
    #auth, host, port = split_authority(authority)
    #auth_top_url = (host + ':' + port if port else host) + path
    #print >> sys.stderr, 'Auth creds: %s:%s (%s)'%(username, password, auth_top_url)
    logger.debug('Auth creds: %s:%s (%s)'%(username, password, top))
    
    # Not setting the realm for now, so use None
    #password_mgr.add_password(None, auth_top_url, username, password)
    password_mgr.add_password(None, top, username, password)
    #password_handler = urllib2.HTTPDigestAuthHandler(password_mgr)
    password_handler = urllib2.HTTPBasicAuthHandler(password_mgr)
    return password_handler


def header_credentials(username, password, headers=None):
    '''
    httplib2's simple HTTP auth support is great, but it doesn't recognize every case
    in which auth is needed, sometimes because of compliance issues on the remote site*
    
    Also, there are unusual cases where you want to always send the auth header,
    without first waiting for  401 challenge
    
    This function helps with these issues by unconditionally setting up httplib2 headers
    for Basic authentication
    
    >>> username = 'me@example.com'
    >>> password = 'password'
    >>> H = httplib2.Http()
    >>> auth_headers = header_credentials(username, password)
    >>> response, content = H.request(url, 'GET', headers=auth_headers)
    
    * For an example of such issues: http://pyre.posterous.com/accessing-posterous-api-in-python
    '''
    credentials = "Basic " + base64.b64encode("%s:%s"%(username, password))
    if headers:
        headers.update({ 'Authorization': credentials })
    else:
        headers = { 'Authorization': credentials }
    return headers


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

#
# ======================================================================
#                       Exceptions
# ======================================================================

# Base exception used to indicate errors.  Rather than replicating tons
# of error handling code, these errors are raised instead.  A top-level
# exception handler catches them and then generates some kind of 
# appropriate HTTP response.  Positional arguments (if any)
# are just passed to the Exception base as before.  Keyword arguments
# are saved in a local dictionary.  They will be used to pass parameters
# to the Template strings used when generating error messages.

class HttpError(Exception): 
    def __init__(self,*args,**kwargs):
        Exception.__init__(self,*args)
        self.parms = kwargs

class BadTargetError(HttpError): pass
class HTTPAuthorizationError(HttpError): pass
class MoinAuthorizationError(HttpError): pass
class UnexpectedResponseError(HttpError): pass
class MoinMustAuthenticateError(HttpError): pass
class MoinNotFoundError(HttpError): pass
class ContentLengthRequiredError(HttpError): pass

