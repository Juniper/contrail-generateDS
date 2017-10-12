#!/usr/bin/env python
"""
Synopsis:
    Generate Python classes from XML Schema definition.
    Input is read from in_xsd_file or, if "-" (dash) arg, from stdin.
    Output is written to files named in "-o" and "-s" options.
Usage:
    python generateDS.py [ options ] <xsd_file>
    python generateDS.py [ options ] -
Options:
    -h, --help               Display this help information.
    -o <outfilename>         Output file name for data representation classes
    -s <subclassfilename>    Output file name for subclasses
    -p <prefix>              Prefix string to be pre-pended to the class names
    -f                       Force creation of output files.  Do not ask.
    -a <namespaceabbrev>     Namespace abbreviation, e.g. "xsd:".
                             Default = 'xs:'.
    -b <behaviorfilename>    Input file name for behaviors added to subclasses
    -m                       Generate properties for member variables
    --subclass-suffix="XXX"  Append XXX to the generated subclass names.
                             Default="Sub".
    --root-element="XXX"     Assume XXX is root element of instance docs.
                             Default is first element defined in schema.
                             Also see section "Recognizing the top level
                             element" in the documentation.
    --super="XXX"            Super module name in subclass module. Default="???"
    --validator-bodies=path  Path to a directory containing files that provide
                             bodies (implementations) of validator methods.
    --use-old-getter-setter  Name getters and setters getVar() and setVar(),
                             instead of get_var() and set_var().
    --user-methods= <module>,
    -u <module>              Optional module containing user methods.  See
                             section "User Methods" in the documentation.
    --no-dates               Do not include the current date in the generated
                             files. This is useful if you want to minimize
                             the amount of (no-operation) changes to the
                             generated python code.
    --no-versions            Do not include the current version in the generated
                             files. This is useful if you want to minimize
                             the amount of (no-operation) changes to the
                             generated python code.
    --no-process-includes    Do not process included XML Schema files.  By
                             default, generateDS.py will insert content
                             from files referenced by <include ... />
                             elements into the XML Schema to be processed.
    --silence                Normally, the code generated with generateDS
                             echoes the information being parsed. To prevent
                             the echo from occurring, use the --silence switch.
    --namespacedef='xmlns:abc="http://www.abc.com"'
                             Namespace definition to be passed in as the
                             value for the namespacedef_ parameter of
                             the export_xml() method by the generated
                             parse() and parseString() functions.
                             Default=''.
    --external-encoding=<encoding>
                             Encode output written by the generated export
                             methods using this encoding.  Default, if omitted,
                             is the value returned by sys.getdefaultencoding().
                             Example: --external-encoding='utf-8'.
    --member-specs=list|dict
                             Generate member (type) specifications in each
                             class: a dictionary of instances of class
                             MemberSpec_ containing member name, type,
                             and array or not.  Allowed values are
                             "list" or "dict".  Default: do not generate.
    -q, --no-questions       Do not ask questios, for example,
                             force overwrite.
    --session=mysession.session
                             Load and use options from session file. You can
                             create session file in generateds_gui.py.  Or,
                             copy and edit sample.session from the
                             distribution.
    --version                Print version and exit.

"""


## LICENSE

## Copyright (c) 2003 Dave Kuhlman

## Permission is hereby granted, free of charge, to any person obtaining
## a copy of this software and associated documentation files (the
## "Software"), to deal in the Software without restriction, including
## without limitation the rights to use, copy, modify, merge, publish,
## distribute, sublicense, and/or sell copies of the Software, and to
## permit persons to whom the Software is furnished to do so, subject to
## the following conditions:

## The above copyright notice and this permission notice shall be
## included in all copies or substantial portions of the Software.

## THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
## EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
## MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
## IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
## CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
## TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
## SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.



#from __future__ import generators   # only needed for Python 2.2

import sys
import os.path
import time
import getopt
import urllib2
import imp
from xml.sax import handler, make_parser
import xml.sax.xmlreader
import logging
import keyword
import StringIO
import textwrap
from cctype import TypeGenerator
from ccmap import IFMapGenerator
from ccsvc import ServiceGenerator

# Default logger configuration
## logging.basicConfig(level=logging.DEBUG,
##                     format='%(asctime)s %(levelname)s %(message)s')

## import warnings
## warnings.warn('importing IPShellEmbed', UserWarning)
## from IPython.Shell import IPShellEmbed
## args = ''
## ipshell = IPShellEmbed(args,
##     banner = 'Dropping into IPython',
##     exit_msg = 'Leaving Interpreter, back to program.')

# Then use the following line where and when you want to drop into the
# IPython shell:
#    ipshell('<some message> -- Entering ipshell.\\nHit Ctrl-D to exit')


#
# Global variables etc.
#

#
# Do not modify the following VERSION comments.
# Used by updateversion.py.
##VERSION##
VERSION = '2.7c'
##VERSION##

class XsdParserGenerator(object):
    def __init__(self):
        self.Version = VERSION
        self.GenerateProperties = 0
        self.UseOldGetterSetter = 0
        self.MemberSpecs = None
        self.DelayedElements = []
        self.DelayedElements_subclass = []
        self.AlreadyGenerated = []
        self.AlreadyGenerated_subclass = []
        self.PostponedExtensions = []
        self.ElementsForSubclasses = []
        self.ElementDict = {}
        self.Force = False
        self.NoQuestions = False
        self.Dirpath = []
        self.ExternalEncoding = sys.getdefaultencoding()
        self.genCategory = None
        self.genLang = None
        self.LangGenr = None
        self.NamespacesDict = {}
        self.Targetnamespace = ""

        self.NameTable = {
            'type': 'type_',
            'float': 'float_',
            'build': 'build_',
            }
        extras = ['self']
        for kw in keyword.kwlist + extras:
            self.NameTable[kw] = '%sxx' % kw


        self.SubclassSuffix = 'Sub'
        self.RootElement = None
        self.AttributeGroups = {}
        self.ElementGroups = {}
        self.SubstitutionGroups = {}
        #
        # SubstitutionGroups can also include simple types that are
        #   not (defined) elements.  Keep a list of these simple types.
        #   These are simple types defined at top level.
        self.SimpleElementDict = {}
        self.SimpleTypeDict = {}
        self.ValidatorBodiesBasePath = None
        self.UserMethodsPath = None
        self.UserMethodsModule = None
        self.XsdNameSpace = ''
        self.CurrentNamespacePrefix = 'xs:'
        self.AnyTypeIdentifier = '__ANY__'
        self.TEMPLATE_HEADER = """\
#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
# Generated %s by generateDS.py%s.
#

import sys
import getopt
import re as re_

etree_ = None
Verbose_import_ = False
(   XMLParser_import_none, XMLParser_import_lxml,
    XMLParser_import_elementtree
    ) = range(3)
XMLParser_import_library = None
try:
    # lxml
    from lxml import etree as etree_
    XMLParser_import_library = XMLParser_import_lxml
    if Verbose_import_:
        print("running with lxml.etree")
except ImportError:
    try:
        # cElementTree from Python 2.5+
        import xml.etree.cElementTree as etree_
        XMLParser_import_library = XMLParser_import_elementtree
        if Verbose_import_:
            print("running with cElementTree on Python 2.5+")
    except ImportError:
        try:
            # ElementTree from Python 2.5+
            import xml.etree.ElementTree as etree_
            XMLParser_import_library = XMLParser_import_elementtree
            if Verbose_import_:
                print("running with ElementTree on Python 2.5+")
        except ImportError:
            try:
                # normal cElementTree install
                import cElementTree as etree_
                XMLParser_import_library = XMLParser_import_elementtree
                if Verbose_import_:
                    print("running with cElementTree")
            except ImportError:
                try:
                    # normal ElementTree install
                    import elementtree.ElementTree as etree_
                    XMLParser_import_library = XMLParser_import_elementtree
                    if Verbose_import_:
                        print("running with ElementTree")
                except ImportError:
                    raise ImportError("Failed to import ElementTree from any known place")

def parsexml_(*args, **kwargs):
    if (XMLParser_import_library == XMLParser_import_lxml and
        'parser' not in kwargs):
        # Use the lxml ElementTree compatible parser so that, e.g.,
        #   we ignore comments.
        kwargs['parser'] = etree_.ETCompatXMLParser()
    doc = etree_.parse(*args, **kwargs)
    return doc

#
# User methods
#
# Calls to the methods in these classes are generated by generateDS.py.
# You can replace these methods by re-implementing the following class
#   in a module named generatedssuper.py.

try:
    from generatedssuper import GeneratedsSuper
except ImportError, exp:

    class GeneratedsSuper(object):
        def gds_format_string(self, input_data, input_name=''):
            return input_data
        def gds_validate_string(self, input_data, node, input_name=''):
            return input_data
        def gds_format_integer(self, input_data, input_name=''):
            return '%%d' %% input_data
        def gds_validate_integer(self, input_data, node, input_name=''):
            return input_data
        def gds_format_integer_list(self, input_data, input_name=''):
            return '%%s' %% input_data
        def gds_validate_integer_list(self, input_data, node, input_name=''):
            values = input_data.split()
            for value in values:
                try:
                    fvalue = float(value)
                except (TypeError, ValueError), exp:
                    raise_parse_error(node, 'Requires sequence of integers')
            return input_data
        def gds_format_float(self, input_data, input_name=''):
            return '%%f' %% input_data
        def gds_validate_float(self, input_data, node, input_name=''):
            return input_data
        def gds_format_float_list(self, input_data, input_name=''):
            return '%%s' %% input_data
        def gds_validate_float_list(self, input_data, node, input_name=''):
            values = input_data.split()
            for value in values:
                try:
                    fvalue = float(value)
                except (TypeError, ValueError), exp:
                    raise_parse_error(node, 'Requires sequence of floats')
            return input_data
        def gds_format_double(self, input_data, input_name=''):
            return '%%e' %% input_data
        def gds_validate_double(self, input_data, node, input_name=''):
            return input_data
        def gds_format_double_list(self, input_data, input_name=''):
            return '%%s' %% input_data
        def gds_validate_double_list(self, input_data, node, input_name=''):
            values = input_data.split()
            for value in values:
                try:
                    fvalue = float(value)
                except (TypeError, ValueError), exp:
                    raise_parse_error(node, 'Requires sequence of doubles')
            return input_data
        def gds_format_boolean(self, input_data, input_name=''):
            return '%%s' %% input_data
        def gds_validate_boolean(self, input_data, node, input_name=''):
            return input_data
        def gds_format_boolean_list(self, input_data, input_name=''):
            return '%%s' %% input_data
        def gds_validate_boolean_list(self, input_data, node, input_name=''):
            values = input_data.split()
            for value in values:
                if value not in ('true', '1', 'false', '0', ):
                    raise_parse_error(node, 'Requires sequence of booleans ("true", "1", "false", "0")')
            return input_data
        def gds_str_lower(self, instring):
            return instring.lower()
        def get_path_(self, node):
            path_list = []
            self.get_path_list_(node, path_list)
            path_list.reverse()
            path = '/'.join(path_list)
            return path
        Tag_strip_pattern_ = re_.compile(r'\{.*\}')
        def get_path_list_(self, node, path_list):
            if node is None:
                return
            tag = GeneratedsSuper.Tag_strip_pattern_.sub('', node.tag)
            if tag:
                path_list.append(tag)
            self.get_path_list_(node.getparent(), path_list)
        def get_class_obj_(self, node, default_class=None):
            class_obj1 = default_class
            if 'xsi' in node.nsmap:
                classname = node.get('{%%s}type' %% node.nsmap['xsi'])
                if classname is not None:
                    names = classname.split(':')
                    if len(names) == 2:
                        classname = names[1]
                    class_obj2 = globals().get(classname)
                    if class_obj2 is not None:
                        class_obj1 = class_obj2
            return class_obj1
        def gds_build_any(self, node, type_name=None):
            return None


#
# If you have installed IPython you can uncomment and use the following.
# IPython is available from http://ipython.scipy.org/.
#

## from IPython.Shell import IPShellEmbed
## args = ''
## ipshell = IPShellEmbed(args,
##     banner = 'Dropping into IPython',
##     exit_msg = 'Leaving Interpreter, back to program.')

# Then use the following line where and when you want to drop into the
# IPython shell:
#    ipshell('<some message> -- Entering ipshell.\\nHit Ctrl-D to exit')

#
# Globals
#

ExternalEncoding = '%s'
Tag_pattern_ = re_.compile(r'({.*})?(.*)')
String_cleanup_pat_ = re_.compile(r"[\\n\\r\\s]+")
Namespace_extract_pat_ = re_.compile(r'{(.*)}(.*)')

#
# Support/utility functions.
#

def showIndent(outfile, level, pretty_print=True):
    if pretty_print:
        for idx in range(level):
            outfile.write('    ')

def quote_xml(inStr):
    if not inStr:
        return ''
    s1 = (isinstance(inStr, basestring) and inStr or
          '%%s' %% inStr)
    s1 = s1.replace('&', '&amp;')
    s1 = s1.replace('<', '&lt;')
    s1 = s1.replace('>', '&gt;')
    return s1

def quote_attrib(inStr):
    s1 = (isinstance(inStr, basestring) and inStr or
          '%%s' %% inStr)
    s1 = s1.replace('&', '&amp;')
    s1 = s1.replace('<', '&lt;')
    s1 = s1.replace('>', '&gt;')
    if '"' in s1:
        if "'" in s1:
            s1 = '"%%s"' %% s1.replace('"', "&quot;")
        else:
            s1 = "'%%s'" %% s1
    else:
        s1 = '"%%s"' %% s1
    return s1

def quote_python(inStr):
    s1 = inStr
    if s1.find("'") == -1:
        if s1.find('\\n') == -1:
            return "'%%s'" %% s1
        else:
            return "'''%%s'''" %% s1
    else:
        if s1.find('"') != -1:
            s1 = s1.replace('"', '\\\\"')
        if s1.find('\\n') == -1:
            return '"%%s"' %% s1
        else:
            return '\"\"\"%%s\"\"\"' %% s1

def get_all_text_(node):
    if node.text is not None:
        text = node.text
    else:
        text = ''
    for child in node:
        if child.tail is not None:
            text += child.tail
    return text

def find_attr_value_(attr_name, node):
    attrs = node.attrib
    attr_parts = attr_name.split(':')
    value = None
    if len(attr_parts) == 1:
        value = attrs.get(attr_name)
    elif len(attr_parts) == 2:
        prefix, name = attr_parts
        namespace = node.nsmap.get(prefix)
        if namespace is not None:
            value = attrs.get('{%%s}%%s' %% (namespace, name, ))
    return value


class GDSParseError(Exception):
    pass

def raise_parse_error(node, msg):
    if XMLParser_import_library == XMLParser_import_lxml:
        msg = '%%s (element %%s/line %%d)' %% (msg, node.tag, node.sourceline, )
    else:
        msg = '%%s (element %%s)' %% (msg, node.tag, )
    raise GDSParseError(msg)


class MixedContainer:
    # Constants for category:
    CategoryNone = 0
    CategoryText = 1
    CategorySimple = 2
    CategoryComplex = 3
    # Constants for content_type:
    TypeNone = 0
    TypeText = 1
    TypeString = 2
    TypeInteger = 3
    TypeFloat = 4
    TypeDecimal = 5
    TypeDouble = 6
    TypeBoolean = 7
    def __init__(self, category, content_type, name, value):
        self.category = category
        self.content_type = content_type
        self.name = name
        self.value = value
    def getCategory(self):
        return self.category
    def getContenttype(self, content_type):
        return self.content_type
    def getValue(self):
        return self.value
    def getName(self):
        return self.name
    def export_xml(self, outfile, level, name, namespace, pretty_print=True):
        if self.category == MixedContainer.CategoryText:
            # Prevent exporting empty content as empty lines.
            if self.value.strip():
                outfile.write(self.value)
        elif self.category == MixedContainer.CategorySimple:
            self.exportSimple(outfile, level, name)
        else:    # category == MixedContainer.CategoryComplex
            self.value.export_xml(outfile, level, namespace, name, pretty_print)
    def exportSimple(self, outfile, level, name):
        if self.content_type == MixedContainer.TypeString:
            outfile.write('<%%s>%%s</%%s>' %% (self.name, self.value, self.name))
        elif self.content_type == MixedContainer.TypeInteger or \\
                self.content_type == MixedContainer.TypeBoolean:
            outfile.write('<%%s>%%d</%%s>' %% (self.name, self.value, self.name))
        elif self.content_type == MixedContainer.TypeFloat or \\
                self.content_type == MixedContainer.TypeDecimal:
            outfile.write('<%%s>%%f</%%s>' %% (self.name, self.value, self.name))
        elif self.content_type == MixedContainer.TypeDouble:
            outfile.write('<%%s>%%g</%%s>' %% (self.name, self.value, self.name))
    def exportLiteral(self, outfile, level, name):
        if self.category == MixedContainer.CategoryText:
            showIndent(outfile, level)
            outfile.write('model_.MixedContainer(%%d, %%d, "%%s", "%%s"),\\n' %% \\
                (self.category, self.content_type, self.name, self.value))
        elif self.category == MixedContainer.CategorySimple:
            showIndent(outfile, level)
            outfile.write('model_.MixedContainer(%%d, %%d, "%%s", "%%s"),\\n' %% \\
                (self.category, self.content_type, self.name, self.value))
        else:    # category == MixedContainer.CategoryComplex
            showIndent(outfile, level)
            outfile.write('model_.MixedContainer(%%d, %%d, "%%s",\\n' %% \\
                (self.category, self.content_type, self.name,))
            self.value.exportLiteral(outfile, level + 1)
            showIndent(outfile, level)
            outfile.write(')\\n')


class MemberSpec_(object):
    def __init__(self, name='', data_type='', container=0):
        self.name = name
        self.data_type = data_type
        self.container = container
    def set_name(self, name): self.name = name
    def get_name(self): return self.name
    def set_data_type(self, data_type): self.data_type = data_type
    def get_data_type_chain(self): return self.data_type
    def get_data_type(self):
        if isinstance(self.data_type, list):
            if len(self.data_type) > 0:
                return self.data_type[-1]
            else:
                return 'xs:string'
        else:
            return self.data_type
    def set_container(self, container): self.container = container
    def get_container(self): return self.container

def cast_(typ, value):
    if typ is None or value is None:
        return value
    return typ(value)

#
# Data representation classes.
#

"""
        self.TEMPLATE_MAIN = """\
USAGE_TEXT = \"\"\"
Usage: python <%(prefix)sParser>.py [ -s ] <in_xml_file>
\"\"\"

def usage():
    print USAGE_TEXT
    sys.exit(1)


def get_root_tag(node):
    tag = Tag_pattern_.match(node.tag).groups()[-1]
    rootClass = globals().get(tag)
    return tag, rootClass


def parse(inFileName):
    doc = parsexml_(inFileName)
    rootNode = doc.getroot()
    rootTag, rootClass = get_root_tag(rootNode)
    if rootClass is None:
        rootTag = '%(name)s'
        rootClass = %(prefix)s%(root)s
    rootObj = rootClass.factory()
    rootObj.build(rootNode)
    # Enable Python to collect the space used by the DOM.
    doc = None
#silence#    sys.stdout.write('<?xml version="1.0" ?>\\n')
#silence#    rootObj.export_xml(sys.stdout, 0, name_=rootTag,
#silence#        namespacedef_='%(namespacedef)s',
#silence#        pretty_print=True)
    return rootObj


def parseString(inString):
    from StringIO import StringIO
    doc = parsexml_(StringIO(inString))
    rootNode = doc.getroot()
    rootTag, rootClass = get_root_tag(rootNode)
    if rootClass is None:
        rootTag = '%(name)s'
        rootClass = %(prefix)s%(root)s
    rootObj = rootClass.factory()
    rootObj.build(rootNode)
    # Enable Python to collect the space used by the DOM.
    doc = None
#silence#    sys.stdout.write('<?xml version="1.0" ?>\\n')
#silence#    rootObj.export_xml(sys.stdout, 0, name_="%(name)s",
#silence#        namespacedef_='%(namespacedef)s')
    return rootObj


def parseLiteral(inFileName):
    doc = parsexml_(inFileName)
    rootNode = doc.getroot()
    rootTag, rootClass = get_root_tag(rootNode)
    if rootClass is None:
        rootTag = '%(name)s'
        rootClass = %(prefix)s%(root)s
    rootObj = rootClass.factory()
    rootObj.build(rootNode)
    # Enable Python to collect the space used by the DOM.
    doc = None
#silence#    sys.stdout.write('#from %(module_name)s import *\\n\\n')
#silence#    sys.stdout.write('import %(module_name)s as model_\\n\\n')
#silence#    sys.stdout.write('rootObj = model_.rootTag(\\n')
#silence#    rootObj.exportLiteral(sys.stdout, 0, name_=rootTag)
#silence#    sys.stdout.write(')\\n')
    return rootObj


def main():
    args = sys.argv[1:]
    if len(args) == 1:
        parse(args[0])
    else:
        usage()


if __name__ == '__main__':
    main()

        """
        self.SchemaToPythonTypeMap = {}
        self.SchemaToCppTypeMap = {}

    def args_parse(self):
        #LG global Force, GenerateProperties, SubclassSuffix, RootElement, \
        #LG     ValidatorBodiesBasePath, UseOldGetterSetter, \
        #LG     UserMethodsPath, XsdNameSpace, \
        #LG     Namespacedef, NoDates, NoVersion, \
        #LG     TEMPLATE_MAIN, TEMPLATE_SUBCLASS_FOOTER, Dirpath, \
        #LG     ExternalEncoding, MemberSpecs, NoQuestions, LangGenr
        self.outputText = True
        self.args = sys.argv[1:]
        try:
            options, self.args = getopt.getopt(self.args, 'l:g:hfyo:s:p:a:b:mu:q',
                ['help', 'subclass-suffix=',
                'root-element=', 'super=',
                'validator-bodies=', 'use-old-getter-setter',
                'user-methods=', 'no-process-includes', 'silence',
                'namespacedef=', 'external-encoding=',
                'member-specs=', 'no-dates', 'no-versions',
                'no-questions', 'session=', 'generator-category=',
                'generated-language=', 'version',
                ])
        except getopt.GetoptError, exp:
            usage()
        self.prefix = ''
        self.outFilename = None
        self.subclassFilename = None
        self.behaviorFilename = None
        self.nameSpace = 'xs:'
        superModule = '???'
        self.processIncludes = 1
        self.namespacedef = ''
        self.ExternalEncoding = sys.getdefaultencoding()
        self.NoDates = False
        self.NoVersion = False
        self.NoQuestions = False
        showVersion = False
        self.xschemaFileName = None
        for option in options:
            if option[0] == '--session':
                sessionFilename = option[1]
                from libgenerateDS.gui import generateds_gui_session
                from xml.etree import ElementTree as etree
                doc = etree.parse(sessionFilename)
                rootNode = doc.getroot()
                sessionObj = generateds_gui_session.sessionType()
                sessionObj.build(rootNode)
                if sessionObj.get_input_schema():
                    self.xschemaFileName = sessionObj.get_input_schema()
                if sessionObj.get_output_superclass():
                    self.outFilename = sessionObj.get_output_superclass()
                if sessionObj.get_output_subclass():
                    self.subclassFilename = sessionObj.get_output_subclass()
                if sessionObj.get_force():
                    self.Force = True
                if sessionObj.get_prefix():
                    self.prefix = sessionObj.get_prefix()
                if sessionObj.get_empty_namespace_prefix():
                    self.nameSpace = ''
                elif sessionObj.get_namespace_prefix():
                    self.nameSpace = sessionObj.get_namespace_prefix()
                if sessionObj.get_behavior_filename():
                    self.behaviorFilename = sessionObj.get_behavior_filename()
                if sessionObj.get_properties():
                    self.GenerateProperties = True
                if sessionObj.get_subclass_suffix():
                    SubclassSuffix = sessionObj.get_subclass_suffix()
                if sessionObj.get_root_element():
                    self.RootElement = sessionObj.get_root_element()
                if sessionObj.get_superclass_module():
                    superModule = sessionObj.get_superclass_module()
                if sessionObj.get_old_getters_setters():
                    self.UseOldGetterSetter = 1
                if sessionObj.get_validator_bodies():
                    ValidatorBodiesBasePath = sessionObj.get_validator_bodies()
                    if not os.path.isdir(ValidatorBodiesBasePath):
                        err_msg('*** Option validator-bodies must specify an existing path.\n')
                        sys.exit(1)
                if sessionObj.get_user_methods():
                    UserMethodsPath = sessionObj.get_user_methods()
                if sessionObj.get_no_dates():
                    self.NoDates = True
                if sessionObj.get_no_versions():
                    self.NoVersion = True
                if sessionObj.get_no_process_includes():
                    self.processIncludes = 0
                if sessionObj.get_silence():
                    self.outputText = False
                if sessionObj.get_namespace_defs():
                    self.namespacedef = sessionObj.get_naspace_defs()
                if sessionObj.get_external_encoding():
                    self.ExternalEncoding = sessionObj.get_external_encoding()
                if sessionObj.get_member_specs() in ('list', 'dict'):
                    MemberSpecs = sessionObj.get_member_specs()
                break
        for option in options:
            if option[0] == '-h' or option[0] == '--help':
                usage()
            elif option[0] == '-p':
                self.prefix = option[1]
            elif option[0] == '-o':
                self.outFilename = option[1]
            elif option[0] == '-s':
                self.subclassFilename = option[1]
            elif option[0] == '-f':
                self.Force = 1
            elif option[0] == '-a':
                self.nameSpace = option[1]
            elif option[0] == '-b':
                self.behaviorFilename = option[1]
            elif option[0] == '-m':
                self.GenerateProperties = 1
            elif option[0] == '--no-dates':
                self.NoDates = True
            elif option[0] == '--no-versions':
                self.NoVersion = True
            elif option[0] == '--subclass-suffix':
                SubclassSuffix = option[1]
            elif option[0] == '--root-element':
                self.RootElement = option[1]
            elif option[0] == '--super':
                superModule = option[1]
            elif option[0] == '--validator-bodies':
                ValidatorBodiesBasePath = option[1]
                if not os.path.isdir(ValidatorBodiesBasePath):
                    err_msg('*** Option validator-bodies must specify an existing path.\n')
                    sys.exit(1)
            elif option[0] == '--use-old-getter-setter':
                self.UseOldGetterSetter = 1
            elif option[0] in ('-u', '--user-methods'):
                UserMethodsPath = option[1]
            elif option[0] == '--no-process-includes':
                self.processIncludes = 0
            elif option[0] == "--silence":
                self.outputText = False
            elif option[0] == "--namespacedef":
                self.namespacedef = option[1]
            elif option[0] == '--external-encoding':
                self.ExternalEncoding = option[1]
            elif option[0] in ('-q', '--no-questions'):
                self.NoQuestions = True
            elif option[0] == '--version':
                showVersion = True
            elif option[0] == '--member-specs':
                MemberSpecs = option[1]
                if MemberSpecs not in ('list', 'dict', ):
                    raise RuntimeError('Option --member-specs must be "list" or "dict".')
            elif option[0] in ('-l', '--generated-language'):
                self.genLang = option[1]
                if self.genLang not in ('py', 'c++'):
                    raise RuntimeError('Option --generated-language must be "py" or "c++".')
            elif option[0] in ('-g', '--generator-category'):
                self.genCategory = option[1]
                if self.genCategory not in ('type',
                                            'service',
                                            'ifmap-frontend',
                                            'ifmap-backend',
                                            'device-api',
                                            'java-api',
                                            'golang-api',
                                            'contrail-json-schema',
                                            'json-schema'):
                    raise RuntimeError('Option --generator-category must be "type", service", "ifmap-frontend", "ifmap-backend", "device-api", "java-api", "golang-api", "contrail-json-schema" or "json-schema".')
        if showVersion:
            print 'generateDS.py version %s' % VERSION
            sys.exit(0)

    def countChildren(self, element, count):
        count += len(element.getChildren())
        base = element.getBase()
        if base and base in self.ElementDict:
            parent = self.ElementDict[base]
            count = self.countChildren(parent, count)
        return count

    def getParentName(self, element):
        base = element.getBase()
        rBase = element.getRestrictionBaseObj()
        parentName = None
        parentObj = None
        if base and base in self.ElementDict:
            parentObj = self.ElementDict[base]
            parentName = self.cleanupName(parentObj.getName())
        elif rBase:
            base = element.getRestrictionBase()
            parentObj = self.ElementDict[base]
            parentName = self.cleanupName(parentObj.getName())
        return parentName, parentObj

    def makeFile(self, outFileName, outAppend = False):
        outFile = None
        if ((not self.Force) and os.path.exists(outFileName)
                             and not outAppend):
            if self.NoQuestions:
                sys.stderr.write('File %s exists.  Change output file or use -f (force).\n' % outFileName)
                sys.exit(1)
            else:
                reply = raw_input('File %s exists.  Overwrite? (y/n): ' % outFileName)
                if reply == 'y':
                    outFile = file(outFileName, 'w')
        else:
            if (outAppend):
                outFile = file(outFileName, 'a')
            else:
                outFile = file(outFileName, 'w')
        return outFile

    def mapName(self, oldName):
        newName = oldName
        if self.NameTable:
            if oldName in self.NameTable:
                newName = self.NameTable[oldName]
        return newName

    def cleanupName(self, oldName):
        newName = oldName.replace(':', '_')
        newName = newName.replace('-', '_')
        newName = newName.replace('.', '_')
        return newName

    def make_gs_name(self, oldName):
        if self.UseOldGetterSetter:
            newName = oldName.capitalize()
        else:
            newName = '_%s' % oldName
        return newName

    def is_builtin_simple_type(self, type_val):
        if type_val in self.StringType or \
            type_val == self.TokenType or \
            type_val == self.DateTimeType or \
            type_val == self.TimeType or \
            type_val == self.DateType or \
            type_val in self.IntegerType or \
            type_val == self.DecimalType or \
            type_val == self.PositiveIntegerType or \
            type_val == self.NonPositiveIntegerType or \
            type_val == self.NegativeIntegerType or \
            type_val == self.NonNegativeIntegerType or \
            type_val == self.BooleanType or \
            type_val == self.FloatType or \
            type_val == self.DoubleType or \
            type_val in self.OtherSimpleTypes:
            return True
        else:
            return False

    def set_type_constants(self, nameSpace):
        #LG global CurrentNamespacePrefix, \
        #LG     StringType, TokenType, \
        #LG     IntegerType, DecimalType, \
        #LG     PositiveIntegerType, NegativeIntegerType, \
        #LG     NonPositiveIntegerType, NonNegativeIntegerType, \
        #LG     BooleanType, FloatType, DoubleType, \
        #LG     ElementType, ComplexTypeType, GroupType, SequenceType, ChoiceType, \
        #LG     AttributeGroupType, AttributeType, SchemaType, \
        #LG     DateTimeType, DateType, TimeType, \
        #LG     SimpleContentType, ComplexContentType, ExtensionType, \
        #LG     IDType, IDREFType, IDREFSType, IDTypes, \
        #LG     NameType, NCNameType, QNameType, NameTypes, \
        #LG     AnyAttributeType, SimpleTypeType, RestrictionType, \
        #LG     WhiteSpaceType, ListType, EnumerationType, UnionType, \
        #LG     AnyType, \
        #LG     AnnotationType, DocumentationType, \
        #LG     OtherSimpleTypes
        self.CurrentNamespacePrefix = nameSpace
        self.AttributeGroupType = nameSpace + 'attributeGroup'
        self.AttributeType = nameSpace + 'attribute'
        self.BooleanType = nameSpace + 'boolean'
        self.ChoiceType = nameSpace + 'choice'
        self.SimpleContentType = nameSpace + 'simpleContent'
        self.ComplexContentType = nameSpace + 'complexContent'
        self.ComplexTypeType = nameSpace + 'complexType'
        self.GroupType = nameSpace + 'group'
        self.SimpleTypeType = nameSpace + 'simpleType'
        self.RestrictionType = nameSpace + 'restriction'
        self.WhiteSpaceType = nameSpace + 'whiteSpace'
        self.AnyAttributeType = nameSpace + 'anyAttribute'
        self.DateTimeType = nameSpace + 'dateTime'
        self.TimeType = nameSpace + 'time'
        self.DateType = nameSpace + 'date'
        self.IntegerType = (nameSpace + 'integer',
                 nameSpace + 'unsignedShort',
                 nameSpace + 'unsignedLong',
                 nameSpace + 'unsignedInt',
                 nameSpace + 'unsignedByte',
                 nameSpace + 'byte',
                 nameSpace + 'short',
                 nameSpace + 'long',
                 nameSpace + 'int',
                 )
        self.DecimalType = nameSpace + 'decimal'
        self.PositiveIntegerType = nameSpace + 'positiveInteger'
        self.NegativeIntegerType = nameSpace + 'negativeInteger'
        self.NonPositiveIntegerType = nameSpace + 'nonPositiveInteger'
        self.NonNegativeIntegerType = nameSpace + 'nonNegativeInteger'
        self.DoubleType = nameSpace + 'double'
        self.ElementType = nameSpace + 'element'
        self.ExtensionType = nameSpace + 'extension'
        self.FloatType = nameSpace + 'float'
        self.IDREFSType = nameSpace + 'IDREFS'
        self.IDREFType = nameSpace + 'IDREF'
        self.IDType = nameSpace + 'ID'
        self.IDTypes = (self.IDREFSType, self.IDREFType, self.IDType, )
        self.SchemaType = nameSpace + 'schema'
        self.SequenceType = nameSpace + 'sequence'
        self.StringType = (nameSpace + 'string',
                 nameSpace + 'duration',
                 nameSpace + 'anyURI',
                 nameSpace + 'base64Binary',
                 nameSpace + 'hexBinary',
                 nameSpace + 'normalizedString',
                 nameSpace + 'NMTOKEN',
                 nameSpace + 'ID',
                 nameSpace + 'Name',
                 nameSpace + 'language',
                 )
        self.TokenType = nameSpace + 'token'
        self.NameType = nameSpace + 'Name'
        self.NCNameType = nameSpace + 'NCName'
        self.QNameType = nameSpace + 'QName'
        self.NameTypes = (self.NameType, self.NCNameType, self.QNameType, )
        self.ListType = nameSpace + 'list'
        self.EnumerationType = nameSpace + 'enumeration'
        self.MinInclusiveType = nameSpace + 'minInclusive'
        self.MaxInclusiveType = nameSpace + 'maxInclusive'
        self.UnionType = nameSpace + 'union'
        self.AnnotationType = nameSpace + 'annotation'
        self.DocumentationType = nameSpace + 'documentation'
        self.AnyType = nameSpace + 'any'
        self.OtherSimpleTypes = (
                 nameSpace + 'ENTITIES',
                 nameSpace + 'ENTITY',
                 nameSpace + 'ID',
                 nameSpace + 'IDREF',
                 nameSpace + 'IDREFS',
                 nameSpace + 'NCName',
                 nameSpace + 'NMTOKEN',
                 nameSpace + 'NMTOKENS',
                 nameSpace + 'NOTATION',
                 nameSpace + 'Name',
                 nameSpace + 'QName',
                 nameSpace + 'anyURI',
                 nameSpace + 'base64Binary',
                 nameSpace + 'hexBinary',
                 nameSpace + 'boolean',
                 nameSpace + 'byte',
                 nameSpace + 'date',
                 nameSpace + 'dateTime',
                 nameSpace + 'time',
                 nameSpace + 'decimal',
                 nameSpace + 'double',
                 nameSpace + 'duration',
                 nameSpace + 'float',
                 nameSpace + 'gDay',
                 nameSpace + 'gMonth',
                 nameSpace + 'gMonthDay',
                 nameSpace + 'gYear',
                 nameSpace + 'gYearMonth',
                 nameSpace + 'int',
                 nameSpace + 'integer',
                 nameSpace + 'language',
                 nameSpace + 'long',
                 nameSpace + 'negativeInteger',
                 nameSpace + 'nonNegativeInteger',
                 nameSpace + 'nonPositiveInteger',
                 nameSpace + 'normalizedString',
                 nameSpace + 'positiveInteger',
                 nameSpace + 'short',
                 nameSpace + 'string',
                 nameSpace + 'time',
                 nameSpace + 'token',
                 nameSpace + 'unsignedByte',
                 nameSpace + 'unsignedInt',
                 nameSpace + 'unsignedLong',
                 nameSpace + 'unsignedShort',
                 nameSpace + 'anySimpleType',
             )

        #LG global SchemaToPythonTypeMap
        self.SchemaToPythonTypeMap = {
            self.BooleanType : 'bool',
            self.DecimalType : 'float',
            self.DoubleType : 'float',
            self.FloatType : 'float',
            self.NegativeIntegerType : 'int',
            self.NonNegativeIntegerType : 'int',
            self.NonPositiveIntegerType : 'int',
            self.PositiveIntegerType : 'int',
        }
        self.SchemaToPythonTypeMap.update(dict((x, 'int') for x in self.IntegerType))
        self.SchemaToPythonTypeMap.update(dict((x.lower(), 'int') for x in self.IntegerType))
        self.SchemaToPythonTypeMap.update(dict((x, 'str') for x in self.StringType))

        #LG global SchemaToCppTypeMap
        self.SchemaToCppTypeMap = {
            self.BooleanType : 'bool',
            self.DecimalType : 'float',
            self.DoubleType : 'float',
            self.FloatType : 'float',
            self.NegativeIntegerType : 'int',
            self.NonNegativeIntegerType : 'int',
            self.NonPositiveIntegerType : 'int',
            self.PositiveIntegerType : 'int',
            self.StringType : 'string',
        }
        self.SchemaToCppTypeMap.update(dict((x, 'int') for x in self.IntegerType))
        self.SchemaToCppTypeMap.update(dict((x, 'string') for x in self.StringType))

    def init_with_args(self):
        global TEMPLATE_SUBCLASS_FOOTER

        self.XsdNameSpace = self.nameSpace
        self.Namespacedef = self.namespacedef
        self.set_type_constants(self.nameSpace)
        if self.behaviorFilename and not self.subclassFilename:
            err_msg(USAGE_TEXT)
            err_msg('\n*** Error.  Option -b requires -s\n')
        if self.xschemaFileName is None:
            if len(self.args) != 1:
                usage()
            else:
                self.xschemaFileName = self.args[0]
        silent = not self.outputText
        self.TEMPLATE_MAIN = fixSilence(self.TEMPLATE_MAIN, silent)
        TEMPLATE_SUBCLASS_FOOTER = fixSilence(TEMPLATE_SUBCLASS_FOOTER, silent)
        self._load_config()

        if self.genCategory == 'type':
            self._Generator = TypeGenerator(self)
        elif self.genCategory == 'service':
            self._Generator = ServiceGenerator(self)
        elif (self.genCategory == 'ifmap-backend' or
              self.genCategory == 'ifmap-frontend' or
              self.genCategory == 'device-api' or
              self.genCategory == 'java-api' or
              self.genCategory == 'golang-api' or
              self.genCategory == 'contrail-json-schema' or
              self.genCategory == 'json-schema'):
            self._Generator = IFMapGenerator(self, self.genCategory)
        self._Generator.setLanguage(self.genLang)

    def _load_config(self):
        try:
            #print '1. updating NameTable'
            import generateds_config
            NameTable.update(generateds_config.NameTable)
            #print '2. updating NameTable'
        except ImportError, exp:
            pass

    def parseAndGenerate(self):
        #LG global DelayedElements, DelayedElements_subclass, AlreadyGenerated, SaxDelayedElements, \
        #LG     AlreadyGenerated_subclass, UserMethodsPath, UserMethodsModule
        self.DelayedElements = []
        self.DelayedElements_subclass = []
        self.AlreadyGenerated = []
        self.AlreadyGenerated_subclass = []
        if self.UserMethodsPath:
            # UserMethodsModule = __import__(UserMethodsPath)
            path_list = self.UserMethodsPath.split('.')
            mod_name = path_list[-1]
            mod_path = os.sep.join(path_list[:-1])
            module_spec = imp.find_module(mod_name, [mod_path, ])
            self.UserMethodsModule = imp.load_module(mod_name, *module_spec)
    ##    parser = saxexts.make_parser("xml.sax.drivers2.drv_pyexpat")
        parser = make_parser()
        dh = XschemaHandler(self)
    ##    parser.setDocumentHandler(dh)
        parser.setContentHandler(dh)
        if self.xschemaFileName == '-':
            infile = sys.stdin
        else:
            infile = open(self.xschemaFileName, 'r')
        if self.processIncludes:
            import process_includes
            outfile = StringIO.StringIO()
            process_includes.process_include_files(infile, outfile,
                inpath=self.xschemaFileName)
            outfile.seek(0)
            infile = outfile
        parser.parse(infile)
        root = dh.getRoot()
        root.annotate()
    ##     print '-' * 60
    ##     root.show(sys.stdout, 0)
    ##     print '-' * 60
        #debug_show_elements(root)
        infile.seek(0)
        self._Generator.generate(root, infile, self.outFilename)

