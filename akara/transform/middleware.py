# -*- coding: utf-8 -*-
"""
Akara transform middleware (XSLT and more)

XSLT:

xslt_transform_manager manages a pool of Amara XSLT processor instances
to dispatch requests rapidly.

Note on extensions:

If you wish to use any XPath or XSLT extensions put the extension modules
into a directory and indicate that directory in your server config such
that it's made available as environ['http://purl.org/xml3k/akara/transform/extensions'].
An example:

-- % --
... = '/usr/share/amara/extensions'
-- % --

For more on Amara XSLT extensions See <http://4suite.org/docs/CoreManual.xml> <- FIXME: update
"""

# Used for locking the cache of XSLT processors
import thread
# Used to check whether or not an XSLT stylesheet has been modified
from stat import ST_MTIME
from os import stat

import amara
from amara.lib import iri
from amara.lib import inputsource
from amara.xpath.util import parameterize
from amara.xslt.processor import processor
from amara import sax

USER_AGENT_REGEXEN = [
'.*MSIE 5.5.*',
'.*MSIE 6.0.*',
'.*MSIE 7.0.*',
'.*Gecko/2005.*',
'.*Gecko/2006.*',
'.*Opera/9.*',
'.*AppleWebKit/31.*',
'.*AppleWebKit/4.*',
]

USER_AGENT_REGEXEN = [ re.compile(regex) for regex in USER_AGENT_REGEXEN ]
WSGI_NS = u'http://www.wsgi.org/'

MTYPE_PAT = re.compile('.*/.*xml.*')

#We use processor pooling, but we eventually want to get it to the point where we can just
#cache compiled stylesheets

#FIXME: does not yet handle extensions

DUMMY_SOURCE_DOC_URI = "http://purl.org/xml3k/akara/transform/source-doc"

class processor_info:
    def __init__(self, lock, last_modified, instance):
        #Even if you're using multiple processes rather than threads use locking, just to be safe
        self.lock = lock
        self.last_modified = last_modified
        self.instance = {}

class processor_pool:
    """
    A hash table (LRU trimmed) that caches from XSLT transform tuples to prepared
    processor instances
    """
    def __init__(self):
        #Even if you're using multiple processes rather than threads use locking, just to be safe
        self._main_lock = thread.allocate_lock()
        self._granular_locks = {}
        self._processors = {}

    def get_processor(self, transform_hash, ext_functions=None, ext_elements=None):
        try:
            # First make sure we avoid race conditions...
            self._main_lock.acquire()
            if transform_hash not in self._granular_locks:
                self._granular_locks[transform_hash] = thread.allocate_lock()
        finally:
            self._main_lock.release()

        proc = None
        try:
            self._granular_locks[transform_hash].acquire()
            # If we do not have that stylesheet yet in the pool, let's add it
            if not self._processors.has_key(transform_hash):
                processor = Processor()
                self._processors[transform_hash] = processor_info(
                    thread.allocate_lock(), stat(transform_hash)[ST_MTIME], processor
                )
                for (ns, local), func in ext_functions.items():
                    processor.registerExtensionFunction(ns, local, func)
                for (ns, local), elem in ext_elements.items():
                    processor.registerExtensionElement(ns, local, elem)

                self._processors[transform_hash].instance.append_transform(iri.os_path_to_uri(transform_hash))
            # If the stylesheet has been modified, reload it
            elif stat(transform_hash)[ST_MTIME] != self._processors[transform_hash].last_modified:
                self._processors[transform_hash].instance.reset()
                self._processors[transform_hash].last_modified = stat(transform_hash)[ST_MTIME]
                self._processors[transform_hash].instance.append_transform(iri.os_path_to_uri(transform_hash))

            # now we can lock the processor...
            self._processors[transform_hash]['lock'].acquire()
            proc = self._processors[transform_hash].instance
        finally:
            self._granular_locks[transform_hash].release()
        # ... and return it
        return proc

    def release_processor(self, transform_hash):
        try:
            if self._processors[transform_hash]['lock'].locked():
               self._processors[transform_hash]['lock'].release()
        except: pass


