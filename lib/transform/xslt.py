"""
WSGI middleware that applies XSLT to an XML response body if needed

See also:
  http://4suite.org/docs/CoreManual.xml#id1964053292
  http://trac.defuze.org/wiki/Picket
  http://projects.dowski.com/view/buffetxslt
  
"""

import re, sys, time
from cStringIO import StringIO
from itertools import *
from xml import sax
from util import geturl

from Ft.Xml import Sax, InputSource, CreateInputSource
from Ft.Xml.Xslt import Processor
from Ft.Lib import Uri

USER_AGENT_REGEXEN = [
  '.*MSIE 5.5.*',
  '.*MSIE 6.0.*',
  '.*MSIE 7.0.*',
  '.*Gecko/2005.*',
  '.*Gecko/2006.*',
  '.*Gecko/2007.*',
  '.*Gecko/2008.*',
  '.*Opera/9.*',
  '.*AppleWebKit/31.*',
  '.*AppleWebKit/4.*',
]

USER_AGENT_REGEXEN = [ re.compile(regex) for regex in USER_AGENT_REGEXEN ]
WSGI_NS = u'http://www.wsgi.org/'

MTYPE_PAT = re.compile('.*/.*xml.*')


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
            self.parser.setProperty(Sax.PROPERTY_YIELD_RESULT, self.xslt_pi)
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
                    self.parser.setProperty(Sax.PROPERTY_YIELD_RESULT, self.xslt_pi)
        return

ACTIVE_KEY = 'amara.transform.active'
FORCE_SERVER_SIDE_KEY = 'akara.transform.force-server-side'
CACHEABLE_KEY = 'wsgixml.applyxslt.cacheable'

class applyxslt(object):
    """
    Middleware to conditionally apply XSLT on the server side.
    
    It checks for XSLT transform capability in the client and performs any
    specified transform on the server side if needed.  You can force it to
    run on the server side too by setting
    environ['akara.transform.force-server-side'] to True.
    
    Transforms are specified either through a stylesheet PI or as
    environ['akara.transform.xslt'] which can be a single XSLT input source
    or a list of same.
    
    You can also specify an environ['akara.transform.xsltparams'] environ entry
    with top-level parameters.  Remember that you can use
    amara.xpath.util.parameterize() to prep these
    """
    def __init__(self, app, check_pis=True, use_wsgi_env=True, stock_xslt_params=None,
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
        send_browser_xslt = any( ua_pat.match(client_ua) 
                                 for ua_pat in USER_AGENT_REGEXEN )

        #We'll hack a bit for dealing with Python's imperfect nested scopes.
        response_params = []
        def start_response_wrapper(status, response_headers, exc_info=None):
            #Assume response does not use XSLT; do not activate middleware
            environ[ACTIVE_KEY] = False
            #Check for response content type to see whether it is XML
            for name, value in response_headers:
                #content-type value is a media type, defined as
                #media-type = type "/" subtype *( ";" parameter )
                media_type = value.split(';')[0]
                if ( name.lower() == 'content-type'
                     and MTYPE_PAT.match(media_type)):
                     #.endswith('/xml')
                     #      or media_type.find('/xml+') != -1 )):
                    environ[ACTIVE_KEY] = True
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
        force_server_side = environ.get(FORCE_SERVER_SIDE_KEY, False)
        send_browser_xslt = send_browser_xslt and not force_server_side
        #import pprint; pprint.pprint(environ)

        #This function processes each chunk of output (simple string) from
        #the app, returning The modified chunk to be passed on to the server
        def next_response_block(response_iter):
            if send_browser_xslt or not environ['wsgixml.applyxslt.active']:
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
            if not send_browser_xslt and environ[ACTIVE_KEY]:
                use_pi = False
                if force_server_side and force_server_side != True:
                    #True is a special flag meaning "don't delegate to the browser but still check for XSLT PIs"
                    xslt = force_server_side
                else:
                    #Check for a Stylesheet PI
                    parser = Sax.CreateParser()
                    parser.setFeature(Sax.FEATURE_GENERATOR, True)
                    handler = find_xslt_pis(parser)
                    pi_iter = parser.parse(CreateInputSource(response))
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
                    if xslt in self.processor_cache:
                        processor = self.processor_cache[xslt]
                        #Any transform would have already been loaded
                        use_pi = False
                        print >> sys.stderr, 'Using cached processor instance for transform', xslt
                        #environ['wsgi.errors'].write('Using cached processor instance for transform %s\n'%xslt)
                    else:
                        print >> sys.stderr, 'Creating new processor instance for transform', xslt
                        #environ['wsgi.errors'].write('Creating new processor instance for transform %s\n'%xslt)
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
                    if environ.get(CACHEABLE_KEY):
                        self.path_cache[path] = imt, content
                    response_headers.append(('content-type', imt))
                    start_response(status, response_headers, exc_info)
                    end = time.time()
                    print >> sys.stderr, '%s: elapsed time: %0.3f\n'%(xslt, end-start)
                    #environ['wsgi.errors'].write('%s: elapsed time: %0.3f\n'%(xslt, end-start))
                    return content
                    
            #If it reaches this point, no XSLT was applied.
            return

        return iterwrapper(iterable, next_response_block)


#if __name__ == '__main__':
    