#LG #
#LG # For debugging.
#LG #
#LG
#LG # Print only if DEBUG is true.
#LG DEBUG = 0
#LG def dbgprint(level, msg):
#LG     if DEBUG and level > 0:
#LG         print msg
#LG
#LG def pplist(lst):
#LG     for count, item in enumerate(lst):
#LG         print '%d. %s' % (count, item)



#
# Representation of element definition.
#

def showLevel(outfile, level):
    for idx in range(level):
        outfile.write('    ')


class XschemaElementBase:
    def __init__(self):
        pass


class SimpleTypeElement(XschemaElementBase):
    def __init__(self, name):
        XschemaElementBase.__init__(self)
        self.name = name
        self.base = None
        self.collapseWhiteSpace = 0
        # Attribute definitions for the current attributeGroup, if there is one.
        self.attributeGroup = None
        # Attribute definitions for the currect element.
        self.attributeDefs = {}
        self.complexType = 0
        # Enumeration values for the current element.
        self.values = list()
        # The other simple types this is a union of.
        self.unionOf = list()
        self.simpleType = 0
        self.listType = 0
        self.documentation = ''
        self.default = None
        self.restrictionAttrs = None
    def setName(self, name): self.name = name
    def getName(self): return self.name
    def setBase(self, base): self.base = base
    def getBase(self): return self.base
    def getDefault(self): return self.default
    def setDefault(self, default): self.default = default
    def setSimpleType(self, simpleType): self.simpleType = simpleType
    def getSimpleType(self): return self.simpleType
    def getAttributeGroups(self): return self.attributeGroups
    def setAttributeGroup(self, attributeGroup): self.attributeGroup = attributeGroup
    def getAttributeGroup(self): return self.attributeGroup
    def setListType(self, listType): self.listType = listType
    def isListType(self): return self.listType
    def setRestrictionAttrs(self, restrictionAttrs): self.restrictionAttrs = restrictionAttrs
    def getRestrictionAttrs(self): return self.restrictionAttrs
    def __str__(self):
        s1 = '<"%s" SimpleTypeElement instance at 0x%x>' % \
            (self.getName(), id(self))
        return s1

    def __repr__(self):
        s1 = '<"%s" SimpleTypeElement instance at 0x%x>' % \
            (self.getName(), id(self))
        return s1

    def resolve_list_type(self, SimpleTypeDict):
        if self.isListType():
            return 1
        elif self.getBase() in SimpleTypeDict:
            base = SimpleTypeDict[self.getBase()]
            return base.resolve_list_type(SimpleTypeDict)
        else:
            return 0


class XschemaElement(XschemaElementBase):
    def __init__(self, parser_generator, attrs):
        XschemaElementBase.__init__(self)
        self._PGenr = parser_generator
        self.cleanName = ''
        self.attrs = dict(attrs)
        name_val = ''
        type_val = ''
        ref_val = ''
        if 'name' in self.attrs:
            name_val = strip_namespace(self.attrs['name'])
        if 'type' in self.attrs:
            if (len(self._PGenr.XsdNameSpace) > 0 and
                self.attrs['type'].startswith(self._PGenr.XsdNameSpace)):
                type_val = self.attrs['type']
            else:
                type_val = strip_namespace(self.attrs['type'])
        if 'ref' in self.attrs:
            ref_val = strip_namespace(self.attrs['ref'])
        if type_val and not name_val:
            name_val = type_val
        if ref_val and not name_val:
            name_val = ref_val
        if ref_val and not type_val:
            type_val = ref_val
        if name_val:
            self.attrs['name'] = name_val
        if type_val:
            self.attrs['type'] = type_val
        if ref_val:
            self.attrs['ref'] = ref_val
        # fix_abstract
        abstract_type = attrs.get('abstract', 'false').lower()
        self.abstract_type = abstract_type in ('1', 'true')
        self.default = self.attrs.get('default')
        self.name = name_val
        self.children = []
        self.optional = False
        self.minOccurs = 1
        self.maxOccurs = 1
        self.complex = 0
        self.complexType = 0
        self.type = 'NoneType'
        self.mixed = 0
        self.base = None
        self.mixedExtensionError = 0
        self.collapseWhiteSpace = 0
        # Attribute definitions for the currect element.
        self.attributeDefs = {}
        # Attribute definitions for the current attributeGroup, if there is one.
        self.attributeGroup = None
        # List of names of attributes for this element.
        # We will add the attribute defintions in each of these groups
        #   to this element in annotate().
        self.attributeGroupNameList = []
        # similar things as above, for groups of elements
        self.elementGroup = None
        self.topLevel = 0
        # Does this element contain an anyAttribute?
        self.anyAttribute = 0
        self.explicit_define = 0
        self.simpleType = None
        # Enumeration values for the current element.
        self.values = list()
        # The parent choice for the current element.
        self.choice = None
        self.listType = 0
        self.simpleBase = []
        self.required = attrs.get('required')
        self.description = attrs.get('description')
        self.documentation = ''
        self.restrictionBase = None
        self.simpleContent = False
        self.extended = False

    def addChild(self, element):
        self.children.append(element)
    def getChildren(self): return self.children
    def getName(self): return self.name
    def getCleanName(self): return self.cleanName
    def getUnmappedCleanName(self): return self.unmappedCleanName
    def setName(self, name): self.name = name
    def getAttrs(self): return self.attrs
    def setAttrs(self, attrs): self.attrs = attrs
    def getMinOccurs(self): return self.minOccurs
    def getMaxOccurs(self): return self.maxOccurs
    def getOptional(self): return self.optional
    def getRawType(self): return self.type
    def setExplicitDefine(self, explicit_define):
        self.explicit_define = explicit_define
    def isExplicitDefine(self): return self.explicit_define
    def isAbstract(self): return self.abstract_type
    def setListType(self, listType): self.listType = listType
    def isListType(self): return self.listType
    def getType(self):
        returnType = self.type
        if self._PGenr.ElementDict.has_key(self.type):
            typeObj = self._PGenr.ElementDict[self.type]
            typeObjType = typeObj.getRawType()
            if self._PGenr.is_builtin_simple_type(typeObjType):
                returnType = typeObjType
        return returnType
    def getSchemaType(self):
        if self.schema_type:
            return self.schema_type
        return None
    def isComplex(self): return self.complex
    def addAttributeDefs(self, attrs): self.attributeDefs.append(attrs)
    def getAttributeDefs(self): return self.attributeDefs
    def isMixed(self): return self.mixed
    def setMixed(self, mixed): self.mixed = mixed
    def setBase(self, base): self.base = base
    def getBase(self): return self.base
    def getMixedExtensionError(self): return self.mixedExtensionError
    def getAttributeGroups(self): return self.attributeGroups
    def addAttribute(self, name, attribute):
        self.attributeGroups[name] = attribute
    def setAttributeGroup(self, attributeGroup): self.attributeGroup = attributeGroup
    def getAttributeGroup(self): return self.attributeGroup
    def setElementGroup(self, elementGroup): self.elementGroup = elementGroup
    def getElementGroup(self): return self.elementGroup
    def setTopLevel(self, topLevel): self.topLevel = topLevel
    def getTopLevel(self): return self.topLevel
    def setAnyAttribute(self, anyAttribute): self.anyAttribute = anyAttribute
    def getAnyAttribute(self): return self.anyAttribute
    def setSimpleType(self, simpleType): self.simpleType = simpleType
    def getSimpleType(self): return self.simpleType
    def setDefault(self, default): self.default = default
    def getDefault(self): return self.default
    def getSimpleBase(self): return self.simpleBase
    def setSimpleBase(self, simpleBase): self.simpleBase = simpleBase
    def addSimpleBase(self, simpleBase): self.simpleBase.append(simpleBase)
    def getRestrictionBase(self): return self.restrictionBase
    def setRestrictionBase(self, base): self.restrictionBase = base
    def getRestrictionBaseObj(self):
        rBaseObj = None
        rBaseName = self.getRestrictionBase()
        if rBaseName and rBaseName in self._PGenr.ElementDict:
            rBaseObj = self._PGenr.ElementDict[rBaseName]
        return rBaseObj
    def setSimpleContent(self, simpleContent):
        self.simpleContent = simpleContent
    def getSimpleContent(self):
        return self.simpleContent
    def getExtended(self): return self.extended
    def setExtended(self, extended): self.extended = extended

    def show(self, outfile, level):
        if self.name == 'Reference':
            showLevel(outfile, level)
            outfile.write('Name: %s  Type: %s  id: %d\n' % (self.name,
                self.getType(), id(self),))
            showLevel(outfile, level)
            outfile.write('  - Complex: %d  MaxOccurs: %d  MinOccurs: %d\n' % \
                (self.complex, self.maxOccurs, self.minOccurs))
            showLevel(outfile, level)
            outfile.write('  - Attrs: %s\n' % self.attrs)
            showLevel(outfile, level)
            #outfile.write('  - AttributeDefs: %s\n' % self.attributeDefs)
            outfile.write('  - AttributeDefs:\n')
            for key, value in self.getAttributeDefs().items():
                showLevel(outfile, level + 1)
                outfile.write('- key: %s  value: %s\n' % (key, value, ))
        for child in self.children:
            child.show(outfile, level + 1)

    def annotate(self):
        # resolve group references within groups
        for grp in self._PGenr.ElementGroups.values():
            expandGroupReferences(grp)
        # Recursively expand group references
        visited = set()
        self.expandGroupReferences_tree(visited)
        self.collect_element_dict()
        self.annotate_find_type()
        self.annotate_tree()
        self.fix_dup_names()
        self.coerce_attr_types()
        self.checkMixedBases()
        self.markExtendedTypes()

    def markExtendedTypes(self):
        base = self.getBase()
        if base and base in self._PGenr.ElementDict:
            parent = self._PGenr.ElementDict[base]
            parent.setExtended(True)
        for child in self.children:
            child.markExtendedTypes()

    def expandGroupReferences_tree(self, visited):
        if self.getName() in visited:
            return
        visited.add(self.getName())
        expandGroupReferences(self)
        for child in self.children:
            child.expandGroupReferences_tree(visited)

    def collect_element_dict(self):
        base = self.getBase()
        if self.getTopLevel() or len(self.getChildren()) > 0 or \
            len(self.getAttributeDefs()) > 0 or base:
            self._PGenr.ElementDict[self.name] = self
        for child in self.children:
            child.collect_element_dict()

    def build_element_dict(self, elements):
        base = self.getBase()
        if self.getTopLevel() or len(self.getChildren()) > 0 or \
            len(self.getAttributeDefs()) > 0 or base:
            if self.name not in elements:
                elements[self.name] = self
        for child in self.children:
            child.build_element_dict(elements)

    def get_element(self, element_name):
        if self.element_dict is None:
            self.element_dict = dict()
            self.build_element_dict(self.element_dict)
        return self.element_dict.get(element_name)

    # If it is a mixed-content element and it is defined as
    #   an extension, then all of its bases (base, base of base, ...)
    #   must be mixed-content.  Mark it as an error, if not.
    def checkMixedBases(self):
        self.rationalizeMixedBases()
        self.collectSimpleBases()
        self.checkMixedBasesChain(self, self.mixed)
        for child in self.children:
            child.checkMixedBases()

    def collectSimpleBases(self):
        if self.base:
            self.addSimpleBase(self.base.encode('utf-8'))
        if self.simpleBase:
            base1 = self._PGenr.SimpleTypeDict.get(self.simpleBase[0])
            if base1:
                base2 = base1.base or None
            else:
                base2 = None
            while base2:
                self.addSimpleBase(base2.encode('utf-8'))
                base2 = self._PGenr.SimpleTypeDict.get(base2)
                if base2:
                    base2 = base2.getBase()

    def rationalizeMixedBases(self):
        mixed = self.hasMixedInChain()
        if mixed:
            self.equalizeMixedBases()

    def hasMixedInChain(self):
        if self.isMixed():
            return True
        base = self.getBase()
        if base and base in self._PGenr.ElementDict:
            parent = self._PGenr.ElementDict[base]
            return parent.hasMixedInChain()
        else:
            return False

    def equalizeMixedBases(self):
        if not self.isMixed():
            self.setMixed(True)
        base = self.getBase()
        if base and base in self._PGenr.ElementDict:
            parent = self._PGenr.ElementDict[base]
            parent.equalizeMixedBases()

    def checkMixedBasesChain(self, child, childMixed):
        base = self.getBase()
        if base and base in self._PGenr.ElementDict:
            parent = self._PGenr.ElementDict[base]
            if childMixed != parent.isMixed():
                self.mixedExtensionError = 1
                return
            parent.checkMixedBasesChain(child, childMixed)

    def resolve_type(self):
        self.complex = 0
        # If it has any attributes, then it's complex.
        attrDefs = self.getAttributeDefs()
        if len(attrDefs) > 0:
            self.complex = 1
            # type_val = ''
        type_val = self.resolve_type_1()
        if type_val == self._PGenr.AnyType:
            return self._PGenr.AnyType
        if type_val in self._PGenr.SimpleTypeDict:
            self.addSimpleBase(type_val.encode('utf-8'))
            simple_type = self._PGenr.SimpleTypeDict[type_val]
            list_type = simple_type.resolve_list_type(self._PGenr.SimpleTypeDict)
            self.setListType(list_type)
        if type_val:
            if type_val in self._PGenr.ElementDict:
                type_val1 = type_val
                # The following loop handles the case where an Element's
                # reference element has no sub-elements and whose type is
                # another simpleType (potentially of the same name). Its
                # fundamental function is to avoid the incorrect
                # categorization of "complex" to Elements which are not and
                # correctly resolve the Element's type as well as its
                # potential values. It also handles cases where the Element's
                # "simpleType" is so-called "top level" and is only available
                # through the global SimpleTypeDict.
                i = 0
                while True:
                    element = self._PGenr.ElementDict[type_val1]
                    # Resolve our potential values if present
                    self.values = element.values
                    # If the type is available in the SimpleTypeDict, we
                    # know we've gone far enough in the Element hierarchy
                    # and can return the correct base type.
                    t = element.resolve_type_1()
                    if t in self._PGenr.SimpleTypeDict:
                        type_val1 = self._PGenr.SimpleTypeDict[t].getBase()
                        if type_val1 and not self._PGenr.is_builtin_simple_type(type_val1):
                            type_val1 = strip_namespace(type_val1)
                        break
                    # If the type name is the same as the previous type name
                    # then we know we've fully resolved the Element hierarchy
                    # and the Element is well and truely "complex". There is
                    # also a need to handle cases where the Element name and
                    # its type name are the same (ie. this is our first time
                    # through the loop). For example:
                    #   <xsd:element name="ReallyCool" type="ReallyCool"/>
                    #   <xsd:simpleType name="ReallyCool">
                    #     <xsd:restriction base="xsd:string">
                    #       <xsd:enumeration value="MyThing"/>
                    #     </xsd:restriction>
                    #   </xsd:simpleType>
                    if t == type_val1 and i != 0:
                        break
                    if t not in self._PGenr.ElementDict:
                        type_val1 = t
                        break
                    type_val1 = t
                    i += 1
                if self._PGenr.is_builtin_simple_type(type_val1):
                    type_val = type_val1
                else:
                    self.complex = 1
            elif type_val in self._PGenr.SimpleTypeDict:
                count = 0
                type_val1 = type_val
                while True:
                    element = self._PGenr.SimpleTypeDict[type_val1]
                    type_val1 = element.getBase()
                    if type_val1 and not self._PGenr.is_builtin_simple_type(type_val1):
                        type_val1 = strip_namespace(type_val1)
                    if type_val1 is None:
                        # Something seems wrong.  Can't find base simple type.
                        #   Give up and use default.
                        type_val = self._PGenr.StringType[0]
                        break
                    if type_val1 in self._PGenr.SimpleTypeDict:
                        count += 1
                        if count > 10:
                            # Give up.  We're in a loop.  Use default.
                            type_val = self._PGenr.StringType[0]
                            break
                    else:
                        type_val = type_val1
                        break
            else:
                if self._PGenr.is_builtin_simple_type(type_val):
                    pass
                else:
                    type_val = self._PGenr.StringType[0]
        else:
            type_val = self._PGenr.StringType[0]
        return type_val

    def resolve_type_1(self):
        type_val = ''
        if 'type' in self.attrs:
            type_val = self.attrs['type']
            if type_val in self._PGenr.SimpleTypeDict:
                self.simpleType = type_val
        elif 'ref' in self.attrs:
            type_val = strip_namespace(self.attrs['ref'])
        elif 'name' in self.attrs:
            type_val = strip_namespace(self.attrs['name'])
            #type_val = self.attrs['name']
        return type_val

    def annotate_find_type(self):
        self.schema_type = None
        if 'type' in self.attrs:
            self.schema_type = self.attrs['type']
        if self.type == self._PGenr.AnyTypeIdentifier:
            pass
        else:
            type_val = self.resolve_type()
            self.attrs['type'] = type_val
            self.type = type_val
        if not self.complex:
            self._PGenr.SimpleElementDict[self.name] = self
        for child in self.children:
            child.annotate_find_type()

    def annotate_tree(self):
        # If there is a namespace, replace it with an underscore.
        if self.base:
            self.base = strip_namespace(self.base)
        self.unmappedCleanName = self._PGenr.cleanupName(self.name)
        self.cleanName = self._PGenr.mapName(self.unmappedCleanName)
        self.replace_attributeGroup_names()
        # Resolve "maxOccurs" attribute
        if 'maxOccurs' in self.attrs.keys():
            maxOccurs = self.attrs['maxOccurs']
        elif self.choice and 'maxOccurs' in self.choice.attrs.keys():
            maxOccurs = self.choice.attrs['maxOccurs']
        else:
            maxOccurs = 1
        # Resolve "minOccurs" attribute
        if 'minOccurs' in self.attrs.keys():
            minOccurs = self.attrs['minOccurs']
        elif self.choice and 'minOccurs' in self.choice.attrs.keys():
            minOccurs = self.choice.attrs['minOccurs']
        else:
            minOccurs = 1
        # Cleanup "minOccurs" and "maxOccurs" attributes
        try:
            minOccurs = int(minOccurs)
            if minOccurs == 0:
                self.optional = True
        except ValueError:
            err_msg('*** %s  minOccurs must be integer.\n' % self.getName())
            sys.exit(1)
        try:
            if maxOccurs == 'unbounded':
                maxOccurs = 99999
            else:
                maxOccurs = int(maxOccurs)
        except ValueError:
            err_msg('*** %s  maxOccurs must be integer or "unbounded".\n' % (
                self.getName(), ))
            sys.exit(1)
        self.minOccurs = minOccurs
        self.maxOccurs = maxOccurs

        # If it does not have a type, then make the type the same as the name.
        if self.type == 'NoneType' and self.name:
            self.type = self.name
        # Is it a mixed-content element definition?
        if 'mixed' in self.attrs.keys():
            mixed = self.attrs['mixed'].strip()
            if mixed == '1' or mixed.lower() == 'true':
                self.mixed = 1
        # If this element has a base and the base is a simple type and
        #   the simple type is collapseWhiteSpace, then mark this
        #   element as collapseWhiteSpace.
        base = self.getBase()
        if base and base in self._PGenr.SimpleTypeDict:
            parent = self._PGenr.SimpleTypeDict[base]
            if isinstance(parent, SimpleTypeElement) and \
                parent.collapseWhiteSpace:
                self.collapseWhiteSpace = 1
        # Do it recursively for all descendents.
        for child in self.children:
            child.annotate_tree()

    #
    # For each name in the attributeGroupNameList for this element,
    #   add the attributes defined for that name in the global
    #   attributeGroup dictionary.
    def replace_attributeGroup_names(self):
        for groupName in self.attributeGroupNameList:
            key = None
            if self._PGenr.AttributeGroups.has_key(groupName):
                key =groupName
            else:
                # Looking for name space prefix
                keyList = groupName.split(':')
                if len(keyList) > 1:
                    key1 = keyList[1]
                    if self._PGenr.AttributeGroups.has_key(key1):
                        key = key1
            if key is not None:
                attrGroup = self._PGenr.AttributeGroups[key]
                for name in attrGroup.getKeys():
                    attr = attrGroup.get(name)
                    self.attributeDefs[name] = attr
            else:
                logging.debug('attributeGroup %s not defined.\n' % (
                    groupName, ))

    def __str__(self):
        s1 = '<XschemaElement name: "%s" type: "%s">' % \
            (self.getName(), self.getType(), )
        return s1
    __repr__ = __str__

    def fix_dup_names(self):
        # Patch-up names that are used for both a child element and an attribute.
        #
        attrDefs = self.getAttributeDefs()
        # Collect a list of child element names.
        #   Must do this for base (extension) elements also.
        elementNames = []
        self.collectElementNames(elementNames, 0)
        replaced = []
        # Create the needed new attributes.
        keys = attrDefs.keys()
        for key in keys:
            attr = attrDefs[key]
            name = attr.getName()
            if name in elementNames:
                newName = name + '_attr'
                newAttr = XschemaAttribute(self_.PGenr, newName)
                attrDefs[newName] = newAttr
                replaced.append(name)
        # Remove the old (replaced) attributes.
        for name in replaced:
            del attrDefs[name]
        for child in self.children:
            child.fix_dup_names()

    def collectElementNames(self, elementNames, count):
        for child in self.children:
            elementNames.append(self._PGenr.cleanupName(child.cleanName))
        base = self.getBase()
        if base and base in self._PGenr.ElementDict:
            parent = self._PGenr.ElementDict[base]
            count += 1
            if count > 100:
                msg = ('Extension/restriction recursion detected.  ' +
                      'Suggest you check definitions of types ' +
                      '%s and %s.'
                      )
                msg = msg % (self.getName(), parent.getName(), )
                raise RuntimeError(msg)
            parent.collectElementNames(elementNames, count)

    def coerce_attr_types(self):
        replacements = []
        attrDefs = self.getAttributeDefs()
        for idx, name in enumerate(attrDefs):
            attr = attrDefs[name]
            attrType = attr.getData_type()
            if attrType == self._PGenr.IDType or \
                attrType == self._PGenr.IDREFType or \
                attrType == self._PGenr.IDREFSType:
                attr.setData_type(self._PGenr.StringType[0])
        for child in self.children:
            child.coerce_attr_types()
