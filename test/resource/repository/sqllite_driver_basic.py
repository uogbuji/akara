import unittest
from amara.lib import testsupport
import os
import tempfile
import sqlite3
from cStringIO import StringIO
import amara

from akara.resource.repository import driver

MONTY_XML = """<monty>
  <python spam="eggs">What do you mean "bleh"</python>
  <python ministry="abuse">But I was looking for argument</python>
</monty>"""

NS_XML = """<doc xmlns:a="urn:bogus:a" xmlns:b="urn:bogus:b">
  <a:monty/>
  <b:python/>
</doc>"""

#TEST_FILE = "Xml/Core/disclaimer.xml"

### modify this url
#TEST_URL = "http://cvs.4suite.org/viewcvs/*checkout*/4Suite/test/Xml/Core/disclaimer.xml"


class Test_parse_functions_1(unittest.TestCase):
    """Testing local sources"""
    def test_simple_roundtrip(self):
        """Parse with string"""
        def myindex(content):
            doc = amara.parse(content)
            yield u'root-element-name', doc.xml_select(u'name(*)')
            yield u'element-count', doc.xml_select(u'count(//*)')
        fname = tempfile.mktemp('.xml')
        driver.init_db(sqlite3.connect(fname))
        drv = driver(sqlite3.connect(fname))
        content = MONTY_XML
        id = drv.create_resource(StringIO(content), metadata=dict(myindex(content)))
        content1, metadata = drv.get_resource(id)
        content1 = content1.read()
        doc = amara.parse(content)
        self.assertEqual(content, content1)
        self.assertEqual(metadata[u'root-element-name'], doc.xml_select(u'name(*)'))
        self.assertEqual(metadata[u'element-count'], doc.xml_select(u'count(//*)'))
        return


if __name__ == '__main__':
    testsupport.test_main()
