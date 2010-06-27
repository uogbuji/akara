# -*- encoding: utf-8 -*-
'''Demo of how to use Akara to talk with SVN via POST -- *INSECURE*

It includes an example of how to forward security information to a new
request.

This module takes an optional configuration section in akara.conf. The
default settings are:

class svntools:
    svn_commit = ["svn", "commit", "-m", "$MSG", "$FPATH"]
    svn_add = ["svn", "add", "$FPATH"]

where "$MSG" is replaced with the commit message (from the form
variable "msg") and "$FPATH" is replaced with the path to the file
under SVN.

NOTE: This demo module is *insecure*. Do not use in an untrusted
network. The module can be told to fetch an arbitrary URL and write
the result to an arbitrary file. It can also do SVN commits against
any accessible file in the file system.

'''
from __future__ import with_statement
import sys, time
import urllib, urllib2, urlparse
from subprocess import *
import cgi
from cStringIO import StringIO
from itertools import *
from contextlib import closing

from amara import _
from amara.lib.util import *

import akara
from akara.util import copy_auth
from akara.services import simple_service

Q_REQUIRED = _("The 'q' POST parameter is mandatory.")
SVN_COMMIT_CMD = akara.module_config().get('svn_commit', 'svn commit -m "%(msg)s" %(fpath)s')
SVN_ADD_CMD = akara.module_config().get('svn_add', 'svn add %(fpath)s')

SERVICE_ID = 'http://purl.org/akara/services/demo/svncommit'
@simple_service('POST', SERVICE_ID, 'akara.svncommit', 'text/plain')
def svncommit(body, ctype, **params):
    '''Commit a file. Can optionally populate the file contents from a given URL.

    The form parameters are:
      fpath - the name of the file to commit to SVN
      msg - the commit message
      q (optional) - fetch the given URL and save it to the specified file before commmiting
    
    The form must be POSTed as multipart/form-data. If the request includes
    the 'q' parameter then the new fetch will contain authentication 
    forward 
    
    Sample request:
      curl -F "msg=fixed a typo" -F fpath="/path/to/file" -F "q=http://example.org/content" http://localhost:8880/akara.svncommit

    '''
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

SERVICE_ID = 'http://purl.org/akara/services/demo/svncheckout'
@simple_service('GET', SERVICE_ID, 'akara.svncheckout')
def svncheckout(url=None):
    '''
    url - 
    
    Sample request:
    curl "http://localhost:8880/akara.svncheckout?url=http://zepheira.com"
    '''
    # Requires Python 2.6 or http://code.google.com/p/json/
    from amara.thirdparty import json
    ids = set()
    if url is None:
        raise AssertionError(URL_REQUIRED)
    with closing(urllib2.urlopen(url)) as resp:
        content = resp.read()
    resources = rdfaparse(content)
    return json.dumps({'items': resources}, indent=4)