# end class XschemaElement

class XschemaAttributeGroup:
    def __init__(self, name='', group=None):
        self.name = name
        if group:
            self.group = group
        else:
            self.group = {}
    def setName(self, name): self.name = name
    def getName(self): return self.name
    def setGroup(self, group): self.group = group
    def getGroup(self): return self.group
    def get(self, name, default=None):
        if self.group.has_key(name):
            return self.group[name]
        else:
            return default
    def getKeys(self):
        return self.group.keys()
    def add(self, name, attr):
        self.group[name] = attr
    def delete(self, name):
        if has_key(self.group, name):
            del self.group[name]
            return 1
        else:
            return 0
# end class XschemaAttributeGroup

class XschemaGroup:
    def __init__(self, ref):
        self.ref = ref
# end class XschemaGroup

class XschemaAttribute:
    def __init__(self, parser_generator, name, data_type='xs:string', use='optional', default=None):
        self._PGenr = parser_generator
        self.name = name
        self.cleanName = self._PGenr.cleanupName(name)
        self.data_type = data_type
        self.use = use
        self.default = default
        # Enumeration values for the attribute.
        self.values = list()
    def getCleanName(self): return self.cleanName
    def setName(self, name): self.name = name
    def getName(self): return self.name
    def setData_type(self, data_type): self.data_type = data_type
    def getData_type(self): return self.data_type
    def getType(self):
        returnType = self.data_type
        if self._PGenr.SimpleElementDict.has_key(self.data_type):
            typeObj = self._PGenr.SimpleElementDict[self.data_type]
            typeObjType = typeObj.getRawType()
            if typeObjType in StringType or \
                typeObjType == TokenType or \
                typeObjType == DateTimeType or \
                typeObjType == TimeType or \
                typeObjType == DateType or \
                typeObjType in IntegerType or \
                typeObjType == DecimalType or \
                typeObjType == PositiveIntegerType or \
                typeObjType == NegativeIntegerType or \
                typeObjType == NonPositiveIntegerType or \
                typeObjType == NonNegativeIntegerType or \
                typeObjType == BooleanType or \
                typeObjType == FloatType or \
                typeObjType == DoubleType:
                returnType = typeObjType
        return returnType
    def setUse(self, use): self.use = use
    def getUse(self): return self.use
    def setDefault(self, default): self.default = default
    def getDefault(self): return self.default
# end class XschemaAttribute


#
# SAX handler
#
class XschemaHandler(handler.ContentHandler):
    def __init__(self, parser_generator):
        handler.ContentHandler.__init__(self)
        self.stack = []
        self.root = None
        self.inElement = 0
        self.inComplexType = 0
        self.inNonanonymousComplexType = 0
        self.inSequence = 0
        self.inChoice = 1
        self.inAttribute = 0
        self.inAttributeGroup = 0
        self.inSimpleType = 0
        self.inSimpleContent = 0
        self.inRestrictionType = 0
        self.inAnnotationType = 0
        self.inDocumentationType = 0
        # The last attribute we processed.
        self.lastAttribute = None
        # Simple types that exist in the global context and may be used to
        # qualify the type of many elements and/or attributes.
        self.topLevelSimpleTypes = list()
        # The current choice type we're in
        self.currentChoice = None
        self.firstElement = True
        self._PGenr = parser_generator

    def getRoot(self):
        return self.root

    def extractSchemaNamespace(self, attrs):
        schemaUri = 'http://www.w3.org/2001/XMLSchema'
        keys = [ x for x, v in attrs.items() if v == schemaUri ]
        if not keys:
            return None
        keys = [ x[6:] for x in keys if x.startswith('xmlns:') ]
        if not keys:
            return None
        return keys[0]

    def startElement(self, name, attrs):
        #LG global Targetnamespace, NamespacesDict, XsdNameSpace
        logging.debug("Start element: %s %s" % (name, repr(attrs.items())))
        if len(self.stack) == 0 and self.firstElement:
            self.firstElement = False
            schemaNamespace = self.extractSchemaNamespace(attrs)
            if schemaNamespace:
                self._PGenr.XsdNameSpace = schemaNamespace
                self._PGenr.set_type_constants(schemaNamespace + ':')
            else:
                if len(name.split(':')) == 1:
                    self._PGenr.XsdNameSpace = ''
                    self._PGenr.set_type_constants('')

        SchemaType = self._PGenr.SchemaType
        ElementType = self._PGenr.ElementType
        ComplexTypeType = self._PGenr.ComplexTypeType
        AnyType = self._PGenr.AnyType
        GroupType = self._PGenr.GroupType
        SequenceType = self._PGenr.SequenceType
        ChoiceType = self._PGenr.ChoiceType
        AttributeType = self._PGenr.AttributeType
        AttributeGroupType = self._PGenr.AttributeGroupType
        SimpleContentType = self._PGenr.SimpleContentType
        ComplexContentType = self._PGenr.ComplexContentType
        ExtensionType = self._PGenr.ExtensionType
        StringType             = self._PGenr.StringType
        IDTypes                = self._PGenr.IDTypes
        NameTypes              = self._PGenr.NameTypes
        TokenType              = self._PGenr.TokenType
        DateTimeType           = self._PGenr.DateTimeType
        TimeType               = self._PGenr.TimeType
        DateType               = self._PGenr.DateType
        IntegerType            = self._PGenr.IntegerType
        DecimalType            = self._PGenr.DecimalType
        PositiveIntegerType    = self._PGenr.PositiveIntegerType
        NegativeIntegerType    = self._PGenr.NegativeIntegerType
        NonPositiveIntegerType = self._PGenr.NonPositiveIntegerType
        NonNegativeIntegerType = self._PGenr.NonNegativeIntegerType
        BooleanType            = self._PGenr.BooleanType
        FloatType              = self._PGenr.FloatType
        DoubleType             = self._PGenr.DoubleType
        OtherSimpleTypes       = self._PGenr.OtherSimpleTypes
        AnyAttributeType = self._PGenr.AnyAttributeType
        SimpleTypeType = self._PGenr.SimpleTypeType
        RestrictionType = self._PGenr.RestrictionType
        EnumerationType = self._PGenr.EnumerationType
        MinInclusiveType = self._PGenr.MinInclusiveType
        MaxInclusiveType = self._PGenr.MaxInclusiveType
        UnionType = self._PGenr.UnionType
        WhiteSpaceType = self._PGenr.WhiteSpaceType
        ListType = self._PGenr.ListType
        AnnotationType = self._PGenr.AnnotationType
        DocumentationType = self._PGenr.DocumentationType

        if name == SchemaType:
            self.inSchema = 1
            element = XschemaElement(self._PGenr, attrs)
            if len(self.stack) == 1:
                element.setTopLevel(1)
            self.stack.append(element)
            # If there is an attribute "xmlns" and its value is
            #   "http://www.w3.org/2001/XMLSchema", then remember and
            #   use that namespace prefix.
            for name, value in attrs.items():
                if name[:6] == 'xmlns:':
                    nameSpace = name[6:] + ':'
                    self._PGenr.NamespacesDict[value] = nameSpace
                elif name == 'targetNamespace':
                    self.Targetnamespace = value
        elif (name == ElementType or
            ((name == ComplexTypeType) and (len(self.stack) == 1))
            ):
            self.inElement = 1
            self.inNonanonymousComplexType = 1
            element = XschemaElement(self._PGenr, attrs)
            if not 'type' in attrs.keys() and not 'ref' in attrs.keys():
                element.setExplicitDefine(1)
            if len(self.stack) == 1:
                element.setTopLevel(1)
            if 'substitutionGroup' in attrs.keys() and 'name' in attrs.keys():
                substituteName = attrs['name']
                headName = attrs['substitutionGroup']
                if headName not in self.SubstitutionGroups:
                    self.SubstitutionGroups[headName] = []
                self.SubstitutionGroups[headName].append(substituteName)
            if name == ComplexTypeType:
                element.complexType = 1
            if self.inChoice and self.currentChoice:
                element.choice = self.currentChoice
            self.stack.append(element)
        elif name == ComplexTypeType:
            # If it have any attributes and there is something on the stack,
            #   then copy the attributes to the item on top of the stack.
            if len(self.stack) > 1 and len(attrs) > 0:
                parentDict = self.stack[-1].getAttrs()
                for key in attrs.keys():
                    parentDict[key] = attrs[key]
            self.inComplexType = 1
        elif name == AnyType:
            element = XschemaElement(self._PGenr, attrs)
            element.type = AnyTypeIdentifier
            self.stack.append(element)
        elif name == GroupType:
            element = XschemaElement(self._PGenr, attrs)
            if len(self.stack) == 1:
                element.setTopLevel(1)
            self.stack.append(element)
        elif name == SequenceType:
            self.inSequence = 1
        elif name == ChoiceType:
            self.currentChoice = XschemaElement(self._PGenr, attrs)
            self.inChoice = 1
        elif name == AttributeType:
            self.inAttribute = 1
            if 'name' in attrs.keys():
                name = attrs['name']
            elif 'ref' in attrs.keys():
                name = strip_namespace(attrs['ref'])
            else:
                name = 'no_attribute_name'
            if 'type' in attrs.keys():
                data_type = attrs['type']
            else:
                data_type = StringType[0]
            if 'use' in attrs.keys():
                use = attrs['use']
            else:
                use = 'optional'
            if 'default' in attrs.keys():
                default = attrs['default']
            else:
                default = None
            if self.stack[-1].attributeGroup:
                # Add this attribute to a current attributeGroup.
                attribute = XschemaAttribute(self._PGenr, name, data_type, use, default)
                self.stack[-1].attributeGroup.add(name, attribute)
            else:
                # Add this attribute to the element/complexType.
                attribute = XschemaAttribute(self._PGenr, name, data_type, use, default)
                self.stack[-1].attributeDefs[name] = attribute
            self.lastAttribute = attribute
        elif name == AttributeGroupType:
            self.inAttributeGroup = 1
            # If it has attribute 'name', then it's a definition.
            #   Prepare to save it as an attributeGroup.
            if 'name' in attrs.keys():
                name = strip_namespace(attrs['name'])
                attributeGroup = XschemaAttributeGroup(name)
                element = XschemaElement(self._PGenr, attrs)
                if len(self.stack) == 1:
                    element.setTopLevel(1)
                element.setAttributeGroup(attributeGroup)
                self.stack.append(element)
            # If it has attribute 'ref', add it to the list of
            #   attributeGroups for this element/complexType.
            if 'ref' in attrs.keys():
                self.stack[-1].attributeGroupNameList.append(attrs['ref'])
        elif name == SimpleContentType:
            self.inSimpleContent = 1
            if len(self.stack) > 0:
                self.stack[-1].setSimpleContent(True)
        elif name == ComplexContentType:
            pass
        elif name == ExtensionType:
            if 'base' in attrs.keys() and len(self.stack) > 0:
                extensionBase = attrs['base']
                if extensionBase in StringType or \
                    extensionBase in IDTypes or \
                    extensionBase in NameTypes or \
                    extensionBase == TokenType or \
                    extensionBase == DateTimeType or \
                    extensionBase == TimeType or \
                    extensionBase == DateType or \
                    extensionBase in IntegerType or \
                    extensionBase == DecimalType or \
                    extensionBase == PositiveIntegerType or \
                    extensionBase == NegativeIntegerType or \
                    extensionBase == NonPositiveIntegerType or \
                    extensionBase == NonNegativeIntegerType or \
                    extensionBase == BooleanType or \
                    extensionBase == FloatType or \
                    extensionBase == DoubleType or \
                    extensionBase in OtherSimpleTypes:
                    if (len(self.stack) > 0 and
                        isinstance(self.stack[-1], XschemaElement)):
                        self.stack[-1].addSimpleBase(extensionBase.encode('utf-8'))
                else:
                    self.stack[-1].setBase(extensionBase)
        elif name == AnyAttributeType:
            # Mark the current element as containing anyAttribute.
            self.stack[-1].setAnyAttribute(1)
        elif name == SimpleTypeType:
            # fixlist
            if self.inAttribute:
                pass
            elif self.inSimpleType and self.inRestrictionType:
                pass
            else:
                # Save the name of the simpleType, but ignore everything
                #   else about it (for now).
                if 'name' in attrs.keys():
                    stName = self._PGenr.cleanupName(attrs['name'])
                elif len(self.stack) > 0:
                    stName = self._PGenr.cleanupName(self.stack[-1].getName())
                else:
                    stName = None
                # If the parent is an element, mark it as a simpleType.
                if len(self.stack) > 0:
                    self.stack[-1].setSimpleType(1)
                element = SimpleTypeElement(stName)
                element.setDefault(attrs.get('default'))
                self._PGenr.SimpleTypeDict[stName] = element
                self.stack.append(element)
            self.inSimpleType = 1
        elif name == RestrictionType:
            if self.inAttribute:
                if attrs.has_key('base'):
                    self.lastAttribute.setData_type(attrs['base'])
            else:
                # If we are in a simpleType, capture the name of
                #   the restriction base.
                if ((self.inSimpleType or self.inSimpleContent) and
                    'base' in attrs.keys()):
                    self.stack[-1].setBase(attrs['base'])
                else:
                    if 'base' in attrs.keys():
                        self.stack[-1].setRestrictionBase(attrs['base'])
                self.stack[-1].setRestrictionAttrs(dict(attrs))
            self.inRestrictionType = 1
        elif name in [EnumerationType, MinInclusiveType, MaxInclusiveType]:
            if not attrs.has_key('value'):
                return
            if self.inAttribute:
                # We know that the restriction is on an attribute and the
                # attributes of the current element are un-ordered so the
                # instance variable "lastAttribute" will have our attribute.
                values = self.lastAttribute.values
            elif self.inElement and attrs.has_key('value'):
                # We're not in an attribute so the restriction must have
                # been placed on an element and that element will still be
                # in the stack. We search backwards through the stack to
                # find the last element.
                element = None
                if self.stack:
                    for entry in reversed(self.stack):
                        if isinstance(entry, XschemaElement):
                            element = entry
                            break
                if element is None:
                    err_msg('Cannot find element to attach enumeration: %s\n' % (
                            attrs['value']), )
                    sys.exit(1)
                values = element.values
            elif self.inSimpleType and attrs.has_key('value'):
                # We've been defined as a simpleType on our own.
                values = self.stack[-1].values
            if name == EnumerationType:
                values.append(attrs['value'])
            else:
                if len(values) == 0:
                    values.extend([None, None])
                if name == MinInclusiveType:
                    values[0] = {'minimum': int(attrs['value'])}
                else:
                    values[1] = {'maximum': int(attrs['value'])}
        elif name == UnionType:
            # Union types are only used with a parent simpleType and we want
            # the parent to know what it's a union of.
            parentelement = self.stack[-1]
            if (isinstance(parentelement, SimpleTypeElement) and
                attrs.has_key('memberTypes')):
                for member in attrs['memberTypes'].split(" "):
                    self.stack[-1].unionOf.append(member)
        elif name == WhiteSpaceType and self.inRestrictionType:
            if attrs.has_key('value'):
                if attrs.getValue('value') == 'collapse':
                    self.stack[-1].collapseWhiteSpace = 1
        elif name == ListType:
            self.inListType = 1
            # fixlist
            if self.inSimpleType: # and self.inRestrictionType:
                self.stack[-1].setListType(1)
            if self.inSimpleType:
                if attrs.has_key('itemType'):
                    self.stack[-1].setBase(attrs['itemType'])
        elif name == AnnotationType:
            self.inAnnotationType = 1
        elif name == DocumentationType:
            if self.inAnnotationType:
                self.inDocumentationType = 1
        logging.debug("Start element stack: %d" % len(self.stack))

    def endElement(self, name):
        logging.debug("End element: %s" % (name))
        logging.debug("End element stack: %d" % (len(self.stack)))

        SchemaType = self._PGenr.SchemaType
        ElementType = self._PGenr.ElementType
        ComplexTypeType = self._PGenr.ComplexTypeType
        AnyType = self._PGenr.AnyType
        GroupType = self._PGenr.GroupType
        SequenceType = self._PGenr.SequenceType
        ChoiceType = self._PGenr.ChoiceType
        AttributeType = self._PGenr.AttributeType
        AttributeGroupType = self._PGenr.AttributeGroupType
        SimpleContentType = self._PGenr.SimpleContentType
        ComplexContentType = self._PGenr.ComplexContentType
        ExtensionType = self._PGenr.ExtensionType
        StringType             = self._PGenr.StringType
        IDTypes                = self._PGenr.IDTypes
        NameTypes              = self._PGenr.NameTypes
        TokenType              = self._PGenr.TokenType
        DateTimeType           = self._PGenr.DateTimeType
        TimeType               = self._PGenr.TimeType
        DateType               = self._PGenr.DateType
        IntegerType            = self._PGenr.IntegerType
        DecimalType            = self._PGenr.DecimalType
        PositiveIntegerType    = self._PGenr.PositiveIntegerType
        NegativeIntegerType    = self._PGenr.NegativeIntegerType
        NonPositiveIntegerType = self._PGenr.NonPositiveIntegerType
        NonNegativeIntegerType = self._PGenr.NonNegativeIntegerType
        BooleanType            = self._PGenr.BooleanType
        FloatType              = self._PGenr.FloatType
        DoubleType             = self._PGenr.DoubleType
        OtherSimpleTypes       = self._PGenr.OtherSimpleTypes
        AnyAttributeType = self._PGenr.AnyAttributeType
        SimpleTypeType = self._PGenr.SimpleTypeType
        RestrictionType = self._PGenr.RestrictionType
        EnumerationType = self._PGenr.EnumerationType
        MinInclusiveType = self._PGenr.MinInclusiveType
        UnionType = self._PGenr.UnionType
        WhiteSpaceType = self._PGenr.WhiteSpaceType
        ListType = self._PGenr.ListType
        AnnotationType = self._PGenr.AnnotationType
        DocumentationType = self._PGenr.DocumentationType

        if name == SimpleTypeType: # and self.inSimpleType:
            self.inSimpleType = 0
            if self.inAttribute:
                pass
            else:
                # If the simpleType is directly off the root, it may be used to
                # qualify the type of many elements and/or attributes so we
                # don't want to loose it entirely.
                simpleType = self.stack.pop()
                # fixlist
                if len(self.stack) == 1:
                    self.topLevelSimpleTypes.append(simpleType)
                    self.stack[-1].setListType(simpleType.isListType())
        elif name == RestrictionType and self.inRestrictionType:
            self.inRestrictionType = 0
        elif name == ElementType or (name == ComplexTypeType and self.stack[-1].complexType):
            self.inElement = 0
            self.inNonanonymousComplexType = 0
            if len(self.stack) >= 2:
                element = self.stack.pop()
                self.stack[-1].addChild(element)
        elif name == AnyType:
            if len(self.stack) >= 2:
                element = self.stack.pop()
                self.stack[-1].addChild(element)
        elif name == ComplexTypeType:
            self.inComplexType = 0
        elif name == SequenceType:
            self.inSequence = 0
        elif name == ChoiceType:
            self.currentChoice = None
            self.inChoice = 0
        elif name == AttributeType:
            self.inAttribute = 0
        elif name == AttributeGroupType:
            self.inAttributeGroup = 0
            if self.stack[-1].attributeGroup:
                # The top of the stack contains an XschemaElement which
                #   contains the definition of an attributeGroup.
                #   Save this attributeGroup in the
                #   global AttributeGroup dictionary.
                attributeGroup = self.stack[-1].attributeGroup
                name = attributeGroup.getName()
                self.AttributeGroups[name] = attributeGroup
                self.stack[-1].attributeGroup = None
                self.stack.pop()
            else:
                # This is a reference to an attributeGroup.
                # We have already added it to the list of attributeGroup names.
                # Leave it.  We'll fill it in during annotate.
                pass
        elif name == GroupType:
            element = self.stack.pop()
            name = element.getAttrs()['name']
            elementGroup = XschemaGroup(element.name)
            ref = element.getAttrs().get('ref')
            if len(self.stack) == 1 and ref is None:
                # This is the definition
                ElementGroups[name] = element
            elif len(self.stack) > 1 and ref is not None:
                # This is a reference. Add it to the parent's children. We
                # need to preserve the order of elements.
                element.setElementGroup(elementGroup)
                self.stack[-1].addChild(element)
        elif name == SchemaType:
            self.inSchema = 0
            if len(self.stack) != 1:
                # fixlist
                err_msg('*** error stack.  len(self.stack): %d\n' % (
                    len(self.stack), ))
                sys.exit(1)
            if self.root: #change made to avoide logging error
                logging.debug("Previous root: %s" % (self.root.name))
            else:
                logging.debug ("Prvious root:   None")
            self.root = self.stack[0]
            if self.root:
                logging.debug("New root: %s"  % (self.root.name))
            else:
                logging.debug("New root: None")
        elif name == SimpleContentType:
            self.inSimpleContent = 0
        elif name == ComplexContentType:
            pass
        elif name == ExtensionType:
            pass
        elif name == ListType:
            # List types are only used with a parent simpleType and can have a
            # simpleType child. So, if we're in a list type we have to be
            # careful to reset the inSimpleType flag otherwise the handler's
            # internal stack will not be unrolled correctly.
            self.inSimpleType = 1
            self.inListType = 0
        elif name == AnnotationType:
            self.inAnnotationType = 0
        elif name == DocumentationType:
            if self.inAnnotationType:
                self.inDocumentationType = 0

    def characters(self, chrs):
        if self.inDocumentationType:
            # If there is an annotation/documentation element, save it.
            text = ' '.join(chrs.strip().split())
            if len(self.stack) > 1 and len(chrs) > 0:
                self.stack[-1].documentation += chrs
        elif self.inElement:
            pass
        elif self.inComplexType:
            pass
        elif self.inSequence:
            pass
        elif self.inChoice:
            pass


#
# Code generation
#

#LG def generateExportFn_1(wrt, child, name, namespace, fill):
#LG     cleanName = cleanupName(name)
#LG     mappedName = mapName(cleanName)
#LG     child_type = child.getType()
#LG     if child_type in StringType or \
#LG         child_type == TokenType or \
#LG         child_type == DateTimeType or \
#LG         child_type == TimeType or \
#LG         child_type == DateType:
#LG         wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
#LG         wrt('%s            showIndent(outfile, level, pretty_print)\n' % fill)
#LG         # fixlist
#LG         if (child.getSimpleType() in SimpleTypeDict and
#LG             SimpleTypeDict[child.getSimpleType()].isListType()):
#LG             s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_string(quote_xml(' '.join(self.%s)).encode(ExternalEncoding), input_name='%s'), namespace_, eol_))\n" % \
#LG                 (fill, name, name, mappedName, name, )
#LG         else:
#LG             s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_string(quote_xml(self.%s).encode(ExternalEncoding), input_name='%s'), namespace_, eol_))\n" % \
#LG                 (fill, name, name, mappedName, name, )
#LG         wrt(s1)
#LG     elif child_type in IntegerType or \
#LG         child_type == PositiveIntegerType or \
#LG         child_type == NonPositiveIntegerType or \
#LG         child_type == NegativeIntegerType or \
#LG         child_type == NonNegativeIntegerType:
#LG         wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
#LG         wrt('%s            showIndent(outfile, level, pretty_print)\n' % fill)
#LG         if child.isListType():
#LG             s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_integer_list(self.%s, input_name='%s'), namespace_, eol_))\n" % \
#LG                 (fill, name, name, mappedName, name, )
#LG         else:
#LG             s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_integer(self.%s, input_name='%s'), namespace_, eol_))\n" % \
#LG                 (fill, name, name, mappedName, name, )
#LG         wrt(s1)
#LG     elif child_type == BooleanType:
#LG         wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
#LG         wrt('%s            showIndent(outfile, level, pretty_print)\n' % fill)
#LG         if child.isListType():
#LG             s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_boolean_list(self.gds_str_lower(str(self.%s)), input_name='%s'), namespace_, eol_))\n" % \
#LG                 (fill, name, name, mappedName, name, )
#LG         else:
#LG             s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_boolean(self.gds_str_lower(str(self.%s)), input_name='%s'), namespace_, eol_))\n" % \
#LG                 (fill, name, name, mappedName, name, )
#LG         wrt(s1)
#LG     elif child_type == FloatType or \
#LG         child_type == DecimalType:
#LG         wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
#LG         wrt('%s            showIndent(outfile, level, pretty_print)\n' % fill)
#LG         if child.isListType():
#LG             s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_float_list(self.%s, input_name='%s'), namespace_, eol_))\n" % \
#LG                 (fill, name, name, mappedName, name, )
#LG         else:
#LG             s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_float(self.%s, input_name='%s'), namespace_, eol_))\n" % \
#LG                 (fill, name, name, mappedName, name, )
#LG         wrt(s1)
#LG     elif child_type == DoubleType:
#LG         wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
#LG         wrt('%s            showIndent(outfile, level, pretty_print)\n' % fill)
#LG         if child.isListType():
#LG             s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_double_list(self.%s, input_name='%s'), namespace_, eol_))\n" % \
#LG                 (fill, name, name, mappedName, name, )
#LG         else:
#LG             s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_double(self.%s, input_name='%s'), namespace_, eol_))\n" % \
#LG                 (fill, name, name, mappedName, name, )
#LG         wrt(s1)
#LG     else:
#LG         wrt("%s        if self.%s is not None:\n" % (fill, mappedName))
#LG         # name_type_problem
#LG         if False:        # name == child.getType():
#LG             s1 = "%s            self.%s.export_xml(outfile, level, namespace_, pretty_print=pretty_print)\n" % \
#LG                 (fill, mappedName)
#LG         else:
#LG             s1 = "%s            self.%s.export_xml(outfile, level, namespace_, name_='%s', pretty_print=pretty_print)\n" % \
#LG                 (fill, mappedName, name)
#LG         wrt(s1)
#LG # end generateExportFn_1


