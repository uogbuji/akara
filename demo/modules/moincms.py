# -*- coding: iso-8859-1 -*-
# 
"""
moin2cms.py (Akara demo)

Accesses a Moin wiki (via the moinrest module) to use as a source for a Web feed

Copyright 2009 Uche Ogbuji
This file is part of the open source Akara project,
provided under the Apache 2.0 license.
See the files LICENSE and NOTICE for details.
Project home, documentation, distributions: http://wiki.xml3k.org/Akara

@copyright: 2009 by Uche ogbuji <uche@ogbuji.net>
"""

from __future__ import with_statement
import os
import sys
import re
import pprint
import httplib
import urllib, urllib2
import datetime
import cgi
from string import Template
from cStringIO import StringIO
from functools import partial
from itertools import *
from contextlib import closing

# Requires Python 2.6 or http://code.google.com/p/json/
from amara.thirdparty import json
from dateutil.parser import parse as dateparse

import amara
from amara import bindery, _
from amara.namespaces import *
from amara.bindery.model import generate_metadata
from amara.bindery.model.examplotron import examplotron_model
from amara.writers.struct import *
from amara.bindery.html import parse as htmlparse
from amara.lib import U
from amara.lib.iri import split_fragment, relativize, absolutize
from amara.lib.date import timezone, UTC
from amara.bindery.util import dispatcher, node_handler, property_sequence_getter

from akara.util import copy_auth
from akara.util.moin import node, ORIG_BASE_HEADER, DOCBOOK_IMT, RDF_IMT, HTML_IMT, CMS_BASE, register_node_type
from akara.services import simple_service


#
# This part is partly obsolete, and is used to handle the Web/CMS component.
# It needs a bit of update for the more general Moin/CMS framework
# FIXME: It should actually probably go in a different file
#

class webcms_node(node):
    '''
    Akara CMS node, a Moin wiki page in a lightly specialized format
    from which semi-structured information can be extracted
    '''
    NODES = {}
    #Processing priority
    PRIORITY = 0
    @staticmethod
    def factory(rest_uri, relative, outputdir):
        req = urllib2.Request(rest_uri, headers={'Accept': DOCBOOK_IMT})
        resp = urllib2.urlopen(req)
        doc = bindery.parse(resp, standalone=True, model=MOIN_DOCBOOK_MODEL)
        original_wiki_base = dict(resp.info())[ORIG_BASE_HEADER]
        #self.original_wiki_base = dict(resp.info())[ORIG_BASE_HEADER]
        #amara.xml_print(self.content_cache)
        output = os.path.join(outputdir, relative)
        parent_dir = os.path.split(output)[0]
        try:
            os.makedirs(parent_dir)
        except OSError:
            pass
        metadata, first_id = metadata_dict(generate_metadata(doc))
        metadata = metadata[first_id]
        akara_type = first_item(first_item(metadata[u'ak-type']))
        #import sys; print >> sys.stderr, 'GRIPPO', akara_type.xml_value
        cls = node.NODES[akara_type.xml_value]
        instance = cls(rest_uri, relative, outputdir, cache=(doc, metadata, original_wiki_base))
        return instance

    def __init__(self, rest_uri, relative, outputdir, cache=None):
        '''
        rest_uri - the full URI to the Moin/REST wrapper for this page
        relative - the URI of this page relative to the Wiki base
        '''
        self.relative = relative
        self.rest_uri = rest_uri
        self.output = os.path.join(outputdir, relative)
        self.outputdir = outputdir
        self.cache = cache#(doc, metadata)
        return

    def load(self):
        return

    def up_to_date(self, force_update=False):
        '''
        Checks whether there needs to be an update of the CMS output file or folder
        '''
        #By default just always update
        return False
        if force_update:
            self.load()
        doc, metadata, original_wiki_base = self.cache
        entrydate = dateparse(unicode(doc.article.articleinfo.revhistory.revision.date))
        if entrydate.tzinfo == None: entrydate = entrydate.replace(tzinfo=UTC)
        if not os.access(self.output, os.R_OK):
            return False
        try:
            lastrev = dateparse(unicode(bindery.parse(self.output).entry.updated))
        except amara.ReaderError:
            return False
        if lastrev.tzinfo == None: lastrev = lastrev.replace(tzinfo=UTC)
        if (entrydate == lastrev):
            #print >> sys.stderr, 'Not updated.  Skipped...'
            return False
        return True


