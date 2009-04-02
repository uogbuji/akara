# -*- encoding: utf-8 -*-
'''
'''

from __future__ import with_statement
import urllib, urllib2
from itertools import *
from contextlib import closing

import simplejson

#from amara.tools.atomtools import feed
from akara.services import simple_service, response

#text/uri-list from RFC 2483
SERVICE_ID = 'http://purl.org/akara/services/builtin/luckygoogle'
@simple_service('get', SERVICE_ID, 'akara.luckygoogle', 'text/uri-list')
def lucky_google(q=None):
    '''
    A simple and fun transform to return the first ghit for a given search
    
    Sample request:
    * curl "http://localhost:8888/akara.luckygoogle?q=zepheira"
    '''
    q = q[0]
    #qstr = urllib2.urlopen(url).read()
    query = urllib.urlencode({'q' : q})
    url = 'http://ajax.googleapis.com/ajax/services/search/web?v=1.0&%s' % (query)
    with closing(urllib.urlopen(url)) as search_results:
        json = simplejson.loads(search_results.read())
    results = json['responseData']['results']
    return results[0]['url'].encode('utf-8') + '\n'

