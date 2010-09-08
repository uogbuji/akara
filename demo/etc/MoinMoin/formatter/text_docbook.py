# -*- coding: iso-8859-1 -*-
"""
    MoinMoin - DocBook Formatter

    @copyright: 2010 by Uche ogbuji <uche@ogbuji.net>
    
    Based on 4Suite version by:
    @copyright: 2005,2008 by Mikko Virkkilä <mvirkkil@cc.hut.fi>
    @copyright: 2005 by MoinMoin:AlexanderSchremmer (small modifications)
    @copyright: 2005 by MoinMoin:Petr Pytelka <pyta@lightcomp.com> (small modifications)

    @license: GNU GPL, see COPYING for details.
"""

import os
import StringIO

try:
    import amara
    from amara import tree #Amara 2.x-only
except ImportError:
    raise InternalError("You need to install Amara 2.x to use this version of the DocBook formatter.")

from MoinMoin.formatter import FormatterBase
from MoinMoin import wikiutil
from MoinMoin.action import AttachFile

#For revision history
from MoinMoin.logfile import editlog
from MoinMoin import user


class Formatter(FormatterBase):
    #TODO: How to handle revision history and other meta-info from included files?
    #      The problem is that we don't know what the original page is, since
    #      the Inlcude-macro doesn't pass us the information.

    # this list is extended as the page is parsed. Could be optimized by adding them here?
    section_should_break = [u'abstract', u'para', u'emphasis']

    blacklisted_macros = ('TableOfContents', 'ShowSmileys', 'Navigation')

    # If the current node is one of the following and we are about the emit
    # text, the text should be wrapped in a paragraph
    wrap_text_in_para = (u'listitem', u'glossdef', u'article', u'chapter', u'tip', u'warning', u'note', u'caution', u'important')

    # from dtd
    _can_contain_section = (u"section", u"appendix", u"article", u"chapter", u"patintro", u"preface")

    def __init__(self, request, doctype=u"article", **kw):
        FormatterBase.__init__(self, request, **kw)
        self.request = request

        '''
        If the formatter is used by the Include macro, it will set
        is_included=True in which case we know we need to call startDocument
        and endDocument from startContent and endContent respectively, since
        the Include macro will not be calling them, and the formatter doesn't
        work properly unless they are called.
        '''
        if kw.has_key("is_included") and kw["is_included"]:
            self.include_kludge = True
        else:
            self.include_kludge = False

        self.doctype = doctype
        self.curdepth = 0
        self.cur = None

    def startDocument(self, pagename):
        self.doc = tree.entity()
        self.doc.xml_public_id = "-//OASIS//DTD DocBook XML V4.4//EN"
        self.doc.xml_system_id = "http://www.docbook.org/xml/4.4/docbookx.dtd"
        self.root = tree.element(None, unicode(self.doctype))
        self.doc.xml_append(self.root)
        self.title = pagename
        if not self.include_kludge and self.doctype == u"article":
            info = tree.element(None, u"articleinfo")
            self.root.xml_append(info)
            self._addTitleElement(self.title, targetNode=info)
            self._addRevisionHistory(targetNode=info)
        else:
            self._addTitleElement(self.title, targetNode=self.root)

        self.cur = self.root
        return ""

    def startContent(self, content_id="content", **kw):
        if self.include_kludge and not self.cur:
            return self.startDocument(u"OnlyAnIdiotWouldCreateSuchaPage")
        return ""

    def endContent(self):
        if self.include_kludge:
            return self.endDocument()
        return ""

    def endDocument(self):
        txt = self.doc.xml_encode()
        self.cur = None
        return txt

    def text(self, text, **kw):
        if text == u"\\n":
            srcText = u"\n"
        else:
            srcText = text

        if srcText and self._isInsidePreformatted():
            # 4Suite version used CDATASection nodes.  Don't bother
            self.cur.xml_last_child.xml_append(tree.text(srcText))

        elif self.cur.xml_qname in self.wrap_text_in_para:
            """
            If we already wrapped one text item in a para, we should add to that para
            and not create a new one. Another question is if we should add a space?
            """
            if self.cur.xml_last_child is not None and self.cur.xml_last_child.xml_qname == u'para':
                self.cur.xml_last_child.xml_append(tree.text(srcText))
            else:
                self.paragraph(1)
                self.text(text)
                self.paragraph(0)
        else:
            self.cur.xml_append(tree.text(srcText))
        return ""

    def heading(self, on, depth, **kw):
        while self.cur.xml_qname in self.section_should_break:
            self.cur = self.cur.xml_parent

        if on:
            # try to go to higher level if needed
            if depth <= self.curdepth:
                # number of levels we want to go higher
                numberOfLevels = self.curdepth - depth + 1
                for dummy in range(numberOfLevels):
                    # find first non section node
                    while not self.cur.xml_qname in self._can_contain_section:
                        self.cur = self.cur.xml_parent

                    if self.cur.xml_qname == u"section":
                        self.cur = self.cur.xml_parent

            section = tree.element(None, u"section")
            self.cur.xml_append(section)
            self.cur = section

            title = tree.element(None, u"title")
            self.cur.xml_append(title)
            self.cur = title
            self.curdepth = depth
        else:
            self.cur = self.cur.xml_parent

        return ""

    def paragraph(self, on, **kw):
        FormatterBase.paragraph(self, on)

        # Let's prevent empty paras
        if not on:
            if not self._hasContent(self.cur):
                oldnode = self.cur
                self.cur = oldnode.xml_parent
                self.cur.xml_remove(oldnode)
                return ""

        # Let's prevent para inside para
        if on and self.cur.xml_qname == u"para":
            return ""
        return self._handleNode(u"para", on)

    def linebreak(self, preformatted=1):
        """
        If preformatted, it will simply output a linebreak.
        If we are in a paragraph, we will close it, and open another one.
        """
        if preformatted:
            self.text(u'\\n')
        elif self.cur.xml_qname == u"para":
            self.paragraph(0)
            self.paragraph(1)
        else:
            self._emitComment(u"Warning: Probably not emitting right sort of linebreak")
            self.text(u'\n')
        return ""

