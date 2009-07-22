from server_support import server

from urllib2 import urlopen
from amara import bindery
from amara.tools import atomtools

# luckygoogle.py
def test_luckygoogle():
    url = server() + "akara.luckygoogle?q=google"
    f = urlopen(url)
    s = f.read()
    assert s == "http://www.google.com/\n", repr(s)

# atomtools.py
def test_atom_json():
    import simplejson
    url = server() + "akara.atom.json?url=http://zepheira.com/feeds/news.atom"
    f = urlopen(url)
    results = simplejson.load(f)
    items = results["items"]
    for item in items:
        assert "title" in item

def test_aggregate_atom():
    url = server() + "akara.aggregate.atom"
    f = urlopen(url)
    doc = bindery.parse(f, model=atomtools.FEED_MODEL)
    assert str(doc.feed.title[0]) == "Feed me!", str(doc.feed.title[0])
    assert len(doc.feed.entry) == 3, len(doc.feed.entry)

def test_webfeedjson():
    import simplejson
    url = server() + "akara.webfeed.json?url=http://feeds.delicious.com/v2/rss/recent%3Fmin=1%26count=15"
    f = urlopen(url)
    results = simplejson.load(f)
    print results

# calweb.py
# Frankly, this module doesn't seem that useful, so I'll only check
# to see that I get a response and that it contains a "bcCalendarToday"
def test_calendar():
    url = server() + "akara.calendar"
    s = urlopen(url).read()
    assert "bcCalendarToday" in s



if __name__ == "__main__":
    raise SystemExit("Use nosetests")