class folder(webcms_node):
    AKARA_TYPE = CMS_BASE + u'/folder'
    PRIORITY = 1000
    def render(self):
        #Copy attachments to dir
        req = urllib2.Request(self.rest_uri, headers={'Accept': ATTACHMENTS_IMT})
        resp = urllib2.urlopen(req)
        doc = bindery.parse(resp, model=ATTACHMENTS_MODEL)
        for attachment in (doc.attachments.attachment or ()):
            print attachment
        return

node.NODES[folder.AKARA_TYPE] = folder


class page(webcms_node):
    AKARA_TYPE = CMS_BASE + u'/page'
    def up_to_date(self, force_update=False):
        '''
        Checks whether there needs to be an update of the CMS output file or folder
        '''
        if force_update:
            self.load()
        doc, metadata, original_wiki_base = self.cache
        pagedate = dateparse(unicode(doc.article.articleinfo.revhistory.revision.date))
        #Note from the Moin FAQ: http://moinmo.in/MoinMoinQuestions/UsingTheWiki
        #"Moin internally only uses UTC, but calculates your local time according to your UserPreferences setting on page view. If you set your timezone offset to 0, you get UTC."
        #Check the behavior if using the Moin REST wrapper with user auth where that user's prefs specify TZ
        if pagedate.tzinfo == None: pagedate = pagedate.replace(tzinfo=UTC)
        if not os.access(self.output, os.R_OK):
            return False
        lastrev = datetime.datetime.utcfromtimestamp(os.stat(self.output)[stat.ST_MTIME])
        #try:
        #    published_doc = bindery.parse(self.output)
        #    datestr = first_item([ m for m in published_doc.html.head.meta if m.name==u'updated']).content
        #    lastrev = dateparse(datestr)
        #except amara.ReaderError:
        #    return False
        if lastrev.tzinfo == None: lastrev = lastrev.replace(tzinfo=UTC)
        if (lastrev > pagedate):
            return True
        return False

    def render(self):
        '''
        The typical approach is along the lines of "Style-free XSLT Style Sheets"
        * http://www.xml.com/pub/a/2000/07/26/xslt/xsltstyle.html
        * http://www.cocooncenter.org/articles/stylefree.html
        But using div/@id rather than custome elements
        '''
        doc, metadata, original_wiki_base = self.cache
        self.content = content_handlers(original_wiki_base)
        #metadata = doc.article.xml_model.generate_metadata(doc)
        #import pprint
        #pprint.pprint(resources)
        '''
         akara:type:: [[http://purl.org/dc/org/xml3k/akara/cms/folder|folder]]
         title:: A page
         template:: http://wiki.example.com/Site;attachment=foo.xslt ##Just XSLT for now.  Plan to support other templating systems soon
         link:: [[http://example.org|]] rel=...
         meta:: dc:Creator value=Uche Ogbuji
         script:: `...` ##preferably they'd only use linked scripts: [[myscript...]]
        '''
        
        page_id = doc.article.xml_nodeid
        header = doc.article.glosslist[0]
        #node_type = first_item(header.xml_select(u'glossentry[glossterm = "akara:type"]/glossdef'))
        template = unicode(first_item(header.xml_select(u'glossentry[glossterm = "template"]/glossdef'))).strip()
        template = os.path.join(self.outputdir, template)
        title = first_item(header.xml_select(u'glossentry[glossterm = "title"]/glossdef'))
        #title = resources[articleid]['title']
        #sections = dict([ (unicode(s.title), s) for s in page.article.section ])
        #print sections
         # if unicode(g.glossterm) == u'page:header' ]
        #authors = [ a
        #    for a in page.article.section.glosslist.glossentry
        #    if unicode(a.glossterm) == u'entry:authors'
        #]
        #title = article.xml_select(u'section[@title = ]')

        #revdate = dateparse(unicode(page.article.articleinfo.revhistory.revision.date))
        #if revdate.tzinfo == None: revdate = revdate.replace(tzinfo=UTC)
        
        #Create ouput file
        #print >> sys.stderr, 'Writing to ', self.output
        buf = StringIO()
        w = structwriter(indent=u"yes", stream=buf)
        w.feed(
        ROOT(
            E((XHTML_NAMESPACE, u'html'), {(XML_NAMESPACE, u'xml:lang'): u'en'},
                E(u'head',
                    E(u'title', title),
                    E(u'meta', {u'content': unicode(first_item(metadata[u'ak-updated'])), u'name': u'updated'}),
                    #E(u'link', {u'href': unicode(uri), u'rel': u'alternate', u'title': u"Permalink"}),
                ),
                E(u'body',
                    (self.content.dispatch(s) for s in doc.article.section)
                ),
            ),
        ))
        with open(self.output, 'w') as output:
            #text = f.read().rstrip()
            #print buf.getvalue()
            transform(buf.getvalue(), template, output=output)
        return

    def meta(self):
        #Create ouput file
        doc = bindery.parse(source, model=AK_DOCBOOK_MODEL)

