# -*- encoding: utf-8 -*-
'''
See also:
'''

from __future__ import with_statement
import sys, time
import urllib, urlparse
from cgi import parse_qs
from cStringIO import StringIO
import feedparser
from itertools import *

import amara
from amara.xslt import transform

from akara.services import simple_service, response

SERVICE_ID = 'http://purl.org/akara/services/builtin/xslt'
@simple_service('post', SERVICE_ID, 'akara.xslt')
def akara_xslt(body, ctype, **params):
    '''
    akaraxslttransform - URL to the XSLT transform to be applied
    all other query parameters are passed ot the XSLT processor as top-level params
    
    Sample request:
    curl --request POST --data-binary "@foo.xml" --header "Content-Type: application/xml" "http://localhost:8880/akara.xslt?akara.xslt=http://cvs.4suite.org/viewcvs/*checkout*/4Suite/Ft/Data/identity.xslt"
    '''
    if "akara.xslt" not in params:
        raise ValueError('XSLT transform required')
    akaraxslttransform = params["akara.xslt"][0]
    result = transform(body, akaraxslttransform)
    return response(str(result), result.parameters.media_type)

