# -*- encoding: utf-8 -*-
'''
See also:
'''

import sys, time
import urllib, urllib2, urlparse
from subprocess import *
import cgi
from cStringIO import StringIO
from itertools import *
from contextlib import closing

from amara import _
from amara.lib.util import *

from akara.util import copy_auth
from akara.services import simple_service, response

Q_REQUIRED = _("The 'Q' POST parameter is mandatory.")
SVN_COMMIT_CMD = AKARA_MODULE_CONFIG.get('svn_commit', 'svn commit -m "%(msg)s" %(fpath)s')
SVN_ADD_CMD = AKARA_MODULE_CONFIG.get('svn_add', 'svn add %(fpath)s')

TARGET_SVNS = dict(( (k.split('-', 1)[1], AKARA_MODULE_CONFIG[k].rstrip('/') + '/') for k in AKARA_MODULE_CONFIG if k.startswith('svn-')))

SERVICE_ID = 'http://purl.org/akara/services/builtin/svncommit'
@simple_service('POST', SERVICE_ID, 'akara.svncommit', 'text/plain')
def svncommit(body, ctype, **params):
    '''
    Requires POST body of multipart/form-data
    
    Sample request:
    curl -F "POR=@foo.por" http://localhost:8880/spss.json
    curl -F "msg=akara test" -F "fpath=/path/to/file" -F "q=http://example.org/my-rest-request" http://localhost:8880/akara.svncommit
    '''
    #Useful:
    # * [[http://wiki.math.yorku.ca/index.php/R:_Data_conversion_from_SPSS|R: Data conversion from SPSS]]

    body = StringIO(body)
    form = cgi.FieldStorage(fp=body, environ=WSGI_ENVIRON)
    #for k in form:
    #    print >> sys.stderr, (k, form.getvalue(k)[:100])
    q = form.getvalue('q')
    fpath = form.getvalue('fpath')
    msg = form.getvalue('msg')
    #assert_not_equal(q, None, msg=Q_REQUIRED)

    if q:
        handler = copy_auth(WSGI_ENVIRON, q)
        opener = urllib2.build_opener(handler) if handler else urllib2.build_opener()
        req = urllib2.Request(q)
        with closing(opener.open(req)) as resp:
            result = resp.read()
            ctype = dict(resp.info()).get('Content-Type')

        with closing(open(fpath, 'w')) as f:
            f.write(result)

    cmdline = SVN_COMMIT_CMD%{'msg': msg, 'fpath': fpath}
    print >> sys.stderr, 'Executing subprocess in shell: ', cmdline
    
    process = Popen(cmdline, stdout=PIPE, universal_newlines=True, shell=True)
    output, perr = process.communicate()

    return 'SVN commit OK\n'


URL_REQUIRED = _("The 'URL' POST parameter is mandatory.")

SERVICE_ID = 'http://purl.org/akara/services/builtin/svncheckout'
@simple_service('GET', SERVICE_ID, 'akara.svncheckout')
def svncheckout(url=None):
    '''
    url - 
    
    Sample request:
    curl "http://localhost:8880/akara.svncheckout?url=http://zepheira.com"
    '''
    ids = set()
    url = first_item(url, next=partial(assert_not_equal, None, msg=URL_REQUIRED))
    with closing(urllib2.urlopen(url)) as resp:
        content = resp.read()
    resources = rdfaparse(content)
    return simplejson.dumps({'items': resources}, indent=4)