node.NODES[page.AKARA_TYPE] = page
#AKARA_TYPES = [page, folder]


class content_handlers(dispatcher):
    def __init__(self, orig_wikibase):
        dispatcher.__init__(self)
        self.orig_wikibase = orig_wikibase
        return

    @node_handler(u'article/section', priority=10)
    def top_section(self, node):
        yield E((XHTML_NAMESPACE, u'div'), {u'id': node.title},
            chain(*imap(self.dispatch, node.xml_children))
        )

    @node_handler(u'section')
    def section(self, node):
        depth = node.xml_select(u'count(ancestor::section)')
        yield E((XHTML_NAMESPACE, u'h%i'%depth), unicode(node.title))
        for node in chain(*imap(self.dispatch, node.xml_children)):
            yield node

    @node_handler(u'section/title')
    def section_title(self, node):
        #Ignore this node
        raise StopIteration

    @node_handler(u'para')
    def para(self, node):
        #print 'content_handlers.para'
        yield E((XHTML_NAMESPACE, u'p'),
            chain(*imap(self.dispatch, node.xml_children))
        )

    @node_handler(u'code')
    def code(self, node):
        yield E((XHTML_NAMESPACE, u'code'),
            chain(*imap(self.dispatch, node.xml_children))
        )

    @node_handler(u'emphasis')
    def emphasis(self, node):
        ename = u'strong' if node.xml_attributes.get((None, u'role')) == u'strong' else u'em'
        yield E((XHTML_NAMESPACE, ename),
            chain(*imap(self.dispatch, node.xml_children))
        )

    @node_handler(u'screen')
    def screen(self, node):
        yield E((XHTML_NAMESPACE, u'pre'),
            chain(*imap(self.dispatch, node.xml_children))
        )

    @node_handler(u'ulink')
    def a(self, node):
        '''
        [[Some_page]] -> @url == $WIKIBASE/Some_page
        [[Some_page/Child]] -> @url == $WIKIBASE/Some_page/Child
        [[http://moinmo.in/]] -> @url == http://moinmo.in/
        '''
        url = node.url
        if url.startswith(self.orig_wikibase):
            url = url[len(self.orig_wikibase):]
        yield E((XHTML_NAMESPACE, u'a'), {u'href': url},
            chain(*imap(self.dispatch, node.xml_children))
        )

    @node_handler(u'inlinemediaobject')
    def img(self, node):
        '''
        {{http://static.moinmo.in/logos/moinmoin.png}} -> img/@src=...
        '''
        url = node.imageobject.imagedata.fileref
        if url.startswith(self.orig_wikibase):
            url = url[len(self.orig_wikibase):]
        yield E((XHTML_NAMESPACE, u'img'), {u'src': url},
            chain(*imap(self.dispatch, node.xml_children))
        )

    @node_handler(u'itemizedlist')
    def ul(self, node):
        '''
        * foo
        '''
        yield E((XHTML_NAMESPACE, u'ul'),
            chain(*imap(self.dispatch, node.xml_children))
        )

    @node_handler(u'listitem')
    def li(self, node):
        yield E((XHTML_NAMESPACE, u'li'),
            chain(*imap(self.dispatch, [ grandchild for grandchild in node.para.xml_children ]))
        )

    #@node_handler(u'*', priority=-1)
    #def etc(self, node):