class find_xslt_pis(sax.ContentHandler):
    def __init__(self, parser):
        parser.setContentHandler(self)
        self.parser = parser
        return

    def startDocument(self):
        self.ecount = 0
        self.xslt_pi = None

    def startElementNS(self, name, qname, attribs):
        self.ecount += 1
        if self.ecount == 2:
            #We're now within the doc proper, so we're done
            self.parser.setProperty(sax.PROPERTY_YIELD_RESULT, self.xslt_pi)
        return
            
    def processingInstruction(self, target, data):
        if target == u'xml-stylesheet':
            data = data.split()
            pseudo_attrs = {}
            for d in data:
                seg = d.split('=')
                if len(seg) == 2:
                    pseudo_attrs[seg[0]] = seg[1][1:-1]

            # PI must have both href, type pseudo-attributes;
            # type pseudo-attr must match valid XSLT types;
            # media pseudo-attr must match preferred media
            # (which can be None)
            if (pseudo_attrs.has_key('href')
                and pseudo_attrs.has_key('type')
                and pseudo_attrs['type'] in Processor.XSLT_IMT):
                    self.xslt_pi = pseudo_attrs['href']
                    self.parser.setProperty(sax.PROPERTY_YIELD_RESULT, self.xslt_pi)
        return


ACTIVE_FLAG = 'http://purl.org/xml3k/akara/transform/active'
SERVER_SIDE_FLAG = 'http://purl.org/xml3k/akara/transform/force-server-side'
CACHEABLE_FLAG = 'http://purl.org/xml3k/akara/transform/cacheable'

