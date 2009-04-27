# -*- encoding: utf-8 -*-
'''
See also:
 * [[http://www.eprints.org/software/xslt.php|"OAI2 to HTML XSLT Style Sheet"]]
'''

from __future__ import with_statement
import sys, time
import datetime
import urllib, urlparse
from cgi import parse_qs
from cStringIO import StringIO
import feedparser
from itertools import *

import simplejson

import amara
from amara import bindery
from amara import tree
from amara.writers.struct import *
from amara.bindery.model import *
from amara.bindery.util import dispatcher, node_handler

from amara.tools.atomtools import feed

from akara.services import simple_service, response

OAI_NAMESPACE = u"http://www.openarchives.org/OAI/2.0/"

#OAI-PMH verbs:
# * Identify
# * ListMetadataFormats
# * ListSets
# * GetRecord
# * ListIdentifiers
# * ListRecords


#Useful:
# http://www.nostuff.org/words/tag/oai-pmh/
# http://libraries.mit.edu/dspace-mit/about/faq.html
# http://wiki.dspace.org/index.php/OaiInstallations - List of OAI installations harvested by DSpace
#Examples:
# http://eprints.sussex.ac.uk/perl/oai2?verb=GetRecord&metadataPrefix=oai_dc&identifier=oai:eprints.sussex.ac.uk:67
# http://dspace.mit.edu/oai/request?verb=Identify
# http://dspace.mit.edu/oai/request?verb=GetRecord&metadataPrefix=oai_dc&identifier=oai:dspace.mit.edu:1721.1/5451

#Based on: http://dspace.mit.edu/oai/request?verb=GetRecord&metadataPrefix=oai_dc&identifier=oai:dspace.mit.edu:1721.1/5451
OAI_MODEL_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:o="http://www.openarchives.org/OAI/2.0/"
         xsi:schemaLocation="http://www.openarchives.org/OAI/2.0/ http://www.openarchives.org/OAI/2.0/OAI-PMH.xsd"
         xmlns:eg="http://examplotron.org/0/" xmlns:ak="http://purl.org/dc/org/xml3k/akara">
  <responseDate>2009-03-30T06:09:23Z</responseDate>
  <request verb="GetRecord" identifier="oai:dspace.mit.edu:1721.1/5451" metadataPrefix="oai_dc">http://dspace.mit.edu/oai/request</request>
  <GetRecord>
    <record ak:resource="o:header/o:identifier">
      <header>
        <identifier>oai:dspace.mit.edu:1721.1/5451</identifier>
        <datestamp ak:rel="local-name()" ak:value=".">2006-09-20T00:15:44Z</datestamp>
        <setSpec>hdl_1721.1_5443</setSpec>
      </header>
      <metadata>
        <oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" xmlns:dc="http://purl.org/dc/elements/1.1/" xsi:schemaLocation="http://www.openarchives.org/OAI/2.0/oai_dc/ http://www.openarchives.org/OAI/2.0/oai_dc.xsd">
          <dc:creator ak:rel="local-name()" ak:value=".">Cohen, Joshua</dc:creator>
          <dc:date ak:rel="local-name()" ak:value=".">2004-08-20T19:48:34Z</dc:date>
          <dc:date>2004-08-20T19:48:34Z</dc:date>
          <dc:date>1991</dc:date>
          <dc:identifier ak:rel="'handle'" ak:value=".">http://hdl.handle.net/1721.1/5451</dc:identifier>
          <dc:description ak:rel="local-name()" ak:value=".">Cohen's Comments on Adam Przeworski's article "Could We Feed Everyone?"</dc:description>
          <dc:format>2146519 bytes</dc:format>
          <dc:format>application/pdf</dc:format>
          <dc:language>en_US</dc:language>
          <dc:publisher ak:rel="local-name()" ak:value=".">Politics and Society</dc:publisher>
          <dc:title ak:rel="local-name()" ak:value=".">"Maximizing Social Welfare or Institutionalizing Democratic Ideals?"</dc:title>
          <dc:type>Article</dc:type>
          <dc:identifier>Joshua Cohen, "Maximizing Social Welfare or Institutionalizing Democratic Ideals?"; Politics and Society, Vol. 19, No. 1</dc:identifier>
        </oai_dc:dc>
      </metadata>
    </record>
  </GetRecord>
