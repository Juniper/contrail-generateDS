#
# Copyright (c) 2013 Juniper Networks, Inc. All rights reserved.
#

"""
Generate the parsing methods for each metadata message.

For each 'resultItem', the identity elements are decoded and then the
metadata processed.

There are 3 scenarios:
  - Properties: the contents of which are stored in the parent identifier;
  - Links: create a graph edge;
  - Link meta with content: creates an object;
"""

from ifmap_global import GetModuleName
from ifmap_model import IFMapIdentifier, IFMapProperty, IFMapLink, IFMapLinkAttr, SimpleTypeWrapper
from type_parser import TypeParserGenerator

class IFMapGenIdentity(object):
    def __init__(self, identifier):
        self._identifier = identifier

    def getName(self):
        return self._identifier.getCppName()

    def getElementName(self):
        return self._identifier.getName()

    def GenerateEncoder(self, file):
        cdecl = """
void %(class)s::EncodeUpdate(xml_node *node) const {
""" % {'class': self.getName(), 'element': self.getElementName() }
        file.write(cdecl)
        for prop in self._identifier.getProperties():
            cdecl = """
    if (property_set_.test(%(prop_id)s)) {
        xml_node p = node->append_child("%(element)s");
""" % {'prop_id': prop.getPropertyId(), 'element': prop.getName()}
            file.write(cdecl)
            info = prop.getMemberInfo()
            assert info
            if info.isSequence:
                cdecl = """
        for (%(ctypename)s::const_iterator iter = %(member)s.begin();
             iter != %(member)s.end(); ++iter) {
""" % {'ctypename': info.ctypename, 'member': info.membername}
                file.write(cdecl)
                indent = ' ' * 12
                file.write(indent + 'xml_node s = p.append_child("%s");\n' %
                        info.xsd_object.getName());
                if info.xsd_object.isComplex():
                    file.write(indent + 'iter->Encode(&s);\n')
                else:
                    if info.sequenceType == 'std::string':
                        file.write(indent + 's.text().set(iter->c_str());\n')
                    else:
                        file.write(indent + 's.text().set(*iter);\n')
                indent = ' ' * 8
                file.write(indent + '}\n')
            elif info.isComplex:
                indent = ' ' * 8
                file.write(indent + prop.getPropertyName() + '_.Encode(&p);\n')
            else:
                indent = ' ' * 8
                if info.ctypename == 'std::string':
                    file.write(indent + 'p.text().set(%s.c_str());\n' %
                               info.membername)
                elif info.ctypename == 'bool':
                    file.write(indent + 'p.text().set(%s);\n' % info.membername)
                elif (info.ctypename == 'int' or
                      info.ctypename == 'uint32_t'):
                    file.write(indent + 'p.text().set(%s);\n' % info.membername)
                elif info.ctypename == 'uint64_t':
                    cdecl = """
        {
            ostringstream oss;
            oss << %(membername)s;
            p.text().set(oss.str().c_str());
        }
""" % {'membername': info.membername}
                    file.write(cdecl)
                else:
                    file.write(indent + '// TODO: unimplemented\n')
                
            indent = ' ' * 4
            file.write(indent + '}\n')
        file.write('}\n')

    def GenerateDecoder(self, file):
        cdecl = """
bool %(class)s::Decode(const xml_node &parent, std::string *id_name,
                       %(class)s *ptr) {
    for (xml_node node = parent.first_child(); node;
         node = node.next_sibling()) {
        if (strcmp(node.name(), "name") == 0) {
            *id_name = node.child_value();
        }
""" % {'class': self.getName() }
        file.write(cdecl)
        for prop in self._identifier.getProperties():
            indent = ' ' * 8
            file.write(indent + 'if (strcmp(node.name(), "%s") == 0) {\n' %
                       prop.getName())
            indent = ' ' * 12
            info = prop.getMemberInfo()
            assert info
            if info.isSequence:
                cdecl = """
            for (xml_node item = node.first_child(); item;
                item = item.next_sibling()) {
                if (strcmp(item.name(), "%s") != 0) {
                    continue;
                }
""" % (info.xsd_object.getName())
                file.write(cdecl)
                if info.xsd_object.isComplex():
                    cdecl = """
                %(type)s var;
                var.Clear();
                bool success = var.XmlParse(item);
                if (!success) {
                    return false;
                }
                ptr->%(member)s.push_back(var);
                ptr->property_set_.set(%(property)s);
""" % {'type': info.sequenceType, 'member': info.membername, 'property' : prop.getPropertyId()}
                    file.write(cdecl)
                else:
                    indent = ' ' * 16
                    if info.sequenceType == 'std::string':
                        file.write(indent + 'string var(item.child_value());\n')
                        file.write(indent + 'boost::trim(var);\n')
                        file.write(indent + 'ptr->%s.push_back(var);\n' %
                                   info.membername)
                        file.write(indent + 'ptr->property_set_.set(%s);\n' %
                                prop.getPropertyId())
                    elif info.sequenceType == 'int':
                        cdecl = """
                int var;
                bool success = autogen::ParseInteger(node, &var);
                if (!success) {
                    return false;
                }
                ptr->%(member)s.push_back(var);
		ptr->property_set_.set(%(property)s);
""" % {'member': info.membername, 'property' : prop.getPropertyId() }
                        file.write(cdecl)
                    else:
                        file.write(indent + '// TODO: unimplemented %s \n'
                                   % info.sequenceType)
                    indent = ' ' * 12
                file.write(indent + '}\n')
            elif info.isComplex:
                cdecl = """
            bool success = ptr->%(membername)s_.XmlParse(node);
            if (!success) {
                return false;
            }
            ptr->property_set_.set(%(property)s);
""" % {'membername' : prop.getPropertyName(), 'property' : prop.getPropertyId()}
                file.write(cdecl)
            else:
                if info.ctypename == 'std::string':
                    file.write(indent + 'ptr->%s = node.child_value();\n' %
                               info.membername)
                    file.write(indent + 'ptr->property_set_.set(%s);\n' % prop.getPropertyId())
                elif info.ctypename == 'bool':
                    file.write(indent + 'ptr->%s = node.text().as_bool();\n' %
                               info.membername)
                    file.write(indent + 'ptr->property_set_.set(%s);\n' % prop.getPropertyId())
                elif info.ctypename == 'uint64_t':
                    fmt = 'if (!autogen::ParseUnsignedLong(node, &ptr->%s)) return false;'
                    file.write(indent + fmt % info.membername)
                    file.write(indent + 'ptr->property_set_.set(%s);\n' % prop.getPropertyId())
                elif info.ctypename == 'int':
                    file.write(indent + 
                               'ptr->%s = atoi(node.child_value());\n' %
                               info.membername)
                    file.write(indent + 'ptr->property_set_.set(%s);\n' % prop.getPropertyId())
                else:
                    file.write(indent + '// TODO: unimplemented\n')
            indent = ' ' * 8
            file.write(indent + '}\n')

        file.write('    }\n    return true;\n}\n')