class xslt_transform_manager(object):
    """
    Middleware for XSLT transform processing.
    
    Also optionally checks for XSLT transform capability in the client and
    performs the transform on the server side if one is required, and the
    client can't do it
    """
    def __init__(self, app, use_wsgi_env=True, stock_xslt_params=None,
                 ext_modules=None):
        """
        use_wsgi_env - Optional bool determining whether to make the
            WSGI environment available to the XSLT as top level parameter
            overrides (e.g. wsgi:SCRIPT_NAME and wsgi:wsgi.url_scheme).
            Only passes on values it can handle (UTF-8 strings, Unicode,
            numbers, boolean, lists of "nodes").  Default to True
        stock_xslt_params - optional dict of dicts to also pass along as XSLT
            params.  The outer dict is onf the form: {<namespace>: <inner-dict>}
            And the inner dicts are of the form {pname: pvalue}.  The keys
            (pname) may be given as unicode objects if they have no namespace,
            or as (uri, localname) tuples if they do.  The values are
            (UTF-8 strings, Unicode, numbers, boolean, lists of "nodes").
            This is usually used for passing configuration info into XSLT
        ext_modules - Optional list of modules with XPath and XSLT extensions
        """
        #Set-up phase
        self.wrapped_app = app
        self.use_wsgi_env = use_wsgi_env
        self.stock_xslt_params = stock_xslt_params or {}
        self.ext_modules = ext_modules or []
        self.processor_cache = {}
        self.path_cache = {}
        return

    def __call__(self, environ, start_response):
        #Guess whether the client supports XML+XSLT?
        #See: http://copia.ogbuji.net/blog/2006-08-26/LazyWeb_Ho
        client_ua = environ.get('HTTP_USER_AGENT', '')
        path = environ['PATH_INFO']
        send_browser_xslt = True in [ ua_pat.match(client_ua) is not None
                                for ua_pat in USER_AGENT_REGEXEN ]

        #We'll hack a bit for dealing with Python's imperfect nested scopes.
        response_params = []
        def start_response_wrapper(status, response_headers, exc_info=None):
            #Assume response does not use XSLT; do not activate middleware
            environ[ACTIVE_FLAG] = False
            #Check for response content type to see whether it is XML
            for name, value in response_headers:
                #content-type value is a media type, defined as
                #media-type = type "/" subtype *( ";" parameter )
                media_type = value.split(';')[0]
                if ( name.lower() == 'content-type'
                     and MTYPE_PAT.match(media_type)):
                     #.endswith('/xml')
                     #      or media_type.find('/xml+') != -1 )):
                    environ[ACTIVE_FLAG] = True
            response_params.extend([status, response_headers, exc_info])
            #Replace any write() callable with a dummy that gives an error
            #The idea is to refuse support for apps that use write()
            def dummy_write(data):
                raise RuntimeError('applyxslt does not support the deprecated write() callable in WSGI apps')
            return dummy_write

        #Get the iterator from the application that will yield response
        #body fragments
        iterable = self.wrapped_app(environ, start_response_wrapper)
        (status, response_headers, exc_info) = response_params
        force_server_side = environ.get(SERVER_SIDE_FLAG, False)
        send_browser_xslt = send_browser_xslt and not force_server_side
        #import pprint; pprint.pprint(environ)

        #This function processes each chunk of output (simple string) from
        #the app, returning The modified chunk to be passed on to the server
        def next_response_block(response_iter):
            if send_browser_xslt or not environ[ACTIVE_FLAG]:
                #The client can handle XSLT, or it's not an XML source doc,
                #so nothing for this middleware to do
                start_response(status, response_headers, exc_info)
                for block in response_iter.next():
                    yield block
            elif path in self.path_cache:
                print >> sys.stderr, 'Using cached result for path', path
                imt, content = self.path_cache[path]
                response_headers.append(('content-type', imt))
                start_response(status, response_headers, exc_info)
                yield content
            else:
                yield produce_final_output(''.join(response_iter))
            return  

        #After the app has finished sending its response body fragments
        #if transform is required, it's necessary to send one more chunk,
        #with the fully transformed result
        def produce_final_output(response, response_headers=response_headers):
            log = sys.stderr
            if not send_browser_xslt and environ[ACTIVE_FLAG]:
                use_pi = False
                if force_server_side and force_server_side != True:
                    #True is a special flag meaning "don't delegate to the browser but still check for XSLT PIs"
                    xslt = force_server_side
                else:
                    #Check for a Stylesheet PI
                    parser = sax.reader()
                    parser.setFeature(sax.FEATURE_GENERATOR, True)
                    handler = find_xslt_pis(parser)
                    pi_iter = parser.parse(inputsource(response))
                    try:
                        #Note: only grabs the first PI.  Consider whether we should handle multiple
                        xslt = pi_iter.next()
                    except StopIteration:
                        xslt = None
                    use_pi = True
                if xslt:
                    xslt = xslt.encode('utf-8')
                    result = StringIO()
                    #self.xslt_sources = environ.get(
                    #    'wsgixml.applyxslt.xslt_sources', {})
                    source = InputSource.DefaultFactory.fromString(
                        response, uri=get_request_url(environ))
                    params = {}
                    for ns in self.stock_xslt_params:
                        params.update(setup_xslt_params(ns, self.stock_xslt_params[ns]))
                    start = time.time()


                        processor = self.processorPool.get_processor(
                            stylesheet, self.ext_functions, self.ext_elements)
                        cherrypy.response.body = processor.run(
                            DefaultFactory.fromString(picket.document,
                                                      picket.uri),
                            topLevelParams=picket.parameters)
                        if self.default_content_type:
                            cherrypy.response.headers['Content-Type'] = self.default_content_type
                        if picket.content_type:
                            cherrypy.response.headers['Content-Type'] = picket.content_type
                    finally:
                        self.processorPool.release_processor(stylesheet)


                    if xslt in self.processor_cache:
                        processor = self.processor_cache[xslt]
                        #Any transform would have already been loaded
                        use_pi = False
                        print >> log, 'Using cached processor instance for transform', xslt
                    else:
                        print >> log, 'Creating new processor instance for transform', xslt
                        processor = Processor.Processor()
                        if self.ext_modules:
                            processor.registerExtensionModules(self.ext_modules)
                        if self.use_wsgi_env:
                            params.update(setup_xslt_params(WSGI_NS, environ))
                        #srcAsUri = OsPathToUri()
                        #if False:
                        if environ.has_key('paste.recursive.include'):
                            #paste's recursive facilities are available, to
                            #so we can get the XSLT with a middleware call
                            #rather than a full Web invocation
                            #print environ['paste.recursive.include']
                            xslt_resp = environ['paste.recursive.include'](xslt)
                            #FIXME: this should be relative to the XSLT, not XML
                            #print xslt_resp, xslt_resp.body
                            isrc = InputSource.DefaultFactory.fromString(
                                xslt_resp.body, get_request_url(environ))
                            processor.appendStylesheet(isrc)
                        else:
                            #We have to make a full Web call to get the XSLT.
                            #4Suite will do that for us in processing the PI
                            if not use_pi:
                                uri = Uri.Absolutize(xslt, get_request_url(environ))
                                isrc = InputSource.DefaultFactory.fromUri(uri)
                                processor.appendStylesheet(isrc)
                        self.processor_cache[xslt] = processor
                    processor.run(source, outputStream=result,
                                  ignorePis=not use_pi, topLevelParams=params)

                    #Strip content-length if present (needs to be
                    #recalculated by server)
                    #Also strip content-type, which will be replaced below
                    response_headers = [ (name, value)
                        for name, value in response_headers
                            if ( name.lower()
                                 not in ['content-length', 'content-type'])
                    ]
                    #Put in the updated content type
                    imt = processor.outputParams.mediaType
                    content = result.getvalue()
                    if environ.get(CACHEABLE_FLAG):
                        self.path_cache[path] = imt, content
                    response_headers.append(('content-type', imt))
                    start_response(status, response_headers, exc_info)
                    end = time.time()
                    print >> log, '%s: elapsed time: %0.3f\n'%(xslt, end-start)
                    #environ['wsgi.errors'].write('%s: elapsed time: %0.3f\n'%(xslt, end-start))
                    return content
                    
            #If it reaches this point, no XSLT was applied.
            return

        return iterwrapper(iterable, next_response_block)