### Inline ##########################################################

    def strong(self, on, **kw):
        return self._handleFormatting(u"emphasis", on, ((u'role', u'strong'), ))

    def emphasis(self, on, **kw):
        return self._handleFormatting(u"emphasis", on)

    def underline(self, on, **kw):
        return self._handleFormatting(u"emphasis", on, ((u'role', u'underline'), ))

    def highlight(self, on, **kw):
        return self._handleFormatting(u"emphasis", on, ((u'role', u'highlight'), ))

    def sup(self, on, **kw):
        return self._handleFormatting(u"superscript", on)

    def sub(self, on, **kw):
        return self._handleFormatting(u"subscript", on)

    def strike(self, on, **kw):
        # does not yield <strike> using the HTML XSLT files here ...
        # but seems to be correct
        return self._handleFormatting(u"emphasis", on,
                                      ((u'role', u'strikethrough'), ))

    def code(self, on, **kw):
        # Let's prevent empty code
        if not on:
            if not self._hasContent(self.cur):
                oldnode = self.cur
                self.cur = oldnode.xml_parent
                self.cur.xml_remove(oldnode)
                return ""
        return self._handleFormatting(u"code", on)

    def preformatted(self, on, **kw):
        return self._handleFormatting(u"screen", on)


### Lists ###########################################################

    def number_list(self, on, type=None, start=None, **kw):
        docbook_ol_types = {'1': "arabic",
                            'a': "loweralpha",
                            'A': "upperalpha",
                            'i': "lowerroman",
                            'I': "upperroman"}

        if type and docbook_ol_types.has_key(type):
            attrs = [("numeration", docbook_ol_types[type])]
        else:
            attrs = []

        return self._handleNode('orderedlist', on, attrs)

    def bullet_list(self, on, **kw):
        return self._handleNode(u"itemizedlist", on)

    def listitem(self, on, style=None, **kw):
        if self.cur.xml_qname == u"glosslist" or self.cur.xml_qname == u"glossentry":
            return self.definition_desc(on)
        if on and self.cur.xml_qname == u"listitem":
            """If we are inside a listitem, and someone wants to create a new one, it
            means they forgot to close the old one, and we need to do it for them."""
            self.listitem(0)

        args = []
        if on and style:
            styles = self._convertStylesToDict(style)
            if styles.has_key('list-style-type'):
                args.append(('override', styles['list-style-type']))

        return self._handleNode("listitem", on, attributes=args)

    def definition_list(self, on, **kw):
        return self._handleNode(u"glosslist", on)

    def definition_term(self, on, compact=0, **kw):
        if on:
            self._handleNode(u"glossentry", on)
            self._handleNode(u"glossterm", on)
        else:
            if self._hasContent(self.cur):
                self._handleNode(u"glossterm", on)
                self._handleNode(u"glossentry", on)
            else:
                # No term info :(
                term = self.cur
                entry = term.xml_parent
                self.cur = entry.xml_parent
                self.cur.xml_remove(entry)
        return ""

    def definition_desc(self, on, **kw):
        if on:
            if self.cur.xml_qname == u"glossentry":
                # Good, we can add it here.
                self._handleNode(u"glossdef", on)
                return ""

            # We are somewhere else, let's see...
            if self.cur.xml_qname != u"glosslist":
                self._emitComment(u"Trying to add a definition, but we arent in a glosslist")
                return ""
            if not self.cur.xml_last_child or not isinstance(self.cur.xml_last_child, tree.element) or self.cur.xml_last_child.xml_qname != u"glossentry":
                self._emitComment(u"Trying to add a definition, but there is no entry")
                return ""

            # Found it, calling again
            self.cur = self.cur.xml_last_child
            return self.definition_desc(on)
        else:
            if not self._hasContent(self.cur):
                # Seems no valuable info was added
                assert(self.cur.xml_qname == u"glossdef")
                toRemove = self.cur
                self.cur = toRemove.xml_parent
                self.cur.xml_remove(toRemove)

            while self.cur.xml_qname != u"glosslist":
                self.cur = self.cur.xml_parent
        return ""