class IFMapGenProperty(object):
    def __init__(self, meta):
        self._meta = meta

    def GenerateParser(self, DecoderDict, file):
        def getMetaParentName(meta):
            if meta.getParent() == 'all':
                return meta.getCppName() + 'Type'
            return meta.getParent().getCppName()

        meta = self._meta
        fnname = '%s_ParseMetadata' % meta.getCppName()
	decl = """
bool %s(const pugi::xml_node &parent, std::auto_ptr<AutogenProperty > *resultp) {
""" % fnname
	file.write(decl)

	if meta.getCType():
	    file.write('    return autogen::%s::XmlParseProperty(parent, resultp);\n' %
		       meta.getCTypename())
	else:
            indent = ' ' * 4
            info = meta.getMemberInfo()
            cdecl = """
    %(class)s::%(wtype)s *data = new %(class)s::%(wtype)s();
    resultp->reset(data);
""" % {'class': getMetaParentName(meta), 'wtype': SimpleTypeWrapper(info)}
            file.write(cdecl)
            if info.ctypename == 'std::string':
                file.write(indent + 'data->data = parent.child_value();\n')
            elif info.ctypename == 'int':
                file.write(indent +
                           'data->data = atoi(parent.child_value());\n')
            elif info.ctypename == 'bool':
                file.write(indent + 'data->data = parent.text().as_bool();\n');
            file.write(indent + 'return true;\n')

	file.write('}\n')
        DecoderDict[meta.getName()] = fnname

class IFMapGenLink(object):
    def __init__(self, meta):
        self._meta = meta

    def GenerateParser(self, DecoderDict, file):
        fnname = 'ParseLinkMetadata'
        DecoderDict[self._meta.getName()] = fnname

