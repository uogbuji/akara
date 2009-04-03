# -*- coding: iso-8859-1 -*-
# 
"""
moincms.py (Akara demo)

Accesses a Moin wiki (via akara.restwrap.moin) to use as a source for a Web feed

Copyright 2009 Uche Ogbuji
This file is part of the open source Akara project,
provided under the Apache 2.0 license.
See the files LICENSE and NOTICE for details.
Project home, documentation, distributions: http://wiki.xml3k.org/Akara

@copyright: 2009 by Uche ogbuji <uche@ogbuji.net>

Can be launched from the command line, e.g.:
    python akara/services/moincms.py -p "Site.*" http://restwrap.mywiki.example.com/ /path/to/output/dir http://localhost:8080/
"""
#python akara/services/moincms.py -p "Site.*" http://localhost:8880/ ~/tmp/ http://localhost:8080/
#
#Detailed license and copyright information: http://4suite.org/COPYRIGHT

from __future__ import with_statement
import os
import stat  # index constants for os.stat()
import re
import pprint
import httplib
import urllib, urllib2
import datetime
from wsgiref.util import shift_path_info, request_uri
from string import Template
from cStringIO import StringIO
from functools import partial
from itertools import *
from operator import *
from collections import defaultdict
from contextlib import closing

from dateutil.parser import parse as dateparse
import pytz

import amara
from amara import bindery
from amara.namespaces import *
from amara.xslt import transform
from amara.writers.struct import *
from amara.bindery.html import parse as htmlparse
from amara.lib.iri import * #split_fragment, relativize, absolutize
from amara.bindery.util import dispatcher, node_handler, property_sequence_getter
from amara.lib.util import *
from amara.bindery.model import *

from akara.restwrap.moin import *

UTC = pytz.timezone('UTC')
DEFAULT_LOCAL_TZ = pytz.timezone('UTC')

#aname = partial(property_sequence_getter, u"name")
#aemail = partial(property_sequence_getter, u"email")
#auri = partial(property_sequence_getter, u"uri")

AKARA_NS = u'http://purl.org/dc/org/xml3k/akara'
CMS_BASE = AKARA_NS + u'/cms'

class node(object):
    '''
    Akara CMS node, a Moin wiki page in a lightly specialized format
    from which semi-structured information can be extracted
    '''
    NODES = {}
    #Processing priority
    PRIORITY = 0
    def __init__(self, rest_uri, relative, outputdir, cache=None):
        self.relative = relative
        self.rest_uri = rest_uri
        self.output = os.path.join(outputdir, relative)
        self.outputdir = outputdir
        self.cache = cache#(doc, metadata)
        return

    @staticmethod
    def factory(rest_uri, relative, outputdir):
        req = urllib2.Request(rest_uri, headers={'Accept': DOCBOOK_IMT})
        with closing(urllib2.urlopen(req)) as resp:
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
        raw_metadata = doc.xml_model.generate_metadata(doc)
        metadata = {}
        for eid, row in groupby(sorted(raw_metadata), itemgetter(0)):
            #It's all crazy lazy, so use list to consume the iterator
            list( metadata.setdefault(key, []).append(val) for (i, key, val) in row )
        #print metadata
        akara_type = first_item(metadata[u'ak-type'])
        cls = node.NODES[akara_type]
        instance = cls(rest_uri, relative, outputdir, cache=(doc, metadata, original_wiki_base))
        return instance

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
        if entrydate.tzinfo == None: entrydate = entrydate.replace(tzinfo=DEFAULT_LOCAL_TZ)
        if not os.access(self.output, os.R_OK):
            return False
        try:
            lastrev = dateparse(unicode(bindery.parse(self.output).entry.updated))
        except amara.ReaderError:
            return False
        if lastrev.tzinfo == None: lastrev = lastrev.replace(tzinfo=DEFAULT_LOCAL_TZ)
        if (entrydate == lastrev):
            print >> sys.stderr, 'Not updated.  Skipped...'
            return False
        return True


class folder(node):
    AKARA_TYPE = CMS_BASE + u'/folder'
    PRIORITY = 1000
    def render(self):
        #Copy attachments to dir
        req = urllib2.Request(self.rest_uri, headers={'Accept': ATTACHMENTS_IMT})
        with closing(urllib2.urlopen(req)) as resp:
            doc = bindery.parse(resp, model=ATTACHMENTS_MODEL)
        for attachment in (doc.attachments.attachment or ()):
            print attachment
        return

node.NODES[folder.AKARA_TYPE] = folder


class page(node):
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
        if lastrev.tzinfo == None: lastrev = lastrev.replace(tzinfo=DEFAULT_LOCAL_TZ)
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
        #if revdate.tzinfo == None: revdate = revdate.replace(tzinfo=DEFAULT_LOCAL_TZ)
        
        #Create ouput file
        print >> sys.stderr, 'Writing to ', self.output
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
            text = f.read().rstrip()
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
    with closing(urllib2.urlopen(req)) as resp:
        original_wiki_base = dict(resp.info())[ORIG_BASE_HEADER]
        feed = bindery.parse(resp)
    process_list = []
    for item in feed.RDF.channel.items.Seq.li:
        uri = split_fragment(item.resource)[0]
        #Deal with the wrapped URI
        if original_wiki_base:
            relative = relativize(uri, original_wiki_base+'/')
            uri = absolutize(relative, wikibase)
        if pattern and not pattern.match(relative):
            continue
        #print >> sys.stderr, uri, relative
        n = node.factory(uri, relative, outputdir)
        if n.up_to_date():
            print >> sys.stderr, 'Up to date.  Skipped...'
        else:
            process_list.append(n)
            
    #Process nodes needing update according to priority
    for n in sorted(process_list, key=attrgetter('PRIORITY'), reverse=True):
        print >> sys.stderr, "processing ", n.rest_uri
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


if __name__ == "__main__":
    sys.exit(main(sys.argv))