def moincms(wikibase, outputdir, pattern):
    if pattern: pattern = re.compile(pattern)
    #print (wikibase, outputdir, rewrite)
    req = urllib2.Request(wikibase, headers={'Accept': RDF_IMT})
    resp = urllib2.urlopen(req)
    original_wiki_base = dict(resp.info())[ORIG_BASE_HEADER]
    feed = bindery.parse(resp)
    process_list = []
    for item in feed.RDF.channel.items.Seq.li:
        uri = split_fragment(item.resource)[0]
        #print >> sys.stderr, (uri, str(item.resource), split_fragment(item.resource))
        #Deal with the wrapped URI
        if original_wiki_base:
            #print >> sys.stderr, (uri, original_wiki_base.rstrip('/')+'/')
            relative = relativize(uri, original_wiki_base.rstrip('/')+'/').lstrip('/')
            uri = absolutize(relative, wikibase)
        #print >> sys.stderr, (uri, relative)
        if pattern and not pattern.match(relative):
            continue
        n = node.factory(uri, relative, outputdir)
        if n.up_to_date():
            pass
            #print >> sys.stderr, 'Up to date.  Skipped...'
        else:
            process_list.append(n)
            
    #Process nodes needing update according to priority
    for n in sorted(process_list, key=attrgetter('PRIORITY'), reverse=True):
        #print >> sys.stderr, "processing ", n.rest_uri
        n.render()
    return

#Ideas borrowed from
# http://www.artima.com/forums/flat.jsp?forum=106&thread=4829

import sys
import SocketServer
from wsgiref import simple_server


def command_line_prep():
    from optparse import OptionParser
    usage = "%prog [options] wikibase outputdir"
    parser = OptionParser(usage=usage)
    parser.add_option("-p", "--pattern",
                      action="store", type="string", dest="pattern",
                      help="limit the pages treated as Atom entries to those matching this pattern")
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
            wikibase = args[0]
            try:
                outputdir = args[1]
            except IndexError:
                optparser.error("Missing output directory")
        except IndexError:
            optparser.error("Missing Wiki base URL")
    except SystemExit, status:
        return status

    # Perform additional setup work here before dispatching to run()
    # Detectable errors encountered here should be handled and a status
    # code of 1 should be returned. Note, this would be the default code
    # for a SystemExit exception with a string message.
    pattern = options.pattern and options.pattern.decode('utf-8')

    moincms(wikibase, outputdir, pattern)
    return


#aname = partial(property_sequence_getter, u"name")
#aemail = partial(property_sequence_getter, u"email")
#auri = partial(property_sequence_getter, u"uri")

UNSUPPORTED_IN_FILENAME = re.compile('\W')
#SOURCE = AKARA_MODULE_CONFIG['source-wiki-root']
#POST_TO = AKARA_MODULE_CONFIG['post-to']