### Links ###########################################################
    # TODO: Fix anchors to documents which are included. Needs probably to be
    #       a postprocessing rule. Could be done by having the anchors have
    #       the "linkend" value of PageName#anchor. Then at post process the
    #       following would be done for all urls:
    #        - get all ulinks with an anchor part in their url
    #        - get the ulink's PageName#anchor -part by removing baseurl part
    #        - if any of our <anchor> elements have the same PageName#anchor
    #          value as our <ulink>, then replace the ulink with a link
    #          element.
    #       Note: This would the case when someone wants to link to a
    #             section on the original webpage impossible. The link would
    #             instead point within the docbook page and not to the webpage.


    def pagelink(self, on, pagename='', page=None, **kw):
        FormatterBase.pagelink(self, on, pagename, page, **kw)
        return self.interwikilink(on, 'Self', pagename, **kw)

    def interwikilink(self, on, interwiki='', pagename='', **kw):
        if not on:
            return self.url(on, **kw)

        wikitag, wikiurl, wikitail, wikitag_bad = wikiutil.resolve_interwiki(self.request, interwiki, pagename)
        wikiurl = wikiutil.mapURL(self.request, wikiurl)
        href = wikiutil.join_wiki(wikiurl, wikitail)
        if kw.has_key("anchor"):
            href="%s#%s"%(href, kw['anchor'])

        if pagename == self.page.page_name:
            kw['is_self']=True

        return self.url(on, href, **kw)

    def url(self, on, url=None, css=None, **kw):
        if url and url.startswith("/"):
            # convert to absolute path:
            url = "%s%s"%(self.request.getBaseURL(), url)

        if not on:
            self._cleanupUlinkNode()

        if kw.has_key("anchor") and kw.has_key("is_self") and kw["is_self"]:
            #handle the case where we are pointing to somewhere insidee our own document
            return self._handleNode(u"link", on, attributes=((u'linkend', kw["anchor"]), ))
        else:
            return self._handleNode(u"ulink", on, attributes=((u'url', url), ))

    def anchordef(self, name):
        self._handleNode(u"anchor", True, attributes=((u'id', name), ))
        self._handleNode(u"anchor", False)
        return ""

    def anchorlink(self, on, name='', **kw):
        linkid = kw.get('id', None)
        attrs = []
        if name != '':
            attrs.append(('endterm', name))
        if id is not None:
            attrs.append(('linkend', linkid))
        elif name != '':
            attrs.append(('linkend', name))

        return self._handleNode("link", on, attrs)

