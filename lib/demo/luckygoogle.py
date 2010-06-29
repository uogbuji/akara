# -*- encoding: utf-8 -*-
'''
Demo module which forwards a search term to Google and returns the first hit's URL
'''

import urllib, urllib2
from gettext import gettext as _

# Requires Python 2.6 or http://code.google.com/p/json/
from amara.thirdparty import json

from amara.lib.util import first_item, assert_not_equal
from akara.services import simple_service

Q_REQUIRED = _("The 'q' query parameter is mandatory.")

#text/uri-list from RFC 2483
SERVICE_ID = 'http://purl.org/akara/services/demo/luckygoogle'
@simple_service('GET', SERVICE_ID, 'akara.luckygoogle', 'text/uri-list')
def lucky_google(q=None):
    '''
    A simple and fun transform to return the first hit for a given search
    
    Sample request:
    * curl "http://localhost:8880/akara.luckygoogle?q=zepheira"
    '''
    if q is None:
        raise AssertionError(Q_REQUIRED)
    query = urllib.urlencode({'q' : q})
    url = 'http://ajax.googleapis.com/ajax/services/search/web?v=1.0&' + query
    json_content = json.load(urllib.urlopen(url))
    results = json_content['responseData']['results']
    return results[0]['url'].encode('utf-8') + '\n'
