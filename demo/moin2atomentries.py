# -*- coding: iso-8859-1 -*-
# 
"""
moin2atomentries.py (Akara demo)

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

WIKITEXT_IMT = 'text/plain'
DOCBOOK_IMT = 'application/docbook+xml'
RDF_IMT = 'application/rdf+xml'
DEFAULT_TZ = pytz.timezone('UTC')

import sys
import SocketServer
from wsgiref import simple_server

#aname = partial(property_sequence_getter, u"name")
#aemail = partial(property_sequence_getter, u"email")
#auri = partial(property_sequence_getter, u"uri")

class author(object):
    def __init__(self, para):
        self.name = unicode(para.ulink)
        self.email = unicode(para.ulink[1])
        self.uri = para.ulink.url
        return

UNSUPPORTED_IN_FILENAME = re.compile('\W')
LINK_PATTERN = u'http://zepheira.com/news/#%s'

def pathsegment(relative):
    return UNSUPPORTED_IN_FILENAME.sub('_', relative)

def handle_page(uri, page, outputdir, relative, output):
    #tags = [u"xml", u"python", u"atom"]
    print >> sys.stderr, 'Processing ', uri
    title = unicode(page.article.section[0].title)
    sections = dict([ (unicode(s.title), s) for s in page.article.section ])
    #print sections
    summary = sections["entry:summary"]
    content = sections["entry:content"]
    tags = [ g for g in page.article.section.glosslist.glossentry if unicode(g.glossterm) == u'entry:tags' ]
    if tags: tags = [ unicode(gd.para).strip() for gd in tags[0].glossdef ]
    authors = [ a
        for a in page.article.section.glosslist.glossentry
        if unicode(a.glossterm) == u'entry:authors'
    ]
    if authors: authors = [ author(gd.para) for gd in authors[0].glossdef ]
    #title = article.xml_select(u'section[@title = ]')

    revdate = dateparse(unicode(page.article.articleinfo.revhistory.revision.date))
    if revdate.tzinfo == None: revdate = revdate.replace(tzinfo=DEFAULT_TZ)

    w = structwriter(indent=u"yes", stream=output)
    w.feed(
    ROOT(
        E((ATOM_NAMESPACE, u'entry'), {(XML_NAMESPACE, u'xml:lang'): u'en'},
            #E(u'link', {u'href': u'/blog'}),
            E(u'link', {u'href': unicode(uri), u'rel': u'edit'}),
            E(u'link', {u'href': LINK_PATTERN%unicode(uri), u'rel': u'alternate', u'title': u"Permalink"}),
            E(u'id', unicode(uri)),
            E(u'title', title),
            #FIXME: Use updated time from feed
            E(u'updated', unicode(revdate)),
            #E(u'updated', datetime.datetime.now().isoformat()),
            #E(u'updated', page.updated),
            ( E(u'category', {u'term': t}) for t in tags ),
            ( E(u'author',
                E(u'name', a.name),
                E(u'uri', a.uri),
                E(u'email', a.email),
            ) for a in authors ),
            E(u'summary', {u'type': u'xhtml'},
                E((XHTML_NAMESPACE, u'div'),
                    CONTENT.dispatch(summary)
                )
            ),
            E(u'content', {u'type': u'xhtml'},
                E((XHTML_NAMESPACE, u'div'),
                    CONTENT.dispatch(content)
                )
            ),
        ),
    ))
    return


class content_handlers(dispatcher):
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
        #print dict(node.xml_attributes)
        #print; print type(node.xml_attributes.get(None, u'role'))
        #ename = u'strong' if node.xml_attributes.get(None, u'role') == u'strong' else u'em'
        ename = u'strong' if node.xml_attributes.get(None, u'role') == u'strong' else u'em'
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
        yield E((XHTML_NAMESPACE, u'a'), {u'href': node.url},
            chain(*imap(self.dispatch, node.xml_children))
        )

    #@node_handler(u'*', priority=-1)
    #def etc(self, node):

CONTENT = content_handlers()
OUTPUTPATTERN = 'MOIN.%s.atom'

def moin2atomentries(wikibase, outputdir, rewrite, pattern):
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

#FIXME: A lot of this is copied boilerplate that neds to be cleaned up

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

    moin2atomentries(wikibase, outputdir, rewrite, pattern)
    return


if __name__ == "__main__":
    sys.exit(main(sys.argv))