### Attachments ######################################################

    def attachment_link(self, on, url=None, **kw):
        assert on in (0, 1, False, True) # make sure we get called the new way, not like the 1.5 api was
        # we do not output a "upload link" when outputting docbook
        if on:
            pagename, filename = AttachFile.absoluteName(url, self.page.page_name)
            fname = wikiutil.taintfilename(filename)
            target = AttachFile.getAttachUrl(pagename, filename, self.request)
            return self.url(1, target, title="attachment:%s" % url)
        else:
            return self.url(0)

    def attachment_image(self, url, **kw):
        """
        Figures out the absolute path to the image and then hands over to
        the image function. Any title is also handed over, and an additional
        title suggestion is made based on filename. The image function will
        use the suggestion if no other text alternative is found.

        If the file is not found, then a simple text will replace it.
        """
        _ = self.request.getText
        pagename, filename = AttachFile.absoluteName(url, self.page.page_name)
        fname = wikiutil.taintfilename(filename)
        fpath = AttachFile.getFilename(self.request, pagename, fname)
        if not os.path.exists(fpath):
            return self.text(u"[attachment:%s]" % url)
        else:
            return self.image(
                src=AttachFile.getAttachUrl(pagename, filename,
                                            self.request, addts=1),
                attachment_title=url,
                **kw)


    def attachment_drawing(self, url, text, **kw):
        _ = self.request.getText
        pagename, filename = AttachFile.absoluteName(url, self.page.page_name)
        fname = wikiutil.taintfilename(filename)
        drawing = fname
        fname = fname + ".png"
        filename = filename + ".png"
        fpath = AttachFile.getFilename(self.request, pagename, fname)
        if not os.path.exists(fpath):
            return self.text(u"[drawing:%s]" % url)
        else:
            src = AttachFile.getAttachUrl(pagename, filename, self.request, addts=1)
            return self.image(alt=drawing, src=src, html_class="drawing")

### Images and Smileys ##############################################

    def image(self, src=None, **kw):
        if src:
            kw['src'] = src
        media = tree.element(None, u"inlinemediaobject")
        imagewrap = tree.element(None, u"imageobject")

        media.xml_append(imagewrap)

        image = tree.element(None, u"imagedata")
        if kw.has_key('src'):
            src = kw['src']
            if src.startswith("/"):
                # convert to absolute path:
                src = self.request.getBaseURL()+src
            image.xml_attributes[u'fileref'] = src.decode('utf-8')
        if kw.has_key('width'):
            image.xml_attributes[u'width'] = unicode(kw['width'])
        if kw.has_key('height'):
            image.xml_attributes[u'depth'] = unicode(kw['height'])
        imagewrap.xml_append(image)

        # Look for any suitable title, order is important.
        title = ''
        for a in ('title', 'html_title', 'alt', 'html_alt', 'attachment_title'):
            if kw.has_key(a):
                title = kw[a]
                break
        if title:
            txtcontainer = tree.element(None, u"textobject")
            self._addTextElem(txtcontainer, u"phrase", title)
            media.xml_append(txtcontainer)

        self.cur.xml_append(media)
        return ""

    def transclusion(self, on, **kw):
        # TODO, see text_html formatter
        self._emitComment(u'transclusion is not implemented in DocBook formatter')
        return ""

    def transclusion_param(self, **kw):
        # TODO, see text_html formatter
        self._emitComment(u'transclusion parameters are not implemented in DocBook formatter')
        return ""

    def smiley(self, text):
        return self.request.theme.make_icon(text)

    def icon(self, type):
        return '' # self.request.theme.make_icon(type)


### Code area #######################################################

    def code_area(self, on, code_id, code_type=None, show=0, start=-1, step=-1):
        """Creates a formatted code region using screen or programlisting,
        depending on if a programming language was defined (code_type).

        The code_id is not used for anything in this formatter, but is just
        there to remain compatible with the HTML formatter's function.

        Line numbering is supported natively by DocBook so if linenumbering
        is requested the relevant attribute will be set.

        Call once with on=1 to start the region, and a second time
        with on=0 to end it.
        """

        if not on:
            return self._handleNode(None, on)

        show = show and 'numbered' or 'unnumbered'
        if start < 1:
            start = 1

        programming_languages = {"ColorizedJava": "java",
                                 "ColorizedPython": "python",
                                 "ColorizedCPlusPlus": "c++",
                                 "ColorizedPascal": "pascal",
                                }

        if code_type is None:
            attrs = ((u'linenumbering', show),
                     (u'startinglinenumber', str(start)),
                     (u'format', 'linespecific'),
                     )
            return self._handleNode("screen", on, attributes=attrs)
        else:
            if programming_languages.has_key(code_type):
                code_type = programming_languages[code_type]

            attrs = ((u'linenumbering', show),
                     (u'startinglinenumber', unicode(start)),
                     (u'language', code_type),
                     (u'format', u'linespecific'),
                     )
            return self._handleNode("programlisting", on, attributes=attrs)

    def code_line(self, on):
        if on:
            self.cur.xml_append(tree.text(u'\n'))
        return ''

    def code_token(self, on, tok_type):
        """
        DocBook has some support for semantic annotation of code so the
        known tokens will be mapped to DocBook entities.
        """
        toks_map = {'ID': 'methodname',
                    'Operator': '',
                    'Char': '',
                    'Comment': 'lineannotation',
                    'Number': '',
                    'String': 'phrase',
                    'SPChar': '',
                    'ResWord': 'token',
                    'ConsWord': 'symbol',
                    'Error': 'errortext',
                    'ResWord2': 'type',
                    'Special': '',
                    'Preprc': '',
                    'Text': '',
                   }
        if toks_map.has_key(tok_type) and toks_map[tok_type]:
            return self._handleFormatting(toks_map[tok_type], on)
        else:
            return ""
