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
#
#Detailed license and copyright information: http://4suite.org/COPYRIGHT

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

import simplejson
from dateutil.parser import parse as dateparse
import pytz

import amara
from amara import bindery, _
from amara.namespaces import *
from amara.bindery.model import *
from amara.writers.struct import *
from amara.bindery.html import parse as htmlparse
from amara.lib.iri import * #split_fragment, relativize, absolutize
from amara.bindery.util import dispatcher, node_handler, property_sequence_getter

from akara.util import *
from akara.util.moin import *
from akara.services.moincms import *
from akara.services import *


#DEFAULT_TZ = pytz.timezone('UTC')
UTC = pytz.timezone('UTC')
DEFAULT_LOCAL_TZ = pytz.timezone('UTC')


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
        if entrydate.tzinfo == None: entrydate = entrydate.replace(tzinfo=DEFAULT_TZ)
        output = os.path.join(outputdir, self.OUTPUTPATTERN%pathsegment(relative))
        if os.access(output, os.R_OK):
            lastrev = dateparse(unicode(bindery.parse(output).entry.updated))
            if lastrev.tzinfo == None: lastrev = lastrev.replace(tzinfo=DEFAULT_TZ)
            if (entrydate == lastrev):
                print >> sys.stderr, 'Not updated.  Skipped...'
                continue

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

SELF = AKARA_MODULE_CONFIG.get('self', 'http://localhost:8880/')
REST_WIKI_BASE = AKARA_MODULE_CONFIG.get('rest_wiki_base', 'http://localhost:8880/moin/loc/')


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

DEFAULT_TRANSFORM = AKARA_MODULE_CONFIG.get('default_transform')
#print DEFAULT_TRANSFORM

SERVICE_ID = 'http://purl.org/akara/services/builtin/moincms.execute'
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
    return simplejson.dumps({'items': items}, indent=4)

