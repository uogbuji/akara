# -*- coding: iso-8859-1 -*-
# 
"""

See: http://wiki.xml3k.org/Akara/Services/MoinCMS

Copyright 2009 Uche Ogbuji
This file is part of the open source Akara project,
provided under the Apache 2.0 license.
See the files LICENSE and NOTICE for details.
Project home, documentation, distributions: http://wiki.xml3k.org/Akara

@copyright: 2009 by Uche ogbuji <uche@ogbuji.net>
"""

__all__ = [
    "WIKITEXT_IMT", "DOCBOOK_IMT", "RDF_IMT", "HTML_IMT", "ATTACHMENTS_IMT",
    "ORIG_BASE_HEADER", "ATTACHMENTS_MODEL_XML", "ATTACHMENTS_MODEL",
    "MOIN_DOCBOOK_MODEL_XML", "MOIN_DOCBOOK_MODEL",
]

#import pprint
import os
import stat  # index constants for os.stat()
import re
import httplib, urllib, urllib2, cookielib
import datetime
from gettext import gettext as _

from dateutil.parser import parse as dateparse
import pytz

import amara
from amara import bindery
from amara.namespaces import *
from amara.xslt import transform
from amara.writers.struct import *
from amara.bindery.html import parse as htmlparse
from amara.lib import U
from amara.lib.iri import split_fragment, relativize, absolutize
from amara.bindery.model import examplotron_model, generate_metadata, metadata_dict
from amara.bindery.util import dispatcher, node_handler, property_sequence_getter

from akara import logger


WIKITEXT_IMT = 'text/plain'
HTML_IMT = 'text/html'
DOCBOOK_IMT = 'application/docbook+xml'
RDF_IMT = 'application/rdf+xml'
ATTACHMENTS_IMT = 'application/x-moin-attachments+xml'
ORIG_BASE_HEADER = 'x-akara-wrapped-moin'

#Note: this will change to app/xml as soon as we release a fixed Moin XML formatter
XML_IMT = 'text/xml'

# XML models

ATTACHMENTS_MODEL_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<attachments xmlns:eg="http://examplotron.org/0/" xmlns:ak="http://purl.org/xml3k/akara/xmlmodel">
  <attachment href="" ak:rel="name()" ak:value="@href"/>