### Macro ###########################################################

    def macro(self, macro_obj, name, args, markup=None):
        """As far as the DocBook formatter is concerned there are three
        kinds of macros: Bad, Handled and Unknown.

        The Bad ones are the ones that are known not to work, and are on its
        blacklist. They will be ignored and an XML comment will be written
        noting that the macro is not supported.

        Handled macros are such macros that code is written to handle them.
        For example for the FootNote macro it means that instead of executing
        the macro, a DocBook footnote entity is created, with the relevant
        pieces of information filles in.

        The Unknown are handled by executing the macro and capturing any
        textual output. There shouldn't be any textual output since macros
        should call formatter methods. This is unfortunately not always true,
        so the output it is then fed in to an xml parser and the
        resulting nodes copied to the DocBook-dom tree. If the output is not
        valid xml then a comment is written in the DocBook that the macro
        should be fixed.

        """
        # Another alternative would be to feed the output to rawHTML or even
        # combining these two approaches. The _best_ alternative would be to
        # fix the macros.
        excludes=(u"articleinfo", u"title")

        if name in self.blacklisted_macros:
            self._emitComment("The macro %s doesn't work with the DocBook formatter." % name)

        elif name == u"FootNote":
            footnote = tree.element(None, u"footnote")
            self._addTextElem(footnote, u"para", str(args))
            self.cur.xml_append(footnote)

        elif name == u"Include":
            was_in_para = self.cur.xml_qname == u"para"
            if was_in_para:
                self.paragraph(0)
            text = FormatterBase.macro(self, macro_obj, name, args)
            if text.strip():
                self._includeExternalDocument(text, exclude=excludes)
            if was_in_para:
                self.paragraph(1)

        else:
            text = FormatterBase.macro(self, macro_obj, name, args)
            if text:
                try:
                    self._includeExternalDocument(text, exclude=excludes)
                #FIXME: check for parse-related errors, realy
                except ExpatError:
                    self._emitComment(u"The macro %s caused an error and should be blacklisted (and you might want to file a bug with the developer). It returned the following data which caused the docbook-formatter to choke. '%s'" % (name, text))

        return u""

