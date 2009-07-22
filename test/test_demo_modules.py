from server_support import server

import urllib, urllib2
from urllib2 import urlopen
import os

from amara import bindery
from amara.tools import atomtools

# luckygoogle.py
def test_luckygoogle():
    url = server() + "akara.luckygoogle?q=google"
    response = urlopen(url)
    s = response.read()
    assert s == "http://www.google.com/\n", repr(s)

# atomtools.py
def test_atom_json():
    import simplejson
    url = server() + "akara.atom.json?url=http://zepheira.com/feeds/news.atom"
    response = urlopen(url)
    results = simplejson.load(response)
    items = results["items"]
    for item in items:
        assert "title" in item

def test_aggregate_atom():
    url = server() + "akara.aggregate.atom"
    response = urlopen(url)
    doc = bindery.parse(response, model=atomtools.FEED_MODEL)
    assert str(doc.feed.title[0]) == "Feed me!", str(doc.feed.title[0])
    assert len(doc.feed.entry) == 3, len(doc.feed.entry)

def test_webfeedjson():
    import simplejson
    url = server() + "akara.webfeed.json?url=http://feeds.delicious.com/v2/rss/recent%3Fmin=1%26count=15"
    response = urlopen(url)
    results = simplejson.load(response)
    print results

# calweb.py
# Frankly, this module doesn't seem that useful, so I'll only check
# to see that I get a response and that it contains a "bcCalendarToday"
def test_calendar():
    url = server() + "akara.calendar"
    s = urlopen(url).read()
    assert "bcCalendarToday" in s


# icaltools.py
def test_ical2json():
    import simplejson

    ical_filename = os.path.join(os.path.dirname(__file__), "resource", "icalendar_test.ics")
    url = server() + "ical.json"

    req = urllib2.Request(url)
    req.add_header('Content-Type', 'text/calendar')

    data = open(ical_filename).read()

    response = urllib2.urlopen(req, data)
    results = simplejson.load(response)

    items = results["items"]
    assert len(items) == 2
    assert items[0]["summary"] == "Bastille Day Party"
    assert items[1]["summary"] == "Akara test"

# markuptools.py

def test_akara_twc():
    url = server() + "akara.twc?max=5" # max 5 words in the result

    req = urllib2.Request(url)
    req.add_header('Content-Type', 'application/xml')

    data = "<a>one two <b>three four </b><c>five <d>six seven</d> eight</c> nine</a>"
    
    result = urllib2.urlopen(req, data).read()
    assert result == """\
<?xml version="1.0" encoding="UTF-8"?>
<html><head/><body><a>one two <b>three four </b><c>five </c></a></body></html>""", repr(result)

# NOTE: the underlying trim code is NOT correct. This checks the invalid output
# for consistency. See trac #11.
def test_akara_twc_html():
    url = server() + "akara.twc?html=yes" # max 500 words

    req = urllib2.Request(url)
    req.add_header('Content-Type', 'application/xml')

    data = ("<html><head/><body>" + " ".join(map(str, range(510))) + "</body></html>")
    
    result = urllib2.urlopen(req, data).read()
    assert result == """\
<?xml version="1.0" encoding="UTF-8"?>
<html><head/><body>0 1 2 3 4 5 6 7 8 9</body></html>""", repr(result)





if __name__ == "__main__":
    raise SystemExit("Use nosetests")
