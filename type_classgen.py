#
# Copyright (c) 2013 Juniper Networks, Inc. All rights reserved.
#
from ifmap_global import GetModuleName

class TypeClassGenerator(object):
    def __init__(self, cTypeDict):
        self._cTypeDict = cTypeDict
        self._generated_types = { }

    def _GenerateTypeSub(self, file, ctype):
        depend_types = ctype.getDependentTypes()
        for child in depend_types:
            if not child.getName() in self._generated_types:
                self._generated_types[child.getName()] = child
                self._GenerateTypeSub(file, child)

        file.write('\nstruct %s : public AutogenProperty {\n' % ctype.getName())

        file.write('    %s();\n' % ctype.getName())
        file.write('    virtual ~%s();\n' % ctype.getName())

        members = ctype.getDataMembers()
        if len(members) == 1 and members[0].isSequence:
            member = members[0]
            cdecl = """
    typedef %(vectype)s::const_iterator const_iterator;
    const_iterator begin() const { return %(membername)s.begin(); }
    const_iterator end() const { return %(membername)s.end(); }
    %(vectype)s::size_type size() const { return %(membername)s.size(); }
    bool empty() const { return %(membername)s.empty(); }
"""  % {'vectype': member.ctypename, 'membername': member.membername}
            file.write(cdecl)
        
        for member in ctype.getDataMembers():
            file.write('    %s %s;\n' % (member.ctypename, member.membername))
        tail = """
    void Clear();
    void Copy(const %s &rhs);
    bool XmlParse(const pugi::xml_node &node);
    static bool XmlParseProperty(const pugi::xml_node &node,
                                 std::auto_ptr<AutogenProperty> *resultp);
    void Encode(pugi::xml_node *node) const;
    void CalculateCrc(boost::crc_32_type *crc) const;
    bool JsonParse(const contrail_rapidjson::Value &node);
    static bool JsonParseProperty(const contrail_rapidjson::Value &node,
                                  std::auto_ptr<AutogenProperty> *resultp);
};
""" % (ctype.getName())
        file.write(tail)

    def GenerateType(self, file, ctype):
        if not ctype.getName() in self._generated_types:
            self._generated_types[ctype.getName()] = ctype
            self._GenerateTypeSub(file, ctype)

    def Generate(self, file, ctype):
        module_name = GetModuleName(file, '_types.h')
        header = """
// autogenerated file --- DO NOT EDIT ---
#ifndef __SCHEMA__%(modname)s_TYPES_H__
#define __SCHEMA__%(modname)s_TYPES_H__
#include <iostream>
#include <string.h>
#include <vector>

#include <boost/dynamic_bitset.hpp>
#include <boost/crc.hpp>      // for boost::crc_32_type
namespace pugi {
class xml_node;
class xml_document;
}  // namespace pugi

#include "rapidjson/document.h"

#include "ifmap/autogen.h"

namespace autogen {

""" % {'modname': module_name.upper()}
        file.write(header)
        self.GenerateType(file, ctype)
        file.write('}  // namespace autogen\n')
        file.write('#endif  // __SCHEMA__%s_TYPES_H__\n' %
                   module_name.upper())
        pass