#LG def generateExportFn_2(wrt, child, name, namespace, fill):
#LG     cleanName = cleanupName(name)
#LG     mappedName = mapName(cleanName)
#LG     child_type = child.getType()
#LG     # fix_simpletype
#LG     wrt("%s    for %s_ in self.%s:\n" % (fill, cleanName, mappedName, ))
#LG     if child_type in StringType or \
#LG         child_type == TokenType or \
#LG         child_type == DateTimeType or \
#LG         child_type == TimeType or \
#LG         child_type == DateType:
#LG         wrt('%s        showIndent(outfile, level, pretty_print)\n' % fill)
#LG         wrt("%s        outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_string(quote_xml(%s_).encode(ExternalEncoding), input_name='%s'), namespace_, eol_))\n" %
#LG             (fill, name, name, cleanName, name,))
#LG     elif child_type in IntegerType or \
#LG         child_type == PositiveIntegerType or \
#LG         child_type == NonPositiveIntegerType or \
#LG         child_type == NegativeIntegerType or \
#LG         child_type == NonNegativeIntegerType:
#LG         wrt('%s        showIndent(outfile, level, pretty_print)\n' % fill)
#LG         if child.isListType():
#LG             s1 = "%s        outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_integer_list(%s_, input_name='%s'), namespace_, eol_))\n" % \
#LG                 (fill, name, name, cleanName, name, )
#LG         else:
#LG             s1 = "%s        outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_integer(%s_, input_name='%s'), namespace_, eol_))\n" % \
#LG                 (fill, name, name, cleanName, name, )
#LG         wrt(s1)
#LG     elif child_type == BooleanType:
#LG         wrt('%s        showIndent(outfile, level, pretty_print)\n' % fill)
#LG         if child.isListType():
#LG             s1 = "%s        outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_boolean_list(self.gds_str_lower(str(%s_)), input_name='%s'), namespace_, eol_))\n" % \
#LG                 (fill, name, name, cleanName, name, )
#LG         else:
#LG             s1 = "%s        outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_boolean(self.gds_str_lower(str(%s_)), input_name='%s'), namespace_, eol_))\n" % \
#LG                 (fill, name, name, cleanName, name, )
#LG         wrt(s1)
#LG     elif child_type == FloatType or \
#LG         child_type == DecimalType:
#LG         wrt('%s        showIndent(outfile, level, pretty_print)\n' % fill)
#LG         if child.isListType():
#LG             s1 = "%s        outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_float_list(%s_, input_name='%s'), namespace_, eol_))\n" % \
#LG                 (fill, name, name, cleanName, name, )
#LG         else:
#LG             s1 = "%s        outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_float(%s_, input_name='%s'), namespace_, eol_))\n" % \
#LG                 (fill, name, name, cleanName, name, )
#LG         wrt(s1)
#LG     elif child_type == DoubleType:
#LG         wrt('%s        showIndent(outfile, level, pretty_print)\n' % fill)
#LG         if child.isListType():
#LG             s1 = "%s        outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_double_list(%s_, input_name='%s'), namespace_, eol_))\n" % \
#LG                 (fill, name, name, cleanName, name, )
#LG         else:
#LG             s1 = "%s        outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_double(%s_, input_name='%s'), namespace_, eol_))\n" % \
#LG                 (fill, name, name, cleanName, name, )
#LG         wrt(s1)
#LG     else:
#LG         # name_type_problem
#LG         if False:        # name == child.getType():
#LG             s1 = "%s        %s_.export_xml(outfile, level, namespace_, pretty_print=pretty_print)\n" % (fill, cleanName)
#LG         else:
#LG             s1 = "%s        %s_.export_xml(outfile, level, namespace_, name_='%s', pretty_print=pretty_print)\n" % \
#LG                 (fill, cleanName, name)
#LG         wrt(s1)
#LG # end generateExportFn_2


#LG def generateExportFn_3(wrt, child, name, namespace, fill):
#LG     cleanName = cleanupName(name)
#LG     mappedName = mapName(cleanName)
#LG     child_type = child.getType()
#LG     # fix_simpletype
#LG     if child_type in StringType or \
#LG         child_type == TokenType or \
#LG         child_type == DateTimeType or \
#LG         child_type == TimeType or \
#LG         child_type == DateType:
#LG         wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
#LG         wrt('%s            showIndent(outfile, level, pretty_print)\n' % fill)
#LG         # fixlist
#LG         if (child.getSimpleType() in SimpleTypeDict and
#LG             SimpleTypeDict[child.getSimpleType()].isListType()):
#LG             s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_string(quote_xml(' '.join(self.%s)).encode(ExternalEncoding), input_name='%s'), namespace_, eol_))\n" % \
#LG                 (fill, name, name, mappedName, name, )
#LG         else:
#LG             s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_string(quote_xml(self.%s).encode(ExternalEncoding), input_name='%s'), namespace_, eol_))\n" % \
#LG                 (fill, name, name, mappedName, name, )
#LG         wrt(s1)
#LG     elif child_type in IntegerType or \
#LG         child_type == PositiveIntegerType or \
#LG         child_type == NonPositiveIntegerType or \
#LG         child_type == NegativeIntegerType or \
#LG         child_type == NonNegativeIntegerType:
#LG         wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
#LG         wrt('%s            showIndent(outfile, level, pretty_print)\n' % fill)
#LG         if child.isListType():
#LG             s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_integer_list(self.%s, input_name='%s'), namespace_, eol_))\n" % \
#LG                 (fill, name, name, mappedName, name, )
#LG         else:
#LG             s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_integer(self.%s, input_name='%s'), namespace_, eol_))\n" % \
#LG                 (fill, name, name, mappedName, name, )
#LG         wrt(s1)
#LG     elif child_type == BooleanType:
#LG         wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
#LG         wrt('%s            showIndent(outfile, level, pretty_print)\n' % fill)
#LG         if child.isListType():
#LG             s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_boolean_list(self.gds_str_lower(str(self.%s)), input_name='%s'), namespace_, eol_))\n" % \
#LG                 (fill, name, name, mappedName, name )
#LG         else:
#LG             s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_boolean(self.gds_str_lower(str(self.%s)), input_name='%s'), namespace_, eol_))\n" % \
#LG                 (fill, name, name, mappedName, name )
#LG         wrt(s1)
#LG     elif child_type == FloatType or \
#LG         child_type == DecimalType:
#LG         wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
#LG         wrt('%s            showIndent(outfile, level, pretty_print)\n' % fill)
#LG         if child.isListType():
#LG             s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_float_list(self.%s, input_name='%s'), namespace_, eol_))\n" % \
#LG                 (fill, name, name, mappedName, name, )
#LG         else:
#LG             s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_float(self.%s, input_name='%s'), namespace_, eol_))\n" % \
#LG                 (fill, name, name, mappedName, name, )
#LG         wrt(s1)
#LG     elif child_type == DoubleType:
#LG         wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
#LG         wrt('%s            showIndent(outfile, level, pretty_print)\n' % fill)
#LG         if child.isListType():
#LG             s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_double_list(self.%s, input_name='%s'), namespace_, eol_))\n" % \
#LG                 (fill, name, name, mappedName, name, )
#LG         else:
#LG             s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_double(self.%s, input_name='%s'), namespace_, eol_))\n" % \
#LG                 (fill, name, name, mappedName, name, )
#LG         wrt(s1)
#LG     else:
#LG         wrt("%s        if self.%s is not None:\n" % (fill, mappedName))
#LG         # name_type_problem
#LG         if False:        # name == child.getType():
#LG             s1 = "%s            self.%s.export_xml(outfile, level, namespace_, pretty_print=pretty_print)\n" % \
#LG                 (fill, mappedName)
#LG         else:
#LG             s1 = "%s            self.%s.export_xml(outfile, level, namespace_, name_='%s', pretty_print=pretty_print)\n" % \
#LG                 (fill, mappedName, name)
#LG         wrt(s1)
#LG # end generateExportFn_3


#LG def generateExportAttributes(wrt, element, hasAttributes):
#LG     if len(element.getAttributeDefs()) > 0:
#LG         hasAttributes += 1
#LG         attrDefs = element.getAttributeDefs()
#LG         for key in attrDefs.keys():
#LG             attrDef = attrDefs[key]
#LG             name = attrDef.getName()
#LG             cleanName = mapName(cleanupName(name))
#LG             capName = make_gs_name(cleanName)
#LG             if True:            # attrDef.getUse() == 'optional':
#LG                 wrt("        if self.%s is not None and '%s' not in already_processed:\n" % (
#LG                     cleanName, cleanName, ))
#LG                 wrt("            already_processed.append('%s')\n" % (
#LG                     cleanName, ))
#LG                 indent = "    "
#LG             else:
#LG                 indent = ""
#LG             if (attrDef.getType() in StringType or
#LG                 attrDef.getType() in IDTypes or
#LG                 attrDef.getType() == TokenType or
#LG                 attrDef.getType() == DateTimeType or
#LG                 attrDef.getType() == TimeType or
#LG                 attrDef.getType() == DateType):
#LG                 s1 = '''%s        outfile.write(' %s=%%s' %% (self.gds_format_string(quote_attrib(self.%s).encode(ExternalEncoding), input_name='%s'), ))\n''' % \
#LG                     (indent, name, cleanName, name, )
#LG             elif attrDef.getType() in IntegerType or \
#LG                 attrDef.getType() == PositiveIntegerType or \
#LG                 attrDef.getType() == NonPositiveIntegerType or \
#LG                 attrDef.getType() == NegativeIntegerType or \
#LG                 attrDef.getType() == NonNegativeIntegerType:
#LG                 s1 = '''%s        outfile.write(' %s="%%s"' %% self.gds_format_integer(self.%s, input_name='%s'))\n''' % (
#LG                     indent, name, cleanName, name, )
#LG             elif attrDef.getType() == BooleanType:
#LG                 s1 = '''%s        outfile.write(' %s="%%s"' %% self.gds_format_boolean(self.gds_str_lower(str(self.%s)), input_name='%s'))\n''' % (
#LG                     indent, name, cleanName, name, )
#LG             elif attrDef.getType() == FloatType or \
#LG                 attrDef.getType() == DecimalType:
#LG                 s1 = '''%s        outfile.write(' %s="%%s"' %% self.gds_format_float(self.%s, input_name='%s'))\n''' % (
#LG                     indent, name, cleanName, name)
#LG             elif attrDef.getType() == DoubleType:
#LG                 s1 = '''%s        outfile.write(' %s="%%s"' %% self.gds_format_double(self.%s, input_name='%s'))\n''' % (
#LG                     indent, name, cleanName, name)
#LG             else:
#LG                 s1 = '''%s        outfile.write(' %s=%%s' %% (quote_attrib(self.%s), ))\n''' % (
#LG                     indent, name, cleanName, )
#LG             wrt(s1)
#LG     if element.getExtended():
#LG         wrt("        if self.extensiontype_ is not None and 'xsi:type' not in already_processed:\n")
#LG         wrt("            already_processed.append('xsi:type')\n")
#LG         wrt("            outfile.write(' xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\"')\n")
#LG         wrt('''            outfile.write(' xsi:type="%s"' % self.extensiontype_)\n''')
#LG     return hasAttributes
#LG # end generateExportAttributes

#LG def generateExportChildren(wrt, element, hasChildren, namespace):
#LG     fill = '        '
#LG     if len(element.getChildren()) > 0:
#LG         hasChildren += 1
#LG         if element.isMixed():
#LG             wrt('%sif not fromsubclass_:\n' % (fill, ))
#LG             wrt("%s    for item_ in self.content_:\n" % (fill, ))
#LG             wrt("%s        item_.export_xml(outfile, level, item_.name, namespace_, pretty_print=pretty_print)\n" % (
#LG                 fill, ))
#LG         else:
#LG             wrt('%sif pretty_print:\n' % (fill, ))
#LG             wrt("%s    eol_ = '\\n'\n" % (fill, ))
#LG             wrt('%selse:\n' % (fill, ))
#LG             wrt("%s    eol_ = ''\n" % (fill, ))
#LG             any_type_child = None
#LG             for child in element.getChildren():
#LG                 unmappedName = child.getName()
#LG                 name = mapName(cleanupName(child.getName()))
#LG                 # fix_abstract
#LG                 type_element = None
#LG                 abstract_child = False
#LG                 type_name = child.getAttrs().get('type')
#LG                 if type_name:
#LG                     type_element = ElementDict.get(type_name)
#LG                 if type_element and type_element.isAbstract():
#LG                     abstract_child = True
#LG                 if child.getType() == AnyTypeIdentifier:
#LG                     any_type_child = child
#LG                 else:
#LG                     if abstract_child and child.getMaxOccurs() > 1:
#LG                         wrt("%sfor %s_ in self.get%s():\n" % (fill,
#LG                             name, make_gs_name(name),))
#LG                         wrt("%s    %s_.export_xml(outfile, level, namespace_, name_='%s', pretty_print=pretty_print)\n" % (
#LG                             fill, name, name, ))
#LG                     elif abstract_child:
#LG                         wrt("%sif self.%s is not None:\n" % (fill, name, ))
#LG                         wrt("%s    self.%s.export_xml(outfile, level, namespace_, name_='%s', pretty_print=pretty_print)\n" % (
#LG                             fill, name, name, ))
#LG                     elif child.getMaxOccurs() > 1:
#LG                         generateExportFn_2(wrt, child, unmappedName, namespace, '    ')
#LG                     else:
#LG                         if (child.getOptional()):
#LG                             generateExportFn_3(wrt, child, unmappedName, namespace, '')
#LG                         else:
#LG                             generateExportFn_1(wrt, child, unmappedName, namespace, '')
#LG             if any_type_child is not None:
#LG                 if any_type_child.getMaxOccurs() > 1:
#LG                     wrt('        for obj_ in self.anytypeobjs_:\n')
#LG                     wrt("            obj_.export_xml(outfile, level, namespace_, pretty_print=pretty_print)\n")
#LG                 else:
#LG                     wrt('        if self.anytypeobjs_ is not None:\n')
#LG                     wrt("            self.anytypeobjs_.export_xml(outfile, level, namespace_, pretty_print=pretty_print)\n")
#LG     return hasChildren
#LG # end generateExportChildren


#LG def countChildren(element, count):
#LG     count += len(element.getChildren())
#LG     base = element.getBase()
#LG     if base and base in self._PGenr.ElementDict:
#LG         parent = self._PGenr.ElementDict[base]
#LG         count = countChildren(parent, count)
#LG     return count

#LG def getParentName(element):
#LG     base = element.getBase()
#LG     rBase = element.getRestrictionBaseObj()
#LG     parentName = None
#LG     parentObj = None
#LG     if base and base in self._PGenr.ElementDict:
#LG         parentObj = self._PGenr.ElementDict[base]
#LG         parentName = cleanupName(parentObj.getName())
#LG     elif rBase:
#LG         base = element.getRestrictionBase()
#LG         parentObj = self._PGenr.ElementDict[base]
#LG         parentName = cleanupName(parentObj.getName())
#LG     return parentName, parentObj

#LG def generateExportFn(wrt, prefix, element, namespace):
#LG     childCount = countChildren(element, 0)
#LG     name = element.getName()
#LG     base = element.getBase()
#LG     LangGenr.generateExport(wrt, namespace, element)
#LG     #LG wrt("    def export_xml(self, outfile, level, namespace_='%s', name_='%s', namespacedef_='', pretty_print=True):\n" % \
#LG     #LG     (namespace, name, ))
#LG     #LG wrt('        if pretty_print:\n')
#LG     #LG wrt("            eol_ = '\\n'\n")
#LG     #LG wrt('        else:\n')
#LG     #LG wrt("            eol_ = ''\n")
#LG     #LG wrt('        showIndent(outfile, level, pretty_print)\n')
#LG     #LG wrt("        outfile.write('<%s%s%s' % (namespace_, name_, namespacedef_ and ' ' + namespacedef_ or '', ))\n")
#LG     #LG wrt("        already_processed = []\n")
#LG     #LG wrt("        self.exportAttributes(outfile, level, already_processed, namespace_, name_='%s')\n" % \
#LG     #LG     (name, ))
#LG     #LG # fix_abstract
#LG     #LG if base and base in ElementDict:
#LG     #LG     base_element = ElementDict[base]
#LG     #LG     # fix_derived
#LG     #LG     if base_element.isAbstract():
#LG     #LG         pass
#LG     #LG if childCount == 0 and element.isMixed():
#LG     #LG     wrt("        outfile.write('>')\n")
#LG     #LG     wrt("        self.exportChildren(outfile, level + 1, namespace_, name_, pretty_print=pretty_print)\n")
#LG     #LG     wrt("        outfile.write('</%s%s>%s' % (namespace_, name_, eol_))\n")
#LG     #LG else:
#LG     #LG     wrt("        if self.hasContent_():\n")
#LG     #LG     # Added to keep value on the same line as the tag no children.
#LG     #LG     if element.getSimpleContent():
#LG     #LG         wrt("            outfile.write('>')\n")
#LG     #LG         if not element.isMixed():
#LG     #LG             wrt("            outfile.write(str(self.valueOf_).encode(ExternalEncoding))\n")
#LG     #LG     else:
#LG     #LG         wrt("            outfile.write('>%s' % (eol_, ))\n")
#LG     #LG     wrt("            self.exportChildren(outfile, level + 1, namespace_, name_, pretty_print=pretty_print)\n")
#LG     #LG     # Put a condition on the indent to require children.
#LG     #LG     if childCount != 0:
#LG     #LG         wrt('            showIndent(outfile, level, pretty_print)\n')
#LG     #LG     wrt("            outfile.write('</%s%s>%s' % (namespace_, name_, eol_))\n")
#LG     #LG     wrt("        else:\n")
#LG     #LG     wrt("            outfile.write('/>%s' % (eol_, ))\n")
#LG     LangGenr.generateExportAttributesFn(wrt, namespace, element)
#LG     #LG wrt("    def exportAttributes(self, outfile, level, already_processed, namespace_='%s', name_='%s'):\n" % \
#LG     #LG     (namespace, name, ))
#LG     #LG hasAttributes = 0
#LG     #LG if element.getAnyAttribute():
#LG     #LG     wrt("        unique_counter = 0\n")
#LG     #LG     wrt('        for name, value in self.anyAttributes_.items():\n')
#LG     #LG     wrt("            xsinamespaceprefix = 'xsi'\n")
#LG     #LG     wrt("            xsinamespace1 = 'http://www.w3.org/2001/XMLSchema-instance'\n")
#LG     #LG     wrt("            xsinamespace2 = '{%s}' % (xsinamespace1, )\n")
#LG     #LG     wrt("            if name.startswith(xsinamespace2):\n")
#LG     #LG     wrt("                name1 = name[len(xsinamespace2):]\n")
#LG     #LG     wrt("                name2 = '%s:%s' % (xsinamespaceprefix, name1, )\n")
#LG     #LG     wrt("                if name2 not in already_processed:\n")
#LG     #LG     wrt("                    already_processed.append(name2)\n")
#LG     #LG     wrt("                    outfile.write(' %s=%s' % (name2, quote_attrib(value), ))\n")
#LG     #LG     wrt("            else:\n")
#LG     #LG     wrt("                mo = re_.match(Namespace_extract_pat_, name)\n")
#LG     #LG     wrt("                if mo is not None:\n")
#LG     #LG     wrt("                    namespace, name = mo.group(1, 2)\n")
#LG     #LG     wrt("                    if name not in already_processed:\n")
#LG     #LG     wrt("                        already_processed.append(name)\n")
#LG     #LG     wrt("                        if namespace == 'http://www.w3.org/XML/1998/namespace':\n")
#LG     #LG     wrt("                            outfile.write(' %s=%s' % (name, quote_attrib(value), ))\n")
#LG     #LG     wrt("                        else:\n")
#LG     #LG     wrt("                            unique_counter += 1\n")
#LG     #LG     wrt("                            outfile.write(' xmlns:yyy%d=\"%s\"' % (unique_counter, namespace, ))\n")
#LG     #LG     wrt("                            outfile.write(' yyy%d:%s=%s' % (unique_counter, name, quote_attrib(value), ))\n")
#LG     #LG     wrt("                else:\n")
#LG     #LG     wrt("                    if name not in already_processed:\n")
#LG     #LG     wrt("                        already_processed.append(name)\n")
#LG     #LG     wrt("                        outfile.write(' %s=%s' % (name, quote_attrib(value), ))\n")
#LG     #LG parentName, parent = getParentName(element)
#LG     #LG if parentName:
#LG     #LG     hasAttributes += 1
#LG     #LG     elName = element.getCleanName()
#LG     #LG     wrt("        super(%s, self).exportAttributes(outfile, level, already_processed, namespace_, name_='%s')\n" % \
#LG     #LG         (elName, name, ))
#LG     #LG hasAttributes += generateExportAttributes(wrt, element, hasAttributes)
#LG     #LG if hasAttributes == 0:
#LG     #LG     wrt("        pass\n")
#LG     LangGenr.generateExportChildrenFn(wrt, namespace, element)
#LG     #LG wrt("    def exportChildren(self, outfile, level, namespace_='%s', name_='%s', fromsubclass_=False, pretty_print=True):\n" % \
#LG     #LG     (namespace, name, ))
#LG     #LG hasChildren = 0
#LG     #LG # Generate call to exportChildren in the superclass only if it is
#LG     #LG #  an extension, but *not* if it is a restriction.
#LG     #LG parentName, parent = getParentName(element)
#LG     #LG if parentName and not element.getRestrictionBaseObj():
#LG     #LG     hasChildren += 1
#LG     #LG     elName = element.getCleanName()
#LG     #LG     wrt("        super(%s, self).exportChildren(outfile, level, namespace_, name_, True, pretty_print=pretty_print)\n" % (elName, ))
#LG     #LG hasChildren += generateExportChildren(wrt, element, hasChildren, namespace)
#LG     #LG if childCount == 0:   # and not element.isMixed():
#LG     #LG     wrt("        pass\n")
#LG     #LG if True or hasChildren > 0 or element.isMixed():
#LG     #LG     generateHascontentMethod(wrt, element)
# end generateExportFn


#
# Generate exportLiteral method.
#

#LG def generateExportLiteralFn_1(wrt, child, name, fill):
#LG     cleanName = cleanupName(name)
#LG     mappedName = mapName(cleanName)
#LG     childType = child.getType()
#LG     if childType == AnyTypeIdentifier:
#LG         wrt('%s        if self.anytypeobjs_ is not None:\n' % (fill, ))
#LG         wrt('%s            showIndent(outfile, level)\n' % fill)
#LG         wrt("%s            outfile.write('anytypeobjs_=model_.anytypeobjs_(\\n')\n" % \
#LG             (fill, ))
#LG         wrt("%s            self.anytypeobjs_.exportLiteral(outfile, level)\n" % (
#LG             fill, ))
#LG         wrt('%s            showIndent(outfile, level)\n' % fill)
#LG         wrt("%s            outfile.write('),\\n')\n" % (fill, ))
#LG     else:
#LG         wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
#LG         if childType in StringType or \
#LG             childType in IDTypes or \
#LG             childType == TokenType or \
#LG             childType == DateTimeType or \
#LG             childType == TimeType or \
#LG             childType == DateType:
#LG     #        wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
#LG             wrt('%s            showIndent(outfile, level)\n' % fill)
#LG             if (child.getSimpleType() in SimpleTypeDict and
#LG                 SimpleTypeDict[child.getSimpleType()].isListType()):
#LG                 wrt("%s            if self.%s:\n" % (fill, mappedName, ))
#LG                 wrt("%s                outfile.write('%s=%%s,\\n' %% quote_python(' '.join(self.%s)).encode(ExternalEncoding)) \n" % \
#LG                     (fill, mappedName, mappedName, ))
#LG                 wrt("%s            else:\n" % (fill, ))
#LG                 wrt("%s                outfile.write('%s=None,\\n')\n" % \
#LG                     (fill, mappedName, ))
#LG             else:
#LG                 wrt("%s            outfile.write('%s=%%s,\\n' %% quote_python(self.%s).encode(ExternalEncoding))\n" % \
#LG                     (fill, mappedName, mappedName, ))
#LG         elif childType in IntegerType or \
#LG             childType == PositiveIntegerType or \
#LG             childType == NonPositiveIntegerType or \
#LG             childType == NegativeIntegerType or \
#LG             childType == NonNegativeIntegerType:
#LG     #        wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
#LG             wrt('%s            showIndent(outfile, level)\n' % fill)
#LG             wrt("%s            outfile.write('%s=%%d,\\n' %% self.%s)\n" % \
#LG                 (fill, mappedName, mappedName, ))
#LG         elif childType == BooleanType:
#LG     #        wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
#LG             wrt('%s            showIndent(outfile, level)\n' % fill)
#LG             wrt("%s            outfile.write('%s=%%s,\\n' %% self.%s)\n" % \
#LG                 (fill, mappedName, mappedName, ))
#LG         elif childType == FloatType or \
#LG             childType == DecimalType:
#LG     #        wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
#LG             wrt('%s            showIndent(outfile, level)\n' % fill)
#LG             wrt("%s            outfile.write('%s=%%f,\\n' %% self.%s)\n" % \
#LG                 (fill, mappedName, mappedName, ))
#LG         elif childType == DoubleType:
#LG     #        wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
#LG             wrt('%s            showIndent(outfile, level)\n' % fill)
#LG             wrt("%s            outfile.write('%s=%%e,\\n' %% self.%s)\n" % \
#LG                 (fill, name, mappedName, ))
#LG         else:
#LG     #        wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
#LG             wrt('%s            showIndent(outfile, level)\n' % fill)
#LG             wrt("%s            outfile.write('%s=model_.%s(\\n')\n" % \
#LG                 (fill, mappedName, mapName(cleanupName(child.getType()))))
#LG             if name == child.getType():
#LG                 s1 = "%s            self.%s.exportLiteral(outfile, level)\n" % \
#LG                     (fill, mappedName)
#LG             else:
#LG                 s1 = "%s            self.%s.exportLiteral(outfile, level, name_='%s')\n" % \
#LG                     (fill, mappedName, name)
#LG             wrt(s1)
#LG             wrt('%s            showIndent(outfile, level)\n' % fill)
#LG             wrt("%s            outfile.write('),\\n')\n" % (fill, ))
# end generateExportLiteralFn_1


#LG def generateExportLiteralFn_2(wrt, child, name, fill):
#LG     cleanName = cleanupName(name)
#LG     mappedName = mapName(cleanName)
#LG     childType = child.getType()
#LG     if childType in StringType or \
#LG         childType == TokenType or \
#LG         childType == DateTimeType or \
#LG         childType == TimeType or \
#LG         childType == DateType:
#LG         wrt('%s        showIndent(outfile, level)\n' % fill)
#LG         wrt("%s        outfile.write('%%s,\\n' %% quote_python(%s_).encode(ExternalEncoding))\n" % \
#LG             (fill, name))
#LG     elif childType in IntegerType or \
#LG         childType == PositiveIntegerType or \
#LG         childType == NonPositiveIntegerType or \
#LG         childType == NegativeIntegerType or \
#LG         childType == NonNegativeIntegerType:
#LG         wrt('%s        showIndent(outfile, level)\n' % fill)
#LG         wrt("%s        outfile.write('%%d,\\n' %% %s)\n" % (fill, name))
#LG     elif childType == BooleanType:
#LG         wrt('%s        showIndent(outfile, level)\n' % fill)
#LG         wrt("%s        outfile.write('%%s,\\n' %% %s)\n" % (fill, name))
#LG     elif childType == FloatType or \
#LG         childType == DecimalType:
#LG         wrt('%s        showIndent(outfile, level)\n' % fill)
#LG         wrt("%s        outfile.write('%%f,\\n' %% %s_)\n" % (fill, name))
#LG     elif childType == DoubleType:
#LG         wrt('%s        showIndent(outfile, level)\n' % fill)
#LG         wrt("%s        outfile.write('%%e,\\n' %% %s)\n" % (fill, name))
#LG     else:
#LG         wrt('%s        showIndent(outfile, level)\n' % fill)
#LG         name1 = mapName(cleanupName(child.getType()))
#LG         wrt("%s        outfile.write('model_.%s(\\n')\n" % (fill, name1, ))
#LG         if name == child.getType():
#LG             s1 = "%s        %s_.exportLiteral(outfile, level)\n" % (
#LG                 fill, cleanupName(child.getType()), )
#LG         else:
#LG             s1 = "%s        %s_.exportLiteral(outfile, level, name_='%s')\n" % \
#LG                 (fill, name, child.getType(), )
#LG         wrt(s1)
#LG         wrt('%s        showIndent(outfile, level)\n' % fill)
#LG         wrt("%s        outfile.write('),\\n')\n" % (fill, ))
# end generateExportLiteralFn_2