class atom_entry(node):
    AKARA_TYPE = CMS_BASE + u'/atom-entry'
    OUTPUTPATTERN = None
    def __init__(self, rest_uri, relative, outputdir, cache=None):
        node.__init__(self, rest_uri, relative, outputdir, cache)
        self.relative = relative
        return

    def up_to_date(self, force_update=False):
        '''
        Checks whether there needs to be an update of the CMS output file or folder
        '''
        doc, metadata, original_wiki_base = self.cache
        entrydate = dateparse(unicode(doc.article.articleinfo.revhistory.revision.date))
        if entrydate.tzinfo == None: entrydate = entrydate.replace(tzinfo=UTC)
        output = os.path.join(outputdir, self.OUTPUTPATTERN%pathsegment(relative))
        if os.access(output, os.R_OK):
            lastrev = dateparse(unicode(bindery.parse(output).entry.updated))
            if lastrev.tzinfo == None: lastrev = lastrev.replace(tzinfo=UTC)
            if (entrydate == lastrev):
                print >> sys.stderr, 'Not updated.  Skipped...'
                # continue
                return

        if force_update:
            self.load()

        pagedate = dateparse(unicode(doc.article.articleinfo.revhistory.revision.date))
        #Note from the Moin FAQ: http://moinmo.in/MoinMoinQuestions/UsingTheWiki
        #"Moin internally only uses UTC, but calculates your local time according to your UserPreferences setting on page view. If you set your timezone offset to 0, you get UTC."
        #Check the behavior if using the Moin REST wrapper with user auth where that user's prefs specify TZ
        if pagedate.tzinfo == None: pagedate = pagedate.replace(tzinfo=UTC)
        if not os.access(self.output, os.R_OK):
            return False
        lastrev = datetime.datetime.utcfromtimestamp(os.stat(self.output)[stat.ST_MTIME])
        #try:
        #    published_doc = bindery.parse(self.output)
        #    datestr = first_item([ m for m in published_doc.html.head.meta if m.name==u'updated']).content
        #    lastrev = dateparse(datestr)
        #except amara.ReaderError:
        #    return False
        if lastrev.tzinfo == None: lastrev = lastrev.replace(tzinfo=UTC)
        if (lastrev > pagedate):
            return True
        return False

    def render(self):
        '''
        The typical approach is along the lines of "Style-free XSLT Style Sheets"
        * http://www.xml.com/pub/a/2000/07/26/xslt/xsltstyle.html
        * http://www.cocooncenter.org/articles/stylefree.html
        But using div/@id rather than custome elements
        '''
        doc, metadata, original_wiki_base = self.cache
        self.content = content_handlers(original_wiki_base)
        #metadata = doc.article.xml_model.generate_metadata(doc)
        #import pprint
        #pprint.pprint(resources)
        '''
         akara:type:: [[http://purl.org/xml3k/akara/xmlmodel/cms/folder|folder]]
         title:: A page
         template:: http://wiki.example.com/Site;attachment=foo.xslt ##Just XSLT for now.  Plan to support other templating systems soon
         link:: [[http://example.org|]] rel=...
         meta:: dc:Creator value=Uche Ogbuji
         script:: `...` ##preferably they'd only use linked scripts: [[myscript...]]
        '''
        
        page_id = doc.article.xml_nodeid
        header = doc.article.glosslist[0]
        #node_type = first_item(header.xml_select(u'glossentry[glossterm = "akara:type"]/glossdef'))
        template = unicode(first_item(header.xml_select(u'glossentry[glossterm = "template"]/glossdef'))).strip()
        template = os.path.join(self.outputdir, template)
        title = first_item(header.xml_select(u'glossentry[glossterm = "title"]/glossdef'))
        #title = resources[articleid]['title']
        #sections = dict([ (unicode(s.title), s) for s in page.article.section ])
        #print sections
         # if unicode(g.glossterm) == u'page:header' ]
        #authors = [ a
        #    for a in page.article.section.glosslist.glossentry
        #    if unicode(a.glossterm) == u'entry:authors'
        #]
        #title = article.xml_select(u'section[@title = ]')

        #revdate = dateparse(unicode(page.article.articleinfo.revhistory.revision.date))
        #if revdate.tzinfo == None: revdate = revdate.replace(tzinfo=UTC)
        
        #Create ouput file
        print >> sys.stderr, 'Writing to ', self.output
        buf = StringIO()
        w = structwriter(indent=u"yes", stream=buf)
        w.feed(
        ROOT(
            E((XHTML_NAMESPACE, u'html'), {(XML_NAMESPACE, u'xml:lang'): u'en'},
                E(u'head',
                    E(u'title', title),
                    E(u'meta', {u'content': U(metadata[u'ak-updated']), u'name': u'updated'}),
                    #E(u'link', {u'href': unicode(uri), u'rel': u'alternate', u'title': u"Permalink"}),
                ),
                E(u'body',
                    (self.content.dispatch(s) for s in doc.article.section)
                ),
            ),
        ))
        with open(self.output, 'w') as output:
            #text = f.read().rstrip()
            #print buf.getvalue()
            transform(buf.getvalue(), template, output=output)
        return

