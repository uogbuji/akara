from urllib import quote

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


# Requires python-magic <http://pypi.python.org/pypi/python-magic/0.1>
# >>> import magic
# >>> m = magic.Magic()
# >>> m.from_file("testdata/test.pdf")
# 'PDF document, version 1.2'
# >>> m.from_buffer(open("testdata/test.pdf").read(1024))
# 'PDF document, version 1.2'
# For MIME types
# >>> mime = magic.Magic(mime=True)
# >>> mime.from_file("testdata/test.pdf")
# 'application/pdf
try:
    import magic
    def guess_mediatype(content):
        m = magic.Magic()
        pass
except ImportError:
    pass