</OAI-PMH>
'''

OAI_MODEL = examplotron_model(OAI_MODEL_XML)

ATOM_ENVELOPE = '''<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:sd="http://kds.elsevier.com/datamodel/sciencedirect#" xmlns:os="http://a9.com/-/spec/opensearch/1.1/">
  <title>MIT DSpace</title>
  <id>http://dspace.mit.edu/</id>
</feed>
'''

SERVICE_ID = 'http://purl.org/akara/services/builtin/oai.json'
@simple_service('GET', SERVICE_ID, 'akara.oai.atom', 'application/atom+xml')
def atomize_oai_record(endpoint=None, id=None):
    '''
    endpoint - the OAI request URL, e.g. http://dspace.mit.edu/oai/request
    id, e.g. the article ID, e.g. oai:dspace.mit.edu:1721.1/5451
    
    Sample request:
    curl "http://localhost:8880/akara.oai.atom?endpoint=http://dspace.mit.edu/oai/request&id=oai:dspace.mit.edu:1721.1/5451"
    '''
    if not endpoint:
        raise ValueError('endpoint required')
    if not id:
        raise ValueError('id required')
    id, endpoint = id[0], endpoint[0]
    qstr = urllib.urlencode({'verb' : 'GetRecord', 'metadataPrefix': 'oai_dc', 'identifier': id})
    url = endpoint + '?' + qstr
    doc = bindery.parse(url, model=OAI_MODEL)
    resources = metadata_dict(doc.xml_model.generate_metadata(doc))
    #print resources
    f = feed(ATOM_ENVELOPE)
    #f = feed(ATOM_ENVELOPE, title=resources['title'], id=resources['id'])
    #f.source.feed.xml_append(E((ATOM_NAMESPACE, u'link'), {u'rel': u'self', u'type': u'application/atom+xml', u'href': self_link.decode('utf-8')}))
    #f.source.feed.xml_append(E((ATOM_NAMESPACE, u'link'), {u'rel': u'search', u'type': u'application/opensearchdescription+xml', u'href': u'http://kds-kci.zepheira.com/sciencedirect.discovery'}))
    #f.source.feed.xml_append(E((ATOM_NAMESPACE, u'link'), {u'rel': u'alternate', u'type': u'text/xml', u'href': alt_link.decode('utf-8')}))
    #f.source.feed.xml_append(E((OPENSEARCH_NAMESPACE, u'Query'), {u'role': u'request', u'searchTerms': search_terms.decode('utf-8')}))
    #maxarticles = DEFAULT_MAX_RESULTS
    maxarticles = 3
    for record in islice(doc.OAI_PMH, 0, maxarticles):
        resource = resources[id]
        print resource
        authors = [ (a, None, None) for a in resource[u'creator'] ]
        links = [
            (resource['handle'], u'alternate'),
        ]
        #categories = [ (unicode(k), SD_NS+u'authorKeyword') for k in authkw(article) ]
        #elements = [
        #    E((SD_NS, u'sd:journal-cover'), unicode(article.journalCover).strip() if hasattr(article, 'journalCover') else DEFAULT_ICON),
        #    E((SD_NS, u'sd:journal-name'), unicode(article.journalName)),
        #]
        f.append(
            id,
            resource['title'][0],
            updated=resource['date'][0],
            summary=resource['description'][0],
            authors=authors,
            links=links,
            #categories=categories,
            #elements=elements,
        )

    buf = StringIO()
    amara.xml_print(f.source, stream=buf, indent=True)
    return buf.getvalue()