#LG def generateExportLiteralFn(wrt, prefix, element):
#LG     base = element.getBase()
#LG     wrt("    def exportLiteral(self, outfile, level, name_='%s'):\n" % element.getName())
#LG     wrt("        level += 1\n")
#LG     wrt("        self.exportLiteralAttributes(outfile, level, [], name_)\n")
#LG     wrt("        if self.hasContent_():\n")
#LG     wrt("            self.exportLiteralChildren(outfile, level, name_)\n")
#LG     childCount = countChildren(element, 0)
#LG     if element.getSimpleContent() or element.isMixed():
#LG         wrt("        showIndent(outfile, level)\n")
#LG         wrt("        outfile.write('valueOf_ = \"\"\"%s\"\"\",\\n' % (self.valueOf_,))\n")
#LG     wrt("    def exportLiteralAttributes(self, outfile, level, already_processed, name_):\n")
#LG     count = 0
#LG     attrDefs = element.getAttributeDefs()
#LG     for key in attrDefs:
#LG         attrDef = attrDefs[key]
#LG         count += 1
#LG         name = attrDef.getName()
#LG         cleanName = cleanupName(name)
#LG         capName = make_gs_name(cleanName)
#LG         mappedName = mapName(cleanName)
#LG         data_type = attrDef.getData_type()
#LG         attrType = attrDef.getType()
#LG         if attrType in SimpleTypeDict:
#LG             attrType = SimpleTypeDict[attrType].getBase()
#LG         if attrType in SimpleTypeDict:
#LG             attrType = SimpleTypeDict[attrType].getBase()
#LG         wrt("        if self.%s is not None and '%s' not in already_processed:\n" % (
#LG             mappedName, mappedName, ))
#LG         wrt("            already_processed.append('%s')\n" % (
#LG             mappedName, ))
#LG         if attrType in StringType or \
#LG             attrType in IDTypes or \
#LG             attrType == TokenType or \
#LG             attrType == DateTimeType or \
#LG             attrType == TimeType or \
#LG             attrType == DateType or \
#LG             attrType == NCNameType:
#LG             wrt("            showIndent(outfile, level)\n")
#LG             wrt("            outfile.write('%s = \"%%s\",\\n' %% (self.%s,))\n" % \
#LG                 (mappedName, mappedName,))
#LG         elif attrType in IntegerType or \
#LG             attrType == PositiveIntegerType or \
#LG             attrType == NonPositiveIntegerType or \
#LG             attrType == NegativeIntegerType or \
#LG             attrType == NonNegativeIntegerType:
#LG             wrt("            showIndent(outfile, level)\n")
#LG             wrt("            outfile.write('%s = %%d,\\n' %% (self.%s,))\n" % \
#LG                 (mappedName, mappedName,))
#LG         elif attrType == BooleanType:
#LG             wrt("            showIndent(outfile, level)\n")
#LG             wrt("            outfile.write('%s = %%s,\\n' %% (self.%s,))\n" % \
#LG                 (mappedName, mappedName,))
#LG         elif attrType == FloatType or \
#LG             attrType == DecimalType:
#LG             wrt("            showIndent(outfile, level)\n")
#LG             wrt("            outfile.write('%s = %%f,\\n' %% (self.%s,))\n" % \
#LG                 (mappedName, mappedName,))
#LG         elif attrType == DoubleType:
#LG             wrt("            showIndent(outfile, level)\n")
#LG             wrt("            outfile.write('%s = %%e,\\n' %% (self.%s,))\n" % \
#LG                 (mappedName, mappedName,))
#LG         else:
#LG             wrt("            showIndent(outfile, level)\n")
#LG             wrt("            outfile.write('%s = %%s,\\n' %% (self.%s,))\n" % \
#LG                 (mappedName, mappedName,))
#LG     if element.getAnyAttribute():
#LG         count += 1
#LG         wrt('        for name, value in self.anyAttributes_.items():\n')
#LG         wrt('            showIndent(outfile, level)\n')
#LG         wrt("            outfile.write('%s = \"%s\",\\n' % (name, value,))\n")
#LG     parentName, parent = getParentName(element)
#LG     if parentName:
#LG         count += 1
#LG         elName = element.getCleanName()
#LG         wrt("        super(%s, self).exportLiteralAttributes(outfile, level, already_processed, name_)\n" % \
#LG             (elName, ))
#LG     if count == 0:
#LG         wrt("        pass\n")
#LG     wrt("    def exportLiteralChildren(self, outfile, level, name_):\n")
#LG     parentName, parent = getParentName(element)
#LG     if parentName:
#LG         elName = element.getCleanName()
#LG         wrt("        super(%s, self).exportLiteralChildren(outfile, level, name_)\n" % \
#LG             (elName, ))
#LG     for child in element.getChildren():
#LG         name = child.getName()
#LG         name = cleanupName(name)
#LG         mappedName = mapName(name)
#LG         if element.isMixed():
#LG             wrt("        showIndent(outfile, level)\n")
#LG             wrt("        outfile.write('content_ = [\\n')\n")
#LG             wrt('        for item_ in self.content_:\n')
#LG             wrt('            item_.exportLiteral(outfile, level, name_)\n')
#LG             wrt("        showIndent(outfile, level)\n")
#LG             wrt("        outfile.write('],\\n')\n")
#LG         else:
#LG             # fix_abstract
#LG             type_element = None
#LG             abstract_child = False
#LG             type_name = child.getAttrs().get('type')
#LG             if type_name:
#LG                 type_element = ElementDict.get(type_name)
#LG             if type_element and type_element.isAbstract():
#LG                 abstract_child = True
#LG             if abstract_child:
#LG                 pass
#LG             else:
#LG                 type_name = name
#LG             if child.getMaxOccurs() > 1:
#LG                 if child.getType() == AnyTypeIdentifier:
#LG                     wrt("        showIndent(outfile, level)\n")
#LG                     wrt("        outfile.write('anytypeobjs_=[\\n')\n")
#LG                     wrt("        level += 1\n")
#LG                     wrt("        for anytypeobjs_ in self.anytypeobjs_:\n")
#LG                     wrt("            anytypeobjs_.exportLiteral(outfile, level)\n")
#LG                     wrt("        level -= 1\n")
#LG                     wrt("        showIndent(outfile, level)\n")
#LG                     wrt("        outfile.write('],\\n')\n")
#LG                 else:
#LG                     wrt("        showIndent(outfile, level)\n")
#LG                     wrt("        outfile.write('%s=[\\n')\n" % (mappedName, ))
#LG                     wrt("        level += 1\n")
#LG                     wrt("        for %s_ in self.%s:\n" % (name, mappedName))
#LG                     generateExportLiteralFn_2(wrt, child, name, '    ')
#LG                     wrt("        level -= 1\n")
#LG                     wrt("        showIndent(outfile, level)\n")
#LG                     wrt("        outfile.write('],\\n')\n")
#LG             else:
#LG                 generateExportLiteralFn_1(wrt, child, type_name, '')
#LG     if childCount == 0 or element.isMixed():
#LG         wrt("        pass\n")
# end generateExportLiteralFn

#
# Generate build method.
#

#LG def generateBuildAttributes(wrt, element, hasAttributes):
#LG     attrDefs = element.getAttributeDefs()
#LG     for key in attrDefs:
#LG         attrDef = attrDefs[key]
#LG         hasAttributes += 1
#LG         name = attrDef.getName()
#LG         cleanName = cleanupName(name)
#LG         mappedName = mapName(cleanName)
#LG         atype = attrDef.getType()
#LG         if atype in SimpleTypeDict:
#LG             atype = SimpleTypeDict[atype].getBase()
#LG         LangGenr.generateBuildAttributeForType(wrt, element, atype, name, mappedName)
#LG         #LG if atype in IntegerType or \
#LG         #LG     atype == PositiveIntegerType or \
#LG         #LG     atype == NonPositiveIntegerType or \
#LG         #LG     atype == NegativeIntegerType or \
#LG         #LG     atype == NonNegativeIntegerType:
#LG         #LG     wrt("        value = find_attr_value_('%s', node)\n" % (name, ))
#LG         #LG     wrt("        if value is not None and '%s' not in already_processed:\n" % (
#LG         #LG         name, ))
#LG         #LG     wrt("            already_processed.append('%s')\n" % (name, ))
#LG         #LG     wrt('            try:\n')
#LG         #LG     wrt("                self.%s = int(value)\n" % (mappedName, ))
#LG         #LG     wrt('            except ValueError, exp:\n')
#LG         #LG     wrt("                raise_parse_error(node, 'Bad integer attribute: %s' % exp)\n")
#LG         #LG     if atype == PositiveIntegerType:
#LG         #LG         wrt('            if self.%s <= 0:\n' % mappedName)
#LG         #LG         wrt("                raise_parse_error(node, 'Invalid PositiveInteger')\n")
#LG         #LG     elif atype == NonPositiveIntegerType:
#LG         #LG         wrt('            if self.%s > 0:\n' % mappedName)
#LG         #LG         wrt("                raise_parse_error(node, 'Invalid NonPositiveInteger')\n")
#LG         #LG     elif atype == NegativeIntegerType:
#LG         #LG         wrt('            if self.%s >= 0:\n' % mappedName)
#LG         #LG         wrt("                raise_parse_error(node, 'Invalid NegativeInteger')\n")
#LG         #LG     elif atype == NonNegativeIntegerType:
#LG         #LG         wrt('            if self.%s < 0:\n' % mappedName)
#LG         #LG         wrt("                raise_parse_error(node, 'Invalid NonNegativeInteger')\n")
#LG         #LG elif atype == BooleanType:
#LG         #LG     wrt("        value = find_attr_value_('%s', node)\n" % (name, ))
#LG         #LG     wrt("        if value is not None and '%s' not in already_processed:\n" % (
#LG         #LG         name, ))
#LG         #LG     wrt("            already_processed.append('%s')\n" % (name, ))
#LG         #LG     wrt("            if value in ('true', '1'):\n")
#LG         #LG     wrt("                self.%s = True\n" % mappedName)
#LG         #LG     wrt("            elif value in ('false', '0'):\n")
#LG         #LG     wrt("                self.%s = False\n" % mappedName)
#LG         #LG     wrt('            else:\n')
#LG         #LG     wrt("                raise_parse_error(node, 'Bad boolean attribute')\n")
#LG         #LG elif atype == FloatType or atype == DoubleType or atype == DecimalType:
#LG         #LG     wrt("        value = find_attr_value_('%s', node)\n" % (name, ))
#LG         #LG     wrt("        if value is not None and '%s' not in already_processed:\n" % (
#LG         #LG         name, ))
#LG         #LG     wrt("            already_processed.append('%s')\n" % (name, ))
#LG         #LG     wrt('            try:\n')
#LG         #LG     wrt("                self.%s = float(value)\n" % \
#LG         #LG         (mappedName, ))
#LG         #LG     wrt('            except ValueError, exp:\n')
#LG         #LG     wrt("                raise ValueError('Bad float/double attribute (%s): %%s' %% exp)\n" % \
#LG         #LG         (name, ))
#LG         #LG elif atype == TokenType:
#LG         #LG     wrt("        value = find_attr_value_('%s', node)\n" % (name, ))
#LG         #LG     wrt("        if value is not None and '%s' not in already_processed:\n" % (
#LG         #LG         name, ))
#LG         #LG     wrt("            already_processed.append('%s')\n" % (name, ))
#LG         #LG     wrt("            self.%s = value\n" % (mappedName, ))
#LG         #LG     wrt("            self.%s = ' '.join(self.%s.split())\n" % \
#LG         #LG         (mappedName, mappedName, ))
#LG         #LG else:
#LG         #LG     # Assume attr['type'] in StringType or attr['type'] == DateTimeType:
#LG         #LG     wrt("        value = find_attr_value_('%s', node)\n" % (name, ))
#LG         #LG     wrt("        if value is not None and '%s' not in already_processed:\n" % (
#LG         #LG         name, ))
#LG         #LG     wrt("            already_processed.append('%s')\n" % (name, ))
#LG         #LG     wrt("            self.%s = value\n" % (mappedName, ))
#LG         #LG typeName = attrDef.getType()
#LG         #LG if typeName and typeName in SimpleTypeDict:
#LG         #LG     wrt("            self.validate_%s(self.%s)    # validate type %s\n" % (
#LG         #LG         typeName, mappedName, typeName, ))
#LG     hasAttributes += LangGenr.generateBuildAttributeForAny(wrt, element)
#LG     #LG if element.getAnyAttribute():
#LG     #LG     hasAttributes += 1
#LG     #LG     wrt('        self.anyAttributes_ = {}\n')
#LG     #LG     wrt('        for name, value in attrs.items():\n')
#LG     #LG     wrt("            if name not in already_processed:\n")
#LG     #LG     wrt('                self.anyAttributes_[name] = value\n')
#LG     hasAttributes += LangGenr.generateBuildAttributeForExt(wrt, element)
#LG     #LG if element.getExtended():
#LG     #LG     hasAttributes += 1
#LG     #LG     wrt("        value = find_attr_value_('xsi:type', node)\n")
#LG     #LG     wrt("        if value is not None and 'xsi:type' not in already_processed:\n")
#LG     #LG     wrt("            already_processed.append('xsi:type')\n")
#LG     #LG     wrt("            self.extensiontype_ = value\n")
#LG     return hasAttributes
# end generateBuildAttributes


#LG def generateBuildMixed_1(wrt, prefix, child, headChild, keyword, delayed):
#LG     nestedElements = 1
#LG     origName = child.getName()
#LG     name = child.getCleanName()
#LG     headName = cleanupName(headChild.getName())
#LG     childType = child.getType()
#LG     mappedName = mapName(name)
#LG     base = child.getBase()
#LG     if childType in StringType or \
#LG         childType == TokenType or \
#LG         childType == DateTimeType or \
#LG         childType == TimeType or \
#LG         childType == DateType:
#LG         wrt("        %s nodeName_ == '%s' and child_.text is not None:\n" % (
#LG             keyword, origName, ))
#LG         wrt("            valuestr_ = child_.text\n")
#LG         if childType == TokenType:
#LG             wrt('            valuestr_ = re_.sub(String_cleanup_pat_, " ", valuestr_).strip()\n')
#LG         wrt("            obj_ = self.mixedclass_(MixedContainer.CategorySimple,\n")
#LG         wrt("                MixedContainer.TypeString, '%s', valuestr_)\n" % \
#LG             origName)
#LG         wrt("            self.content_.append(obj_)\n")
#LG     elif childType in IntegerType or \
#LG         childType == PositiveIntegerType or \
#LG         childType == NonPositiveIntegerType or \
#LG         childType == NegativeIntegerType or \
#LG         childType == NonNegativeIntegerType:
#LG         wrt("        %s nodeName_ == '%s' and child_.text is not None:\n" % (
#LG             keyword, origName, ))
#LG         wrt("            sval_ = child_.text\n")
#LG         wrt("            try:\n")
#LG         wrt("                ival_ = int(sval_)\n")
#LG         wrt("            except (TypeError, ValueError), exp:\n")
#LG         wrt("                raise_parse_error(child_, 'requires integer: %s' % exp)\n")
#LG         if childType == PositiveIntegerType:
#LG             wrt("            if ival_ <= 0:\n")
#LG             wrt("                raise_parse_error(child_, 'Invalid positiveInteger')\n")
#LG         if childType == NonPositiveIntegerType:
#LG             wrt("            if ival_ > 0:\n")
#LG             wrt("                raise_parse_error(child_, 'Invalid nonPositiveInteger)\n")
#LG         if childType == NegativeIntegerType:
#LG             wrt("            if ival_ >= 0:\n")
#LG             wrt("                raise_parse_error(child_, 'Invalid negativeInteger')\n")
#LG         if childType == NonNegativeIntegerType:
#LG             wrt("            if ival_ < 0:\n")
#LG             wrt("                raise_parse_error(child_, 'Invalid nonNegativeInteger')\n")
#LG         wrt("            obj_ = self.mixedclass_(MixedContainer.CategorySimple,\n")
#LG         wrt("                MixedContainer.TypeInteger, '%s', ival_)\n" % (
#LG             origName, ))
#LG         wrt("            self.content_.append(obj_)\n")
#LG     elif childType == BooleanType:
#LG         wrt("        %s nodeName_ == '%s' and child_.text is not None:\n" % (
#LG             keyword, origName, ))
#LG         wrt("            sval_ = child_.text\n")
#LG         wrt("            if sval_ in ('true', '1'):\n")
#LG         wrt("                ival_ = True\n")
#LG         wrt("            elif sval_ in ('false', '0'):\n")
#LG         wrt("                ival_ = False\n")
#LG         wrt("            else:\n")
#LG         wrt("                raise_parse_error(child_, 'requires boolean')\n")
#LG         wrt("        obj_ = self.mixedclass_(MixedContainer.CategorySimple,\n")
#LG         wrt("            MixedContainer.TypeInteger, '%s', ival_)\n" % \
#LG             origName)
#LG         wrt("        self.content_.append(obj_)\n")
#LG     elif childType == FloatType or \
#LG         childType == DoubleType or \
#LG         childType == DecimalType:
#LG         wrt("        %s nodeName_ == '%s' and child_.text is not None:\n" % (
#LG             keyword, origName, ))
#LG         wrt("            sval_ = child_.text\n")
#LG         wrt("            try:\n")
#LG         wrt("                fval_ = float(sval_)\n")
#LG         wrt("            except (TypeError, ValueError), exp:\n")
#LG         wrt("                raise_parse_error(child_, 'requires float or double: %s' % exp)\n")
#LG         wrt("            obj_ = self.mixedclass_(MixedContainer.CategorySimple,\n")
#LG         wrt("                MixedContainer.TypeFloat, '%s', fval_)\n" % \
#LG             origName)
#LG         wrt("            self.content_.append(obj_)\n")
#LG     else:
#LG         # Perhaps it's a complexType that is defined right here.
#LG         # Generate (later) a class for the nested types.
#LG         type_element = None
#LG         abstract_child = False
#LG         type_name = child.getAttrs().get('type')
#LG         if type_name:
#LG             type_element = ElementDict.get(type_name)
#LG         if type_element and type_element.isAbstract():
#LG             abstract_child = True
#LG         if not delayed and not child in DelayedElements:
#LG             DelayedElements.append(child)
#LG             DelayedElements_subclass.append(child)
#LG         wrt("        %s nodeName_ == '%s':\n" % (keyword, origName, ))
#LG         if abstract_child:
#LG             wrt(TEMPLATE_ABSTRACT_CHILD % (mappedName, ))
#LG         else:
#LG             type_obj = ElementDict.get(childType)
#LG             if type_obj is not None and type_obj.getExtended():
#LG                 wrt("            class_obj_ = self.get_class_obj_(child_, %s%s)\n" % (
#LG                     prefix, cleanupName(mapName(childType)), ))
#LG                 wrt("            class_obj_ = %s%s.factory()\n")
#LG             else:
#LG                 wrt("            obj_ = %s%s.factory()\n" % (
#LG                     prefix, cleanupName(mapName(childType))))
#LG             wrt("            obj_.build(child_)\n")
#LG
#LG         wrt("            obj_ = self.mixedclass_(MixedContainer.CategoryComplex,\n")
#LG         wrt("                MixedContainer.TypeNone, '%s', obj_)\n" % \
#LG             origName)
#LG         wrt("            self.content_.append(obj_)\n")
#LG
#LG         # Generate code to sort mixed content in their class
#LG         # containers
#LG         s1 = "            if hasattr(self, 'add_%s'):\n" % (origName, )
#LG         s1 +="              self.add_%s(obj_.value)\n" % (origName, )
#LG         s1 +="            elif hasattr(self, 'set_%s'):\n" % (origName, )
#LG         s1 +="              self.set_%s(obj_.value)\n" % (origName, )
#LG         wrt(s1)
# end generateBuildMixed_1


# AJ assuming we are not using mixed (text also in elem)
#LG def generateBuildMixed(wrt, prefix, element, keyword, delayed, hasChildren):
#LG     for child in element.getChildren():
#LG         generateBuildMixed_1(wrt, prefix, child, child, keyword, delayed)
#LG         hasChildren += 1
#LG         keyword = 'elif'
#LG         # Does this element have a substitutionGroup?
#LG         #   If so generate a clause for each element in the substitutionGroup.
#LG         if child.getName() in SubstitutionGroups:
#LG             for memberName in SubstitutionGroups[child.getName()]:
#LG                 if memberName in ElementDict:
#LG                     member = ElementDict[memberName]
#LG                     generateBuildMixed_1(wrt, prefix, member, child,
#LG                         keyword, delayed)
#LG     wrt("        if not fromsubclass_ and child_.tail is not None:\n")
#LG     wrt("            obj_ = self.mixedclass_(MixedContainer.CategoryText,\n")
#LG     wrt("                MixedContainer.TypeNone, '', child_.tail)\n")
#LG     wrt("            self.content_.append(obj_)\n")
#LG ##    base = element.getBase()
#LG ##    if base and base in ElementDict:
#LG ##        parent = ElementDict[base]
#LG ##        hasChildren = generateBuildMixed(wrt, prefix, parent, keyword, delayed, hasChildren)
#LG     return hasChildren


#LG def generateBuildStandard_1(wrt, prefix, child, headChild,
#LG         element, keyword, delayed):
#LG     origName = child.getName()
#LG     name = cleanupName(child.getName())
#LG     mappedName = mapName(name)
#LG     headName = cleanupName(headChild.getName())
#LG     attrCount = len(child.getAttributeDefs())
#LG     childType = child.getType()
#LG     base = child.getBase()
#LG     LangGenr.generateBuildStandard_1_ForType(wrt, prefix, child, headChild, keyword, delayed)
#LG     #LG if (attrCount == 0 and
#LG     #LG     ((childType in StringType or
#LG     #LG         childType == TokenType or
#LG     #LG         childType == DateTimeType or
#LG     #LG         childType == TimeType or
#LG     #LG         childType == DateType or
#LG     #LG         child.isListType()
#LG     #LG     ))
#LG     #LG     ):
#LG     #LG     wrt("        %s nodeName_ == '%s':\n" % (keyword, origName, ))
#LG     #LG     wrt("            %s_ = child_.text\n" % name)
#LG     #LG     if childType == TokenType:
#LG     #LG         wrt('            %s_ = re_.sub(String_cleanup_pat_, " ", %s_).strip()\n' %(name, name))
#LG     #LG     if child.isListType():
#LG     #LG         if childType in IntegerType or \
#LG     #LG             childType == PositiveIntegerType or \
#LG     #LG             childType == NonPositiveIntegerType or \
#LG     #LG             childType == NegativeIntegerType or \
#LG     #LG             childType == NonNegativeIntegerType:
#LG     #LG             wrt("            %s_ = self.gds_validate_integer_list(%s_, node, '%s')\n" % (
#LG     #LG                 name, name, name, ))
#LG     #LG         elif childType == BooleanType:
#LG     #LG             wrt("            %s_ = self.gds_validate_boolean_list(%s_, node, '%s')\n" % (
#LG     #LG                 name, name, name, ))
#LG     #LG         elif childType == FloatType or \
#LG     #LG             childType == DecimalType:
#LG     #LG             wrt("            %s_ = self.gds_validate_float_list(%s_, node, '%s')\n" % (
#LG     #LG                 name, name, name, ))
#LG     #LG         elif childType == DoubleType:
#LG     #LG             wrt("            %s_ = self.gds_validate_double_list(%s_, node, '%s')\n" % (
#LG     #LG                 name, name, name, ))
#LG     #LG     else:
#LG     #LG         wrt("            %s_ = self.gds_validate_string(%s_, node, '%s')\n" % (
#LG     #LG             name, name, name, ))
#LG     #LG     if child.getMaxOccurs() > 1:
#LG     #LG         wrt("            self.%s.append(%s_)\n" % (mappedName, name, ))
#LG     #LG     else:
#LG     #LG         wrt("            self.%s = %s_\n" % (mappedName, name, ))
#LG     #LG elif childType in IntegerType or \
#LG     #LG     childType == PositiveIntegerType or \
#LG     #LG     childType == NonPositiveIntegerType or \
#LG     #LG     childType == NegativeIntegerType or \
#LG     #LG     childType == NonNegativeIntegerType:
#LG     #LG     wrt("        %s nodeName_ == '%s':\n" % (keyword, origName, ))
#LG     #LG     wrt("            sval_ = child_.text\n")
#LG     #LG     wrt("            try:\n")
#LG     #LG     wrt("                ival_ = int(sval_)\n")
#LG     #LG     wrt("            except (TypeError, ValueError), exp:\n")
#LG     #LG     wrt("                raise_parse_error(child_, 'requires integer: %s' % exp)\n")
#LG     #LG     if childType == PositiveIntegerType:
#LG     #LG         wrt("            if ival_ <= 0:\n")
#LG     #LG         wrt("                raise_parse_error(child_, 'requires positiveInteger')\n")
#LG     #LG     elif childType == NonPositiveIntegerType:
#LG     #LG         wrt("            if ival_ > 0:\n")
#LG     #LG         wrt("                raise_parse_error(child_, 'requires nonPositiveInteger')\n")
#LG     #LG     elif childType == NegativeIntegerType:
#LG     #LG         wrt("            if ival_ >= 0:\n")
#LG     #LG         wrt("                raise_parse_error(child_, 'requires negativeInteger')\n")
#LG     #LG     elif childType == NonNegativeIntegerType:
#LG     #LG         wrt("            if ival_ < 0:\n")
#LG     #LG         wrt("                raise_parse_error(child_, 'requires nonNegativeInteger')\n")
#LG     #LG     wrt("            ival_ = self.gds_validate_integer(ival_, node, '%s')\n" % (
#LG     #LG         name, ))
#LG     #LG     if child.getMaxOccurs() > 1:
#LG     #LG         wrt("            self.%s.append(ival_)\n" % (mappedName, ))
#LG     #LG     else:
#LG     #LG         wrt("            self.%s = ival_\n" % (mappedName, ))
#LG     #LG elif childType == BooleanType:
#LG     #LG     wrt("        %s nodeName_ == '%s':\n" % (keyword, origName, ))
#LG     #LG     wrt("            sval_ = child_.text\n")
#LG     #LG     wrt("            if sval_ in ('true', '1'):\n")
#LG     #LG     wrt("                ival_ = True\n")
#LG     #LG     wrt("            elif sval_ in ('false', '0'):\n")
#LG     #LG     wrt("                ival_ = False\n")
#LG     #LG     wrt("            else:\n")
#LG     #LG     wrt("                raise_parse_error(child_, 'requires boolean')\n")
#LG     #LG     wrt("            ival_ = self.gds_validate_boolean(ival_, node, '%s')\n" % (
#LG     #LG         name, ))
#LG     #LG     if child.getMaxOccurs() > 1:
#LG     #LG         wrt("            self.%s.append(ival_)\n" % (mappedName, ))
#LG     #LG     else:
#LG     #LG         wrt("            self.%s = ival_\n" % (mappedName, ))
#LG     #LG elif childType == FloatType or \
#LG     #LG     childType == DoubleType or \
#LG     #LG     childType == DecimalType:
#LG     #LG     wrt("        %s nodeName_ == '%s':\n" % (keyword, origName, ))
#LG     #LG     wrt("            sval_ = child_.text\n")
#LG     #LG     wrt("            try:\n")
#LG     #LG     wrt("                fval_ = float(sval_)\n")
#LG     #LG     wrt("            except (TypeError, ValueError), exp:\n")
#LG     #LG     wrt("                raise_parse_error(child_, 'requires float or double: %s' % exp)\n")
#LG     #LG     wrt("            fval_ = self.gds_validate_float(fval_, node, '%s')\n" % (
#LG     #LG         name, ))
#LG     #LG     if child.getMaxOccurs() > 1:
#LG     #LG         wrt("            self.%s.append(fval_)\n" % (mappedName, ))
#LG     #LG     else:
#LG     #LG         wrt("            self.%s = fval_\n" % (mappedName, ))
#LG     #LG else:
#LG     #LG     # Perhaps it's a complexType that is defined right here.
#LG     #LG     # Generate (later) a class for the nested types.
#LG     #LG     # fix_abstract
#LG     #LG     type_element = None
#LG     #LG     abstract_child = False
#LG     #LG     type_name = child.getAttrs().get('type')
#LG     #LG     if type_name:
#LG     #LG         type_element = ElementDict.get(type_name)
#LG     #LG     if type_element and type_element.isAbstract():
#LG     #LG         abstract_child = True
#LG     #LG     if not delayed and not child in DelayedElements:
#LG     #LG         DelayedElements.append(child)
#LG     #LG         DelayedElements_subclass.append(child)
#LG     #LG     wrt("        %s nodeName_ == '%s':\n" % (keyword, origName, ))
#LG     #LG     # Is this a simple type?
#LG     #LG     base = child.getBase()
#LG     #LG     if child.getSimpleType():
#LG     #LG         wrt("            obj_ = None\n")
#LG     #LG     else:
#LG     #LG         # name_type_problem
#LG     #LG         # fix_abstract
#LG     #LG         if type_element:
#LG     #LG             type_name = type_element.getType()
#LG     #LG         elif origName in ElementDict:
#LG     #LG             type_name = ElementDict[origName].getType()
#LG     #LG         else:
#LG     #LG             type_name = childType
#LG     #LG         type_name = cleanupName(mapName(type_name))
#LG     #LG         if abstract_child:
#LG     #LG             wrt(TEMPLATE_ABSTRACT_CHILD % (mappedName, ))
#LG     #LG         else:
#LG     #LG             type_obj = ElementDict.get(type_name)
#LG     #LG             if type_obj is not None and type_obj.getExtended():
#LG     #LG                 wrt("            class_obj_ = self.get_class_obj_(child_, %s%s)\n" % (
#LG     #LG                     prefix, type_name, ))
#LG     #LG                 wrt("            obj_ = class_obj_.factory()\n")
#LG     #LG             else:
#LG     #LG                 wrt("            obj_ = %s%s.factory()\n" % (
#LG     #LG                     prefix, type_name, ))
#LG     #LG             wrt("            obj_.build(child_)\n")
#LG     #LG     if headChild.getMaxOccurs() > 1:
#LG     #LG         substitutionGroup = child.getAttrs().get('substitutionGroup')
#LG     #LG         if substitutionGroup is not None:
#LG     #LG             name = substitutionGroup
#LG     #LG         else:
#LG     #LG             name = mappedName
#LG     #LG         s1 = "            self.%s.append(obj_)\n" % (name, )
#LG     #LG     else:
#LG     #LG         substitutionGroup = child.getAttrs().get('substitutionGroup')
#LG     #LG         if substitutionGroup is not None:
#LG     #LG             name = substitutionGroup
#LG     #LG         else:
#LG     #LG             name = headName
#LG     #LG         s1 = "            self.set%s(obj_)\n" % (make_gs_name(name), )
#LG     #LG     wrt(s1)
#LG
#LG     #
#LG     # If this child is defined in a simpleType, then generate
#LG     #   a validator method.
#LG     LangGenr.generateBuildValidator(wrt, child)
#LG     #LG typeName = None
#LG     #LG if child.getSimpleType():
#LG     #LG     #typeName = child.getSimpleType()
#LG     #LG     typeName = cleanupName(child.getName())
#LG     #LG elif (childType in ElementDict and
#LG     #LG     ElementDict[childType].getSimpleType()):
#LG     #LG     typeName = ElementDict[childType].getType()
#LG     #LG # fixlist
#LG     #LG if (child.getSimpleType() in SimpleTypeDict and
#LG     #LG     SimpleTypeDict[child.getSimpleType()].isListType()):
#LG     #LG     wrt("            self.%s = self.%s.split()\n" % (
#LG     #LG         mappedName, mappedName, ))
#LG     #LG typeName = child.getSimpleType()
#LG     #LG if typeName and typeName in SimpleTypeDict:
#LG     #LG     wrt("            self.validate_%s(self.%s)    # validate type %s\n" % (
#LG     #LG         typeName, mappedName, typeName, ))
#LG # end generateBuildStandard_1


