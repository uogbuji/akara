from akara.opensearch import apply_template

import unittest

class Tests(unittest.TestCase):
    def raisesTypeError(self, f, *args, **kwargs):
        try:
            raise AssertionError( f(*args, **kwargs) )
        except TypeError, err:
            return str(err)

    #### These test the public API
    def test_no_expansion(self):
        self.assertEquals(apply_template("http://example.com/osd.xml"),
                          "http://example.com/osd.xml")
        self.assertEquals(apply_template(u"http://example.com/osd.xml"),
                          "http://example.com/osd.xml")
        
    def test_single_term(self):
        self.assertEquals(apply_template("http://example.com/search?q={searchTerms}",
                                         searchTerms="Andrew"),
                          "http://example.com/search?q=Andrew")
    def test_spaces(self):
        self.assertEquals(apply_template("http://example.com/search?q={searchTerms}",
                                         searchTerms="Andrew Dalke"),
                          "http://example.com/search?q=Andrew+Dalke")

    def test_many(self):
        T = "{scheme}://{host}:{port}/{path}?q={arg}#{hash}"
        self.assertEquals(apply_template(T, scheme="gopher",
                                         host="hole", port="70",
                                         path="somewhere/else",
                                         arg="spam & eggs",
                                         hash="browns"),
                          "gopher://hole:70/somewhere%2Felse?q=spam+%26+eggs#browns")
    def test_failure(self):
        self.assertRaises(KeyError, apply_template, "http://{host}/")

    def test_optional(self):
        self.assertEquals(apply_template("http://example.com/{arg?}"),
                          "http://example.com/")
        self.assertEquals(apply_template("http://example.com/{arg?}{arg?}"),
                          "http://example.com/")
        self.assertEquals(apply_template("http://example.com/{arg?}{arg?}", arg="X"),
                          "http://example.com/XX")

    def test_optional_in_scheme(self):
        err = self.raisesTypeError(apply_template, "{scheme?}://example.com/",
                                   scheme="gopher")
        assert err.startswith("URI scheme cannot be an optional template variable")

    def test_optional_in_hostname(self):
        err = self.raisesTypeError(apply_template, "scheme://{hostname?}.com/",
                                   hostname="example")
        assert err.startswith("URI hostname cannot contain an optional template variable")


    def test_unicode_failures(self):
        # Scheme cannot include Unicode
        self.assertRaises(UnicodeEncodeError, apply_template,
                          "{scheme}://blah", scheme=u"Espa\u00F1a")
        # Don't allow non-ascii characters except in the domain
        self.assertRaises(UnicodeEncodeError, apply_template,
                          u"http://google.com/search?q=Espa\u00F1a")
        self.assertRaises(UnicodeEncodeError, apply_template,
                          u"http://\u00F1{q}@example.com")
        

    def test_multiple_args_in_scheme(self):
        for (target, expected_err) in (
            ("{scheme}{scheme}://example.com/", "text or a single template field"),
            ("blah{scheme}://example.com", "text or a single template field"),
            ("blah/", "Missing or unparsable"),
            ):
            err = self.raisesTypeError(apply_template, target, scheme="http")
            assert expected_err in err, (target, expected_err, err)

    def test_unicode_in_host(self):
        # OpenSearch template does not allow this. I do.
        self.assertEquals(apply_template("https://{host}.name/", host=u"Espa\u00F1a"),
                          "https://xn--espaa-rta.name/")
        # I also allow Unicode in the host name (but only there!)
        self.assertEquals(apply_template(u"https://{host}.name/", host=u"Espa\u00F1a"),
                          "https://xn--espaa-rta.name/")
        self.assertEquals(apply_template(u"https://{host}.a\u00F1o/",
                                         host=u"Espa\u00F1a"),
                          "https://xn--espaa-rta.xn--ao-zja/")

    def test_unicode_in_host_part(self):
        # I double checked the encoding with Safari. Seems to be right
        self.assertEquals(apply_template(u"https://{host}.Espa\u00F1a/", host=u"a\u00F1o"),
                          "https://xn--ao-zja.xn--espaa-rta/")
        self.assertEquals(apply_template(u"http://{host}.\u00F1.name/", host=u"Espa\u00F1a"),
                          "http://xn--espaa-rta.xn--ida.name/")

    def test_unicode_in_path(self):
        # I double checked the encoding with Safari. Seems to be right
        self.assertEquals(apply_template("http://google.com/search?q={q}",
                                         q=u"Espa\u00F1a"),
                          "http://google.com/search?q=Espa%C3%B1a")
        self.assertEquals(apply_template(u"http://google.com/search?q={q}",
                                         q=u"Espa\u00F1a"),
                          "http://google.com/search?q=Espa%C3%B1a")


    def test_unicode_in_username(self):
        self.assertEquals(apply_template("http://{q}@example.com",
                                         q=u"Espa\u00F1a"),
                          "http://Espa%C3%B1a@example.com")


    def test_using_prefix(self):
        for uri in ("{spam:x}://dalke:blah@example.com/something",
                    "HTTP://{spam:x}:blah@example.com/something",
                    "HTTP://{spam:x}:blah@example.com/something",
                    "HTTP://dalke:{spam:x}@example.com/something",
                    "HTTP://dalke:blah@{spam:x}.com/something",
                    "HTTP://dalke:blah@example.com/{spam:x}"):
            err = self.raisesTypeError(apply_template, uri)
            assert err.startswith("Template prefix not supported in Akara (in '"), err
            # While this should work just fine
            t = apply_template(uri.replace("spam:", ""), x="123")

    def test_missing_slashes(self):
        for uri in ("http:spam",
                    "http:/spam",
                    "http:/?spam"):
            err = self.raisesTypeError(apply_template, uri)
            assert err.startswith("Missing required '//' in URI"), err
    def test_missing_hostname(self):
        for uri in ("http:///spam/",
                    "http:///spam",
                    "http://dalke@/spam",
                    "http://:@/spam",
                    "http://?spam"):
            err = self.raisesTypeError(apply_template, uri)
            assert err.startswith("Akara requires a hostname in the template"), err

    def test_empty_template_name(self):
        for uri in ("{}://example.com/",
                    "http://{}/",
                    "http://example.com?{}"):
            err = self.raisesTypeError(apply_template, uri)
            assert err.startswith("Empty template variable in '")
                    
    def test_bad_templates(self):
        for uri, c in (("{scheme://example.com/whatever}", "{"),
                       ("{scheme}://example.com/whatever}", "}"),
                       ("http://example.com?whatever=asdf#}", "}"),
                       ("http://example.com?whatever=asdf#{", "{")):
            err = self.raisesTypeError(apply_template, uri)
            assert err.startswith("Unexpected '" + c + "' found in URI"), err

    def test_port_errors(self):
        err = self.raisesTypeError(apply_template, "http://localhost:/")
        assert err.startswith("Port must be either a number or a template name")
        err = self.raisesTypeError(apply_template, "http://localhost:/a")
        assert err.startswith("Port must be either a number or a template name")
        err = self.raisesTypeError(apply_template, "http://localhost:{port}a/")
        assert err.startswith("Port may not contain anything after the template name"), err
        err = self.raisesTypeError(apply_template, "http://localhost:{port}/", port="q")
        assert err.startswith("Port template parameter 'port' is not an integer ('q')"), err
        err = self.raisesTypeError(apply_template, "http://localhost:{port}/", port="-80")
        assert err.startswith("Port template parameter 'port' is not an integer ('-80')")

    def test_port(self):
        self.assertEquals(apply_template("http://localhost:8765/"),
                          "http://localhost:8765/")
        self.assertEquals(apply_template("http://localhost:{port}/", port=8080),
                          "http://localhost:8080/")
        self.assertEquals(apply_template("http://localhost:{port}/", port="8080"),
                          "http://localhost:8080/")
        self.assertEquals(apply_template("http://localhost:{port}/abc", port=""),
                          "http://localhost/abc")
        self.assertEquals(apply_template("http://localhost:{port?}/?q"),
                          "http://localhost/?q")
        self.assertEquals(apply_template("http://localhost:{port?}/?q", port="123"),
                          "http://localhost:123/?q")
        
if __name__ == "__main__":
    unittest.main()