class IFMapGenLinkAttr(object):
    def __init__(self, meta):
        self._meta = meta

    def GenerateParser(self, DecoderDict, file):
        meta = self._meta
        if meta.getCType():
            fnname = '%s::XmlParseProperty' % meta.getCTypename()
        else:
            fnname = '%s::ParseMetadata' % meta.getCppName()

        DecoderDict[self._meta.getName()] = fnname

        if not meta.getCType():
            decl = """
bool %s::ParseMetadata(const pugi::xml_node &parent,
        std::auto_ptr<AutogenProperty> *resultp) {
    %sData *var = new %sData();
    resultp->reset(var);
""" % (meta.getCppName(), meta.getCppName(), meta.getCppName())
            file.write(decl)
            xtypename = meta.getCTypename()
            if xtypename == 'std::string':
                file.write('    var->data = parent.value();\n')
            file.write('    return true;\n')
            file.write('}\n')

    def GenerateEncoder(self, file):
        cdecl =  """
void %(class)s::EncodeUpdate(xml_node *node) const {
""" % {'class': self._meta.getCppName(),
       'element': self._meta._xelement.getName() }
        file.write(cdecl)
        # TODO: Simple type encoding
        if self._meta._xelement.isComplex():
            indent = ' ' * 4
            file.write(indent + 'xml_node data = node->append_child("value");\n');
            file.write(indent + 'data_.Encode(&data);\n')
        file.write('}\n')

    def GenerateDecoder(self, file):
        cdecl = """
bool %(class)s::Decode(const xml_node &parent, std::string *id_name,
                       %(class)s *ptr) {
    for (xml_node node = parent.first_child(); node;
         node = node.next_sibling()) {
        if (strcmp(node.name(), "name") == 0) {
            *id_name = node.child_value();
        }
""" % {'class': self._meta.getCppName() }
        file.write(cdecl)
        # TODO: Simple type decoding
        if self._meta._xelement.isComplex():
            cdecl = """
        if (strcmp(node.name(), "value") == 0) {
            bool success = ptr->data_.XmlParse(node);
            if (!success) {
                return false;
            }
        }
"""
            file.write(cdecl)
        file.write('        }\n    return true;\n}\n')

