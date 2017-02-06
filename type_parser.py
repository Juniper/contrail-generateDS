#
# Copyright (c) 2013 Juniper Networks, Inc. All rights reserved.
#

class TypeParserGenerator(object):
    def __init__(self, cTypeDict):
        self._cTypeDict = cTypeDict
        pass

    def GenerateJsonTypeParser(self, file, ctype):
        print "generating parser for %s" %ctype.getName()
        start = """
bool %s::JsonParse(const rapidjson::Value &parent) {
    for (Value::ConstMemberIterator itr = parent.MemberBegin();
         itr != parent.MemberEnd(); ++itr) {
""" % ctype.getName()
        file.write(start)
        if len(ctype.getDataMembers()) > 0:
            file.write(
                '        const rapidjson::Value &value_node = itr->value;\n')
            file.write('        if (value_node.IsNull()) continue;\n')
            file.write('        std::string var;\n')
            file.write('        if (!autogen::ParseString(itr->name, &var)) return false;\n')
        for member in ctype.getDataMembers():
            object_name = member.xsd_object.getName()
            object_name = object_name.replace('-', '_')
            file.write('        if (strcmp(var.c_str(), "%s") == 0) {\n' % object_name)
            indent = ' ' * 12
            cpptype = member.ctypename
            if cpptype == 'int':
                fmt = 'if (!ParseInteger(value_node, &%s)) return false;\n'
                file.write(indent + fmt % member.membername)
            elif cpptype == 'uint64_t':
                fmt = 'if (!ParseUnsignedLong(value_node, &%s)) return false;\n'
                file.write(indent + fmt % member.membername)
            elif cpptype == 'bool':
                fmt = 'if (!ParseBoolean(value_node, &%s)) return false;\n'
                file.write(indent + fmt % member.membername)
            elif cpptype == 'std::string':
                file.write(indent + 'std::string var;\n')
                file.write(indent +
                           'if (!autogen::ParseString(value_node, &var)) return false;\n')
                fmt = '%s = var.c_str();\n'
                file.write(indent + fmt % member.membername)
            elif cpptype == 'time_t':
                if member.xsd_object.getType() == 'xsd:dateTime':
                    fmt = 'if (!ParseDateTime(value_node, &%s)) return false;\n'
                    file.write(indent + fmt % member.membername)
                elif member.xsd_object.getType() == 'xsd:time':
                    fmt = 'if (!ParseTime(value_node, &%s)) return false;\n'
                    file.write(indent + fmt % member.membername)
            elif member.isSequence:
                indent1 = ' ' * 16
                file.write(indent +
                           'if (!value_node.IsArray()) return false;\n')
                file.write(indent +
                    'for (size_t i = 0; i < value_node.Size(); ++i) {\n')
                if member.isComplex:
                    file.write(indent1 + '%s var;\n' % member.sequenceType)
                    file.write(indent1 + 'var.Clear();\n')
                    file.write(indent1 +
                        'if (!var.JsonParse(value_node[i])) return false;\n')
                    file.write(indent1 + '%s.push_back(var);\n' %
                                member.membername)
                elif member.sequenceType == 'std::string':
                    file.write(indent1 + 'std::string var;\n')
                    file.write(indent1 +
                               'if (!autogen::ParseString(value_node[i], &var)) return false;\n')
                    file.write(indent1 + '%s.push_back(var);\n' %
                               member.membername)
                elif member.sequenceType == 'int':
                    file.write(indent1 +
                               'if (!value_node[i].IsInt()) return false;\n')
                    file.write(indent1 + 'int var;\n')
                    file.write(indent1 +
                      'if (!ParseInteger(value_node[i], &var)) return false;\n')
                    file.write(indent1 + '%s.push_back(var);\n' %
                               member.membername)
                else:
                    file.write(indent + '// TODO: sequence of ' +
                               member.sequenceType)
                file.write(indent + '}\n') # end of for loop
            elif member.isComplex:
                fmt = 'if (!%s.JsonParse(value_node)) return false;\n'
                file.write(indent + fmt % member.membername)
            file.write('        }\n')
        file.write('    }\n    return true;\n}\n')

        static_fn = """
bool %s::JsonParseProperty(const rapidjson::Value &parent,
        auto_ptr<AutogenProperty> *resultp) {
    %s *ptr = new %s();
    resultp->reset(ptr);
    if (!ptr->JsonParse(parent)) {
        return false;
    }
    return true;
}
""" % (ctype.getName(), ctype.getName(), ctype.getName())
        file.write(static_fn)

    def GenerateTypeParser(self, file, ctype):
        print "generating parser for %s" %ctype.getName()
        start = """
bool %s::XmlParse(const xml_node &parent) {
    for (xml_node node = parent.first_child(); node;
         node = node.next_sibling()) {
""" % ctype.getName()
        file.write(start)
        for member in ctype.getDataMembers():
            file.write('        if (strcmp(node.name(), "%s") == 0) {\n' %
                       member.xsd_object.getName())
            indent = ' ' * 12
            cpptype = member.ctypename
            if cpptype == 'int':
                fmt = 'if (!ParseInteger(node, &%s)) return false;\n'
                file.write(indent + fmt % member.membername)
            elif cpptype == 'uint64_t':
                fmt = 'if (!ParseUnsignedLong(node, &%s)) return false;\n'
                file.write(indent + fmt % member.membername)
            elif cpptype == 'bool':
                fmt = 'if (!ParseBoolean(node, &%s)) return false;\n'
                file.write(indent + fmt % member.membername)
            elif cpptype == 'std::string':
                fmt = '%s = node.child_value();\n'
                file.write(indent + fmt % member.membername)
            elif cpptype == 'time_t':
                if member.xsd_object.getType() == 'xsd:dateTime':
                    fmt = 'if (!ParseDateTime(node, &%s)) return false;\n'
                    file.write(indent + fmt % member.membername)
                elif member.xsd_object.getType() == 'xsd:time':
                    fmt = 'if (!ParseTime(node, &%s)) return false;\n'
                    file.write(indent + fmt % member.membername)
            elif member.isSequence:
                if member.isComplex:
                    item = """
            %s var;
            var.Clear();
            if (!var.XmlParse(node)) return false;
            %s.push_back(var);
""" % (member.sequenceType, member.membername)
                    file.write(item)
                elif member.sequenceType == 'std::string':
                    item = """
            string var(node.child_value());
            %s.push_back(var);
""" % member.membername
                    file.write(item)
                elif member.sequenceType == 'int':
                    item = """
            int var;
            if (!ParseInteger(node, &var)) return false;
            %s.push_back(var);
""" % member.membername
                    file.write(item)
                else:
                    file.write(' ' * 12 + '// TODO: sequence of '
                               + member.sequenceType)
            elif member.isComplex:
                fmt = 'if (!%s.XmlParse(node)) return false;\n'
                file.write(indent + fmt % member.membername)
            file.write('        }\n')
        file.write('    }\n    return true;\n}\n')

        static_fn = """
bool %s::XmlParseProperty(const xml_node &parent,
        auto_ptr<AutogenProperty> *resultp) {
    %s *ptr = new %s();
    resultp->reset(ptr);
    if (!ptr->XmlParse(parent)) {
        return false;
    }
    return true;
}
""" % (ctype.getName(), ctype.getName(), ctype.getName())
        file.write(static_fn)

        export = """
void %s::Encode(xml_node *node_p) const {
    pugi::xml_node node_c;

""" % (ctype.getName())
        file.write(export)

        for member in ctype.getDataMembers():
            indent = ' ' * 4
            cpptype = member.ctypename
            if cpptype == 'int':
                file.write(indent + "// Add child node \n");
                fmt = 'node_c = node_p->append_child("%s");\n'
                file.write(indent + fmt % member.elementname)
                fmt = 'node_c.text().set(%s::%s);\n\n'
                file.write(indent + fmt % (ctype.getName(),member.membername))
            if cpptype == 'uint64_t':
                cdecl = """
    node_c = node_p->append_child("%(elementname)s");
    {
        ostringstream oss;
        oss << %(membername)s;
        node_c.text().set(oss.str().c_str());
    }
""" % {'elementname': member.xsd_object.getName(), 'membername': member.membername}
                file.write(cdecl)
            elif cpptype == 'bool':
                file.write(indent + "// Add child node \n");
                fmt = 'node_c = node_p->append_child("%s");\n'
                file.write(indent + fmt % member.elementname)
                fmt = 'node_c.text().set(%s::%s);\n\n'
                file.write(indent + fmt % (ctype.getName(),member.membername))
            elif cpptype == 'std::string':
                file.write(indent + "// Add child node \n");
                fmt = 'node_c = node_p->append_child("%s");\n'
                file.write(indent + fmt % member.elementname)
                fmt = 'node_c.text().set(%s::%s.c_str());\n\n'
                file.write(indent + fmt % (ctype.getName(),member.membername))
            elif cpptype == 'time_t':
                file.write(indent + "// Add child node \n");
                fmt = 'node_c = node_p->append_child("%s");\n'
                file.write(indent + fmt % member.elementname)
                if member.xsd_object.getType() == 'xsd:dateTime':
                    fmt = 'node_c.text().set(FormatDateTime(&%s).c_str());\n\n'
                elif member.xsd_object.getType() == 'xsd:time':
                    fmt = 'node_c.text().set(FormatTime(&%s).c_str());\n\n'
                file.write(indent + fmt % (member.membername))
            elif member.isSequence and member.isComplex:
                item = """
    for (%(type)s::const_iterator iter = %(membername)s.begin();
         iter != %(membername)s.end(); ++iter) {
        node_c = node_p->append_child("%(elementname)s");
        iter->Encode(&node_c);
    }
""" % {'type': cpptype,
       'membername': member.membername,
        'elementname': member.elementname }
                file.write(item)
            elif member.isSequence and member.sequenceType == 'std::string':
                item = """
    for (%(type)s::const_iterator iter = %(membername)s.begin();
         iter != %(membername)s.end(); ++iter) {
        node_c = node_p->append_child("%(elementname)s");
        std::string str = *iter;
        node_c.text().set(str.c_str());
    }
""" % {'type': cpptype,
       'membername': member.membername,
        'elementname': member.elementname }
                file.write(item)
            elif member.isSequence:
                item = """
    for (%(type)s::const_iterator iter = %(membername)s.begin();
         iter != %(membername)s.end(); ++iter) {
        node_c = node_p->append_child("%(elementname)s");
        node_c.text().set(*iter);
    }
""" % {'type': cpptype,
       'membername': member.membername,
        'elementname': member.elementname }
                file.write(item)
            elif member.isSequence:
                item = """
    for (%(type)s::const_iterator iter = %(membername)s.begin();
         iter != %(membername)s.end(); ++iter) {
        node_c = node_p->append_child("%(elementname)s");
        node_c.text().set(*iter);
    }
""" % {'type': cpptype,
       'membername': member.membername,
        'elementname': member.elementname }
                file.write(item)
            elif member.isComplex:
                file.write(indent + "// Add complex node \n");
                fmt = 'node_c = node_p->append_child("%s");\n'
                file.write(indent + fmt % member.elementname)
                fmt = '%s.Encode(&node_c); \n'
                file.write(indent + fmt % (member.membername))
        file.write('}\n')

    def GenerateAttributeParser(self, file, ctype):
        print "generating parser for attribute %s" %ctype.getName()
        start = """
bool %s::XmlParse(const xml_node &parent) {
    for (xml_attribute attr = parent.first_attribute(); attr;
         attr = attr.next_attribute()) {
""" % ctype.getName()
        file.write(start)
        for member in ctype.getDataMembers():
            file.write('        if (strcmp(attr.name(), "%s") == 0) {\n' %
                       member.xsd_object.getName())
            indent = ' ' * 12
            cpptype = member.ctypename
            if cpptype == 'int':
                fmt = 'if (!ParseInteger(attr, &%s)) return false;\n'
                file.write(indent + fmt % member.membername)
            elif cpptype == 'uint64_t':
                fmt = 'if (!ParseUnsignedLong(attr, &%s)) return false;\n'
                file.write(indent + fmt % member.membername)
            elif cpptype == 'bool':
                fmt = 'if (!ParseBoolean(attr, &%s)) return false;\n'
                file.write(indent + fmt % member.membername)
            elif cpptype == 'std::string':
                fmt = '%s = attr.value();\n'
                file.write(indent + fmt % member.membername)
            file.write('        }\n')
        file.write('    }\n    return true;\n}\n')

        static_fn = """
bool %s::XmlParseProperty(const xml_node &parent,
        auto_ptr<AutogenProperty> *resultp) {
    %s *ptr = new %s();
    resultp->reset(ptr);
    if (!ptr->XmlParse(parent)) {
        return false;
    }
    return true;
}
""" % (ctype.getName(), ctype.getName(), ctype.getName())
        file.write(static_fn)

        export = """
void %s::Encode(xml_node *node_p) const {
    pugi::xml_attribute attr;

""" % (ctype.getName())
        file.write(export)

        for member in ctype.getDataMembers():
            indent = ' ' * 4
            cpptype = member.ctypename
            if cpptype == 'int':
                file.write(indent + "// Add child node \n");
                fmt = 'attr = node_p->append_attribute("%s");\n'
                file.write(indent + fmt % member.elementname)
                fmt = 'attr.set_value(%s::%s);\n\n'
                file.write(indent + fmt % (ctype.getName(),member.membername))
            if cpptype == 'uint64_t':
                cdecl = """
    attr = node_p->append_attribute("%(elementname)s");
    {
        ostringstream oss;
        oss << %(membername)s;
        attr.set_value(oss.str().c_str());
    }
""" % {'elementname': member.xsd_object.getName(), 'membername': member.membername}
                file.write(cdecl)
            elif cpptype == 'bool':
                file.write(indent + "// Add child node \n");
                fmt = 'attr = node_p->append_attribute("%s");\n'
                file.write(indent + fmt % member.elementname)
                fmt = 'attr.set_value(%s::%s);\n\n'
                file.write(indent + fmt % (ctype.getName(),member.membername))
            elif cpptype == 'std::string':
                file.write(indent + "// Add child node \n");
                fmt = 'attr = node_p->append_attribute("%s");\n'
                file.write(indent + fmt % member.elementname)
                fmt = 'attr.set_value(%s::%s.c_str());\n\n'
                file.write(indent + fmt % (ctype.getName(),member.membername))
        file.write('}\n')

    def GenerateJsonAttributeParser(self, file, ctype):
        print "generating json parser for attribute %s" %ctype.getName()
        function_def = """
bool %s::JsonParse(const rapidjson::Value &parent) {
    return true;
}
""" % ctype.getName()
        file.write(function_def)

        static_fn = """
bool %s::JsonParseProperty(const rapidjson::Value &parent,
        auto_ptr<AutogenProperty> *resultp) {
    return true;
}
""" % ctype.getName()
        file.write(static_fn)

    def Generate(self, file, hdrname):
        header = """
#include "%s"

#include <stdint.h>
#include <sstream>
#include <boost/algorithm/string/trim.hpp>
#include <pugixml/pugixml.hpp>
#include "rapidjson/rapidjson.h"
#include "rapidjson/document.h"
#include <time.h>

using namespace rapidjson;
using namespace pugi;
using namespace std;

#include "base/compiler.h"
#if defined(__GNUC__) && (__GCC_HAS_PRAGMA > 0)
#pragma GCC diagnostic ignored "-Wunused-function"
#endif

namespace autogen {

// Json Parse routines

static inline bool ParseString(const rapidjson::Value &node, std::string *s) {
    if (node.IsString()) {
        *s = node.GetString();
        return true;
    }

    std::stringstream ss;
    switch (node.GetType()) {
    case rapidjson::kNullType:
        *s = "null";
        break;
    case rapidjson::kTrueType:
        *s = "true";
        break;
    case rapidjson::kFalseType:
        *s = "false";
        break;
    case rapidjson::kStringType:
        *s = node.GetString();
        break;
    case rapidjson::kNumberType:
        if (node.IsUint())
            ss << node.GetUint();
        else if (node.IsInt())
            ss << node.GetInt();
        else if (node.IsUint64())
            ss << node.GetUint64();
        else if (node.IsInt64())
            ss << node.GetInt64();
        else if (node.IsDouble())
            ss << node.GetDouble();
        *s = ss.str();
        break;
    case rapidjson::kObjectType:
        return false;
    case rapidjson::kArrayType:
        return false;
    }
    return true;
}

static bool ParseInteger(const char *nptr, int *valuep) {
    char *endp;
    *valuep = strtoul(nptr, &endp, 10);
    while (isspace(*endp))
        endp++;
    return (endp[0] == '\\0');
}

static bool ParseUnsignedLong(const char *nptr, uint64_t *valuep) {
    char *endp;
    *valuep = strtoull(nptr, &endp, 10);
    while (isspace(*endp))
        endp++;
    return (endp[0] == '\\0');
}

static bool ParseBoolean(const char *bptr, bool *valuep) {
    if (strcmp(bptr, "true") ==0)
        *valuep = true;
    else
        *valuep = false;
    return true;
}

static bool ParseInteger(const pugi::xml_attribute &attr, int *valuep) {
    return ParseInteger(attr.value(), valuep);
}

static bool ParseUnsignedLong(const pugi::xml_attribute &attr,
                              uint64_t *valuep) {
    return ParseUnsignedLong(attr.value(), valuep);
}

static bool ParseBoolean(const pugi::xml_attribute &attr, bool *valuep) {
    return ParseBoolean(attr.value(), valuep);
}

static bool ParseInteger(const pugi::xml_node &node, int *valuep) {
    return ParseInteger(node.child_value(), valuep);
}

static bool ParseUnsignedLong(const pugi::xml_node &node, uint64_t *valuep) {
    return ParseUnsignedLong(node.child_value(), valuep);
}

static bool ParseBoolean(const pugi::xml_node &node, bool *valuep) {
    return ParseBoolean(node.child_value(), valuep);
}

static bool ParseDateTime(const pugi::xml_node &node, time_t *valuep) {
    string value(node.child_value());
    boost::trim(value);
    struct tm tm;
    char *endp;
    memset(&tm, 0, sizeof(tm));
    if (value.size() == 0) return true;
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

// Json Parse routines
static bool ParseInteger(const rapidjson::Value &node, int *valuep) {
    if (node.IsString())
        return ParseInteger(node.GetString(), valuep);
    if (!node.IsInt())
        return false;
    *valuep = node.GetInt();
    return true;
}

static bool ParseUnsignedLong(const rapidjson::Value &node, uint64_t *valuep) {
    if (node.IsString())
        return ParseUnsignedLong(node.GetString(), valuep);
    if (!node.IsUint64())
        return false;
    *valuep = node.GetUint64();
    return true;
}

static bool ParseBoolean(const rapidjson::Value &node, bool *valuep) {
    if (node.IsString())
        return ParseBoolean(node.GetString(), valuep);
    if (!node.IsBool())
        return false;
    *valuep = node.GetBool();
    return true;
}

static bool ParseDateTime(const rapidjson::Value &node, time_t *valuep) {
    if (!node.IsString())
        return false;
    string value(node.GetString());
    boost::trim(value);
    struct tm tm;
    char *endp;
    memset(&tm, 0, sizeof(tm));
    if (value.size() == 0) return true;
    endp = strptime(value.c_str(), "%%FT%%T", &tm);
    if (!endp) return false;
    *valuep = timegm(&tm);
    return true;
}

static bool ParseTime(const rapidjson::Value &node, time_t *valuep) {
    if (!node.IsString())
        return false;
    string value(node.GetString());
    boost::trim(value);
    struct tm tm;
    char *endp;
    endp = strptime(value.c_str(), "%%T", &tm);
    if (!endp) return false;
    *valuep = timegm(&tm);
    return true;
}

""" % hdrname
        file.write(header)
        for ctype in self._cTypeDict.values():
            if ctype._is_attribute:
                self.GenerateAttributeParser(file, ctype)
                self.GenerateJsonAttributeParser(file, ctype)
            else:
                self.GenerateTypeParser(file, ctype)
                self.GenerateJsonTypeParser(file, ctype)
        file.write('}  // namespace autogen\n')
