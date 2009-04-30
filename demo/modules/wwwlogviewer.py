# -*- encoding: utf-8 -*-
'''
A tool for convenient viewing of log files
'''

#See also: Beazley's approach: http://www.dabeaz.com/generators/Generators.pdf (slide 61 et seq)

import sys, time, re
import urllib2
import httplib
import datetime
#from cgi import parse_qs
#from cStringIO import StringIO
from itertools import *

# http://pypi.python.org/pypi/simplejson
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

# This regular expresion is the heart of the code.
# Python uses Perl regex, so it should be readily portable
# The r'' string form is just a convenience so you don't have to escape backslashes
COMBINED_LOGLINE_PAT = re.compile(
  r'(?P<origin>\d+\.\d+\.\d+\.\d+) '
+ r'(?P<identd>-|\w*) (?P<auth>-|\w*) '
+ r'\[(?P<ts>(?P<date>[^\[\]:]+):(?P<time>\d+:\d+:\d+)) (?P<tz>[\-\+]?\d\d\d\d)\] '
+ r'"(?P<method>\w+) (?P<path>[\S]+) (?P<protocol>[^"]+)" (?P<status>\d+) (?P<bytes>-|\d+)'
+ r'( (?P<referrer>"[^"]*")( (?P<client>"[^"]*")( (?P<cookie>"[^"]*"))?)?)?\s*\Z'
)

# Patterns in the client field for sniffing out bots
BOT_TRACES = [
    (re.compile(r".*http://help\.yahoo\.com/help/us/ysearch/slurp.*"),
        "Yahoo robot"),
    (re.compile(r".*\+http://www\.google\.com/bot\.html.*"),
        "Google robot"),
    (re.compile(r".*\+http://about\.ask\.com/en/docs/about/webmasters.shtml.*"),
        "Ask Jeeves/Teoma robot"),
    (re.compile(r".*\+http://search\.msn\.com\/msnbot\.htm.*"),
        "MSN robot"),
    (re.compile(r".*http://www\.entireweb\.com/about/search_tech/speedy_spider/.*"),
        "Speedy Spider"),
    (re.compile(r".*\+http://www\.baidu\.com/search/spider_jp\.html.*"),
        "Baidu spider"),
    (re.compile(r".*\+http://www\.gigablast\.com/spider\.html.*"),
        "Gigabot robot"),
]

# Apache's date/time format is very messy, so dealing with it is messy
# This class provides support for managing timezones in the Apache time field
# Reuses some code from: http://seehuhn.de/blog/52
class timezone(datetime.tzinfo):
    def __init__(self, name="+0000"):
        self.name = name
        seconds = int(name[:-2])*3600+int(name[-2:])*60
        self.offset = datetime.timedelta(seconds=seconds)

    def utcoffset(self, dt):
        return self.offset

    def dst(self, dt):
        return timedelta(0)

    def tzname(self, dt):
        return self.name


def parse_apache_date(date_str, tz_str):
    '''
    Parse the timestamp from the Apache log file, and return a datetime object
    '''
    tt = time.strptime(date_str, "%d/%b/%Y:%H:%M:%S")
    tt = tt[:6] + (0, timezone(tz_str))
    return datetime.datetime(*tt)


def bot_check(match_info):
    '''
    Return True if the matched line looks like a robot
    '''
    for pat, botname in BOT_TRACES:
        if pat.match(match_info.group('client')):
            return True
            break
    return False


SERVICE_ID = 'http://purl.org/akara/services/builtin/wwwlog.json'
@simple_service('POST', SERVICE_ID, 'akara.wwwlog.json', 'application/json')
def wwwlog2json(body, ctype, maxrecords=None, nobots=False):
    '''
    Convert Apache log info to Exhibit JSON
    (see: http://www.ibm.com/developerworks/web/library/wa-realweb6/ )

    Sample request:
    * curl --request POST --data-binary "@access.log" --header "Content-Type: text/plain" "http://localhost:8880/akara.wwwlog.json"
    '''
    entries = []
    #for count, line in enumerate(itertools.islice(sys.stdin, 0, MAXRECORDS)):
    for count, line in enumerate(body.splitlines()):
        if maxrecords and count > maxrecords: break
        match_info = COMBINED_LOGLINE_PAT.match(line)
        if not match_info:
            print >> sys.stderr, "Unable to parse log line: ", line
            continue
        # If you want to include robot clients, comment out the next two lines
        if nobots and bot_check(match_info):
            continue
        entry = {}
        timestamp = parse_apache_date(match_info.group('ts'), match_info.group('tz'))
        timestamp_str = timestamp.isoformat()
        # To make Exhibit happy, set id and label fields that give some information
        # about the entry, but are unique across all entries (ensured by appending count)
        entry['id'] = match_info.group('origin') + ':' + timestamp_str + ':' + str(count)
        entry['label'] = entry['id']
        entry['origin'] = match_info.group('origin')
        entry['timestamp'] = timestamp_str
        entry['path'] = match_info.group('path')
        entry['method'] = match_info.group('method')
        entry['protocol'] = match_info.group('protocol')
        entry['status'] = match_info.group('status')
        entry['status'] += ' ' + httplib.responses[int(entry['status'])]
        if match_info.group('bytes') != '-':
            entry['bytes'] = match_info.group('bytes')
        if match_info.group('referrer') != '"-"':
            entry['referrer'] = match_info.group('referrer')
        entry['client'] = match_info.group('client')
        entries.append(entry)
    return simplejson.dumps({'items': entries}, indent=4)

"""
#Geolocation support
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

"""
