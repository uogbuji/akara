import os

from wsgixml.applyxslt import xsltize
import pkg_resources

from cStringIO import StringIO

from Ft.Lib import Uri, UriException
from Ft.Xml import InputSource, CreateInputSource
from Ft.Xml.InputSource import InputSourceFactory
from Ft.Xml.Xslt.Processor import Processor
from Ft.Xml.Xslt.StylesheetReader import StylesheetReader
from Ft.Xml import Domlette, Parse

from pprint import pprint

class LocalTemplateResolver(Uri.FtUriResolver):

    def normalize(self, uri_ref, base_uri):
        return Uri.Absolutize(uri_ref, base_uri)

    def _orig_resolve(self, uri, baseUri=None):
        """
        This function takes a URI or a URI reference plus a base URI, produces
        a normalized URI using the normalize function if a base URI was given,
        then attempts to obtain access to an entity representing the resource
        identified by the resulting URI, returning the entity as a stream (a
        Python file-like object).

        Raises a UriException if the URI scheme is unsupported or if a stream
        could not be obtained for any reason.
        """
        if baseUri is not None:
            uri = self.normalize(uri, baseUri)
            scheme = Uri.GetScheme(uri)
        else:
            scheme = Uri.GetScheme(uri)
            # since we didn't use normalize(), we need to verify here
            if scheme not in Uri.DEFAULT_URI_SCHEMES:
                if scheme is None:
                    raise ValueError('When the URI to resolve is a relative '
                        'reference, it must be accompanied by a base URI.')
                else:
                    raise UriException(UriException.UNSUPPORTED_SCHEME,
                                       scheme=scheme,
                                       resolver=self.__class__.__name__)

        # Bypass urllib for opening local files. This means we don't get all
        # the extra metadata that urllib adds to the stream (Last-modified,
        # Content-Length, a poorly guessed Content-Type, and the URI), but
        # we also avoid its potentially time-consuming socket.gethostbyname()
        # calls, which aren't even warranted and are part of urllib's dubious
        # interpretation of RFC 1738.
        if scheme == 'file':
            path = Uri.UriToOsPath(uri, attemptAbsolute=False)
            try:
                stream = file(path, 'rb')
            except IOError, e:
                raise UriException(UriException.RESOURCE_ERROR,
                                   loc='%s (%s)' % (uri, path),
                                   uri=uri, msg=str(e))
        else:
            # urllib2.urlopen, wrapped by us, will suffice for http, ftp,
            # data and gopher
            try:
                stream = Uri.UrlOpen(uri)
            except IOError, e:
                raise UriException(UriException.RESOURCE_ERROR,
                                   uri=uri, loc=uri, msg=str(e))
        return stream

    def resolve(self, uri, base_uri=None):
        here = os.path.abspath('.')
        if uri.startswith('local:'):
            uri = uri[6:]
            resource = os.path.join(self.templates, uri)
            if os.path.exists(resource):
                return file(resource, 'rb')
            raise UriException(UriException.RESOURCE_ERROR,
                               uri=uri, loc=uri,
                               msg="The file did not exist in '%s'" % self.templates)
        elif uri.startswith('pkg:'):
            # format: package#path/to/file.xslt
            usage = 'usage: package_name#path/to/file'
            uri = uri[4:]
            package, sep, path = uri.partition('#')
            if not package or path:
                raise UriException(
                    UriException.RESOURCE_ERROR,
                    uri=uri, loc=uri,
                    msg="Invalid pkg_resources uri. \n %s" % usage
                )
            if pkg_resources.resource_exists(package, path):
                return pkg_resources.resource_stream(package, path)
            raise UriException(
                UriException.RESOURCE_ERROR,
                uri=uri, loc=uri,
                msg="'%s' was not found in the python package '%s'" % (path, package)
            )
        else:
            return self._orig_resolve(uri, base_uri)


XParams = 'xsltemplate.params'
XTemplate = 'xsltemplate.template'
XSource = 'xsltemplate.source'