### Util functions ##################################################

    def _includeExternalDocument(self, source, target=None, exclude=()):
        if not target:
            target = self.cur

        extdoc = amara.parse(source)
        for node in extdoc.xml_select(u'/*/node()'):
            if isinstance(node, tree.element) and node.xml_qname in exclude:
                pass
            elif target.xml_qname == u"para" and node.xml_qname == u"para":
                for pchild in node.xml_children:
                    target.xml_append(pchild)
                self.cur = target.xml_parent
            else:
                target.xml_append(node)

    def _emitComment(self, text):
        text = text.replace(u"--", u"- -") # There cannot be "--" in XML comment
        self.cur.xml_append(tree.comment(text))

    def _handleNode(self, name, on, attributes=()):
        if on:
            node = tree.element(None, name)
            self.cur.xml_append(node)
            if len(attributes) > 0:
                for name, value in attributes:
                    node.xml_attributes[None, name] = value
            self.cur = node
        else:
            """
                Because we prevent para inside para, we might get extra "please
                exit para" when we are no longer inside one.

                TODO: Maybe rethink the para in para case
            """
            if name == u"para" and self.cur.xml_qname != u"para":
                return ""

            self.cur = self.cur.xml_parent
        return ""

    def _handleFormatting(self, name, on, attributes=()):
        # We add all the elements we create to the list of elements that should not contain a section
        if name not in self.section_should_break:
            self.section_should_break.append(name)
        return self._handleNode(name, on, attributes)

    def _isInsidePreformatted(self):
        """Walks all parents and checks if one is of a preformatted type, which
           means the child would need to be preformatted == embedded in a cdata
           section"""
        return bool(self.cur.xml_select(u'ancestor::screen|ancestor::programlisting'))

    def _hasContent(self, node):
        if not isinstance(node, tree.element): return False
        if len(node.xml_attributes.keys()):
            return True
        for child in node.xml_children:
            if isinstance(child, tree.text) and child.xml_value.strip():
                return True
            #elif child.nodeType == Node.CDATA_SECTION_NODE and child.nodeValue.strip():
            #    return True

            if self._hasContent(child):
                return True
        return False

    def _addTitleElement(self, titleTxt, targetNode=None):
        if not targetNode:
            targetNode = self.cur
        self._addTextElem(targetNode, u"title", titleTxt)

    def _convertStylesToDict(self, styles):
        '''Takes the CSS styling information and converts it to a dict'''
        attrs = {}
        for s in styles.split(";"):
            if s.strip(' "') == "":
                continue
            if ":" not in s:
                continue
            (key, value) = s.split(":", 1)
            key = key.strip(' "')
            value = value.strip(' "')

            if key == 'vertical-align':
                key = 'valign'
            elif key == 'text-align':
                key = 'align'
            elif key == 'background-color':
                key = 'bgcolor'

            attrs[key] = value
        return attrs

    def _cleanupUlinkNode(self):
        """
        Moin adds the url as the text to a link, if no text is specified.
        Docbook does it when a docbook is rendered, so we don't want moin to
        do it and so if the url is exactly the same as the text node inside
        the ulink, we remove the text node.
        """
        if self.cur.xml_qname == u"ulink" and len(self.cur.xml_children) == 1 \
                and isinstance(self.cur.xml_first_child, tree.text) \
                and self.cur.xml_first_child.xml_value.strip() == self.cur.xml_attributes[None, u'url'].strip():
            self.cur.xml_remove(self.cur.xml_first_child)

    def _addTextElem(self, target, elemName, text):
        """
        Creates an element of the name elemName and adds a text node to it
        with the nodeValue of text. The new element is then added as a child
        to the element target.
        """
        newElement = tree.element(None, elemName)
        newElement.xml_append(tree.text(text))
        target.xml_append(newElement)


    def _addRevisionHistory(self, targetNode):
        """
        This will generate a revhistory element which it will populate with
        revision nodes. Each revision has the revnumber, date and author-
        initial elements, and if a comment was supplied, the comment element.

        The date elements format depends on the users settings, so it will
        be in the same format as the revision history as viewed in the
        page info on the wiki.

        The authorinitials will be the UserName or if it was an anonymous
        edit, then it will be the hostname/ip-address.

        The revision history of included documents is NOT included at the
        moment due to technical difficulties.
        """
        _ = self.request.getText
        log = editlog.EditLog(self.request, rootpagename=self.title)
        user_cache = {}

        history = tree.element(None, u"revhistory")

        # read in the complete log of this page
        for line in log.reverse():
            if not line.action in ('SAVE', 'SAVENEW', 'SAVE/REVERT', 'SAVE/RENAME', ):
                #Let's ignore adding of attachments
                continue
            revision = tree.element(None, u"revision")

            # Revision number (without preceeding zeros)
            self._addTextElem(revision, u"revnumber", line.rev.lstrip('0'))

            # Date of revision
            date_text = self.request.user.getFormattedDateTime(
                wikiutil.version2timestamp(line.ed_time_usecs))
            self._addTextElem(revision, u"date", date_text)

            # Author or revision
            if not (line.userid in user_cache):
                user_cache[line.userid] = user.User(self.request, line.userid, auth_method="text_docbook:740")
            author = user_cache[line.userid]
            if author and author.name:
                self._addTextElem(revision, u"authorinitials", author.name)
            else:
                self._addTextElem(revision, u"authorinitials", line.hostname)

            # Comment from author of revision
            comment = line.comment
            if not comment:
                if '/REVERT' in line.action:
                    comment = _("Revert to revision %(rev)d.") % {'rev': int(line.extra)}
                elif '/RENAME' in line.action:
                    comment = _("Renamed from '%(oldpagename)s'.") % {'oldpagename': line.extra}
            if comment:
                self._addTextElem(revision, u"revremark", comment)

            history.xml_append(revision)

        if history.xml_first_child:
            #only add revision history is there is history to add
            targetNode.xml_append(history)