class TypeImplGenerator(object):
    def __init__(self, cTypeDict):
        self._cTypeDict = cTypeDict
        pass

    def GenerateType(self, file, ctype):
        construct = """
%(class)s::%(class)s() {
    Clear();
}
""" % {'class': ctype.getName()}

        file.write(construct)

        destruct = """
%(class)s::~%(class)s() {
}
""" % {'class': ctype.getName()}
        file.write(destruct)

        cleardef = """
void %s::Clear() {
""" % ctype.getName()
        file.write(cleardef)
        for member in ctype.getDataMembers():
            cpptype = member.ctypename
            if (cpptype == 'int' or
                cpptype == 'uint64_t' or
                cpptype == 'time_t'):
                file.write('    %s = %s;\n' % (member.membername, member.default or '0'))
            elif cpptype == 'bool':
                file.write('    %s = %s;\n' % (member.membername, member.default or 'false'))
            elif member.isComplex and not member.isSequence:
                file.write('    %s.Clear();\n' % member.membername)
            elif member.default:
                file.write('    %s = "%s";\n' % (member.membername, member.default))
            else:
                file.write('    %s.clear();\n' % member.membername)
        file.write('};\n')

        copydef = """
void %s::Copy(const %s &rhs) {
""" % (ctype.getName(), ctype.getName())
        file.write(copydef)
        for member in ctype.getDataMembers():
            cpptype = member.ctypename
            if member.isComplex and not member.isSequence:
                fmt = '    %s.Copy(rhs.%s);\n'
            else:
                fmt = '    %s = rhs.%s;\n'
            file.write(fmt % (member.membername, member.membername))

        file.write('};\n')

        crcdef = """
void %s::CalculateCrc(boost::crc_32_type *crc) const {
""" % ctype.getName()
        file.write(crcdef)
        indent_l1 = ' ' * 4
        indent_l11 = ' ' * 9
        indent_l2 = ' ' * 8
        for member in ctype.getDataMembers():
            cpptype = member.ctypename
            if member.isSequence:
                file.write(indent_l1 + 'for (%s::const_iterator iter = \n' %(cpptype))
                file.write(indent_l11 + '%s.begin();\n' %(member.membername))
                file.write(indent_l11 + 'iter != %s.end(); ++iter) {\n'
                           %(member.membername))

                # code inside the for loop
                sequencetype = member.sequenceType
                if sequencetype == 'std::string':
                    file.write(indent_l2 + 'const std::string &str = *iter;\n');
                    file.write(indent_l2 +
                               'crc->process_bytes(str.c_str(), str.size());\n')
                elif (sequencetype == 'int' or sequencetype == 'uint64_t' or
                      sequencetype == 'bool'):
                    file.write(indent_l2 + 'const %s *obj = iter.operator->();\n'
                               % member.sequenceType)
                    file.write(indent_l2 +
                               'crc->process_bytes(obj, sizeof(*obj));\n')
                elif member.isComplex:
                    file.write(indent_l2 + 'const %s *obj = iter.operator->();\n'
                               % member.sequenceType)
                    file.write(indent_l2 + 'obj->CalculateCrc(crc);\n')
                else:
                    assert()

                file.write(indent_l1 + '}\n')
            elif member.isComplex: # complex but not sequence
                file.write(indent_l1 +
                           '%s.CalculateCrc(crc);\n' % member.membername)
            elif (cpptype == 'int' or cpptype == 'uint64_t' or
                  cpptype == 'time_t' or cpptype == 'bool'):
                file.write(indent_l1 + 'crc->process_bytes(&%s, sizeof(%s));\n'
                           %(member.membername, member.membername));
            elif (cpptype == 'std::string'):
                file.write(indent_l1 + 
                           'crc->process_bytes(%s.c_str(), %s.size());\n'
                           %(member.membername, member.membername));
            else:
                assert()

        file.write('};\n')

    def Generate(self, hdrname, file):
        module_name = GetModuleName(file, '_types.h')
        header = """
// autogenerated file --- DO NOT EDIT ---
#ifndef __SCHEMA__%(modname)s_TYPES_H__
#define __SCHEMA__%(modname)s_TYPES_H__
#include "%(hdrname)s"

#include <boost/bind.hpp>
#include "ifmap/autogen.h"

#include <pugixml/pugixml.hpp>

using namespace std;

namespace autogen {
""" % {'modname': module_name.upper(), 'hdrname': hdrname }
        file.write(header)

        for ctype in self._cTypeDict.values():
            self.GenerateType(file, ctype)
        file.write('}\n')
        file.write('#endif  // __SCHEMA__%s_TYPES_H__\n' %
                   module_name.upper())