def transitiveClosure(m, e):
    t=[]
    if e in m:
        t+=m[e]
        for f in m[e]:
            t+=transitiveClosure(m,f)
    return t

#LG def generateBuildStandard(wrt, prefix, element, keyword, delayed, hasChildren):
#LG     any_type_child = None
#LG     for child in element.getChildren():
#LG         if child.getType() == AnyTypeIdentifier:
#LG             any_type_child = child
#LG         else:
#LG             generateBuildStandard_1(wrt, prefix, child, child,
#LG                 element, keyword, delayed)
#LG             hasChildren += 1
#LG             keyword = 'elif'
#LG             # Does this element have a substitutionGroup?
#LG             #   If so generate a clause for each element in the substitutionGroup.
#LG             childName = child.getName()
#LG             if childName in SubstitutionGroups:
#LG                 for memberName in transitiveClosure(SubstitutionGroups, childName):
#LG                     memberName = cleanupName(memberName)
#LG                     if memberName in ElementDict:
#LG                         member = ElementDict[memberName]
#LG                         generateBuildStandard_1(wrt, prefix, member, child,
#LG                             element, keyword, delayed)
#LG
#LG     hasChildren += LangGenr.generateBuildAnyType(wrt, element, any_type_child)
#LG     #LG if any_type_child is not None:
#LG     #LG     type_name = element.getType()
#LG     #LG     if any_type_child.getMaxOccurs() > 1:
#LG     #LG         if keyword == 'if':
#LG     #LG             fill = ''
#LG     #LG         else:
#LG     #LG             fill = '    '
#LG     #LG             wrt("        else:\n")
#LG     #LG         wrt("        %sobj_ = self.gds_build_any(child_, '%s')\n" % (
#LG     #LG             fill, type_name, ))
#LG     #LG         wrt("        %sif obj_ is not None:\n" % (fill, ))
#LG     #LG         wrt('            %sself.add_anytypeobjs_(obj_)\n' % (fill, ))
#LG     #LG     else:
#LG     #LG         if keyword == 'if':
#LG     #LG             fill = ''
#LG     #LG         else:
#LG     #LG             fill = '    '
#LG     #LG             wrt("        else:\n")
#LG     #LG         wrt("        %sobj_ = self.gds_build_any(child_, '%s')\n" % (
#LG     #LG             fill, type_name, ))
#LG     #LG         wrt("        %sif obj_ is not None:\n" % (fill, ))
#LG     #LG         wrt('            %sself.set_anytypeobjs_(obj_)\n' % (fill, ))
#LG     #LG     hasChildren += 1
#LG     return hasChildren
#LG # end generateBuildStandard


#LG def generateBuildFn(wrt, prefix, element, delayed):
#LG     LangGenr.generateBuild(wrt, element)
#LG     #LG base = element.getBase()
#LG     #LG wrt('    def build(self, node):\n')
#LG     #LG wrt('        self.buildAttributes(node, node.attrib, [])\n')
#LG     #LG childCount = countChildren(element, 0)
#LG     #LG if element.isMixed() or element.getSimpleContent():
#LG     #LG     wrt("        self.valueOf_ = get_all_text_(node)\n")
#LG     #LG if element.isMixed():
#LG     #LG     wrt("        if node.text is not None:\n")
#LG     #LG     wrt("            obj_ = self.mixedclass_(MixedContainer.CategoryText,\n")
#LG     #LG     wrt("                MixedContainer.TypeNone, '', node.text)\n")
#LG     #LG     wrt("            self.content_.append(obj_)\n")
#LG     #LG wrt('        for child in node:\n')
#LG     #LG wrt("            nodeName_ = Tag_pattern_.match(child.tag).groups()[-1]\n")
#LG     #LG wrt("            self.buildChildren(child, node, nodeName_)\n")
#LG
#LG     LangGenr.generateBuildAttributesFn(wrt, element)
#LG     #LG wrt('    def buildAttributes(self, node, attrs, already_processed):\n')
#LG     #LG hasAttributes = 0
#LG     #LG hasAttributes = generateBuildAttributes(wrt, element, hasAttributes)
#LG     #LG parentName, parent = getParentName(element)
#LG     #LG if parentName:
#LG     #LG     hasAttributes += 1
#LG     #LG     elName = element.getCleanName()
#LG     #LG     wrt('        super(%s, self).buildAttributes(node, attrs, already_processed)\n' % (
#LG     #LG         elName, ))
#LG     #LG if hasAttributes == 0:
#LG     #LG     wrt('        pass\n')
#LG
#LG     LangGenr.generateBuildChildren(wrt, element, prefix, delayed)
#LG     #LG wrt('    def buildChildren(self, child_, node, nodeName_, fromsubclass_=False):\n')
#LG     #LG keyword = 'if'
#LG     #LG hasChildren = 0
#LG     #LG if element.isMixed():
#LG     #LG     hasChildren = generateBuildMixed(wrt, prefix, element, keyword,
#LG     #LG         delayed, hasChildren)
#LG     #LG else:      # not element.isMixed()
#LG     #LG     hasChildren = generateBuildStandard(wrt, prefix, element, keyword,
#LG     #LG         delayed, hasChildren)
#LG     #LG # Generate call to buildChildren in the superclass only if it is
#LG     #LG #  an extension, but *not* if it is a restriction.
#LG     #LG base = element.getBase()
#LG     #LG if base and not element.getSimpleContent():
#LG     #LG     elName = element.getCleanName()
#LG     #LG     wrt("        super(%s, self).buildChildren(child_, node, nodeName_, True)\n" % (elName, ))
#LG     #LG eltype = element.getType()
#LG     #LG if hasChildren == 0:
#LG     #LG     wrt("        pass\n")
# end generateBuildFn


def countElementChildren(element, count):
    count += len(element.getChildren())
    base = element.getBase()
    if base and base in ElementDict:
        parent = ElementDict[base]
        countElementChildren(parent, count)
    return count


#LG def buildCtorArgs_multilevel(element, childCount):
#LG     content = []
#LG     addedArgs = {}
#LG     add = content.append
#LG     buildCtorArgs_multilevel_aux(addedArgs, add, element)
#LG     eltype = element.getType()
#LG     if (element.getSimpleContent() or
#LG         element.isMixed() or
#LG         eltype in SimpleTypeDict or
#LG         CurrentNamespacePrefix + eltype in OtherSimpleTypes
#LG         ):
#LG         add(", valueOf_=None")
#LG     if element.isMixed():
#LG         add(', mixedclass_=None')
#LG         add(', content_=None')
#LG     if element.getExtended():
#LG         add(', extensiontype_=None')
#LG     s1 = ''.join(content)
#LG     return s1
#LG
#LG
#LG def buildCtorArgs_multilevel_aux(addedArgs, add, element):
#LG     parentName, parentObj = getParentName(element)
#LG     if parentName:
#LG         buildCtorArgs_multilevel_aux(addedArgs, add, parentObj)
#LG     buildCtorArgs_aux(addedArgs, add, element)
#LG
#LG
#LG def buildCtorArgs_aux(addedArgs, add, element):
#LG     attrDefs = element.getAttributeDefs()
#LG     for key in attrDefs:
#LG         attrDef = attrDefs[key]
#LG         name = attrDef.getName()
#LG         default = attrDef.getDefault()
#LG         mappedName = name.replace(':', '_')
#LG         mappedName = cleanupName(mapName(mappedName))
#LG         if mappedName in addedArgs:
#LG             continue
#LG         addedArgs[mappedName] = 1
#LG         try:
#LG             atype = attrDef.getData_type()
#LG         except KeyError:
#LG             atype = StringType
#LG         if atype in StringType or \
#LG             atype == TokenType or \
#LG             atype == DateTimeType or \
#LG             atype == TimeType or \
#LG             atype == DateType:
#LG             if default is None:
#LG                 add(", %s=None" % mappedName)
#LG             else:
#LG                 default1 = escape_string(default)
#LG                 add(", %s='%s'" % (mappedName, default1))
#LG         elif atype in IntegerType:
#LG             if default is None:
#LG                 add(', %s=None' % mappedName)
#LG             else:
#LG                 add(', %s=%s' % (mappedName, default))
#LG         elif atype == PositiveIntegerType:
#LG             if default is None:
#LG                 add(', %s=None' % mappedName)
#LG             else:
#LG                 add(', %s=%s' % (mappedName, default))
#LG         elif atype == NonPositiveIntegerType:
#LG             if default is None:
#LG                 add(', %s=None' % mappedName)
#LG             else:
#LG                 add(', %s=%s' % (mappedName, default))
#LG         elif atype == NegativeIntegerType:
#LG             if default is None:
#LG                 add(', %s=None' % mappedName)
#LG             else:
#LG                 add(', %s=%s' % (mappedName, default))
#LG         elif atype == NonNegativeIntegerType:
#LG             if default is None:
#LG                 add(', %s=None' % mappedName)
#LG             else:
#LG                 add(', %s=%s' % (mappedName, default))
#LG         elif atype == BooleanType:
#LG             if default is None:
#LG                 add(', %s=None' % mappedName)
#LG             else:
#LG                 if default in ('false', '0'):
#LG                     add(', %s=%s' % (mappedName, "False"))
#LG                 else:
#LG                     add(', %s=%s' % (mappedName, "True"))
#LG         elif atype == FloatType or atype == DoubleType or atype == DecimalType:
#LG             if default is None:
#LG                 add(', %s=None' % mappedName)
#LG             else:
#LG                 add(', %s=%s' % (mappedName, default))
#LG         else:
#LG             if default is None:
#LG                 add(', %s=None' % mappedName)
#LG             else:
#LG                 add(", %s='%s'" % (mappedName, default, ))
#LG     nestedElements = 0
#LG     for child in element.getChildren():
#LG         cleanName = child.getCleanName()
#LG         if cleanName in addedArgs:
#LG             continue
#LG         addedArgs[cleanName] = 1
#LG         default = child.getDefault()
#LG         nestedElements = 1
#LG         if child.getType() == AnyTypeIdentifier:
#LG             add(', anytypeobjs_=None')
#LG         elif child.getMaxOccurs() > 1:
#LG             add(', %s=None' % cleanName)
#LG         else:
#LG             childType = child.getType()
#LG             if childType in StringType or \
#LG                 childType == TokenType or \
#LG                 childType == DateTimeType or \
#LG                 childType == TimeType or \
#LG                 childType == DateType:
#LG                 if default is None:
#LG                     add(", %s=None" % cleanName)
#LG                 else:
#LG                     default1 = escape_string(default)
#LG                     add(", %s='%s'" % (cleanName, default1, ))
#LG             elif (childType in IntegerType or
#LG                 childType == PositiveIntegerType or
#LG                 childType == NonPositiveIntegerType or
#LG                 childType == NegativeIntegerType or
#LG                 childType == NonNegativeIntegerType
#LG                 ):
#LG                 if default is None:
#LG                     add(', %s=None' % cleanName)
#LG                 else:
#LG                     add(', %s=%s' % (cleanName, default, ))
#LG ##             elif childType in IntegerType:
#LG ##                 if default is None:
#LG ##                     add(', %s=-1' % cleanName)
#LG ##                 else:
#LG ##                     add(', %s=%s' % (cleanName, default, ))
#LG ##             elif childType == PositiveIntegerType:
#LG ##                 if default is None:
#LG ##                     add(', %s=1' % cleanName)
#LG ##                 else:
#LG ##                     add(', %s=%s' % (cleanName, default, ))
#LG ##             elif childType == NonPositiveIntegerType:
#LG ##                 if default is None:
#LG ##                     add(', %s=0' % cleanName)
#LG ##                 else:
#LG ##                     add(', %s=%s' % (cleanName, default, ))
#LG ##             elif childType == NegativeIntegerType:
#LG ##                 if default is None:
#LG ##                     add(', %s=-1' % cleanName)
#LG ##                 else:
#LG ##                     add(', %s=%s' % (cleanName, default, ))
#LG ##             elif childType == NonNegativeIntegerType:
#LG ##                 if default is None:
#LG ##                     add(', %s=0' % cleanName)
#LG ##                 else:
#LG ##                     add(', %s=%s' % (cleanName, default, ))
#LG             elif childType == BooleanType:
#LG                 if default is None:
#LG                     add(', %s=None' % cleanName)
#LG                 else:
#LG                     if default in ('false', '0'):
#LG                         add(', %s=%s' % (cleanName, "False", ))
#LG                     else:
#LG                         add(', %s=%s' % (cleanName, "True", ))
#LG             elif childType == FloatType or \
#LG                 childType == DoubleType or \
#LG                 childType == DecimalType:
#LG                 if default is None:
#LG                     add(', %s=None' % cleanName)
#LG                 else:
#LG                     add(', %s=%s' % (cleanName, default, ))
#LG             else:
#LG                 add(', %s=None' % cleanName)
#LG # end buildCtorArgs_aux


MixedCtorInitializers = '''\
        if mixedclass_ is None:
            self.mixedclass_ = MixedContainer
        else:
            self.mixedclass_ = mixedclass_
        if content_ is None:
            self.content_ = []
        else:
            self.content_ = content_
        self.valueOf_ = valueOf_
'''


#LG def generateCtor(wrt, element):
#LG     global LangGenr

#LG    elName = element.getCleanName()
#LG    childCount = countChildren(element, 0)
#LG    s2 = buildCtorArgs_multilevel(element, childCount)
#LG    wrt('    def __init__(self%s):\n' % s2)
#LG    base = element.getBase()
#LG    parentName, parent = getParentName(element)
#LG    if parentName:
#LG        if parentName in AlreadyGenerated:
#LG            args = buildCtorParams(element, parent, childCount)
#LG            s2 = ''.join(args)
#LG            if len(args) > 254:
#LG                wrt('        arglist_ = (%s)\n' % (s2, ))
#LG                wrt('        super(%s, self).__init__(*arglist_)\n' % (elName, ))
#LG            else:
#LG                wrt('        super(%s, self).__init__(%s)\n' % (elName, s2, ))
#LG    attrDefs = element.getAttributeDefs()
#LG    for key in attrDefs:
#LG        attrDef = attrDefs[key]
#LG        mappedName = cleanupName(attrDef.getName())
#LG        mappedName = mapName(mappedName)
#LG        logging.debug("Constructor attribute: %s" % mappedName)
#LG        pythonType = SchemaToPythonTypeMap.get(attrDef.getType())
#LG        attrVal = "cast_(%s, %s)" % (pythonType, mappedName)
#LG        wrt('        self.%s = %s\n' % (mappedName, attrVal))
#LG        member = 1
#LG    # Generate member initializers in ctor.
#LG    member = 0
#LG    nestedElements = 0
#LG    for child in element.getChildren():
#LG        name = cleanupName(child.getCleanName())
#LG        logging.debug("Constructor child: %s" % name)
#LG        logging.debug("Dump: %s" % child.__dict__)
#LG        if child.getType() == AnyTypeIdentifier:
#LG            if child.getMaxOccurs() > 1:
#LG                wrt('        if anytypeobjs_ is None:\n')
#LG                wrt('            self.anytypeobjs_ = []\n')
#LG                wrt('        else:\n')
#LG                wrt('            self.anytypeobjs_ = anytypeobjs_\n')
#LG            else:
#LG                wrt('        self.anytypeobjs_ = anytypeobjs_\n')
#LG        else:
#LG            if child.getMaxOccurs() > 1:
#LG                wrt('        if %s is None:\n' % (name, ))
#LG                wrt('            self.%s = []\n' % (name, ))
#LG                wrt('        else:\n')
#LG                wrt('            self.%s = %s\n' % (name, name))
#LG            else:
#LG                typeObj = ElementDict.get(child.getType())
#LG                if (child.getDefault() and
#LG                    typeObj is not None and
#LG                    typeObj.getSimpleContent()):
#LG                    wrt('        if %s is None:\n' % (name, ))
#LG                    wrt("            self.%s = globals()['%s']('%s')\n" % (name,
#LG                        child.getType(), child.getDefault(), ))
#LG                    wrt('        else:\n')
#LG                    wrt('            self.%s = %s\n' % (name, name))
#LG                else:
#LG                    wrt('        self.%s = %s\n' % (name, name))
#LG        member = 1
#LG        nestedElements = 1
#LG    eltype = element.getType()
#LG    if (element.getSimpleContent() or
#LG        element.isMixed() or
#LG        eltype in SimpleTypeDict or
#LG        CurrentNamespacePrefix + eltype in OtherSimpleTypes
#LG        ):
#LG        wrt('        self.valueOf_ = valueOf_\n')
#LG        member = 1
#LG    if element.getAnyAttribute():
#LG        wrt('        self.anyAttributes_ = {}\n')
#LG        member = 1
#LG    if element.getExtended():
#LG        wrt('        self.extensiontype_ = extensiontype_\n')
#LG        member = 1
#LG    if not member:
#LG        wrt('        pass\n')
#LG    if element.isMixed():
#LG        wrt(MixedCtorInitializers)
# end generateCtor

#
# Attempt to retrieve the body (implementation) of a validator
#   from a directory containing one file for each simpleType.
#   The name of the file should be the same as the name of the
#   simpleType with and optional ".py" extension.
#LG def getValidatorBody(stName):
#LG     retrieved = 0
#LG     if ValidatorBodiesBasePath:
#LG         found = 0
#LG         path = '%s%s%s.py' % (ValidatorBodiesBasePath, os.sep, stName, )
#LG         if os.path.exists(path):
#LG             found = 1
#LG         else:
#LG             path = '%s%s%s' % (ValidatorBodiesBasePath, os.sep, stName, )
#LG             if os.path.exists(path):
#LG                 found = 1
#LG         if found:
#LG             infile = open(path, 'r')
#LG             lines = infile.readlines()
#LG             infile.close()
#LG             lines1 = []
#LG             for line in lines:
#LG                 if not line.startswith('##'):
#LG                     lines1.append(line)
#LG             s1 = ''.join(lines1)
#LG             retrieved = 1
#LG     if not retrieved:
#LG         s1 = '        pass\n'
#LG     return s1
# end getValidatorBody

# Generate get/set/add member functions.
#LG def generateGettersAndSetters(wrt, element):
#LG     generatedSimpleTypes = []
#LG     childCount = countChildren(element, 0)
#LG     for child in element.getChildren():
#LG         if child.getType() == AnyTypeIdentifier:
#LG             LangGenr.generateGetterAnyType(wrt)
#LG             #LG wrt('    def get_anytypeobjs_(self): return self.anytypeobjs_\n')
#LG             LangGenr.generateSetterAnyType(wrt)
#LG             #LG wrt('    def set_anytypeobjs_(self, anytypeobjs_): self.anytypeobjs_ = anytypeobjs_\n')
#LG             if child.getMaxOccurs() > 1:
#LG                 LangGenr.generateAdderAnyType(wrt)
#LG                 #LG wrt('    def add_anytypeobjs_(self, value): self.anytypeobjs_.append(value)\n')
#LG                 LangGenr.generateInserterAnyType(wrt)
#LG                 #LG wrt('    def insert_anytypeobjs_(self, index, value): self._anytypeobjs_[index] = value\n')
#LG         else:
#LG             name = cleanupName(child.getCleanName())
#LG             unmappedName = cleanupName(child.getName())
#LG             capName = make_gs_name(unmappedName)
#LG             getMaxOccurs = child.getMaxOccurs()
#LG             childType = child.getType()
#LG             LangGenr.generateGetter(wrt, capName, name)
#LG             #LG wrt('    def get%s(self): return self.%s\n' % (capName, name))
#LG             LangGenr.generateSetter(wrt, capName, name)
#LG             #LG wrt('    def set%s(self, %s): self.%s = %s\n' %
#LG             #LG    (capName, name, name, name))
#LG             if child.getMaxOccurs() > 1:
#LG                 LangGenr.generateAdder(wrt, capName, name)
#LG                 #LG wrt('    def add%s(self, value): self.%s.append(value)\n' %
#LG                 #LG     (capName, name))
#LG                 LangGenr.generateInserter(wrt, capName, name)
#LG                 #LG wrt('    def insert%s(self, index, value): self.%s[index] = value\n' %
#LG                 #LG     (capName, name))
#LG             if GenerateProperties:
#LG                 LangGenr.generateProperty(wrt, unmappedName, capName, name)
#LG                 #LG wrt('    %sProp = property(get%s, set%s)\n' %
#LG                 #LG     (unmappedName, capName, capName))
#LG             #
#LG             # If this child is defined in a simpleType, then generate
#LG             #   a validator method.
#LG             typeName = None
#LG             name = cleanupName(child.getName())
#LG             mappedName = mapName(name)
#LG             childType = child.getType()
#LG             childType1 = child.getSimpleType()
#LG             if not child.isComplex() and childType1 and childType1 in SimpleTypeDict:
#LG               childType = SimpleTypeDict[childType1].getBase()
#LG             elif mappedName in ElementDict:
#LG               childType = ElementDict[mappedName].getType()
#LG             typeName = child.getSimpleType()
#LG             if (typeName and
#LG                 typeName in SimpleTypeDict and
#LG                 typeName not in generatedSimpleTypes):
#LG                 generatedSimpleTypes.append(typeName)
#LG                 LangGenr.generateValidator(wrt, typeName)
#LG                 #LG wrt('    def validate_%s(self, value):\n' % (typeName, ))
#LG                 #LG if typeName in SimpleTypeDict:
#LG                 #LG     stObj = SimpleTypeDict[typeName]
#LG                 #LG     wrt('        # Validate type %s, a restriction on %s.\n' % (
#LG                 #LG         typeName, stObj.getBase(), ))
#LG                 #LG else:
#LG                 #LG     wrt('        # validate type %s\n' % (typeName, ))
#LG                 #LG wrt(getValidatorBody(typeName))
#LG     attrDefs = element.getAttributeDefs()
#LG     for key in attrDefs:
#LG         attrDef = attrDefs[key]
#LG         name = cleanupName(attrDef.getName().replace(':', '_'))
#LG         mappedName = mapName(name)
#LG         gsName = make_gs_name(name)
#LG         LangGenr.generateGetter(wrt, gsName, mappedName)
#LG         #LG wrt('    def get%s(self): return self.%s\n' %
#LG         #LG     (gsName, mappedName))
#LG         LangGenr.generateSetter(wrt, gsName, mappedName)
#LG         #LG wrt('    def set%s(self, %s): self.%s = %s\n' % (
#LG         #LG     gsName, mappedName, mappedName, mappedName))
#LG         if GenerateProperties:
#LG             LangGenr.generateProperty(wrt, name, gsName, gsName)
#LG             #LG wrt('    %sProp = property(get%s, set%s)\n' %
#LG             #LG    (name, gsName, gsName))
#LG         typeName = attrDef.getType()
#LG         if (typeName and
#LG             typeName in SimpleTypeDict and
#LG             typeName not in generatedSimpleTypes):
#LG             generatedSimpleTypes.append(typeName)
#LG             LangGenr.generateValidator(wrt, typeName)
#LG             #LG wrt('    def validate_%s(self, value):\n' % (typeName, ))
#LG             #LG if typeName in SimpleTypeDict:
#LG             #LG     stObj = SimpleTypeDict[typeName]
#LG             #LG     wrt('        # Validate type %s, a restriction on %s.\n' % (
#LG             #LG         typeName, stObj.getBase(), ))
#LG             #LG else:
#LG             #LG     wrt('        # validate type %s\n' % (typeName, ))
#LG             #LG wrt(getValidatorBody(typeName))
#LG
#LG     #LG TODO put in lang specific parts for these if needed
#LG     if element.getSimpleContent() or element.isMixed():
#LG         wrt('    def get%s_(self): return self.valueOf_\n' % (
#LG             make_gs_name('valueOf'), ))
#LG         wrt('    def set%s_(self, valueOf_): self.valueOf_ = valueOf_\n' % (
#LG             make_gs_name('valueOf'), ))
#LG     if element.getAnyAttribute():
#LG         wrt('    def get%s_(self): return self.anyAttributes_\n' % (
#LG             make_gs_name('anyAttributes'), ))
#LG         wrt('    def set%s_(self, anyAttributes_): self.anyAttributes_ = anyAttributes_\n' % (
#LG             make_gs_name('anyAttributes'), ))
#LG     if element.getExtended():
#LG         wrt('    def get%s_(self): return self.extensiontype_\n' % (
#LG             make_gs_name('extensiontype'), ))
#LG         wrt('    def set%s_(self, extensiontype_): self.extensiontype_ = extensiontype_\n' % (
#LG             make_gs_name('extensiontype'), ))
# end generateGettersAndSetters


#
# Generate a class variable whose value is a list of tuples, one
#   tuple for each member data item of the class.
#   Each tuble has 3 elements: (1) member name, (2) member data type,
#   (3) container/list or not (maxoccurs > 1).
#LG def generateMemberSpec(wrt, element):
#LG     generateDict = MemberSpecs and MemberSpecs == 'dict'
#LG     if generateDict:
#LG         content = ['    member_data_items_ = {']
#LG     else:
#LG         content = ['    member_data_items_ = [']
#LG     add = content.append
#LG     for attrName, attrDef in element.getAttributeDefs().items():
#LG         item1 = attrName
#LG         item2 = attrDef.getType()
#LG         item3 = 0
#LG         if generateDict:
#LG             item = "        '%s': MemberSpec_('%s', '%s', %d)," % (
#LG                 item1, item1, item2, item3, )
#LG         else:
#LG             item = "        MemberSpec_('%s', '%s', %d)," % (
#LG                 item1, item2, item3, )
#LG         add(item)
#LG     for child in element.getChildren():
#LG         name = cleanupName(child.getCleanName())
#LG         item1 = name
#LG         simplebase = child.getSimpleBase()
#LG         if simplebase:
#LG             if len(simplebase) == 1:
#LG                 item2 = "'%s'" % (simplebase[0], )
#LG             else:
#LG                 item2 = simplebase
#LG         else:
#LG             element1 = ElementDict.get(name)
#LG             if element1:
#LG                 item2 = "'%s'" % element1.getType()
#LG             else:
#LG                 item2 = "'%s'" % (child.getType(), )
#LG         if child.getMaxOccurs() > 1:
#LG             item3 = 1
#LG         else:
#LG             item3 = 0
#LG         if generateDict:
#LG             item = "        '%s': MemberSpec_('%s', %s, %d)," % (
#LG                 item1, item1, item2, item3, )
#LG         else:
#LG             #item = "        ('%s', '%s', %d)," % (item1, item2, item3, )
#LG             item = "        MemberSpec_('%s', %s, %d)," % (
#LG                 item1, item2, item3, )
#LG         add(item)
#LG     simplebase = element.getSimpleBase()
#LG     childCount = countChildren(element, 0)
#LG     if element.getSimpleContent() or element.isMixed():
#LG         if len(simplebase) == 1:
#LG             simplebase = "'%s'" % (simplebase[0], )
#LG         if generateDict:
#LG             item = "        'valueOf_': MemberSpec_('valueOf_', %s, 0)," % (
#LG                 simplebase, )
#LG         else:
#LG             item = "        MemberSpec_('valueOf_', %s, 0)," % (
#LG                 simplebase, )
#LG         add(item)
#LG     elif element.isMixed():
#LG         if generateDict:
#LG             item = "        'valueOf_': MemberSpec_('valueOf_', '%s', 0)," % (
#LG                 'xs:string', )
#LG         else:
#LG             item = "        MemberSpec_('valueOf_', '%s', 0)," % (
#LG                 'xs:string', )
#LG         add(item)
#LG     if generateDict:
#LG         add('        }')
#LG     else:
#LG         add('        ]')
#LG     wrt('\n'.join(content))
#LG     wrt('\n')
# end generateMemberSpec


#LG def generateUserMethods(wrt, element):
#LG     if not UserMethodsModule:
#LG         return
#LG     specs = UserMethodsModule.METHOD_SPECS
#LG     name = cleanupName(element.getCleanName())
#LG     values_dict = {'class_name': name, }
#LG     for spec in specs:
#LG         if spec.match_name(name):
#LG             source = spec.get_interpolated_source(values_dict)
#LG             wrt(source)


