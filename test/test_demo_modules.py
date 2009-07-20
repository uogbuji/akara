from server_support import server

import urllib2


def test_luckygoogle():
    url = server() + "akara.luckygoogle?q=google"
    raise SystemExit(url)
    
    f = urllib2.urlopen(url)
    s = f.read()
    assert s == "http://www.google.com/\n", repr(s)

if __name__ == "__main__":
    raise SystemExit("Use nosetests")