class PicketFilter(BaseFilter):
    """
    A filter that applies XSLT templates to XML content
    For any published method with this filter attached, return an
    instance of the Picket class if you want an XSLT transform invoked.
    The string output of the transform becomes the Web response body
    """
    def __init__(self, default_stylesheet=None, default_content_type=None, extension_dir=None):
        self.processorPool = ProcessorPool()
        self.default_stylesheet = default_stylesheet
        self.default_content_type = default_content_type
        self.extensionDir = extension_dir #cherrypy.config.get("picket.extensionDir")
        self.ext_functions, self.ext_elements = _getExtensions(self.extensionDir)

    def before_finalize(self):
        picket = cherrypy.response.body

        if not isinstance(picket, Picket): return

        stylesheet = self.default_stylesheet

        if picket.stylesheet:
            stylesheet = picket.stylesheet

        if stylesheet is None:
            # If a stylesheet was not set, then raise an error
            raise ValueError, "Missing XSLT stylesheet"

        extDir = cherrypy.config.get("picket.extensionDir")
        if extDir != self.extensionDir:
            self.extensionDir =extDir
            self.ext_functions, self.ext_elements = _getExtensions(self.extensionDir)

        try:
            processor = self.processorPool.get_processor(
                stylesheet, self.ext_functions, self.ext_elements)
            cherrypy.response.body = processor.run(
                DefaultFactory.fromString(picket.document,
                                          picket.uri),
                topLevelParams=picket.parameters)
            if self.default_content_type:
                cherrypy.response.headers['Content-Type'] = self.default_content_type
            if picket.content_type:
                cherrypy.response.headers['Content-Type'] = picket.content_type
        finally:
            self.processorPool.release_processor(stylesheet)


def _getExtensions(extensionDirectory):
    import glob
    import os

    retval = ({}, {})
    try:
        os.path.isdir(extensionDirectory)
    except TypeError:
        return retval

    for extensionPath in glob.glob(extensionDirectory + "/*.py"):
        try:
            ns = {}
            execfile(extensionPath, ns, ns)
            retval[0].update(ns.get("ExtFunctions", {}))
            retval[1].update(ns.get("ExtElements", {}))
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            pass

    return retval








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