#LG def generateHascontentMethod(wrt, element):
#LG     childCount = countChildren(element, 0)
#LG     wrt('    def hasContent_(self):\n')
#LG     wrt('        if (\n')
#LG     firstTime = True
#LG     for child in element.getChildren():
#LG         if child.getType() == AnyTypeIdentifier:
#LG             name = 'anytypeobjs_'
#LG         else:
#LG             name = mapName(cleanupName(child.getName()))
#LG         if not firstTime:
#LG             wrt(' or\n')
#LG         firstTime = False
#LG         if child.getMaxOccurs() > 1:
#LG             wrt('            self.%s' % (name, ))
#LG         else:
#LG             wrt('            self.%s is not None' % (name, ))
#LG     if element.getSimpleContent() or element.isMixed():
#LG         if not firstTime:
#LG             wrt(' or\n')
#LG         firstTime = False
#LG         wrt('            self.valueOf_')
#LG     parentName, parent = getParentName(element)
#LG     if parentName:
#LG         elName = element.getCleanName()
#LG         if not firstTime:
#LG             wrt(' or\n')
#LG         firstTime = False
#LG         wrt('            super(%s, self).hasContent_()' % (elName, ))
#LG     wrt('\n            ):\n')
#LG     wrt('            return True\n')
#LG     wrt('        else:\n')
#LG     wrt('            return False\n')



#LG def generateClasses(wrt, prefix, element, delayed):
#LG     logging.debug("Generating class for: %s" % element)
#LG     parentName, base = getParentName(element)
#LG     logging.debug("Element base: %s" % base)
#LG     if not element.isExplicitDefine():
#LG         logging.debug("Not an explicit define, returning.")
#LG         return
#LG     # If this element is an extension (has a base) and the base has
#LG     #   not been generated, then postpone it.
#LG     if parentName:
#LG         if (parentName not in AlreadyGenerated and
#LG             parentName not in SimpleTypeDict.keys()):
#LG             PostponedExtensions.append(element)
#LG             return
#LG     if element.getName() in AlreadyGenerated:
#LG         return
#LG     AlreadyGenerated.append(element.getName())
#LG     if element.getMixedExtensionError():
#LG         err_msg('*** Element %s extension chain contains mixed and non-mixed content.  Not generated.\n' % (
#LG             element.getName(), ))
#LG         return
#LG     ElementsForSubclasses.append(element)
#LG     name = element.getCleanName()
#LG     LangGenr.generateClassDefLine(wrt, parentName, prefix, name)
#LG     #LG if parentName:
#LG     #LG     s1 = 'class %s%s(%s):\n' % (prefix, name, parentName,)
#LG     #LG else:
#LG     #LG     s1 = 'class %s%s(GeneratedsSuper):\n' % (prefix, name)
#LG     #LG wrt(s1)
#LG     # If this element has documentation, generate a doc-string.
#LG     if element.documentation:
#LG         LangGenr.generateElemDoc(element)
#LG         #LG s2 = ' '.join(element.documentation.strip().split())
#LG         #LG s2 = s2.encode('utf-8')
#LG         #LG s2 = textwrap.fill(s2, width=68, subsequent_indent='    ')
#LG         #LG if s2[0] == '"' or s2[-1] == '"':
#LG         #LG     s2 = '    """ %s """\n' % (s2, )
#LG         #LG else:
#LG         #LG     s2 = '    """%s"""\n' % (s2, )
#LG         #LG wrt(s2)
#LG     if UserMethodsModule or MemberSpecs:
#LG         generateMemberSpec(wrt, element)
#LG     #LG wrt('    subclass = None\n')
#LG     parentName, parent = getParentName(element)
#LG     superclass_name = 'None'
#LG     if parentName and parentName in AlreadyGenerated:
#LG         superclass_name = mapName(cleanupName(parentName))
#LG     LangGenr.generateSubSuperInit(wrt, superclass_name)
#LG     #LG wrt('    superclass = %s\n' % (superclass_name, ))
#LG     generateCtor(wrt, element)
#LG     LangGenr.generateFactory(wrt, prefix, name)
#LG     #LG wrt('    def factory(*args_, **kwargs_):\n')
#LG     #LG wrt('        if %s%s.subclass:\n' % (prefix, name))
#LG     #LG wrt('            return %s%s.subclass(*args_, **kwargs_)\n' % (prefix, name))
#LG     #LG wrt('        else:\n')
#LG     #LG wrt('            return %s%s(*args_, **kwargs_)\n' % (prefix, name))
#LG     #LG wrt('    factory = staticmethod(factory)\n')
#LG     generateGettersAndSetters(wrt, element)
#LG     if Targetnamespace in NamespacesDict:
#LG         namespace = NamespacesDict[Targetnamespace]
#LG     else:
#LG         namespace = ''
#LG     generateExportFn(wrt, prefix, element, namespace)
#LG     generateExportLiteralFn(wrt, prefix, element)
#LG     generateBuildFn(wrt, prefix, element, delayed)
#LG     generateUserMethods(wrt, element)
#LG     wrt('# end class %s\n' % name)
#LG     wrt('\n\n')
#LG # end generateClasses



#LG TEMPLATE_HEADER = """\
#LG #!/usr/bin/env python
#LG # -*- coding: utf-8 -*-
#LG
#LG #
#LG # Generated %s by generateDS.py%s.
#LG #
#LG
#LG import sys
#LG import getopt
#LG import re as re_
#LG
#LG etree_ = None
#LG Verbose_import_ = False
#LG (   XMLParser_import_none, XMLParser_import_lxml,
#LG     XMLParser_import_elementtree
#LG     ) = range(3)
#LG XMLParser_import_library = None
#LG try:
#LG     # lxml
#LG     from lxml import etree as etree_
#LG     XMLParser_import_library = XMLParser_import_lxml
#LG     if Verbose_import_:
#LG         print("running with lxml.etree")
#LG except ImportError:
#LG     try:
#LG         # cElementTree from Python 2.5+
#LG         import xml.etree.cElementTree as etree_
#LG         XMLParser_import_library = XMLParser_import_elementtree
#LG         if Verbose_import_:
#LG             print("running with cElementTree on Python 2.5+")
#LG     except ImportError:
#LG         try:
#LG             # ElementTree from Python 2.5+
#LG             import xml.etree.ElementTree as etree_
#LG             XMLParser_import_library = XMLParser_import_elementtree
#LG             if Verbose_import_:
#LG                 print("running with ElementTree on Python 2.5+")
#LG         except ImportError:
#LG             try:
#LG                 # normal cElementTree install
#LG                 import cElementTree as etree_
#LG                 XMLParser_import_library = XMLParser_import_elementtree
#LG                 if Verbose_import_:
#LG                     print("running with cElementTree")
#LG             except ImportError:
#LG                 try:
#LG                     # normal ElementTree install
#LG                     import elementtree.ElementTree as etree_
#LG                     XMLParser_import_library = XMLParser_import_elementtree
#LG                     if Verbose_import_:
#LG                         print("running with ElementTree")
#LG                 except ImportError:
#LG                     raise ImportError("Failed to import ElementTree from any known place")
#LG
#LG def parsexml_(*args, **kwargs):
#LG     if (XMLParser_import_library == XMLParser_import_lxml and
#LG         'parser' not in kwargs):
#LG         # Use the lxml ElementTree compatible parser so that, e.g.,
#LG         #   we ignore comments.
#LG         kwargs['parser'] = etree_.ETCompatXMLParser()
#LG     doc = etree_.parse(*args, **kwargs)
#LG     return doc
#LG
#LG #
#LG # User methods
#LG #
#LG # Calls to the methods in these classes are generated by generateDS.py.
#LG # You can replace these methods by re-implementing the following class
#LG #   in a module named generatedssuper.py.
#LG
#LG try:
#LG     from generatedssuper import GeneratedsSuper
#LG except ImportError, exp:
#LG
#LG     class GeneratedsSuper(object):
#LG         def gds_format_string(self, input_data, input_name=''):
#LG             return input_data
#LG         def gds_validate_string(self, input_data, node, input_name=''):
#LG             return input_data
#LG         def gds_format_integer(self, input_data, input_name=''):
#LG             return '%%d' %% input_data
#LG         def gds_validate_integer(self, input_data, node, input_name=''):
#LG             return input_data
#LG         def gds_format_integer_list(self, input_data, input_name=''):
#LG             return '%%s' %% input_data
#LG         def gds_validate_integer_list(self, input_data, node, input_name=''):
#LG             values = input_data.split()
#LG             for value in values:
#LG                 try:
#LG                     fvalue = float(value)
#LG                 except (TypeError, ValueError), exp:
#LG                     raise_parse_error(node, 'Requires sequence of integers')
#LG             return input_data
#LG         def gds_format_float(self, input_data, input_name=''):
#LG             return '%%f' %% input_data
#LG         def gds_validate_float(self, input_data, node, input_name=''):
#LG             return input_data
#LG         def gds_format_float_list(self, input_data, input_name=''):
#LG             return '%%s' %% input_data
#LG         def gds_validate_float_list(self, input_data, node, input_name=''):
#LG             values = input_data.split()
#LG             for value in values:
#LG                 try:
#LG                     fvalue = float(value)
#LG                 except (TypeError, ValueError), exp:
#LG                     raise_parse_error(node, 'Requires sequence of floats')
#LG             return input_data
#LG         def gds_format_double(self, input_data, input_name=''):
#LG             return '%%e' %% input_data
#LG         def gds_validate_double(self, input_data, node, input_name=''):
#LG             return input_data
#LG         def gds_format_double_list(self, input_data, input_name=''):
#LG             return '%%s' %% input_data
#LG         def gds_validate_double_list(self, input_data, node, input_name=''):
#LG             values = input_data.split()
#LG             for value in values:
#LG                 try:
#LG                     fvalue = float(value)
#LG                 except (TypeError, ValueError), exp:
#LG                     raise_parse_error(node, 'Requires sequence of doubles')
#LG             return input_data
#LG         def gds_format_boolean(self, input_data, input_name=''):
#LG             return '%%s' %% input_data
#LG         def gds_validate_boolean(self, input_data, node, input_name=''):
#LG             return input_data
#LG         def gds_format_boolean_list(self, input_data, input_name=''):
#LG             return '%%s' %% input_data
#LG         def gds_validate_boolean_list(self, input_data, node, input_name=''):
#LG             values = input_data.split()
#LG             for value in values:
#LG                 if value not in ('true', '1', 'false', '0', ):
#LG                     raise_parse_error(node, 'Requires sequence of booleans ("true", "1", "false", "0")')
#LG             return input_data
#LG         def gds_str_lower(self, instring):
#LG             return instring.lower()
#LG         def get_path_(self, node):
#LG             path_list = []
#LG             self.get_path_list_(node, path_list)
#LG             path_list.reverse()
#LG             path = '/'.join(path_list)
#LG             return path
#LG         Tag_strip_pattern_ = re_.compile(r'\{.*\}')
#LG         def get_path_list_(self, node, path_list):
#LG             if node is None:
#LG                 return
#LG             tag = GeneratedsSuper.Tag_strip_pattern_.sub('', node.tag)
#LG             if tag:
#LG                 path_list.append(tag)
#LG             self.get_path_list_(node.getparent(), path_list)
#LG         def get_class_obj_(self, node, default_class=None):
#LG             class_obj1 = default_class
#LG             if 'xsi' in node.nsmap:
#LG                 classname = node.get('{%%s}type' %% node.nsmap['xsi'])
#LG                 if classname is not None:
#LG                     names = classname.split(':')
#LG                     if len(names) == 2:
#LG                         classname = names[1]
#LG                     class_obj2 = globals().get(classname)
#LG                     if class_obj2 is not None:
#LG                         class_obj1 = class_obj2
#LG             return class_obj1
#LG         def gds_build_any(self, node, type_name=None):
#LG             return None
#LG
#LG
#LG #
#LG # If you have installed IPython you can uncomment and use the following.
#LG # IPython is available from http://ipython.scipy.org/.
#LG #
#LG
#LG ## from IPython.Shell import IPShellEmbed
#LG ## args = ''
#LG ## ipshell = IPShellEmbed(args,
#LG ##     banner = 'Dropping into IPython',
#LG ##     exit_msg = 'Leaving Interpreter, back to program.')
#LG
#LG # Then use the following line where and when you want to drop into the
#LG # IPython shell:
#LG #    ipshell('<some message> -- Entering ipshell.\\nHit Ctrl-D to exit')
#LG
#LG #
#LG # Globals
#LG #
#LG
#LG ExternalEncoding = '%s'
#LG Tag_pattern_ = re_.compile(r'({.*})?(.*)')
#LG String_cleanup_pat_ = re_.compile(r"[\\n\\r\\s]+")
#LG Namespace_extract_pat_ = re_.compile(r'{(.*)}(.*)')
#LG
#LG #
#LG # Support/utility functions.
#LG #
#LG
#LG def showIndent(outfile, level, pretty_print=True):
#LG     if pretty_print:
#LG         for idx in range(level):
#LG             outfile.write('    ')
#LG
#LG def quote_xml(inStr):
#LG     if not inStr:
#LG         return ''
#LG     s1 = (isinstance(inStr, basestring) and inStr or
#LG           '%%s' %% inStr)
#LG     s1 = s1.replace('&', '&amp;')
#LG     s1 = s1.replace('<', '&lt;')
#LG     s1 = s1.replace('>', '&gt;')
#LG     return s1
#LG
#LG def quote_attrib(inStr):
#LG     s1 = (isinstance(inStr, basestring) and inStr or
#LG           '%%s' %% inStr)
#LG     s1 = s1.replace('&', '&amp;')
#LG     s1 = s1.replace('<', '&lt;')
#LG     s1 = s1.replace('>', '&gt;')
#LG     if '"' in s1:
#LG         if "'" in s1:
#LG             s1 = '"%%s"' %% s1.replace('"', "&quot;")
#LG         else:
#LG             s1 = "'%%s'" %% s1
#LG     else:
#LG         s1 = '"%%s"' %% s1
#LG     return s1
#LG
#LG def quote_python(inStr):
#LG     s1 = inStr
#LG     if s1.find("'") == -1:
#LG         if s1.find('\\n') == -1:
#LG             return "'%%s'" %% s1
#LG         else:
#LG             return "'''%%s'''" %% s1
#LG     else:
#LG         if s1.find('"') != -1:
#LG             s1 = s1.replace('"', '\\\\"')
#LG         if s1.find('\\n') == -1:
#LG             return '"%%s"' %% s1
#LG         else:
#LG             return '\"\"\"%%s\"\"\"' %% s1
#LG
#LG def get_all_text_(node):
#LG     if node.text is not None:
#LG         text = node.text
#LG     else:
#LG         text = ''
#LG     for child in node:
#LG         if child.tail is not None:
#LG             text += child.tail
#LG     return text
#LG
#LG def find_attr_value_(attr_name, node):
#LG     attrs = node.attrib
#LG     attr_parts = attr_name.split(':')
#LG     value = None
#LG     if len(attr_parts) == 1:
#LG         value = attrs.get(attr_name)
#LG     elif len(attr_parts) == 2:
#LG         prefix, name = attr_parts
#LG         namespace = node.nsmap.get(prefix)
#LG         if namespace is not None:
#LG             value = attrs.get('{%%s}%%s' %% (namespace, name, ))
#LG     return value
#LG
#LG
#LG class GDSParseError(Exception):
#LG     pass
#LG
#LG def raise_parse_error(node, msg):
#LG     if XMLParser_import_library == XMLParser_import_lxml:
#LG         msg = '%%s (element %%s/line %%d)' %% (msg, node.tag, node.sourceline, )
#LG     else:
#LG         msg = '%%s (element %%s)' %% (msg, node.tag, )
#LG     raise GDSParseError(msg)
#LG
#LG
#LG class MixedContainer:
#LG     # Constants for category:
#LG     CategoryNone = 0
#LG     CategoryText = 1
#LG     CategorySimple = 2
#LG     CategoryComplex = 3
#LG     # Constants for content_type:
#LG     TypeNone = 0
#LG     TypeText = 1
#LG     TypeString = 2
#LG     TypeInteger = 3
#LG     TypeFloat = 4
#LG     TypeDecimal = 5
#LG     TypeDouble = 6
#LG     TypeBoolean = 7
#LG     def __init__(self, category, content_type, name, value):
#LG         self.category = category
#LG         self.content_type = content_type
#LG         self.name = name
#LG         self.value = value
#LG     def getCategory(self):
#LG         return self.category
#LG     def getContenttype(self, content_type):
#LG         return self.content_type
#LG     def getValue(self):
#LG         return self.value
#LG     def getName(self):
#LG         return self.name
#LG     def export_xml(self, outfile, level, name, namespace, pretty_print=True):
#LG         if self.category == MixedContainer.CategoryText:
#LG             # Prevent exporting empty content as empty lines.
#LG             if self.value.strip():
#LG                 outfile.write(self.value)
#LG         elif self.category == MixedContainer.CategorySimple:
#LG             self.exportSimple(outfile, level, name)
#LG         else:    # category == MixedContainer.CategoryComplex
#LG             self.value.export_xml(outfile, level, namespace, name, pretty_print)
#LG     def exportSimple(self, outfile, level, name):
#LG         if self.content_type == MixedContainer.TypeString:
#LG             outfile.write('<%%s>%%s</%%s>' %% (self.name, self.value, self.name))
#LG         elif self.content_type == MixedContainer.TypeInteger or \\
#LG                 self.content_type == MixedContainer.TypeBoolean:
#LG             outfile.write('<%%s>%%d</%%s>' %% (self.name, self.value, self.name))
#LG         elif self.content_type == MixedContainer.TypeFloat or \\
#LG                 self.content_type == MixedContainer.TypeDecimal:
#LG             outfile.write('<%%s>%%f</%%s>' %% (self.name, self.value, self.name))
#LG         elif self.content_type == MixedContainer.TypeDouble:
#LG             outfile.write('<%%s>%%g</%%s>' %% (self.name, self.value, self.name))
#LG     def exportLiteral(self, outfile, level, name):
#LG         if self.category == MixedContainer.CategoryText:
#LG             showIndent(outfile, level)
#LG             outfile.write('model_.MixedContainer(%%d, %%d, "%%s", "%%s"),\\n' %% \\
#LG                 (self.category, self.content_type, self.name, self.value))
#LG         elif self.category == MixedContainer.CategorySimple:
#LG             showIndent(outfile, level)
#LG             outfile.write('model_.MixedContainer(%%d, %%d, "%%s", "%%s"),\\n' %% \\
#LG                 (self.category, self.content_type, self.name, self.value))
#LG         else:    # category == MixedContainer.CategoryComplex
#LG             showIndent(outfile, level)
#LG             outfile.write('model_.MixedContainer(%%d, %%d, "%%s",\\n' %% \\
#LG                 (self.category, self.content_type, self.name,))
#LG             self.value.exportLiteral(outfile, level + 1)
#LG             showIndent(outfile, level)
#LG             outfile.write(')\\n')
#LG
#LG
#LG class MemberSpec_(object):
#LG     def __init__(self, name='', data_type='', container=0):
#LG         self.name = name
#LG         self.data_type = data_type
#LG         self.container = container
#LG     def set_name(self, name): self.name = name
#LG     def get_name(self): return self.name
#LG     def set_data_type(self, data_type): self.data_type = data_type
#LG     def get_data_type_chain(self): return self.data_type
#LG     def get_data_type(self):
#LG         if isinstance(self.data_type, list):
#LG             if len(self.data_type) > 0:
#LG                 return self.data_type[-1]
#LG             else:
#LG                 return 'xs:string'
#LG         else:
#LG             return self.data_type
#LG     def set_container(self, container): self.container = container
#LG     def get_container(self): return self.container
#LG
#LG def cast_(typ, value):
#LG     if typ is None or value is None:
#LG         return value
#LG     return typ(value)
#LG
#LG #
#LG # Data representation classes.
#LG #
#LG
#LG """

# Fool (and straighten out) the syntax highlighting.
# DUMMY = '''

#LG def generateHeader(wrt, prefix):
#LG     global NoDates, LangGenr
#LG     LangGenr.generateHeader(wrt, prefix)
#LG   tstamp = (not NoDates and time.ctime()) or ''
#LG   if NoVersion:
#LG       version = ''
#LG   else:
#LG       version = ' version %s' % VERSION
#LG   s1 = TEMPLATE_HEADER % (tstamp, version, ExternalEncoding, )
#LG   wrt(s1)


#LG TEMPLATE_MAIN = """\
#LG USAGE_TEXT = \"\"\"
#LG Usage: python <%(prefix)sParser>.py [ -s ] <in_xml_file>
#LG \"\"\"
#LG
#LG def usage():
#LG     print USAGE_TEXT
#LG     sys.exit(1)
#LG
#LG
#LG def get_root_tag(node):
#LG     tag = Tag_pattern_.match(node.tag).groups()[-1]
#LG     rootClass = globals().get(tag)
#LG     return tag, rootClass
#LG
#LG
#LG def parse(inFileName):
#LG     doc = parsexml_(inFileName)
#LG     rootNode = doc.getroot()
#LG     rootTag, rootClass = get_root_tag(rootNode)
#LG     if rootClass is None:
#LG         rootTag = '%(name)s'
#LG         rootClass = %(prefix)s%(root)s
#LG     rootObj = rootClass.factory()
#LG     rootObj.build(rootNode)
#LG     # Enable Python to collect the space used by the DOM.
#LG     doc = None
#LG #silence#    sys.stdout.write('<?xml version="1.0" ?>\\n')
#LG #silence#    rootObj.export_xml(sys.stdout, 0, name_=rootTag,
#LG #silence#        namespacedef_='%(namespacedef)s',
#LG #silence#        pretty_print=True)
#LG     return rootObj
#LG
#LG
#LG def parseString(inString):
#LG     from StringIO import StringIO
#LG     doc = parsexml_(StringIO(inString))
#LG     rootNode = doc.getroot()
#LG     rootTag, rootClass = get_root_tag(rootNode)
#LG     if rootClass is None:
#LG         rootTag = '%(name)s'
#LG         rootClass = %(prefix)s%(root)s
#LG     rootObj = rootClass.factory()
#LG     rootObj.build(rootNode)
#LG     # Enable Python to collect the space used by the DOM.
#LG     doc = None
#LG #silence#    sys.stdout.write('<?xml version="1.0" ?>\\n')
#LG #silence#    rootObj.export_xml(sys.stdout, 0, name_="%(name)s",
#LG #silence#        namespacedef_='%(namespacedef)s')
#LG     return rootObj
#LG
#LG
#LG def parseLiteral(inFileName):
#LG     doc = parsexml_(inFileName)
#LG     rootNode = doc.getroot()
#LG     rootTag, rootClass = get_root_tag(rootNode)
#LG     if rootClass is None:
#LG         rootTag = '%(name)s'
#LG         rootClass = %(prefix)s%(root)s
#LG     rootObj = rootClass.factory()
#LG     rootObj.build(rootNode)
#LG     # Enable Python to collect the space used by the DOM.
#LG     doc = None
#LG #silence#    sys.stdout.write('#from %(module_name)s import *\\n\\n')
#LG #silence#    sys.stdout.write('import %(module_name)s as model_\\n\\n')
#LG #silence#    sys.stdout.write('rootObj = model_.rootTag(\\n')
#LG #silence#    rootObj.exportLiteral(sys.stdout, 0, name_=rootTag)
#LG #silence#    sys.stdout.write(')\\n')
#LG     return rootObj
#LG
#LG
#LG def main():
#LG     args = sys.argv[1:]
#LG     if len(args) == 1:
#LG         parse(args[0])
#LG     else:
#LG         usage()
#LG
#LG
#LG if __name__ == '__main__':
#LG     main()
#LG
#LG """


# Fool (and straighten out) the syntax highlighting.
# DUMMY = """


#LG def generateMain(outfile, prefix, root):
#LG     name = RootElement or root.getChildren()[0].getName()
#LG     elType = cleanupName(root.getChildren()[0].getType())
#LG     if RootElement:
#LG         rootElement = RootElement
#LG     else:
#LG         rootElement = elType
#LG     params = {
#LG         'prefix': prefix,
#LG         'cap_name': cleanupName(make_gs_name(name)),
#LG         'name': name,
#LG         'cleanname': cleanupName(name),
#LG         'module_name': os.path.splitext(os.path.basename(outfile.name))[0],
#LG         'root': rootElement,
#LG         'namespacedef': Namespacedef,
#LG         }
#LG     s1 = TEMPLATE_MAIN % params
#LG     outfile.write(s1)


def buildCtorParams(element, parent, childCount):
    content = []
    addedArgs = {}
    add = content.append
##     if not element.isMixed():
##         buildCtorParams_aux(addedArgs, add, parent)
    buildCtorParams_aux(addedArgs, add, parent)
    eltype = element.getType()
    if element.getSimpleContent() or element.isMixed():
        add("valueOf_, ")
    if element.isMixed():
        add('mixedclass_, ')
        add('content_, ')
    if element.getExtended():
        add('extensiontype_, ')
    return content


def buildCtorParams_aux(addedArgs, add, element):
    parentName, parentObj = getParentName(element)
    if parentName:
        buildCtorParams_aux(addedArgs, add, parentObj)
    attrDefs = element.getAttributeDefs()
    for key in attrDefs:
        attrDef = attrDefs[key]
        name = attrDef.getName()
        name = cleanupName(mapName(name))
        if name not in addedArgs:
            addedArgs[name] = 1
            add('%s, ' % name)
    for child in element.getChildren():
        if child.getType() == AnyTypeIdentifier:
            add('anytypeobjs_, ')
        else:
            name = child.getCleanName()
            if name not in addedArgs:
                addedArgs[name] = 1
                add('%s, ' % name)


def get_class_behavior_args(classBehavior):
    argList = []
    args = classBehavior.getArgs()
    args = args.getArg()
    for arg in args:
        argList.append(arg.getName())
    argString = ', '.join(argList)
    return argString


#
# Retrieve the implementation body via an HTTP request to a
#   URL formed from the concatenation of the baseImplUrl and the
#   implUrl.
# An alternative implementation of get_impl_body() that also
#   looks in the local file system is commented out below.
#
def get_impl_body(classBehavior, baseImplUrl, implUrl):
    impl = '        pass\n'
    if implUrl:
        if baseImplUrl:
            implUrl = '%s%s' % (baseImplUrl, implUrl)
        try:
            implFile = urllib2.urlopen(implUrl)
            impl = implFile.read()
            implFile.close()
        except urllib2.HTTPError:
            err_msg('*** Implementation at %s not found.\n' % implUrl)
        except urllib2.URLError:
            err_msg('*** Connection refused for URL: %s\n' % implUrl)
    return impl

###
### This alternative implementation of get_impl_body() tries the URL
###   via http first, then, if that fails, looks in a directory on
###   the local file system (baseImplUrl) for a file (implUrl)
###   containing the implementation body.
###
##def get_impl_body(classBehavior, baseImplUrl, implUrl):
##    impl = '        pass\n'
##    if implUrl:
##        trylocal = 0
##        if baseImplUrl:
##            implUrl = '%s%s' % (baseImplUrl, implUrl)
##        try:
##            implFile = urllib2.urlopen(implUrl)
##            impl = implFile.read()
##            implFile.close()
##        except:
##            trylocal = 1
##        if trylocal:
##            try:
##                implFile = file(implUrl)
##                impl = implFile.read()
##                implFile.close()
##            except:
##                print '*** Implementation at %s not found.' % implUrl
##    return impl


def generateClassBehaviors(wrt, classBehaviors, baseImplUrl):
    for classBehavior in classBehaviors:
        behaviorName = classBehavior.getName()
        #
        # Generate the core behavior.
        argString = get_class_behavior_args(classBehavior)
        if argString:
            wrt('    def %s(self, %s, *args):\n' % (behaviorName, argString))
        else:
            wrt('    def %s(self, *args):\n' % (behaviorName, ))
        implUrl = classBehavior.getImpl_url()
        impl = get_impl_body(classBehavior, baseImplUrl, implUrl)
        wrt(impl)
        wrt('\n')
        #
        # Generate the ancillaries for this behavior.
        ancillaries = classBehavior.getAncillaries()
        if ancillaries:
            ancillaries = ancillaries.getAncillary()
        if ancillaries:
            for ancillary in ancillaries:
                argString = get_class_behavior_args(ancillary)
                if argString:
                    wrt('    def %s(self, %s, *args):\n' % (ancillary.getName(), argString))
                else:
                    wrt('    def %s(self, *args):\n' % (ancillary.getName(), ))
                implUrl = ancillary.getImpl_url()
                impl = get_impl_body(classBehavior, baseImplUrl, implUrl)
                wrt(impl)
                wrt('\n')
        #
        # Generate the wrapper method that calls the ancillaries and
        #   the core behavior.
        argString = get_class_behavior_args(classBehavior)
        if argString:
            wrt('    def %s_wrapper(self, %s, *args):\n' % (behaviorName, argString))
        else:
            wrt('    def %s_wrapper(self, *args):\n' % (behaviorName, ))
        if ancillaries:
            for ancillary in ancillaries:
                role = ancillary.getRole()
                if role == 'DBC-precondition':
                    wrt('        if not self.%s(*args)\n' % (ancillary.getName(), ))
                    wrt('            return False\n')
        if argString:
            wrt('        result = self.%s(%s, *args)\n' % (behaviorName, argString))
        else:
            wrt('        result = self.%s(*args)\n' % (behaviorName, ))
        if ancillaries:
            for ancillary in ancillaries:
                role = ancillary.getRole()
                if role == 'DBC-postcondition':
                    wrt('        if not self.%s(*args)\n' % (ancillary.getName(), ))
                    wrt('            return False\n')
        wrt('        return result\n')
        wrt('\n')


