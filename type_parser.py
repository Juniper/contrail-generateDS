#
# Copyright (c) 2013 Juniper Networks, Inc. All rights reserved.
#

class TypeParserGenerator(object):
    def __init__(self, cTypeDict):
        self._cTypeDict = cTypeDict
        pass

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
                file.write(indent + 'boost::trim(%s);\n' % member.membername)
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
            boost::trim(var);
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


    def Generate(self, file, hdrname):
        header = """
#include "%s"

#include <stdint.h>
#include <sstream>
#include <boost/algorithm/string/trim.hpp>
#include <pugixml/pugixml.hpp>
#include <time.h>

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
""" % hdrname
        file.write(header)
        for ctype in self._cTypeDict.values():
            self.GenerateTypeParser(file, ctype)
        file.write('}  // namespace autogen\n')