register_node_type(page.AKARA_TYPE, page)


class freemix(node):
    AKARA_TYPE = 'http://purl.org/dc/gov/loc/recollection/collection'
    def __init__(self, rest_uri, opener):
        self.rest_uri = rest_uri
        self.opener = opener
        #from node.factory
        req = urllib2.Request(rest_uri, headers={'Accept': DOCBOOK_IMT})
        print >> sys.stderr, 'rest_uri: ', rest_uri
        with closing(opener.open(req)) as resp:
            doc = bindery.parse(resp, standalone=True, model=MOIN_DOCBOOK_MODEL)
            original_wiki_base = dict(resp.info())[ORIG_BASE_HEADER]
            #self.original_wiki_base = dict(resp.info())[ORIG_BASE_HEADER]
            #amara.xml_print(self.content_cache)
        metadata = metadata_dict(generate_metadata(doc))
        self.cache=(doc, metadata, original_wiki_base)
        return

    def up_to_date(self, force_update=False):
        '''
        Checks whether there needs to be an update of the output
        '''
        return False

    def render(self):
        '''
        '''
        doc, metadata, original_wiki_base = self.cache
        #metadata = doc.article.xml_model.generate_metadata(doc)
        #import pprint
        #pprint.pprint(resources)
        #amara.xml_print(doc, stream=sys.stderr, indent=True)
        header = doc.article.glosslist[0]
        freemix_info = {
            'id': self.rest_uri,
            'label': self.rest_uri,
            'title': doc.article.xml_select(u'string(section[title = "collection:title"]/para)'),
            'date-created': header.xml_select(u'string(glossentry[glossterm = "date-created"]/glossdef)'),
            'description': doc.article.xml_select(u'string(section[title = "collection:description"]/para)'),
            'link': header.xml_select(u'string(glossentry[glossterm = "link"]/glossdef//ulink/@url)'),
            'original_site': doc.article.xml_select(u'string(section[title = "collection:original site"]/para)'),
            'organization': doc.article.xml_select(u'string(section[title = "collection:organization"]/para)'),
            'restrictions': doc.article.xml_select(u'string(section[title = "collection:restrictions"]/para)'),
            'content': doc.article.xml_select(u'string(section[title = "collection:content"]/para)'),
            'thumbnail': header.xml_select(u'string(glossentry[glossterm = "thumbnail"]/glossdef//ulink/@url)'),
            'tags': [ unicode(tag).strip() for tag in doc.article.xml_select(u'section[title = "collection:tags"]//para')],
        }
        #print >> sys.stderr, 'FINFO ', freemix_info
        return freemix_info

    def meta(self):
        #Create ouput file
        doc = bindery.parse(source, model=AK_DOCBOOK_MODEL)