#LG def generateSubclass(wrt, element, prefix, xmlbehavior,  behaviors, baseUrl):
#LG     if not element.isComplex():
#LG         return
#LG     if element.getName() in AlreadyGenerated_subclass:
#LG         return
#LG     AlreadyGenerated_subclass.append(element.getName())
#LG     name = element.getCleanName()
#LG     wrt('class %s%s%s(supermod.%s):\n' % (prefix, name, SubclassSuffix, name))
#LG     childCount = countChildren(element, 0)
#LG     s1 = buildCtorArgs_multilevel(element, childCount)
#LG     wrt('    def __init__(self%s):\n' % s1)
#LG     args = buildCtorParams(element, element, childCount)
#LG     s1 = ''.join(args)
#LG     if len(args) > 254:
#LG         wrt('        arglist_ = (%s)\n' % (s1, ))
#LG         wrt('        super(%s%s%s, self).__init__(*arglist_)\n' % (prefix, name, SubclassSuffix, ))
#LG     else:
#LG         #wrt('        supermod.%s%s.__init__(%s)\n' % (prefix, name, s1))
#LG         wrt('        super(%s%s%s, self).__init__(%s)\n' % (prefix, name, SubclassSuffix, s1, ))
#LG     if xmlbehavior and behaviors:
#LG         wrt('\n')
#LG         wrt('    #\n')
#LG         wrt('    # XMLBehaviors\n')
#LG         wrt('    #\n')
#LG         # Get a list of behaviors for this class/subclass.
#LG         classDictionary = behaviors.get_class_dictionary()
#LG         if name in classDictionary:
#LG             classBehaviors = classDictionary[name]
#LG         else:
#LG             classBehaviors = None
#LG         if classBehaviors:
#LG             generateClassBehaviors(wrt, classBehaviors, baseUrl)
#LG     wrt('supermod.%s.subclass = %s%s\n' % (name, name, SubclassSuffix))
#LG     wrt('# end class %s%s%s\n' % (prefix, name, SubclassSuffix))
#LG     wrt('\n\n')


TEMPLATE_SUBCLASS_HEADER = """\
#!/usr/bin/env python

#
# Generated %s by generateDS.py%s.
#

import sys

import %s as supermod

etree_ = None
Verbose_import_ = False
(   XMLParser_import_none, XMLParser_import_lxml,
    XMLParser_import_elementtree
    ) = range(3)
XMLParser_import_library = None
try:
    # lxml
    from lxml import etree as etree_
    XMLParser_import_library = XMLParser_import_lxml
    if Verbose_import_:
        print("running with lxml.etree")
except ImportError:
    try:
        # cElementTree from Python 2.5+
        import xml.etree.cElementTree as etree_
        XMLParser_import_library = XMLParser_import_elementtree
        if Verbose_import_:
            print("running with cElementTree on Python 2.5+")
    except ImportError:
        try:
            # ElementTree from Python 2.5+
            import xml.etree.ElementTree as etree_
            XMLParser_import_library = XMLParser_import_elementtree
            if Verbose_import_:
                print("running with ElementTree on Python 2.5+")
        except ImportError:
            try:
                # normal cElementTree install
                import cElementTree as etree_
                XMLParser_import_library = XMLParser_import_elementtree
                if Verbose_import_:
                    print("running with cElementTree")
            except ImportError:
                try:
                    # normal ElementTree install
                    import elementtree.ElementTree as etree_
                    XMLParser_import_library = XMLParser_import_elementtree
                    if Verbose_import_:
                        print("running with ElementTree")
                except ImportError:
                    raise ImportError("Failed to import ElementTree from any known place")

def parsexml_(*args, **kwargs):
    if (XMLParser_import_library == XMLParser_import_lxml and
        'parser' not in kwargs):
        # Use the lxml ElementTree compatible parser so that, e.g.,
        #   we ignore comments.
        kwargs['parser'] = etree_.ETCompatXMLParser()
    doc = etree_.parse(*args, **kwargs)
    return doc

#
# Globals
#

ExternalEncoding = '%s'

#
# Data representation classes
#

"""

TEMPLATE_SUBCLASS_FOOTER = """\

def get_root_tag(node):
    tag = supermod.Tag_pattern_.match(node.tag).groups()[-1]
    rootClass = None
    if hasattr(supermod, tag):
        rootClass = getattr(supermod, tag)
    return tag, rootClass


def parse(inFilename):
    doc = parsexml_(inFilename)
    rootNode = doc.getroot()
    rootTag, rootClass = get_root_tag(rootNode)
    if rootClass is None:
        rootTag = '%(name)s'
        rootClass = supermod.%(root)s
    rootObj = rootClass.factory()
    rootObj.build(rootNode)
    # Enable Python to collect the space used by the DOM.
    doc = None
#silence#    sys.stdout.write('<?xml version="1.0" ?>\\n')
#silence#    rootObj.export_xml(sys.stdout, 0, name_=rootTag,
#silence#        namespacedef_='%(namespacedef)s',
#silence#        pretty_print=True)
    doc = None
    return rootObj


def parseString(inString):
    from StringIO import StringIO
    doc = parsexml_(StringIO(inString))
    rootNode = doc.getroot()
    rootTag, rootClass = get_root_tag(rootNode)
    if rootClass is None:
        rootTag = '%(name)s'
        rootClass = supermod.%(root)s
    rootObj = rootClass.factory()
    rootObj.build(rootNode)
    # Enable Python to collect the space used by the DOM.
    doc = None
#silence#    sys.stdout.write('<?xml version="1.0" ?>\\n')
#silence#    rootObj.export_xml(sys.stdout, 0, name_=rootTag,
#silence#        namespacedef_='%(namespacedef)s')
    return rootObj


def parseLiteral(inFilename):
    doc = parsexml_(inFilename)
    rootNode = doc.getroot()
    rootTag, rootClass = get_root_tag(rootNode)
    if rootClass is None:
        rootTag = '%(name)s'
        rootClass = supermod.%(root)s
    rootObj = rootClass.factory()
    rootObj.build(rootNode)
    # Enable Python to collect the space used by the DOM.
    doc = None
#silence#    sys.stdout.write('#from %(super)s import *\\n\\n')
#silence#    sys.stdout.write('import %(super)s as model_\\n\\n')
#silence#    sys.stdout.write('rootObj = model_.%(cleanname)s(\\n')
#silence#    rootObj.exportLiteral(sys.stdout, 0, name_="%(cleanname)s")
#silence#    sys.stdout.write(')\\n')
    return rootObj


USAGE_TEXT = \"\"\"
Usage: python ???.py <infilename>
\"\"\"

def usage():
    print USAGE_TEXT
    sys.exit(1)


def main():
    args = sys.argv[1:]
    if len(args) != 1:
        usage()
    infilename = args[0]
    root = parse(infilename)


if __name__ == '__main__':
    main()


"""

TEMPLATE_ABSTRACT_CLASS = """\
class %(clsname)s(object):
    subclass = None
    superclass = None
# fix valueof
    def __init__(self, valueOf_=''):
        raise NotImplementedError(
            'Cannot instantiate abstract class %(clsname)s (__init__)')
    def factory(*args_, **kwargs_):
        raise NotImplementedError(
            'Cannot instantiate abstract class %(clsname)s (factory)')
    factory = staticmethod(factory)
    def build(self, node_):
        raise NotImplementedError(
            'Cannot build abstract class %(clsname)s')
        attrs = node_.attributes
        # fix_abstract
        type_name = attrs.getNamedItemNS(
            'http://www.w3.org/2001/XMLSchema-instance', 'type')
        if type_name is not None:
            self.type_ = globals()[type_name.value]()
            self.type_.build(node_)
        else:
            raise NotImplementedError(
                'Class %%s not implemented (build)' %% type_name.value)
# end class %(clsname)s


"""

TEMPLATE_ABSTRACT_CHILD = """\
            type_name_ = child_.attrib.get('{http://www.w3.org/2001/XMLSchema-instance}type')
            if type_name_ is None:
                type_name_ = child_.attrib.get('type')
            if type_name_ is not None:
                type_names_ = type_name_.split(':')
                if len(type_names_) == 1:
                    type_name_ = type_names_[0]
                else:
                    type_name_ = type_names_[1]
                class_ = globals()[type_name_]
                obj_ = class_.factory()
                obj_.build(child_)
            else:
                raise NotImplementedError(
                    'Class not implemented for <%s> element')
"""

#LG def generateSubclasses(root, subclassFilename, behaviorFilename,
#LG         prefix, superModule='xxx'):
#LG     name = root.getChildren()[0].getName()
#LG     subclassFile = makeFile(subclassFilename)
#LG     wrt = subclassFile.write
#LG     if subclassFile:
#LG         # Read in the XMLBehavior file.
#LG         xmlbehavior = None
#LG         behaviors = None
#LG         baseUrl = None
#LG         if behaviorFilename:
#LG             try:
#LG                 # Add the currect working directory to the path so that
#LG                 #   we use the user/developers local copy.
#LG                 sys.path.insert(0, '.')
#LG                 import xmlbehavior_sub as xmlbehavior
#LG             except ImportError:
#LG                 err_msg('*** You have requested generation of extended methods.\n')
#LG                 err_msg('*** But, no xmlbehavior module is available.\n')
#LG                 err_msg('*** Generation of extended behavior methods is omitted.\n')
#LG             if xmlbehavior:
#LG                 behaviors = xmlbehavior.parse(behaviorFilename)
#LG                 behaviors.make_class_dictionary(cleanupName)
#LG                 baseUrl = behaviors.getBase_impl_url()
#LG         wrt = subclassFile.write
#LG         tstamp = (not NoDates and time.ctime()) or ''
#LG         if NoVersion:
#LG             version = ''
#LG         else:
#LG             version = ' version %s' % VERSION
#LG         wrt(TEMPLATE_SUBCLASS_HEADER % (tstamp, version,
#LG             superModule, ExternalEncoding, ))
#LG         for element in ElementsForSubclasses:
#LG             generateSubclass(wrt, element, prefix, xmlbehavior, behaviors, baseUrl)
#LG         name = root.getChildren()[0].getName()
#LG         elType = cleanupName(root.getChildren()[0].getType())
#LG         if RootElement:
#LG             rootElement = RootElement
#LG         else:
#LG             rootElement = elType
#LG         params = {
#LG             'cap_name': make_gs_name(cleanupName(name)),
#LG             'name': name,
#LG             'cleanname': cleanupName(name),
#LG             'module_name': os.path.splitext(os.path.basename(subclassFilename))[0],
#LG             'root': rootElement,
#LG             'namespacedef': Namespacedef,
#LG             'super': superModule,
#LG             }
#LG         wrt(TEMPLATE_SUBCLASS_FOOTER % params)
#LG         subclassFile.close()


#LG def generateFromTree(wrt, prefix, elements, processed):
#LG     for element in elements:
#LG         name = element.getCleanName()
#LG         if 1:     # if name not in processed:
#LG             processed.append(name)
#LG             generateClasses(wrt, prefix, element, 0)
#LG             children = element.getChildren()
#LG             if children:
#LG                 generateFromTree(wrt, prefix, element.getChildren(), processed)


def generateSimpleTypes(wrt, prefix, simpleTypeDict):
    for simpletype in simpleTypeDict.keys():
        wrt('class %s(object):\n' % simpletype)
        wrt('    pass\n')
        wrt('\n\n')


#LG def generate(outfileName, subclassFilename, behaviorFilename,
#LG         prefix, root, superModule):
#LG     global DelayedElements, DelayedElements_subclass
#LG     # Create an output file.
#LG     # Note that even if the user does not request an output file,
#LG     #   we still need to go through the process of generating classes
#LG     #   because it produces data structures needed during generation of
#LG     #   subclasses.
#LG     outfile = None
#LG     if outfileName:
#LG         outfile = makeFile(outfileName)
#LG     if not outfile:
#LG         outfile = os.tmpfile()
#LG     wrt = outfile.write
#LG     processed = []
#LG     generateHeader(wrt, prefix)
#LG     #generateSimpleTypes(outfile, prefix, SimpleTypeDict)
#LG     DelayedElements = []
#LG     DelayedElements_subclass = []
#LG     elements = root.getChildren()
#LG     generateFromTree(wrt, prefix, elements, processed)
#LG     while 1:
#LG         if len(DelayedElements) <= 0:
#LG             break
#LG         element = DelayedElements.pop()
#LG         name = element.getCleanName()
#LG         if name not in processed:
#LG             processed.append(name)
#LG             generateClasses(wrt, prefix, element, 1)
#LG     #
#LG     # Generate the elements that were postponed because we had not
#LG     #   yet generated their base class.
#LG     while 1:
#LG         if len(PostponedExtensions) <= 0:
#LG             break
#LG         element = PostponedExtensions.pop()
#LG         parentName, parent = getParentName(element)
#LG         if parentName:
#LG             if (parentName in AlreadyGenerated or
#LG                 parentName in SimpleTypeDict.keys()):
#LG                 generateClasses(wrt, prefix, element, 1)
#LG             else:
#LG                 PostponedExtensions.insert(0, element)
#LG     #
#LG     # Disable the generation of SAX handler/parser.
#LG     # It failed when we stopped putting simple types into ElementDict.
#LG     # When there are duplicate names, the SAX parser probably does
#LG     #   not work anyway.
#LG     generateMain(outfile, prefix, root)
#LG     outfile.close()
#LG     if subclassFilename:
#LG         generateSubclasses(root, subclassFilename, behaviorFilename,
#LG             prefix, superModule)


#LG def makeFile(outFileName):
#LG     outFile = None
#LG     if (not Force) and os.path.exists(outFileName):
#LG         if NoQuestions:
#LG             sys.stderr.write('File %s exists.  Change output file or use -f (force).\n' % outFileName)
#LG             sys.exit(1)
#LG         else:
#LG             reply = raw_input('File %s exists.  Overwrite? (y/n): ' % outFileName)
#LG             if reply == 'y':
#LG                 outFile = file(outFileName, 'w')
#LG     else:
#LG         outFile = file(outFileName, 'w')
#LG     return outFile


#LG def mapName(oldName):
#LG     global NameTable
#LG     newName = oldName
#LG     if NameTable:
#LG         if oldName in NameTable:
#LG             newName = NameTable[oldName]
#LG     return newName

#LG def cleanupName(oldName):
#LG     newName = oldName.replace(':', '_')
#LG     newName = newName.replace('-', '_')
#LG     newName = newName.replace('.', '_')
#LG     return newName

#LG def make_gs_name(oldName):
#LG     if UseOldGetterSetter:
#LG         newName = oldName.capitalize()
#LG     else:
#LG         newName = '_%s' % oldName
#LG     return newName

## def mapName(oldName):
##     return '_X_%s' % oldName


def strip_namespace(val):
    return val.split(':')[-1]


def escape_string(instring):
    s1 = instring
    s1 = s1.replace('\\', '\\\\')
    s1 = s1.replace("'", "\\'")
    return s1


#LG def is_builtin_simple_type(type_val):
#LG     if type_val in StringType or \
#LG         type_val == TokenType or \
#LG         type_val == DateTimeType or \
#LG         type_val == TimeType or \
#LG         type_val == DateType or \
#LG         type_val in IntegerType or \
#LG         type_val == DecimalType or \
#LG         type_val == PositiveIntegerType or \
#LG         type_val == NonPositiveIntegerType or \
#LG         type_val == NegativeIntegerType or \
#LG         type_val == NonNegativeIntegerType or \
#LG         type_val == BooleanType or \
#LG         type_val == FloatType or \
#LG         type_val == DoubleType or \
#LG         type_val in OtherSimpleTypes:
#LG         return True
#LG     else:
#LG         return False


##def process_include(inpath, outpath):
##    from xml.etree import ElementTree as etree
##    if inpath:
##        doc = etree.parse(inpath)
##        root = doc.getroot()
##        process_include_tree(root)
##    else:
##        s1 = sys.stdin.read()
##        root = etree.fromstring(s1)
##        process_include_tree(root)
##        doc = etree.ElementTree(root)
##    if outpath:
##        outfile = make_file(outpath)
##        if outfile:
##            doc.write(outfile)
##            outfile.close()
##    else:
##        doc.write(sys.stdout)
##
##def process_include_tree(root):
##    idx = 0
##    children = root.getchildren()
##    while idx < len(children):
##        child = children[idx]
##        tag = child.tag
##        if type(tag) == type(""):
##            tag = NAMESPACE_PAT.sub("", tag)
##        else:
##            tag = None
##        if tag == 'include' and 'schemaLocation' in child.attrib:
##            root.remove(child)
##            path = child.attrib['schemaLocation']
##            if os.path.exists(path):
##                doc = etree.parse(path)
##                node = doc.getroot()
##                process_include_tree(node)
##                children1 = node.getchildren()
##                for child1 in children1:
##                    root.insert(idx, child1)
##                    idx += 1
##        else:
##            process_include_tree(child)
##            idx += 1
##        children = root.getchildren()

#LG def parseAndGenerate(outfileName, subclassFilename, prefix,
#LG         xschemaFileName, behaviorFilename,
#LG         processIncludes, superModule='???'):
#LG     global DelayedElements, DelayedElements_subclass, AlreadyGenerated, SaxDelayedElements, \
#LG         AlreadyGenerated_subclass, UserMethodsPath, UserMethodsModule
#LG     DelayedElements = []
#LG     DelayedElements_subclass = []
#LG     AlreadyGenerated = []
#LG     AlreadyGenerated_subclass = []
#LG     if UserMethodsPath:
#LG         # UserMethodsModule = __import__(UserMethodsPath)
#LG         path_list = UserMethodsPath.split('.')
#LG         mod_name = path_list[-1]
#LG         mod_path = os.sep.join(path_list[:-1])
#LG         module_spec = imp.find_module(mod_name, [mod_path, ])
#LG         UserMethodsModule = imp.load_module(mod_name, *module_spec)
#LG ##    parser = saxexts.make_parser("xml.sax.drivers2.drv_pyexpat")
#LG     parser = make_parser()
#LG     dh = XschemaHandler()
#LG ##    parser.setDocumentHandler(dh)
#LG     parser.setContentHandler(dh)
#LG     if xschemaFileName == '-':
#LG         infile = sys.stdin
#LG     else:
#LG         infile = open(xschemaFileName, 'r')
#LG     if processIncludes:
#LG         import process_includes
#LG         outfile = StringIO.StringIO()
#LG         process_includes.process_include_files(infile, outfile,
#LG             inpath=xschemaFileName)
#LG         outfile.seek(0)
#LG         infile = outfile
#LG     parser.parse(infile)
#LG     root = dh.getRoot()
#LG     root.annotate()
#LG ##     print '-' * 60
#LG ##     root.show(sys.stdout, 0)
#LG ##     print '-' * 60
#LG     #debug_show_elements(root)
#LG     generate(outfileName, subclassFilename, behaviorFilename,
#LG         prefix, root, superModule)
#LG     # Generate __all__.  When using the parser as a module it is useful
#LG     # to isolate important classes from internal ones. This way one
#LG     # can do a reasonably safe "from parser import *"
#LG     if outfileName:
#LG         exportableClassList = ['"%s"' % mapName(cleanupName(name))
#LG             for name in AlreadyGenerated]
#LG         exportableClassList.sort()
#LG         exportableClassNames = ',\n    '.join(exportableClassList)
#LG         exportLine = "\n__all__ = [\n    %s\n    ]\n" % exportableClassNames
#LG         outfile = open(outfileName, "a")
#LG         outfile.write(exportLine)
#LG         outfile.close()

# Function that gets called recursively in order to expand nested references
# to element groups
def _expandGR(grp, visited):
    # visited is used for loop detection
    children = []
    changed = False
    for child in grp.children:
        groupRef = child.getElementGroup()
        if not groupRef:
            children.append(child)
            continue
        ref = groupRef.ref
        referencedGroup = ElementGroups.get(ref, None)
        if referencedGroup is None:
            ref = strip_namespace(ref)
            referencedGroup = ElementGroups.get(ref, None)
        if referencedGroup is None:
            #err_msg('*** Reference to unknown group %s' % groupRef.attrs['ref'])
            err_msg('*** Reference to unknown group %s\n' % groupRef.ref)
            continue
        visited.add(id(grp))
        if id(referencedGroup) in visited:
            #err_msg('*** Circular reference for %s' % groupRef.attrs['ref'])
            err_msg('*** Circular reference for %s\n' % groupRef.ref)
            continue
        changed = True
        _expandGR(referencedGroup, visited)
        children.extend(referencedGroup.children)
    if changed:
        # Avoid replacing the list with a copy of the list
        grp.children = children

def expandGroupReferences(grp):
    visited = set()
    _expandGR(grp, visited)

def debug_show_elements(root):
    #print 'ElementDict:', ElementDict
    print '=' * 50
    for name, obj in ElementDict.iteritems():
        print 'element:', name, obj.getName(), obj.type
    print '=' * 50
    #ipshell('debug')
##     root.show(sys.stdout, 0)
##     print '=' * 50
##     response = raw_input('Press Enter')
##     root.show(sys.stdout, 0)
##     print '=' * 50
##     print ']]] root: ', root, '[[['


#LG def load_config():
#LG     try:
#LG         #print '1. updating NameTable'
#LG         import generateds_config
#LG         NameTable.update(generateds_config.NameTable)
#LG         #print '2. updating NameTable'
#LG     except ImportError, exp:
#LG         pass


def fixSilence(txt, silent):
    if silent:
        txt = txt.replace('#silence#', '## ')
    else:
        txt = txt.replace('#silence#', '')
    return txt


def err_msg(msg):
    sys.stderr.write(msg)


USAGE_TEXT = __doc__

def usage():
    print USAGE_TEXT
    sys.exit(1)


def main():

    pgenr = XsdParserGenerator()
    pgenr.args_parse()
    #LG  global Force, GenerateProperties, SubclassSuffix, RootElement, \
    #LG      ValidatorBodiesBasePath, UseOldGetterSetter, \
    #LG      UserMethodsPath, XsdNameSpace, \
    #LG      Namespacedef, NoDates, NoVersion, \
    #LG      TEMPLATE_MAIN, TEMPLATE_SUBCLASS_FOOTER, Dirpath, \
    #LG      ExternalEncoding, MemberSpecs, NoQuestions, LangGenr
    #LG  outputText = True
    #LG  args = sys.argv[1:]
    #LG  try:
    #LG      options, args = getopt.getopt(args, 'g:hfyo:s:p:a:b:mu:q',
    #LG          ['help', 'subclass-suffix=',
    #LG          'root-element=', 'super=',
    #LG          'validator-bodies=', 'use-old-getter-setter',
    #LG          'user-methods=', 'no-process-includes', 'silence',
    #LG          'namespacedef=', 'external-encoding=',
    #LG          'member-specs=', 'no-dates', 'no-versions',
    #LG          'no-questions', 'session=', 'generated-language=',
    #LG          'version',
    #LG          ])
    #LG  except getopt.GetoptError, exp:
    #LG      usage()
    #LG  prefix = ''
    #LG  outFilename = None
    #LG  subclassFilename = None
    #LG  behaviorFilename = None
    #LG  nameSpace = 'xs:'
    #LG  superModule = '???'
    #LG  processIncludes = 1
    #LG  namespacedef = ''
    #LG  ExternalEncoding = sys.getdefaultencoding()
    #LG  NoDates = False
    #LG  NoVersion = False
    #LG  NoQuestions = False
    #LG  showVersion = False
    #LG  xschemaFileName = None
    #LG  for option in options:
    #LG      if option[0] == '--session':
    #LG          sessionFilename = option[1]
    #LG          from libgenerateDS.gui import generateds_gui_session
    #LG          from xml.etree import ElementTree as etree
    #LG          doc = etree.parse(sessionFilename)
    #LG          rootNode = doc.getroot()
    #LG          sessionObj = generateds_gui_session.sessionType()
    #LG          sessionObj.build(rootNode)
    #LG          if sessionObj.get_input_schema():
    #LG              xschemaFileName = sessionObj.get_input_schema()
    #LG          if sessionObj.get_output_superclass():
    #LG              outFilename = sessionObj.get_output_superclass()
    #LG          if sessionObj.get_output_subclass():
    #LG              subclassFilename = sessionObj.get_output_subclass()
    #LG          if sessionObj.get_force():
    #LG              Force = True
    #LG          if sessionObj.get_prefix():
    #LG              prefix = sessionObj.get_prefix()
    #LG          if sessionObj.get_empty_namespace_prefix():
    #LG              nameSpace = ''
    #LG          elif sessionObj.get_namespace_prefix():
    #LG              nameSpace = sessionObj.get_namespace_prefix()
    #LG          if sessionObj.get_behavior_filename():
    #LG              behaviorFilename = sessionObj.get_behavior_filename()
    #LG          if sessionObj.get_properties():
    #LG              GenerateProperties = True
    #LG          if sessionObj.get_subclass_suffix():
    #LG              SubclassSuffix = sessionObj.get_subclass_suffix()
    #LG          if sessionObj.get_root_element():
    #LG              RootElement = sessionObj.get_root_element()
    #LG          if sessionObj.get_superclass_module():
    #LG              superModule = sessionObj.get_superclass_module()
    #LG          if sessionObj.get_old_getters_setters():
    #LG              UseOldGetterSetter = 1
    #LG          if sessionObj.get_validator_bodies():
    #LG              ValidatorBodiesBasePath = sessionObj.get_validator_bodies()
    #LG              if not os.path.isdir(ValidatorBodiesBasePath):
    #LG                  err_msg('*** Option validator-bodies must specify an existing path.\n')
    #LG                  sys.exit(1)
    #LG          if sessionObj.get_user_methods():
    #LG              UserMethodsPath = sessionObj.get_user_methods()
    #LG          if sessionObj.get_no_dates():
    #LG              NoDates = True
    #LG          if sessionObj.get_no_versions():
    #LG              NoVersion = True
    #LG          if sessionObj.get_no_process_includes():
    #LG              processIncludes = 0
    #LG          if sessionObj.get_silence():
    #LG              outputText = False
    #LG          if sessionObj.get_namespace_defs():
    #LG              namespacedef = sessionObj.get_naspace_defs()
    #LG          if sessionObj.get_external_encoding():
    #LG              ExternalEncoding = sessionObj.get_external_encoding()
    #LG          if sessionObj.get_member_specs() in ('list', 'dict'):
    #LG              MemberSpecs = sessionObj.get_member_specs()
    #LG          break
    #LG  for option in options:
    #LG      if option[0] == '-h' or option[0] == '--help':
    #LG          usage()
    #LG      elif option[0] == '-p':
    #LG          prefix = option[1]
    #LG      elif option[0] == '-o':
    #LG          outFilename = option[1]
    #LG      elif option[0] == '-s':
    #LG          subclassFilename = option[1]
    #LG      elif option[0] == '-f':
    #LG          Force = 1
    #LG      elif option[0] == '-a':
    #LG          nameSpace = option[1]
    #LG      elif option[0] == '-b':
    #LG          behaviorFilename = option[1]
    #LG      elif option[0] == '-m':
    #LG          GenerateProperties = 1
    #LG      elif option[0] == '--no-dates':
    #LG          NoDates = True
    #LG      elif option[0] == '--no-versions':
    #LG          NoVersion = True
    #LG      elif option[0] == '--subclass-suffix':
    #LG          SubclassSuffix = option[1]
    #LG      elif option[0] == '--root-element':
    #LG          RootElement = option[1]
    #LG      elif option[0] == '--super':
    #LG          superModule = option[1]
    #LG      elif option[0] == '--validator-bodies':
    #LG          ValidatorBodiesBasePath = option[1]
    #LG          if not os.path.isdir(ValidatorBodiesBasePath):
    #LG              err_msg('*** Option validator-bodies must specify an existing path.\n')
    #LG              sys.exit(1)
    #LG      elif option[0] == '--use-old-getter-setter':
    #LG          UseOldGetterSetter = 1
    #LG      elif option[0] in ('-u', '--user-methods'):
    #LG          UserMethodsPath = option[1]
    #LG      elif option[0] == '--no-process-includes':
    #LG          processIncludes = 0
    #LG      elif option[0] == "--silence":
    #LG          outputText = False
    #LG      elif option[0] == "--namespacedef":
    #LG          namespacedef = option[1]
    #LG      elif option[0] == '--external-encoding':
    #LG          ExternalEncoding = option[1]
    #LG      elif option[0] in ('-q', '--no-questions'):
    #LG          NoQuestions = True
    #LG      elif option[0] == '--version':
    #LG          showVersion = True
    #LG      elif option[0] == '--member-specs':
    #LG          MemberSpecs = option[1]
    #LG          if MemberSpecs not in ('list', 'dict', ):
    #LG              raise RuntimeError('Option --member-specs must be "list" or "dict".')
    #LG      elif option[0] in ('-g', '--generated-language'):
    #LG          genLang = option[1]
    #LG          if genLang not in ('py', 'c++'):
    #LG              raise RuntimeError('Option --generated-language must be "py" or "c++".')
    #LG  if showVersion:
    #LG      print 'generateDS.py version %s' % VERSION
    #LG      sys.exit(0)
    pgenr.init_with_args()
    #LG XsdNameSpace = nameSpace
    #LG Namespacedef = namespacedef
    #LG set_type_constants(nameSpace)
    #LG if behaviorFilename and not subclassFilename:
    #LG     err_msg(USAGE_TEXT)
    #LG     err_msg('\n*** Error.  Option -b requires -s\n')
    #LG if xschemaFileName is None:
    #LG     if len(args) != 1:
    #LG         usage()
    #LG     else:
    #LG         xschemaFileName = args[0]
    #LG silent = not outputText
    #LG TEMPLATE_MAIN = fixSilence(TEMPLATE_MAIN, silent)
    #LG TEMPLATE_SUBCLASS_FOOTER = fixSilence(TEMPLATE_SUBCLASS_FOOTER, silent)
    #LG load_config()
    #LG if (genLang == 'py'):
    #LG     LangGenr = PyGenerator()
    #LG elif (genLang == 'c++'):
    #LG     LangGenr = CppGenerator()

    pgenr.parseAndGenerate()
    #LG parseAndGenerate(outFilename, subclassFilename, prefix,
    #LG     xschemaFileName, behaviorFilename,
    #LG     processIncludes, superModule=superModule)



if __name__ == '__main__':
    import cgitb
    cgitb.enable(format='text')
    logging.basicConfig(level=logging.WARN,)
    main()