</attachments>
'''

ATTACHMENTS_MODEL = examplotron_model(ATTACHMENTS_MODEL_XML)

MOIN_DOCBOOK_MODEL_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<article xmlns:eg="http://examplotron.org/0/" xmlns:ak="http://purl.org/xml3k/akara/xmlmodel" ak:resource="">
  <ak:rel name="'ak-old-type'" ak:value="glosslist[1]/glossentry[glossterm='akara:type']/glossdef//ulink/@url"/>
  <ak:rel name="'ak-type'" ak:value="section[title='akara:metadata']/glosslist/glossentry[glossterm='akara:type']/glossdef//ulink/@url"/>
  <ak:rel name="'ak-updated'" ak:value="articleinfo/revhistory/revision[1]/date"/>
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

MOIN_DOCBOOK_MODEL = examplotron_model(MOIN_DOCBOOK_MODEL_XML)


#python akara/services/moincms.py -p "Site.*" http://localhost:8880/ ~/tmp/ http://localhost:8080/
#
#Detailed license and copyright information: http://4suite.org/COPYRIGHT

UTC = pytz.timezone('UTC')
DEFAULT_LOCAL_TZ = pytz.timezone('UTC')

#aname = partial(property_sequence_getter, u"name")
#aemail = partial(property_sequence_getter, u"email")
#auri = partial(property_sequence_getter, u"uri")

AKARA_NS = u'http://purl.org/dc/org/xml3k/akara'
CMS_BASE = AKARA_NS + u'/cms'

def cleanup_text_blocks(text):
    return u'\n'.join([line.strip() for line in text.splitlines() ])

class node(object):
    '''
    Akara Moin/CMS node, a Moin wiki page that follows a template to direct workflow
    activity, including metadata extraction
    '''
    AKARA_TYPE = u'http://purl.org/xml3k/akara/cms/resource-type'
    NODES = {}
    #Processing priority
    PRIORITY = 0
    ENDPOINTS = None
    @staticmethod
    def factory(rest_uri, moin_link=None, opener=None):
        opener = opener or urllib2.build_opener()
        logger.debug('rest_uri: ' + rest_uri)
        req = urllib2.Request(rest_uri, headers={'Accept': DOCBOOK_IMT})
        resp = opener.open(req)
        doc = bindery.parse(resp, standalone=True, model=MOIN_DOCBOOK_MODEL)
        original_wiki_base = dict(resp.info())[ORIG_BASE_HEADER]
        #self.original_wiki_base = dict(resp.info())[ORIG_BASE_HEADER]
        #amara.xml_print(self.content_cache)
        metadata, first_id = metadata_dict(generate_metadata(doc))
        metadata = metadata[first_id]
        akara_type = U(metadata[u'ak-type'])
        logger.debug('Type: ' + akara_type)
        try:
            #Older Moin CMS resource types are implemented by registration to the global node.NODES
            cls = node.NODES[akara_type]
        except KeyError:
            #Newer Moin CMS resource types are implemented by discovery of a URL,
            #to which a POST request executes the desired action
            return node.ENDPOINTS and (rest_uri, akara_type, node.ENDPOINTS[akara_type], doc, metadata, original_wiki_base)
        else:
            instance = cls(rest_uri, moin_link, opener, cache=(doc, metadata, original_wiki_base))
            return instance

    #FIXME: This cache is to help eliminate unnecessary trips back to moin to get
    #The page body.  It should soon be replaced by the proposed comprehensive caching
    def __init__(self, rest_uri, moin_link, opener=None, cache=None):
        '''
        rest_uri - the full URI to the Moin/REST wrapper for this page
        relative - the URI of this page relative to the Wiki base
        '''
        self.rest_uri = rest_uri
        self.opener = opener
        self.moin_link = moin_link
        #logger.debug('Moin link: ' + moin_link)
        #logger.debug('REST URI: ' + rest_uri)
        self.cache = cache #(doc, metadata, original_wiki_base)
        return

    def load(self):
        raise NotImplementedError

    def render(self):
        raise NotImplementedError

    def up_to_date(self, force_update=False):
        '''
        Checks whether there needs to be an update of the output
        '''
        #By default just always update
        return False

    def section_titled(self, title):
        '''
        Helper to extract content from a specific section within the page
        '''
        #FIXME: rethink this "caching" business
        doc, metadata, original_wiki_base = self.cache
        #logger.debug("section_titled: " + repr(title))
        return doc.article.xml_select(u'section[title = "%s"]'%title)

    #
    def definition_list(self, list_path, contextnode=None, patterns=None):
        '''
        Helper to construct a dictionary from an indicated definition list on the page
        '''
        #FIXME: rethink this "caching" business
        #Use defaultdict instead, for performance
        patterns = patterns or {None: lambda x: U(x) if x else None}
        doc, metadata, original_wiki_base = self.cache
        contextnode = contextnode or doc.article
        top = contextnode.xml_select(list_path)
        if not top:
            return None
        #Go over the glossentries, and map from term to def, applying the matching
        #Unit transform function from the patterns dict
        result = dict((U(i.glossterm), patterns.get(U(i.glossterm), patterns[None])(i.glossdef))
                      for i in top[0].glossentry)
        #logger.debug("definition_list: " + repr(result))
        return result

node.NODES[node.AKARA_TYPE] = node


#XXX: do we really need this function indirection for simple global dict assignment?
def register_node_type(type_id, nclass):
    node.NODES[type_id] = nclass


def wiki_uri(original_base, wrapped_base, link, relative_to=None):
    '''
    Constructs absolute URLs to the original and REST-wrapper for a page, given a link from another page
    
    original_base - The base URI of the actual Moin instance
    wrapped_base - The base URI of the REST-wrapped proxy of the Moin instance
    link - the relative link, generally from one wiki page to another
    relative_to - the REST-wrapped version of the page from which the relative link came, defaults to same as wrapped_base
    '''
    #rel_link = relativize(abs_link, original_wiki_base)
    #e.g. original wiki base is http://myhost:8080/mywiki/ and link is /a/b
    #abs_link is http://myhost:8080/mywiki/a/b note the need to strip the leading / to get that
    if link.startswith('/'):
        rel_link = link.lstrip('/')
        abs_link = absolutize(rel_link, original_base.rstrip('/')+'/')
        rest_uri = absolutize(rel_link, wrapped_base.rstrip('/')+'/')
    else:
        rel_link = link.lstrip('/')
        abs_link = absolutize(rel_link, original_base.rstrip('/')+'/')
        rest_uri = absolutize(rel_link, relative_to)
    return rest_uri, abs_link


