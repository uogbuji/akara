# -*- encoding: utf-8 -*-
'''

Requires a configuration section, for example:

[atomtools]

entries = /path/to/entry/files/*.atom
feed_envelope = <feed xmlns="http://www.w3.org/2005/Atom"><title>My feed</
title><id>http://example.com/myfeed</id></feed>

'''

import sys
import urllib, urllib2
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
    * curl "http://localhost:8880/akara.atom.json?url=http://zepheira.com/news/atom/entries/"
    '''
    import simplejson
    url = url[0]
    return simplejson.dumps({'items': atomparse(url)}, indent=4)


#
ENTRIES = AKARA_MODULE_CONFIG.get('entries')
FEED_ENVELOPE = AKARA_MODULE_CONFIG.get('feed_envelope')

print >> sys.stderr, "Entries:", ENTRIES
print >> sys.stderr, "Feed envelope:", FEED_ENVELOPE

#FIXME: use stat to check dir and apply a cache otherwise
DOC_CACHE = None

SERVICE_ID = 'http://purl.org/akara/services/builtin/aggregate.atom'
@simple_service('GET', SERVICE_ID, 'akara.aggregate.atom', str(ATOM_IMT))
def aggregate_atom():
    '''
]    Sample request:
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

