# -*- coding: iso-8859-1 -*-
# 
"""
moincms.py (Akara demo)

Accesses a Moin wiki (via akara.restwrap.moin) to use as a source for a Web feed

A RESTful wrapper for MoinMoin wikis

Copyright 2009 Uche Ogbuji
This file is part of the open source Akara project,
provided under the Apache 2.0 license.
See the files LICENSE and NOTICE for details.
Project home, documentation, distributions: http://wiki.xml3k.org/Akara

@copyright: 2009 by Uche ogbuji <uche@ogbuji.net>

Can be launched from the command line, e.g.:
    python demo/moin2atomentries.py http://restwrap.mywiki.example.com/ /path/to/output/dir
"""
#
#Detailed license and copyright information: http://4suite.org/COPYRIGHT

import os
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

from dateutil.parser import parse as dateparse
import pytz

import amara
from amara import bindery
from amara.namespaces import *
from amara.writers.struct import *
from amara.bindery.html import parse as htmlparse
from amara.lib.iri import split_fragment
from amara.bindery.util import dispatcher, node_handler, property_sequence_getter

from akara.restwrap.moin import *

DEFAULT_TZ = pytz.timezone('UTC')

#aname = partial(property_sequence_getter, u"name")
#aemail = partial(property_sequence_getter, u"email")
#auri = partial(property_sequence_getter, u"uri")

AKARA_NS = u'http://purl.org/dc/org/xml3k/akara'
CMS_BASE = AKARA_NS + u'/cms'

DOCBOOK_MODEL = '''<?xml version="1.0" encoding="UTF-8"?>
<article xmlns:eg="http://examplotron.org/0/" xmlns:ak="http://purl.org/dc/org/xml3k/akara" ak:resource="">
  <articleinfo>
    <title ak:rel="name()" ak:value=".">FrontPage</title>
    <revhistory>
      <revision eg:occurs="*">
        <revnumber>15</revnumber>
        <date>2009-02-22 07:45:22</date>
        <authorinitials>localhost</authorinitials>
      </revision>
    </revhistory>
  </articleinfo>
  <section eg:occurs="*" ak:resource="">
    <title ak:rel="name()" ak:value=".">A page</title>
    <para>
    Using: <ulink url="http://moinmo.in/DesktopEdition"/> set <code>interface = ''</code>)
    </para>
    <itemizedlist>
      <listitem>
        <para>
          <ulink url="http://localhost:8080/Developer#">Developer</ulink> </para>
      </listitem>
    </itemizedlist>
  </section>
</article>
'''

DOCBOOK_MODEL = examplotron_model(DOCBOOK_MODEL)

class node(object):
    '''
    Akara CMS node, a Moin wiki page in a lightly specialized format
    from which semi-structured information can be extracted
    '''
    def __init__(self, rest_uri):
        self.rest_uri = rest_uri


class folder(node):
    akara_type = CMS_BASE + u'/folder'
    def render(self):
        #Copy attachments to dir
        req = urllib2.Request(self.rest_uri, headers={'Accept': ATTACHMENTS_IMT})
        response = urllib2.urlopen(req)
        doc = bindery.parse(response)
        response.close()
        for attachment in doc.attachments.attachment:
            print attachment
        return