### Not supported ###################################################

    def rule(self, size=0, **kw):
        self._emitComment('rule (<hr>) is not applicable to DocBook')
        return ""

    def small(self, on, **kw):
        if on:
            self._emitComment('"~-smaller-~" is not applicable to DocBook')
        return ""

    def big(self, on, **kw):
        if on:
            self._emitComment('"~+bigger+~" is not applicable to DocBook')
        return ""

    def rawHTML(self, markup):
        if markup.strip() == "":
            return ""

        if "<" not in markup and ">" not in markup:
            # Seems there are no tags.
            # Let's get all the "entity references".
            cleaned = markup
            import re
            entities = re.compile("&(?P<e>[a-zA-Z]+);").findall(cleaned)
            from htmlentitydefs import name2codepoint
            for ent in entities:
                if name2codepoint.has_key(ent):
                    cleaned = cleaned.replace("&%s;" % ent, unichr(name2codepoint[ent]))

            # Then we replace all escaped unicodes.
            escapedunicodes = re.compile("&#(?P<h>[0-9]+);").findall(markup)
            for uni in escapedunicodes:
                cleaned = cleaned.replace("&#%s;" % uni, unichr(int(uni)))

            self.text(cleaned)

        self._emitComment("RAW HTML: "+markup)
        return ""

    def div(self, on, **kw):
        """A div cannot really be supported in DocBook as it carries no
        semantic meaning, but the special cases can be handled when the class
        of the div carries the information.

        A dictionary is used for mapping between class names and the
        corresponding DocBook element.

        A MoinMoin comment is represented in DocBook by the remark element.

        The rest of the known classes are the admonitions in DocBook:
        warning, caution, important, note and hint

        Note: The remark entity can only contain inline elements, so it is
              very likely that the use of a comment div will produce invalid
              DocBook.
        """
        # Map your styles to docbook elements.
        # Even though comment is right now the only one that needs to be
        # mapped, having two different ways is more complicated than having
        # a single common way. Code clarity and generality first, especially
        # since we might want to do more div to docbook mappings in the future.
        class_to_docbook = {"warning":   "warning",
                            "caution":   "caution",
                            "important": "important",
                            "note":      "note",
                            "tip":       "tip",
                            "comment":   "remark"}

        if on and kw.get('css_class'):
            css_classes = kw.get('css_class').split()
            for style in class_to_docbook.keys():
                if style in css_classes:
                    return self._handleNode(class_to_docbook[style], on)

        elif not on:
            if self.cur.xml_qname in class_to_docbook.values():
                return self._handleNode(self.cur.xml_qname, on)

        return ""

    def span(self, on, **kw):
        """A span cannot really be supported in DocBook as it carries no
        semantic meaning, but the special case of a comment can be handled.

        A comment is represented in DocBook by the remark element.

        A comment span is recognized by the fact that it has the class
        "comment". Other cases of div use are ignored.
        """
        css_class = kw.get('css_class')
        if on and css_class and 'comment' in css_class.split():
            self._handleFormatting("remark", on)
        if not on and self.cur.xml_qname == "remark":
            self._handleFormatting("remark", on)
        return ""



### Tables ##########################################################

    def table(self, on, attrs=(), **kw):
        if(on):
            if attrs:
                self.curtable = Table(self, self.doc, self.cur, dict(attrs))
            else:
                self.curtable = Table(self, self.doc, self.cur)
            self.cur = self.curtable.tableNode
        else:
            self.cur = self.curtable.finalizeTable()
            self.curtable = None
        return ""

    def table_row(self, on, attrs=(), **kw):
        if(on):
            if attrs:
                self.curtable.addRow(dict(attrs))
            else:
                self.cur = self.curtable.addRow()
        return ""

    def table_cell(self, on, attrs=(), **kw):
        if(on):
            if attrs:
                self.cur = self.curtable.addCell(dict(attrs))
            else:
                self.cur = self.curtable.addCell()
        return ""

