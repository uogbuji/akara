"""Demo of several ways to work with Amara's Atom tools

Some configurations can be changed in akara.conf. The default settings are:

class atomtools:
    entries = "/path/to/entry/files/*.atom"
    feed_envelope = '''<feed xmlns="http://www.w3.org/2005/Atom">
<title>This is my feed</title><id>http://example.com/my_feed</id>
</feed>'''

'entries' is the glob path to a set of Atom entries, where the root
element to each XML document must be "entry" in the Atom
namespace). The "feed_envelope" goes around the entries to make the
full Atom feed.  The entries are listed after the <title>.

"""
# "Make Emacs happy with a close quote. Otherwise it gets confused.

from datetime import datetime, timedelta
import glob
from itertools import dropwhile

import amara
from amara import bindery
from amara.tools import atomtools
from amara.thirdparty import httplib2
from amara.lib.util import first_item
from amara.thirdparty import json

from akara.services import simple_service
from akara import request, response
from akara import logger, module_config


# These come from the akara.demos.atomtools section of the Akara configuration file
ENTRIES = module_config().warn("entries", "/path/to/entry/files/*.atom",
                               "glob path to Atom entries")

FEED_ENVELOPE = module_config().warn("feed_envelope",
'''<feed xmlns="http://www.w3.org/2005/Atom">
<title>This is my feed</title><id>http://example.com/my_feed</id>
</feed>''', "XML envelope around the Atom entries")


#text/uri-list from RFC 2483
SERVICE_ID = 'http://purl.org/akara/services/demo/atom.json'
@simple_service('GET', SERVICE_ID, 'akara.atom.json', 'application/json')
def atom_json(url):
    '''
    Convert Atom syntax to Exhibit JSON
    (see: http://www.ibm.com/developerworks/web/library/wa-realweb6/ ; this is based on listing 3)
    
    Sample requests:
    * curl "http://localhost:8880/akara.atom.json?url=url=http://zepheira.com/feeds/news.atom"
    * curl "http://localhost:8880/akara.atom.json?url=http://picasaweb.google.com/data/feed/base/user/dysryi/albumid/5342439351589940049"
    * curl "http://localhost:8880/akara.atom.json?url=http://earthquake.usgs.gov/eqcenter/catalogs/7day-M2.5.xml"
    '''
    entries = atomtools.ejsonize(url)
    return json.dumps({'items': entries}, indent=4)

# This uses a simple caching mechanism.
# If the cache is over 15 minutes old then rebuild the cache.
DOC_CACHE = None
def _need_refresh():
    if DOC_CACHE is None:
        return True
    if datetime.now() > DOC_CACHE[1]: # check for expiration
        return True
    return False

SERVICE_ID = 'http://purl.org/akara/services/demo/aggregate.atom'
@simple_service('GET', SERVICE_ID, 'akara.aggregate.atom', str(atomtools.ATOM_IMT))
def aggregate_atom():
    """Aggregate a set of Atom entries and return as an Atom feed
    
    Sample request:
    * curl "http://localhost:8880/akara.aggregate.atom"
    """
    global DOC_CACHE
    if _need_refresh():
        filenames = glob.glob(ENTRIES)
        doc, metadata = atomtools.aggregate_entries(FEED_ENVELOPE, filenames)
        DOC_CACHE = doc.xml_encode('xml-indent'), datetime.now() + timedelta(minutes=15)
    return DOC_CACHE[0]


# We love Atom, but for sake of practicality (and JSON fans), here is
# a transform for general feeds
SERVICE_ID = 'http://purl.org/akara/services/demo/webfeed.json'
@simple_service('GET', SERVICE_ID, 'akara.webfeed.json', 'application/json')
def webfeed_json(url):
    """Convert an Atom feed to Exhibit JSON
    
    Sample request:
    * curl "http://localhost:8880/akara.webfeed.json?url=http://feeds.delicious.com/v2/rss/recent%3Fmin=1%26count=15"
    * curl http://localhost:8880/akara.webfeed.json?url=http://localhost:8880/akara.aggregate.atom
    """
    import feedparser   # From http://www.feedparser.org/

    feed = feedparser.parse(url)
    # Note: bad URLs might mean the feed doesn't have headers
    
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
    return json.dumps({'items': entries}, indent=4)

RDF_IMT = 'application/rdf+xml'
ATOM_IMT = 'application/atom+xml'

# Read RSS2, and generate Atom or other format
SERVICE_ID = 'http://purl.org/akara/services/demo/rss2translate'
@simple_service('GET', SERVICE_ID, 'akara.rss2translate')
def rss2translate(url=None, format=None):
    """Convert RSS 2.0 feed to Atom or RSS 1.0
    
    Sample request:
    * curl "http://localhost:8880/akara.rss2translate?url=http://feeds.delicious.com/v2/rss/recent"

    This is a demo and is not meant as an industrial-strength converter.
    """
    # Support connection-negotiation in addition to query parameter
    if not format:
        accepted_imts = request.environ.get('HTTP_ACCEPT', '').split(',')
        imt = first_item(dropwhile(lambda x: '*' in x, accepted_imts))
        if imt == 'RDF_IMT':
            format = 'rss1'
        else:
            format = 'atom'
    
    if not url:
        raise AssertionError("The 'url' query parameter is mandatory.")

    import feedparser # From http://www.feedparser.org/
    feed = feedparser.parse(url)
    
    # Note: bad URLs might mean the feed doesn't have headers
    logger.debug('Feed info: ' + repr((url, feed.version, feed.encoding, feed.headers.get('Content-type'))))

    updated = getattr(feed.feed, 'updated_parsed', None)
    if updated:
        #FIXME: Double-check this conversion
        updated = datetime(*updated[:7]).isoformat()
    
    f = atomtools.feed(title=feed.feed.title, updated=updated, id=feed.feed.link)
    for e in feed.entries:
        updated = getattr(e, 'updated_parsed', None)
        if updated:
            #FIXME: Double-check this conversion
            updated = datetime(*updated[:7]).isoformat()
        links = [
            #FIXME: self?
            (e.link, u'alternate'),
        ]
        f.append(
            e.link,
            e.title,
            updated = updated,
            summary=e.description,
            #e.author_detail.name
            #authors=authors,
            links=links,
        )

    if format == 'atom':
        result = f.xml_encode()
        response.add_header("Content-Type", ATOM_IMT)
    else:
        result = f.rss1format()
        response.add_header("Content-Type", RDF_IMT)
    return result