class page(node):
    akara_type = CMS_BASE + u'/page'
    def render(self):
        #Create ouput file
        output = open()
        self.content = content_handlers(CMSBASE)
        doc = bindery.parse(source, model=DOCBOOK_MODEL)
        #metadata = doc.article.xml_model.generate_metadata(doc)
        metadata = doc.xml_model.generate_metadata(doc)
        books = {}
        #Use sorted to ensure grouping by resource IDs
        resources = {}
        for rid, row in groupby(sorted(metadata), itemgetter(0)):
            resources[rid] = {}
            #It's all crazy lazy, so use list() to consume the iterator
            list( resources[rid].setdefault(key, []).append(val) for (i, key, val) in row )
        import pprint
        pprint.pprint(resources)
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
        node_type = onenode(header.xml_select(u'glossentry[glossterm = "akara:type"]'))
        template = onenode(header.xml_select(u'glossentry[glossterm = "template"]'))
        title = onenode(header.xml_select(u'glossentry[glossterm = "title"]'))
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
        #if revdate.tzinfo == None: revdate = revdate.replace(tzinfo=DEFAULT_TZ)
        
        w = structwriter(indent=u"yes", stream=output)
        w.feed(
        ROOT(
            E((XHTML_NAMESPACE, u'html'), {(XML_NAMESPACE, u'xml:lang'): u'en'},
                E(u'head',
                    E(u'title', title),
                    #E(u'link', {u'href': unicode(uri), u'rel': u'alternate', u'title': u"Permalink"}),
                ),
                E(u'body',
                    (self.content.dispatch(s) for s in page.article.section)
                ),
            ),
        ))

    def meta(self):
        #Create ouput file
        doc = bindery.parse(source, model=DOCBOOK_MODEL)

AKARA_TYPES = [page, folder]

class content_handlers(dispatcher):
    def __init__(self, wikibase):
        dispatcher.__init__(self)
        self.wikibase = wikibase
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
        if url.startswith(self.wikibase):
            url = url[len(self.wikibase):]
        yield E((XHTML_NAMESPACE, u'a'), {u'href': url},
            chain(*imap(self.dispatch, node.xml_children))
        )

    @node_handler(u'inlinemediaobject')
    def img(self, node):
        '''
        {{http://static.moinmo.in/logos/moinmoin.png}} -> img/@src=...
        '''
        url = node.imageobject.imagedata.fileref.url
        if url.startswith(self.wikibase):
            url = url[len(self.wikibase):]
        yield E((XHTML_NAMESPACE, u'img'), {u'src': url},
            chain(*imap(self.dispatch, node.xml_children))
        )

    #@node_handler(u'*', priority=-1)
    #def etc(self, node):

def moincms(wikibase, outputdir, rewrite, pattern):
    wikibase_len = len(rewrite)
    if pattern: pattern = re.compile(pattern)
    #print (wikibase, outputdir, rewrite)
    req = urllib2.Request(wikibase, headers={'Accept': RDF_IMT})
    feed = bindery.parse(urllib2.urlopen(req))
    for item in feed.RDF.channel.items.Seq.li:
        uri = split_fragment(item.resource)[0]
        relative = uri[wikibase_len:]
        print >> sys.stderr, uri, relative
        if pattern and not pattern.match(relative):
            continue
        if rewrite:
            uri = uri.replace(rewrite, wikibase)
        req = urllib2.Request(uri, headers={'Accept': DOCBOOK_IMT})
        page = bindery.parse(urllib2.urlopen(req))
        entrydate = dateparse(unicode(page.article.articleinfo.revhistory.revision.date))
        if entrydate.tzinfo == None: entrydate = entrydate.replace(tzinfo=DEFAULT_TZ)
        output = os.path.join(outputdir, OUTPUTPATTERN%pathsegment(relative))
        if os.access(output, os.R_OK):
            lastrev = dateparse(unicode(bindery.parse(output).entry.updated))
            if lastrev.tzinfo == None: lastrev = lastrev.replace(tzinfo=DEFAULT_TZ)
            if (entrydate == lastrev):
                print >> sys.stderr, 'Not updated.  Skipped...'
                continue
        print >> sys.stderr, 'Writing to ', output
        output = open(output, 'w')
        handle_page(uri, page, outputdir, relative, output)
        output.close()
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
    rewrite = args[2] if len(args) > 1 else None

    # Perform additional setup work here before dispatching to run()
    # Detectable errors encountered here should be handled and a status
    # code of 1 should be returned. Note, this would be the default code
    # for a SystemExit exception with a string message.
    pattern = options.pattern and options.pattern.decode('utf-8')

    moincms(wikibase, outputdir, rewrite, pattern)
    return


if __name__ == "__main__":
    sys.exit(main(sys.argv))