node.NODES[page.AKARA_TYPE] = page
#AKARA_TYPES = [page, folder]
#print >> sys.stderr, 'Writing to ', POST_TO

SELF = AKARA.module_config.get('self', 'http://localhost:8880/')
REST_WIKI_BASE = AKARA.module_config.get('rest_wiki_base', 'http://localhost:8880/moin/loc/')


def wrapped_uri(original_wiki_base, link):
    abs_link = absolutize(link, original_wiki_base)
    #print >> sys.stderr, 'abs_link: ', abs_link
    rel_link = relativize(abs_link, original_wiki_base)
    #print >> sys.stderr, 'rel_link: ', rel_link
    rest_uri = absolutize(rel_link, REST_WIKI_BASE)
    #print >> sys.stderr, 'rest_uri: ', rest_uri
    return rest_uri

WIKI_REQUIRED = _("The 'wiki' query parameter is mandatory.")
PATTERN_REQUIRED = _("The 'pattern' query parameter is mandatory.")

DEFAULT_TRANSFORM = AKARA.module_config.get('default_transform')
#print DEFAULT_TRANSFORM

SERVICE_ID = 'http://purl.org/akara/services/demo/moincms.execute'
@simple_service('POST', SERVICE_ID, 'moincms.execute')
def execute(top=None):
    '''
    Sample request:
    curl -F "pattern=wiki/path" -F "wiki=http://localhost:8880/moin/foo/" "http://localhost:8880/moincms.execute"
    '''
    #
    #wikibase_len = len(rewrite)
    body = StringIO(body)
    form = cgi.FieldStorage(fp=body, environ=WSGI_ENVIRON)
    #for k in form:
    #    print >> sys.stderr, (k, form[k][:100])
    wiki = form.getvalue('wiki')
    assert_not_equal(wiki, None, msg=WIKI_REQUIRED)
    pattern = form.getvalue('pattern')
    assert_not_equal(pattern, None, msg=PATTERN_REQUIRED)
    pattern = re.compile(pattern)
    
    handler = copy_auth(WSGI_ENVIRON, top)
    opener = urllib2.build_opener(handler) if handler else urllib2.build_opener()
    req = urllib2.Request(wiki, headers={'Accept': RDF_IMT})
    with closing(opener.open(req)) as resp:
        feed = bindery.parse(resp)
        original_wiki_base = dict(resp.info())[ORIG_BASE_HEADER]

    for item in feed.RDF.channel.items.Seq.li:
        uri = split_fragment(item.resource)[0]
        relative = uri[len(original_wiki_base):]
        print >> sys.stderr, uri, relative
        if pattern and not pattern.match(relative):
            continue
        if rewrite:
            uri = uri.replace(rewrite, wikibase)
        req = urllib2.Request(uri, headers={'Accept': DOCBOOK_IMT})
        with closing(urllib2.urlopen(req)) as resp:
            page = bindery.parse(resp)

        print >> sys.stderr, 'Writing to ', output
        with open(output, 'w') as output:
            handle_page(uri, page, outputdir, relative, output)


        doc = htmlparse(resp)

    #print (wikibase, outputdir, rewrite)
    with closing(urllib2.urlopen(req)) as resp:
        raise NotImplementedError
    return



    #wikibase, outputdir, rewrite, pattern
    #wikibase_len = len(rewrite)
    items = []
    for navchild in doc.xml_select(u'//*[@class="navigation"]//@href'):
        link = navchild.xml_value
        #print >> sys.stderr, 'LINK:', link
        #uri = split_fragment(item.resource)[0]
        #relative = uri[wikibase_len:]
        #print >> sys.stderr, uri, relative
        #if rewrite:
        #    uri = uri.replace(rewrite, wikibase)
        rest_uri = wrapped_uri(original_wiki_base, link)
        #print >> sys.stderr, 'rest uri:', rest_uri
        items.append(freemix(rest_uri, opener).render())
    return json.dumps({'items': items}, indent=4)