class TemplateMiddleware(object):

    def __init__(self, app_conf, app, **kw):

        self.ns = unicode(app_conf.get('xsltemplate_namespace',
                                       'http://ionrock.org/ns/xsltemplate'))
        if app_conf.get('use_index_xml'):
            self.content = app_conf['use_index_xml']
        self.template_key = XTemplate
        self.params_key = XParams
        self.source_key = XSource
        self.tdir = app_conf.get('template_directory', 'templates')
        self.resolver = LocalTemplateResolver()
        self.resolver.templates = self.tdir
        self.xslt_factory = InputSourceFactory(resolver=self.resolver)
        self.rs = '%s.xslt'
        self.app = app
        if kw.get('extensions'):
            self.extensions = kw['extensions']
        else:
            self.extensions = None

    def start_response(self, status, headers, exc_info=None):
        self.status = status
        self.headers = headers
        self.exc_info = exc_info

    def __call__(self, environ, start_response):
        source = ''.join(self.app(environ, self.start_response))
        if not source and self.content:
            source = self.content
        if environ.get(self.template_key):
            xslt = environ[self.template_key]
            params = environ.get(self.params_key, {})
            source = self.do_render(source, xslt, params)
        for i, value in enumerate(self.headers):
            k, v = value
            if k.lower() == 'content-length':
                del self.headers[i]
        start_response(self.status, self.headers, self.exc_info)
        return [source]


    def get_processor(self):
        proc = Processor()
        if self.extensions:
            for ext in self.extensions:
                proc.registerExtensionFunction(*(ext))
        return proc

    def get(self, fn):
        if fn.startswith('pkg://'):
            package, sep, path = fn[6:].partition('#')
            if pkg_resources.resource_exists(package, path):
                return self.xslt_factory.fromString(pkg_resources.resource_string(package, path))
        path = Uri.OsPathToUri(os.path.join(self.tdir, fn))
        try:
            xslt = self.xslt_factory.fromUri(path)
        except UriException, e:
            xslt = self.xslt_factory.fromString(
                fn, Uri.OsPathToUri(os.path.abspath('.'))
            )
        return xslt

    def run(self, xml, xslt, params):
        proc = self.get_processor()
        xml = CreateInputSource(xml)
        xslt = self.get(xslt)
        proc.appendStylesheet(xslt)
        out = proc.run(xml, topLevelParams=params)
        del proc
        return out

    def do_render(self, xml, xslt, params):
        params['check_params'] = "Yup they are working!"
        nodes = {}
        for k, v in params.items():
            if isinstance(v, list):
                nodes[k] = v
        params = self.setup_xslt_params(params)
        for k, v in nodes.items():
            params[(self.ns, k)] = v
        return self.run(xml, xslt, params=params)

    def setup_xslt_params(self, params):
        xsltparams = dict([ ((self.ns, k), params[k])
                            for k in params
                            if xsltize(params[k]) is not None ])
        return xsltparams

class IndexXMLMiddleware(object):
    def __init__(self, app_conf, app):
        self.app_conf = app_conf
        self.content = '<?xml version="1.0"?><page />'
        if self.app_conf.get('index_xml'):
            if os.path.exists(self.app_conf['index_xml']):
                self.content = open(self.app_conf['index_xml'],'rb').read()
        self.app = app

    def start_response(self, status, headers, exc_info=None):
        self.status = status
        self.headers = headers
        self.exc_info = exc_info

    def __call__(self, environ, start_response, exc_info=None):
        c = self.app(environ, self.start_response)
        start_response(self.status, self.headers, self.exc_info)
        if c:
            return c
        return [self.content]

def set_params(environ, params):
    values = environ.get(XParams, {})
    values.update(params)
    environ[XParams] = values

def set_template(environ, template):
    environ[XTemplate] = template

def node_set(xml):
    return Parse(xml)

class TemplateConstants(object):

    def __init__(self, constants_dict, app, use_environ=True):
        self.constants = constants_dict
        self.use_environ = use_environ
        self.app = app

    def __call__(self, environ, start_response):
        if self.use_environ:
            # strip out xsltemplates params
            set_params(environ,
                       dict([ (k, v) for k, v in environ.items()
                              if not k.startswith(XParams) ]))
        set_params(environ, self.constants)
        return self.app(environ, start_response)
