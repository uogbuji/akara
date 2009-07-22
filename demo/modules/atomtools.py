# -*- encoding: utf-8 -*-
'''

Requires a configuration section, for example:

[atomtools]

entries = /path/to/entry/files/*.atom
feed_envelope = <feed xmlns="http://www.w3.org/2005/Atom"><title>My feed</
title><id>http://example.com/myfeed</id></feed>

'''

import sys
import urllib2
from cStringIO import StringIO
from operator import *
from itertools import *
from functools import *
import glob

import amara
from amara import bindery
from amara.tools.atomtools import *
from amara.tools.atomtools import parse as atomparse

from akara.services import simple_service, response


#text/uri-list from RFC 2483
SERVICE_ID = 'http://purl.org/akara/services/builtin/atom.json'
@simple_service('GET', SERVICE_ID, 'akara.atom.json', 'application/json')
def atom_json(url=None):
    '''
    Convert Atom syntax to Exhibit JSON
    (see: http://www.ibm.com/developerworks/web/library/wa-realweb6/ ; this is based on listing 3)
    
    Sample request:
    * curl "http://localhost:8880/akara.atom.json?url=url=http://zepheira.com/feeds/news.atom"
    * curl "http://localhost:8880/akara.atom.json?url=http://picasaweb.google.com/data/feed/base/user/dysryi/albumid/5342439351589940049"
    * curl "http://localhost:8880/akara.atom.json?url=http://earthquake.usgs.gov/eqcenter/catalogs/7day-M2.5.xml"
    '''
    # From http://code.google.com/p/simplejson/
    import simplejson
    url = url[0]
    feed, entries = atomparse(url)
    return simplejson.dumps({'items': entries}, indent=4)


#
ENTRIES = AKARA_MODULE_CONFIG.get('entries')
FEED_ENVELOPE = AKARA_MODULE_CONFIG.get('feed_envelope')

#print >> sys.stderr, "Entries:", ENTRIES
#print >> sys.stderr, "Feed envelope:", FEED_ENVELOPE

#FIXME: use stat to check dir and apply a cache otherwise
DOC_CACHE = None

SERVICE_ID = 'http://purl.org/akara/services/builtin/aggregate.atom'
@simple_service('GET', SERVICE_ID, 'akara.aggregate.atom', str(ATOM_IMT))
def aggregate_atom():
    '''
    Sample request:
    * curl "http://localhost:8880/akara.aggregate.atom"
    '''
    global DOC_CACHE
    if DOC_CACHE is None:
        fnames = glob.glob(ENTRIES)
        doc, metadata = aggregate_entries(FEED_ENVELOPE, fnames)
        buf = StringIO()
        amara.xml_print(doc, stream=buf, indent=True)
        DOC_CACHE = buf.getvalue()
    return DOC_CACHE


#We love Atom, but for sake of practicality, here is a transform for general feeds
SERVICE_ID = 'http://purl.org/akara/services/builtin/webfeed.json'
@simple_service('GET', SERVICE_ID, 'akara.webfeed.json', 'application/json')
def webfeed_json(url=None):
    '''
    Convert Web feed to Exhibit JSON
    
    Sample request:
    * curl "http://localhost:8880/akara.webfeed.json?url=http://feeds.delicious.com/v2/rss/recent%3Fmin=1%26count=15"
    '''
    # From http://www.feedparser.org/
    import feedparser
    # From http://code.google.com/p/simplejson/
    import simplejson

    if not url:
        raise AssertionError("The 'url' query parameter is mandatory.")
    url = url[0]
    feed = feedparser.parse(url)
    # Note: bad URLs might mean the feed doesn't have headers
    #print >> sys.stderr, "Feed info:", url, feed.version, feed.encoding, feed.headers.get('Content-type')
    
    def process_entry(e):
        data = {
            u'id': e.link,
            u'label': e.link,
            u'title': e.title,
            u'link': e.link,
            u'updated': e.updated,
        }
        #Optional bits
        if 'content' in data:
            data[u'content'] = e.content
        if 'description' in data:
            data[u'description'] = e.description
        if 'author_detail' in data:
            data[u'author_name'] = e.author_detail.name
        return data

    entries = [ process_entry(e) for e in feed.entries ]
    return simplejson.dumps({'items': entries}, indent=4)