class Table:
    '''The Table class is used as a helper for collecting information about
    what kind of table we are building. When all relelvant data is gathered
    it calculates the different spans of the cells and columns.

    Note that it expects all arguments to be passed in a dict.
    '''

    def __init__(self, formatter, doc, parent, argsdict={}):
        self.formatter = formatter
        self.doc = doc

        self.tableNode = tree.element(None, u'informaltable')
        parent.xml_append(self.tableNode)
        self.colWidths = {}
        self.tgroup = tree.element(None, u'tgroup')
        # Bug in yelp, the two lines below don't affect rendering
        #self.tgroup.setAttribute('rowsep', '1')
        #self.tgroup.setAttribute('colsep', '1')
        self.curColumn = 0
        self.maxColumn = 0
        self.row = None
        self.tableNode.xml_append(self.tgroup)

        self.tbody = tree.element(None, u'tbody') # Note: This gets appended in finalizeTable

    def finalizeTable(self):
        """Calculates the final width of the whole table and the width of each
        column. Adds the colspec-elements and applies the colwidth attributes.
        Inserts the tbody element to the tgroup and returns the tables container
        element.

        A lot of the information is gathered from the style attributes passed
        to the functions
        """
        self.tgroup.xml_attributes[None, u'cols'] = unicode(self.maxColumn)
        for colnr in range(0, self.maxColumn):
            colspecElem = tree.element(None, u'colspec')
            colspecElem.xml_attribute[None, u'colname'] = u'col_%s' % unicode(colnr)
            if self.colWidths.has_key(str(colnr)) and self.colWidths[unicode(colnr)] != "1*":
                colspecElem.xml_attribute[u'colwidth'] = unicode(self.colWidths[unicode(colnr)])
            self.tgroup.xml_append(colspecElem)
        self.tgroup.xml_append(self.tbody)
        return self.tableNode.xml_parent

    def addRow(self, argsdict={}):
        self.curColumn = 0
        self.row = tree.element(None, u'row')
        # Bug in yelp, doesn't affect the outcome.
        self.row.xml_attribute[None, u"rowsep"] = u"1" #Rows should have lines between them
        self.tbody.xml_append(self.row)
        return self.row

    def addCell(self, argsdict={}):
        if 'style' in argsdict:
            argsdict.update(self.formatter._convertStylesToDict(argsdict['style'].strip('"')))

        cell = tree.element(None, u'entry')
        cell.xml_attribute[None, u'rowsep'] = u'1'
        cell.xml_attribute[None, u'colsep'] = u'1'

        self.row.xml_append(cell)
        self._handleSimpleCellAttributes(cell, argsdict)
        self._handleColWidth(argsdict)
        self.curColumn += self._handleColSpan(cell, argsdict)

        self.maxColumn = max(self.curColumn, self.maxColumn)

        return cell

    def _handleColWidth(self, argsdict={}):
        if not argsdict.has_key("width"):
            return
        argsdict["width"] = argsdict["width"].strip('"')
        if not argsdict["width"].endswith("%"):
            self.formatter._emitComment("Width %s not supported" % argsdict["width"])
            return

        self.colWidths[str(self.curColumn)] = argsdict["width"][:-1] + "*"

    def _handleColSpan(self, element, argsdict={}):
        """Returns the number of colums this entry spans"""
        if not argsdict or not argsdict.has_key('colspan'):
            return 1
        assert(element.xml_qname == u"entry")
        extracols = int(argsdict['colspan'].strip('"')) - 1
        element.xml_attribute[None, u'namest'] = u"col_" + unicode(self.curColumn)
        element.xml_attribute[None, u'nameend'] = u"col_" + unicode(self.curColumn + extracols)
        return 1 + extracols

    def _handleSimpleCellAttributes(self, element, argsdict={}):
        if not argsdict:
            return
        assert(element.xml_qname == u"entry")

        safe_values_for = {'valign': ('top', 'middle', 'bottom'),
                           'align': ('left', 'center', 'right'),
                          }

        if argsdict.has_key('rowspan'):
            extrarows = int(argsdict['rowspan'].strip('"')) - 1
            element.xml_attribute[None, u'morerows'] = unicode(extrarows)

        if argsdict.has_key('align'):
            value = argsdict['align'].strip('"')
            if value in safe_values_for['align']:
                element.xml_attributes[u'align'] = unicode(value)
            else:
                self.formatter._emitComment(u"Alignment %s not supported" % value)
                pass

        if argsdict.has_key('valign'):
            value = argsdict['valign'].strip('"')
            if value in safe_values_for['valign']:
                element.xml_attributes[u'valign'] = unicode(value)
            else:
                self.formatter._emitComment(u"Vertical alignment %s not supported" % value)
                pass


