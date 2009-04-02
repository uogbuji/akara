# -*- encoding: utf-8 -*-
'''
A tool for convenient viewing of log files
'''

import sys, time
import urllib2
#from cgi import parse_qs
#from cStringIO import StringIO
from itertools import *

import simplejson

#from amara.tools.atomtools import feed
from amara.tools import rdfascrape

from akara.services import simple_service, response

#def rdfa2json(url=None):
#Support POST body as well

LOGLINE_PAT = re.compile(r'(?P<origin>\d+\.\d+\.\d+\.\d+) '
+r'(?P<identd>-|\w*) (?P<auth>-|\w*) '
+r'\[(?P<date>[^\[\]:]+):(?P<time>\d+:\d+:\d+) (?P<tz>[\-\+]?\d\d\d\d)\] '
+r'(?P<request>"[^"]*") (?P<status>\d+) (?P<bytes>-|\d+) (?P<referrer>"[^"]*") (?P<client>".*")\s*\Z')

#For logs with destination host (at the beginning)
#LOGLINE_PAT = re.compile(r'(?P<targetserver>\S+) (?P<origin>\d+\.\d+\.\d+\.\d+) '
#+r'(?P<identd>-|\w*) (?P<auth>-|\w*) '
#+r'\[(?P<date>[^\[\]:]+):(?P<time>\d+:\d+:\d+) (?P<tz>[\-\+]?\d\d\d\d)\] '
#+r'(?P<request>"[^"]*") (?P<status>\d+) (?P<bytes>-|\d+) (?P<referrer>"[^"]*") (?P<client>".*")\s*\Z')

#For logs where referrer and UA may not be included
#LOGLINE_PAT = re.compile(r'(\d+\.\d+\.\d+\.\d+) (-|\w*) (-|\w*) '
#+r'\[([^\[\]:]+):(\d+:\d+:\d+) -(\d\d\d\d)\] '
#+r'("[^"]*") (\d+) (-|\d+) ("[^"]*")? (".*")?\s*\Z')

MAXRECORDS = 1000

SERVICE_ID = 'http://purl.org/akara/services/builtin/wwwlog.json'
#@simple_service('get', SERVICE_ID, 'akara.wwwlog.json', 'application/json')
@simple_service('post', SERVICE_ID, 'akara.wwwlog.json', 'application/json')
def wwwlog2json(body, ctype, url=None):
    ids = sets.Set()
    entries = []
    #for line in fp:
    #postinput = fp.readlines(clen)
    #print "GRIPPO", postinput
    for count, line in enumerate(body.splitlines()):
        if count > MAXRECORDS: break
        a = LOGLINE_PAT.match(line)
        entry = {}
        if a is not None:
            date = time.strftime("%Y-%m-%dT%H:%M:%S", feedparser._parse_date(a.group('date').replace('/', ' ') + ' ' + a.group('time')))
            localizedtime = time.strftime("%a, %d %b %Y %H:%M:%S", feedparser._parse_date(a.group('date').replace('/', ' ') + ' ' + a.group('time')))
            entry['id'] = a.group('origin') + ':' + date
            if entry['id'] in ids:
                print >> log, "Eeeeek!  A Dupe!", entry['id']
                continue
            entry['label'] = entry['id']
            entry['origin'] = a.group('origin')
            entry['identd'] = a.group('identd')
            entry['auth'] = a.group('auth')
            entry['timestamp'] = date
            entry['localizedtime'] = localizedtime
            entry['request'] = a.group('request').strip('""')
            parts = entry['request'].split()
            entry['request_path'] = ' '.join(parts[1:-1])
            entry['request_method'] = parts[0]
            entry['request_version'] = parts[-1]
            entry['status'] = a.group('status')
            entry['status'] += ' ' + httplib.responses[int(entry['status'])]
            entry['bytes'] = a.group('bytes')
            entry['referrer'] = a.group('referrer').strip('""')
            entry['client'] = a.group('client').strip('""')
            
            entry['latlong'] = ''
            if True:
            #if locateipfor and entry['request_path'].find(locateipfor) != -1:
                result = ip2geo(entry['ip'], db, log)
                if result is not None:
                    entry.update(result)
            ids.add(entry['id'])
            entries.append(entry)
        else:
            print >> log, 'Unable to parse line: ', line
    return simplejson.dumps({'items': entries}, indent=4)