class IFMapParserGenerator(object):
    def __init__(self, cTypesDict):
        self._cTypesDict = cTypesDict
        self._DecoderDict = { }
        self._TypeParserGenerator = TypeParserGenerator(None)

    def Generate(self, file, hdrname, IdDict, MetaDict):
        header = """
#include "%s"

#include <stdint.h>
#include <sstream>
#include <boost/algorithm/string/trim.hpp>
#include <pugixml/pugixml.hpp>

#include "ifmap/ifmap_agent_parser.h"
#include "ifmap/ifmap_server_parser.h"
#include "ifmap/ifmap_table.h"

using namespace pugi;
using namespace std;

#include "base/compiler.h"
#if defined(__GNUC__) && (__GCC_HAS_PRAGMA > 0)
#pragma GCC diagnostic ignored "-Wunused-function"
#endif

namespace autogen {
static bool ParseInteger(const pugi::xml_node &node, int *valuep) {
    char *endp;
    *valuep = strtoul(node.child_value(), &endp, 10);
    while (isspace(*endp)) endp++;
    return endp[0] == '\\0';
}

static bool ParseUnsignedLong(const pugi::xml_node &node, uint64_t *valuep) {
    char *endp;
    *valuep = strtoull(node.child_value(), &endp, 10);
    while (isspace(*endp)) endp++;
    return endp[0] == '\\0';
}

static bool ParseBoolean(const pugi::xml_node &node, bool *valuep) {
    if (strcmp(node.child_value(), "true") ==0) 
        *valuep = true;
    else
        *valuep = false;
    return true;
}
static bool ParseDateTime(const pugi::xml_node &node, time_t *valuep) {
    string value(node.child_value());
    boost::trim(value);
    struct tm tm;
    memset(&tm, 0, sizeof(tm));
    if (value.size() == 0) return true;
    char *endp;
    endp = strptime(value.c_str(), "%%FT%%T", &tm);
    if (!endp) return false;
    *valuep = timegm(&tm);
    return true;
}
static bool ParseTime(const pugi::xml_node &node, time_t *valuep) {
    string value(node.child_value());
    boost::trim(value);
    struct tm tm;
    char *endp;
    endp = strptime(value.c_str(), "%%T", &tm);
    if (!endp) return false;
    *valuep = timegm(&tm);
    return true;
}
static std::string FormatDateTime(const time_t *valuep) {
    struct tm tm;
    char result[100];
    gmtime_r(valuep, &tm);
    strftime(result, sizeof(result), "%%FT%%T", &tm);
    return std::string(result);
}
static std::string FormatTime(const time_t *valuep) {
    struct tm tm;
    char result[100];
    gmtime_r(valuep, &tm);
    strftime(result, sizeof(result), "%%T", &tm);
    return std::string(result);
}
""" % hdrname
        file.write(header)

        for ctype in self._cTypesDict.values():
            self._TypeParserGenerator.GenerateTypeParser(file, ctype)

        for ident in IdDict.itervalues():
            if not ident._xelement:
                # cross-ref'd id from another file
                continue
            genr = IFMapGenIdentity(ident)
            genr.GenerateEncoder(file)
            genr.GenerateDecoder(file)

        for meta in MetaDict.itervalues():
            genr = None
            if type(meta) is IFMapProperty:
                genr = IFMapGenProperty(meta)
            elif type(meta) is IFMapLink:
                genr = IFMapGenLink(meta)
            elif type(meta) is IFMapLinkAttr:
                genr = IFMapGenLinkAttr(meta)
                genr.GenerateEncoder(file)
                genr.GenerateDecoder(file)


        file.write('}  // namespace autogen\n')


    def GenerateServer(self, file, MetaDict):
        cdecl = """
#include <pugixml/pugixml.hpp>
using namespace pugi;
namespace autogen {
"""
        file.write(cdecl)

        n_links = 0
        for meta in MetaDict.itervalues():
            genr = None
            if type(meta) is IFMapProperty:
                genr = IFMapGenProperty(meta)
            elif type(meta) is IFMapLink:
                genr = IFMapGenLink(meta)
                n_links += 1
            elif type(meta) is IFMapLinkAttr:
                genr = IFMapGenLinkAttr(meta)
            if genr:
                genr.GenerateParser(self._DecoderDict, file)

        parse_link_decl = """
static bool ParseLinkMetadata(const xml_node &parent,
    std::auto_ptr<AutogenProperty> *resultp) {
    return true;
}
"""
        if n_links > 0:
            file.write(parse_link_decl)

        file.write('}  // namespace autogen\n')
        
        module_name = GetModuleName(file, '_server.cc')
        file.write('void %s_ParserInit(IFMapServerParser *xparser) {\n' %
                   module_name)
        indent = ' ' * 4
        for kvp in self._DecoderDict.iteritems():
            fmt = 'xparser->MetadataRegister("%s", &autogen::%s);\n'
            file.write(indent + fmt % kvp)
        file.write('}\n')


    def GenerateAgent(self, file, IdDict, MetaDict):
        cdecl = """
#include <pugixml/pugixml.hpp>
using namespace autogen;
using namespace pugi;
"""
        file.write(cdecl)
        module_name = GetModuleName(file, '_agent.cc')
        for ident in IdDict.itervalues():
            if not ident._xelement:
                # cross-ref'd id from another file
                continue
            cdecl = """
IFMapObject* %(class)sAgentParse(xml_node &node, DB *db, std::string *id_name) {
    
    IFMapAgentTable *table = static_cast<IFMapAgentTable *>
                                            (IFMapTable::FindTable(db, "%(nodename)s"));
    if (!table) {
        return NULL;
    }

    %(class)s *data = static_cast<%(class)s *>(table->AllocObject());
    if (%(class)s::Decode(node, id_name, data) == false) {
        delete data;
        return NULL;
    };

    return data;
}

""" % {'class': ident.getCppName(), 'nodename': ident.getName() } 
      	    file.write (cdecl)

        for ident in MetaDict.itervalues():
            if not type(ident) is IFMapLinkAttr:
                continue
            cdecl = """
IFMapObject* %(class)sAgentParse(xml_node &node, DB *db, std::string *id_name) {
    
    IFMapAgentTable *table = static_cast<IFMapAgentTable *>
                                            (IFMapTable::FindTable(db, "%(nodename)s"));
    if (!table) {
        return NULL;
    }

    %(class)s *data = static_cast<%(class)s *>(table->AllocObject());
    if (%(class)s::Decode(node, id_name, data) == false) {
        return NULL;
    };

    return data;
}

""" % {'class': ident.getCppName(), 'nodename': ident.getName() } 
      	    file.write (cdecl)

        file.write('void %s_Agent_ParserInit(DB *db, IFMapAgentParser *xparser) {\n' %
                module_name)
        indent = ' ' * 4
        for ident in IdDict.itervalues():
            if not ident._xelement:
                # cross-ref'd id from another file
                continue
            file.write(indent)
            fmt = 'xparser->NodeRegister("%s", &%sAgentParse);\n'
            file.write(fmt % (ident.getName(),ident.getCppName()))

        for ident in MetaDict.itervalues():
            if not type(ident) is IFMapLinkAttr:
                continue
            indent = ' ' * 4
            file.write(indent)

            fmt = 'xparser->NodeRegister("%s", &%sAgentParse);\n'
            file.write(fmt % (ident.getName(),ident.getCppName()))
        file.write('}\n')

