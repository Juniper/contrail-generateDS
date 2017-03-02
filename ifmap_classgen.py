#
# Copyright (c) 2013 Juniper Networks, Inc. All rights reserved.
#

"""
Generate the class definition corresponding to a given IFMap DB object.
"""

from type_classgen import TypeClassGenerator, TypeImplGenerator
from ifmap_global import CppTypeMap, GetModuleName
from ifmap_model import IFMapIdentifier, IFMapProperty, IFMapLink, IFMapLinkAttr, MemberInfo, SimpleTypeWrapper

class IFMapGenBase(object):
    def __init__(self):
        pass

    def getName(self):
        pass

    def getElementName(self):
        pass


    def TableClassDefn(self, file, component):
        cdecl = """
class DBTable_%(impl)s_%(class)s : public IFMap%(impl)sTable {
  public:
    DBTable_%(impl)s_%(class)s(DB *db, const std::string &name, DBGraph *graph);

    IFMapObject *AllocObject();
    virtual const char *Typename() const;
    static DBTable *CreateTable(DB *db, const std::string &name, DBGraph *graph);

  private:
    DISALLOW_COPY_AND_ASSIGN(DBTable_%(impl)s_%(class)s);
};
""" % {'impl':component, 'class':self.getName()}
        file.write(cdecl)

    def TableClassImpl(self, file, impl):
        cdecl = """
DBTable_%(impl)s_%(class)s::DBTable_%(impl)s_%(class)s(DB *db, const std::string &name, DBGraph *graph)
        : IFMap%(impl)sTable(db, name, graph) {
}

const char *DBTable_%(impl)s_%(class)s::Typename() const {
    return "%(elementname)s";
}

IFMapObject *DBTable_%(impl)s_%(class)s::AllocObject() {
    return new %(class)s();
}

DBTable *DBTable_%(impl)s_%(class)s::CreateTable(DB *db, const string &name, DBGraph *graph) {
    DBTable *tbl = new DBTable_%(impl)s_%(class)s(db, name, graph);
    tbl->Init();
    return tbl;
}
""" % {'impl': impl, 'class': self.getName(),
        'elementname': self.getElementName()}
        file.write(cdecl)

class IFMapGenIdentifier(IFMapGenBase):
    def __init__(self, TypeDict, identifier):
        self._TypeDict = TypeDict
        self._identifier = identifier

    def getName(self):
        return self._identifier.getCppName()

    def getElementName(self):
        return self._identifier.getName()

    def ServerClassDefn(self, file):
        header = """
class %s : public IFMapIdentifier {
public:
""" % self.getName()
        file.write(header)
        self._GenTypedefs(file)
        public_methods = """
    %(class)s();
    virtual std::string ToString() const;
    virtual void EncodeUpdate(pugi::xml_node *parent) const;
    static bool Decode(const pugi::xml_node &parent, std::string *id_name,
                       %(class)s *ptr);
    virtual boost::crc_32_type::value_type CalculateCrc() const;
""" % {'class': self.getName() }
        file.write(public_methods)

        property_methods = """
    virtual bool SetProperty(const std::string &property, AutogenProperty *data);
    virtual void ClearProperty(const std::string &property);
"""
        file.write(property_methods)

        property_tests = """
    bool IsPropertySet(PropertyId property) const {
        return property_set_.test(property);
    }
    virtual bool empty() const;
"""
        if len(self._identifier.getProperties()) > 0:
            file.write(property_tests)

        # accessors
        for prop in self._identifier.getProperties():
            info = prop.getMemberInfo()
            file.write('    const %s &%s() const { return %s; }\n'
                       % (info.ctypename, prop.getPropertyName(),
                          info.membername))

        file.write('\nprivate:\n')
        self._GenServerAttributes(file)
        footer = """
    DISALLOW_COPY_AND_ASSIGN(%s);
};
""" % (self.getName())
        file.write(footer)

    def _GenTypedefs(self, file):
        gen_types = {}
        for ctype in self._identifier.getDataTypes():
            if ctype in gen_types:
                continue
            file.write('    typedef autogen::%s %s;\n' % (ctype, ctype))
            gen_types[ctype] = ctype

        properties = self._identifier.getProperties()
        for prop in properties:
            info = prop.getMemberInfo()
            assert info
            if not info.isComplex:
                if info.ctypename in gen_types:
                    continue
                cdecl = """
    struct %(typename)s : public AutogenProperty {
        %(ctype)s data;
    };
""" % {'typename': SimpleTypeWrapper(info), 'ctype': info.ctypename}
                file.write(cdecl)
                gen_types[info.ctypename] = info.ctypename

        if len(properties) > 0:
            file.write('    enum PropertyId {\n')
        for prop in properties:
            file.write('        %s,\n' % prop.getPropertyId())
        if len(properties) > 0:
            file.write('        PROPERTY_ID_COUNT\n    };\n')

    def _GenServerPrimaryKey(self, file):
        """ Generate the data members that define the object primary key
            Identifier _key_members contains (string, name) which is already
            present in IFMapIdentifier.
        """
        pass

    def _GenServerAttributes(self, file):
        """ Generate the data members that define the object properties
        """
        for member in self._identifier.getDataMembers():
            file.write('    %s %s;\n' % (member.ctypename, member.membername))

    def ServerClassImpl(self, file):
        self._GenConstructor(file)
        self._GenSetProperty(file)
        self._GenClearProperty(file)
        self._GenToString(file)
        self._GenEmpty(file);
        self._GenProcessPropertyDiff(file)

    def _GenConstructor(self, file):
        file.write('%s::%s() ' %
                (self.getName(), self.getName()))
        if len(self._identifier.getProperties()) > 0:
            file.write(': IFMapIdentifier(PROPERTY_ID_COUNT) ')

        file.write('{\n')
        # TODO: key members
        for member in self._identifier.getDataMembers():
            if not member.isComplex:
                if member.ctypename == 'std::string':
                    file.write('    %s.clear();\n' % member.membername)
                elif member.ctypename == 'bool':
                    file.write('    %s = false;\n' % member.membername)
                else:
                    file.write('    %s = 0;\n' % member.membername)
            elif member.isSequence:
                file.write('    %s.clear();\n' % member.membername)
            else:
                file.write('    %s.Clear();\n' % member.membername)

        file.write('}\n')          

    def _GenSetProperty(self, file):
        header = """
bool %s::SetProperty(const string &property, AutogenProperty *data) {
""" % self.getName()
        file.write(header)
        test_else = ''
        for prop in self._identifier.getProperties():
            membername = prop.getPropertyName() + '_'
            file.write('    %sif (property == "%s") {\n' %
                       (test_else, prop.getName()))
            test_else = 'else '
            # TODO: compare with previous value and return false if unchanged
            info = prop.getMemberInfo()
            assert info
            indent = ' ' * 8
            if info.isSequence:
                file.write(indent +
                           'autogen::%(type)s *v = static_cast<autogen::%(type)s *>(data);\n' %
                           {'type': prop._xelement.getType()})
                cinfo = self._TypeDict[prop._xelement.getType()]
                file.write(indent + '%s.swap(v->%s);\n' %
                           (membername, cinfo._data_members[0].membername))
            elif info.isComplex:
                file.write(indent + '%s.Copy(*static_cast<const %s *>(data));\n' % (membername, info.ctypename))
            else:
                file.write(indent +
                           '%s = static_cast<const %s *>(data)->data;\n' %
                           (membername, SimpleTypeWrapper(info)))

            cdecl = """
        property_set_.set(%s);
    }
""" % prop.getPropertyId()
            file.write(cdecl)

        retval = """
    if (property_set_.is_subset_of(old_property_set_)) {
        return false;
    } else {
        return true;
    }
}
"""
        file.write(retval)

    def _GenClearProperty(self, file):
        cdecl = """
void %s::ClearProperty(const string &property) {
""" % self.getName()
        file.write(cdecl)
        elsestmt = ''
        for prop in self._identifier.getProperties():
            cdecl = """
    %sif (property == "%s") {
        property_set_.reset(%s);
    }
""" % (elsestmt, prop.getName(), prop.getPropertyId())
            file.write(cdecl)
            elsestmt = 'else '

        file.write('}\n')

    def _GenToString(self, file):
        """ Generate the method ToString.
        """
        fn = """
string %(typename)s::ToString() const {
    string repr;
    return repr;
}
""" % {'typename': self.getName(), 'elementname' : self.getElementName() }
        file.write(fn)

    def _GenEmpty(self, file):
        if len(self._identifier.getProperties()) > 0:
            cdecl = """
bool %s::empty() const {
    return property_set_.none();
}
""" % self.getName()            
            file.write(cdecl)

    def _GenProcessPropertyDiff(self, file):
        if len(self._identifier.getProperties()) > 0:
            header = """
boost::crc_32_type::value_type %s::CalculateCrc() const {
""" % self.getName()
            file.write(header)

            indent_l0 = ' ' * 4
            indent_l1 = ' ' * 8
            indent_l11 = ' ' * 13
            indent_l2 = ' ' * 12
            file.write(indent_l0 + 'boost::crc_32_type crc;\n')
            for prop in self._identifier.getProperties():
                membername = prop.getPropertyName() + '_'
                info = prop.getMemberInfo()
                assert info
                file.write(indent_l0 + 
                           'if (IsPropertySet(%s)) {\n' % prop.getPropertyId())
                if info.isSequence:
                    file.write(indent_l1 + 'for (%s::const_iterator iter = \n'
                               %(info.ctypename))
                    file.write(indent_l11 + '%s.begin();\n' %(membername))
                    file.write(indent_l11 + 'iter != %s.end(); ++iter) {\n' 
                               %(membername))

                    # code inside the for loop
                    sequencetype = info.sequenceType
                    if sequencetype == 'int':
                        file.write(indent_l2 +
                             'const %s *obj = static_cast<const %s *>(iter.operator->());\n'
                             %(sequencetype, sequencetype))
                        file.write(indent_l2 +
                                   'crc.process_bytes(obj, sizeof(*obj));\n')
                    elif sequencetype == 'std::string':
                        file.write(indent_l2 + 'const std::string &str = *iter;\n');
                        file.write(indent_l2 +
                            'crc.process_bytes(str.c_str(), str.size());\n')
                    elif info.isComplex:
                        # vector of non-basic type
                        file.write(indent_l2 +
                            'const %s *obj = iter.operator->();\n' %sequencetype)
                        file.write(indent_l2 + 'obj->CalculateCrc(&crc);\n')
                    else:
                        assert()

                    file.write(indent_l1 + '}\n')
                elif info.isComplex:
                    file.write(indent_l1 + '%s.CalculateCrc(&crc);\n'
                               % (membername))
                else:
                    cpptype = info.ctypename
                    if (cpptype == 'int' or cpptype == 'bool' or 
                        cpptype == 'uint64_t'):
                        file.write(indent_l1 +
                                   'crc.process_bytes(&%s, sizeof(%s));\n'
                                   %(membername, membername));
                    elif (cpptype == 'std::string'):
                        file.write(indent_l1 +
                                   'crc.process_bytes(%s.c_str(), %s.size());\n'
                                   %(membername, membername));
                    else:
                        assert()
                file.write(indent_l0 + '} \n')

            file.write(indent_l0 + 'return crc.checksum();\n');

            retval = "}\n\n"
            file.write(retval)
        else:
            function = """
boost::crc_32_type::value_type %s::CalculateCrc() const {
    return 0xffffffff;
}\n
""" % self.getName()
            file.write(function)

class IFMapGenLinkAttr(IFMapGenBase):
    def __init__(self, TypeDict, meta):
        self._TypeDict = TypeDict
        self._meta = meta

    def getName(self):
        return self._meta.getCppName()

    def getElementName(self):
        return self._meta.getName()

    def ServerClassDefn(self, file):
        ctypename = self._meta.getCTypename()
        cdef = """
class %s : public IFMapLinkAttr {
public:
""" %  self.getName()
        file.write(cdef)

        if self._meta.getCType():
            file.write('    typedef autogen::%s %s;\n' %
                       (ctypename, ctypename))
        else:
            cdef = """
    struct %sData : public AutogenProperty {
        %s data;
    };
""" % (self.getName(), ctypename)
            file.write(cdef)

        cdef = """
    %(class)s();
    virtual std::string ToString() const;
    virtual void EncodeUpdate(pugi::xml_node *parent) const;
    static bool Decode(const pugi::xml_node &parent, std::string *id_name,
                       %(class)s *ptr);
    virtual boost::crc_32_type::value_type CalculateCrc() const;
    virtual bool SetData(const AutogenProperty *data);

    const %(datatype)s &data() const { return data_; }
""" % {'class':self.getName(), 'datatype': ctypename}
        file.write(cdef)

        if not self._meta.getCType():
            cdef = """
    static bool ParseMetadata(const pugi::xml_node &parent,
                              std::auto_ptr<AutogenProperty> *resultp);
"""
            file.write(cdef)

        cdef = """
private:
    %s data_;
    DISALLOW_COPY_AND_ASSIGN(%s);
};
""" % (ctypename, self.getName())
        file.write(cdef)

    def ServerClassImpl(self, file):
        self._GenConstructor(file)
        self._GenToString(file)
        self._GenSetData(file)
        self._GenProcessPropertyDiff(file)

    def _GenConstructor(self, file):
        if self._meta.getCType():
            ccase = 'C'
        else:
            ccase = 'c'
        ctor = """
%s::%s() {
    data_.%clear();
}
""" % (self.getName(), self.getName(), ccase)
        file.write(ctor)

    def _GenToString(self, file):
        fn = """
string %(typename)s::ToString() const {
    string repr;
    return repr;
}
""" % {'typename': self.getName(), 'elementname': self._meta.getName()}
        file.write(fn)

    def _GenSetData(self, file):
        cdecl = """
bool %s::SetData(const AutogenProperty *data) {
    if (data == NULL) {
        return false;
    }
""" % self.getName()
        file.write(cdecl)

        ctypename = self._meta.getCTypename()
        if self._meta.getCType():
            cdecl = """
    data_ = *static_cast<const %s *>(data);
""" % ctypename
        else:
            cdecl = """
    const %sData *var = static_cast<const %sData *>(data);
    data_ = var->data;
""" % (self.getName(), self.getName())

        file.write(cdecl)
        cdecl = """
    return true;
}
"""
        file.write(cdecl)

    def _GenProcessPropertyDiff(self, file):
        header = """
boost::crc_32_type::value_type %s::CalculateCrc() const { """ % self.getName()
        file.write(header)

        ctypename = self._meta.getCTypename()
        if self._meta.getCType():
            cdecl = """
    boost::crc_32_type crc;
    data_.CalculateCrc(&crc);
    return crc.checksum();
}
"""
        else:
            cdecl = """
}
"""
        file.write(cdecl)

class IFMapClassGenerator(object):
    def __init__(self, cTypeDict):
        self._cTypeDict = cTypeDict
        self._generated_types = { }
        self._TypeGenerator = TypeClassGenerator(cTypeDict)
        self._generated_props = { }

    def _GenerateProperty(self, file, prop):
        ctype = prop.getCType()
        self._TypeGenerator.GenerateType(file, ctype)

    def _GenerateSimpleProperty(self, file, prop):
        name = prop.getCppName() + 'Type'
        if name in self._generated_props:
            return
        self._generated_props[name] = name
        info = prop.getMemberInfo()
        cdecl = """
class %(class)s {
  public:
    struct %(typename)s : public AutogenProperty {
        %(ctype)s data;
    };
};
""" % {'class': name,
       'typename': SimpleTypeWrapper(info),
       'ctype': info.ctypename}
        file.write(cdecl)

    def Generate(self, file, IdentifierDict, MetaDict):
        module_name = GetModuleName(file, '_types.h')

#include <boost/cstdint.hpp>  // for boost::uint16_t
        header = """
// autogenerated file --- DO NOT EDIT ---
#ifndef __SCHEMA__%(modname)s_TYPES_H__
#define __SCHEMA__%(modname)s_TYPES_H__
#include <map>
#include <set>
#include <vector>

#include <boost/dynamic_bitset.hpp>
#include <boost/crc.hpp>      // for boost::crc_32_type
namespace pugi {
class xml_node;
}  // namespace pugi

#include "rapidjson/document.h"

#include "ifmap/autogen.h"
#include "ifmap/ifmap_object.h"

class ConfigJsonParser;
class DB;
class DBGraph;
class IFMapServerParser;
class IFMapAgentParser;

namespace autogen {

""" % {'modname': module_name.upper()}
        file.write(header)
        for idn in IdentifierDict.values():
            # generate all dependent types
            properties = idn.getProperties()
            for prop in properties:
                if prop._xelement.isComplex():
                    self._GenerateProperty(file, prop)
                elif prop.getParent() == 'all':
                    self._GenerateSimpleProperty(file, prop)

        for meta in MetaDict.values():
            if type(meta) is IFMapLinkAttr:
                ctype = meta.getCType()
                if ctype:
                    self._TypeGenerator.GenerateType(file, ctype)

        for idn in IdentifierDict.values():
            if not idn._xelement:
                # cross-ref'd id from another file
                continue
            generator = IFMapGenIdentifier(self._cTypeDict, idn)
            generator.ServerClassDefn(file)

        for meta in MetaDict.values():
            if type(meta) is IFMapLinkAttr:
                generator = IFMapGenLinkAttr(self, meta)
                generator.ServerClassDefn(file)

        file.write('}  // namespace autogen\n')

        file.write('\nstruct %s_GraphFilterInfo {\n' % module_name)
        file.write('    %s_GraphFilterInfo(std::string left, std::string right,\n' % module_name) 
        file.write('                            std::string meta, bool linkattr) :\n')
        file.write('        left_(left), right_(right), metadata_(meta), linkattr_(linkattr) { }\n')
        file.write('    std::string left_;\n')
        file.write('    std::string right_;\n')
        file.write('    std::string metadata_;\n')
        file.write('    bool linkattr_;\n')
        file.write('};\n')
        file.write('typedef std::vector<%s_GraphFilterInfo> %s_FilterInfo;\n\n' % (module_name, module_name))


        file.write('typedef std::map<std::string, std::string> %s_WrapperPropertyInfo;\n\n' % (module_name))


        file.write('extern void %s_Server_ModuleInit(DB *, DBGraph *);\n'
                   % module_name)
        file.write('extern void %s_Server_GenerateGraphFilter(%s_FilterInfo *);\n'
                   % (module_name, module_name))
        file.write('extern void %s_Server_GenerateWrapperPropertyInfo(%s_WrapperPropertyInfo *);\n'
                   % (module_name, module_name))
        file.write('extern void %s_Server_GenerateObjectTypeList(std::set<std::string> *);\n'
                   % (module_name))
        file.write('extern void %s_Agent_ModuleInit(DB *, DBGraph *);\n'
                   % module_name)
        file.write('extern void %s_Agent_ParserInit(DB *, IFMapAgentParser *);\n'
                   % module_name)
        file.write('extern void %s_ParserInit(IFMapServerParser *);\n'
                   % module_name)
        file.write('extern void %s_JsonParserInit(ConfigJsonParser *);\n'
                   % module_name)
        file.write('#endif  // __SCHEMA__%s_TYPES_H__\n' %
                   module_name.upper())

class IFMapImplGenerator(object):
    def __init__(self, cTypeDict):
        self._cTypeDict = cTypeDict
        self._TypeImplGenerator = TypeImplGenerator(None)
        self._DBTableList = []
        self._module_name = ''

    def Generate(self, file, hdrname, IdentifierDict, MetaDict):
        header = """
// autogenerated file --- DO NOT EDIT ---
#include "%s"

#include "ifmap/autogen.h"

#include <pugixml/pugixml.hpp>

using namespace std;

namespace autogen {
""" % hdrname
        file.write(header)

        for ctype in self._cTypeDict.values():
            self._TypeImplGenerator.GenerateType(file, ctype)

        self._module_name = GetModuleName(file, '_types.cc')

        for idn in IdentifierDict.values():
            if not idn._xelement:
                # cross-ref'd id from another file
                continue
            generator = IFMapGenIdentifier(self._cTypeDict, idn)
            generator.ServerClassImpl(file)
            tbl = (idn.getCIdentifierName(), idn.getCppName())
            self._DBTableList.append(tbl)

        for meta in MetaDict.values():
            if type(meta) is IFMapLinkAttr:
                generator = IFMapGenLinkAttr(self, meta)
                generator.ServerClassImpl(file)
                tbl = (meta.getCIdentifierName(), meta.getCppName())
                self._DBTableList.append(tbl)

        file.write('}  // namespace autogen\n')
        # end

    def _GenerateGraphFilter(self, file, hdrname, component, IdentifierDict,
                             MetaDict):
        cdecl = """
void %(module)s_%(comp)s_GenerateGraphFilter(%(module)s_FilterInfo *filter_info) {
""" % { 'module': self._module_name, 'comp': component}
        file.write(cdecl)

        for idn in IdentifierDict.values():
            links = idn.getLinksInfo()
            for link_info in links:
                to_ident = idn.getLinkTo(link_info)
                link_meta = idn.getLink(link_info)
                if link_meta.getXsdType():
                    linkattr = "true"
                else:
                    linkattr = "false"
                fmt = '    filter_info->push_back(%s_GraphFilterInfo("%s", "%s", "%s", %s));\n'
                file.write(fmt % (self._module_name, idn.getName().replace('-', '_'),
                                  to_ident.getName().replace('-', '_'), link_meta.getName(),
                                  linkattr))

        file.write('}\n')
        # end

    def _GenerateWrapperPropertyDetails(self, file, hdrname, component, IdentifierDict):
        cdecl = """
void %(module)s_%(comp)s_GenerateWrapperPropertyInfo(%(module)s_WrapperPropertyInfo *wrapper_property_info) {
""" % { 'module': self._module_name, 'comp': component}
        file.write(cdecl)

        for idn in IdentifierDict.values():
            properties = idn.getProperties()
            for prop in properties:
                if prop.isListUsingWrapper() or prop.isMapUsingWrapper():
                    fmt = '    wrapper_property_info->insert(std::make_pair("%s", "%s"));\n'
                    file.write(fmt % (idn.getName().replace('-', '_') + ':' + prop.getElement().getCleanName(),
                        prop.getMemberInfo().xsd_object.getName()))

        file.write('}\n')
        # end

    def _GenerateObjectTypeList(self, file, hdrname, component, IdentifierDict):
        cdecl = """
void %(module)s_%(comp)s_GenerateObjectTypeList(std::set<std::string> *object_type_list) {
""" % { 'module': self._module_name, 'comp': component}
        file.write(cdecl)

        for idn in IdentifierDict.values():
            fmt = '    object_type_list->insert("%s");\n'
            file.write(fmt % (idn.getName().replace('-', '_')))

        file.write('}\n')
        # end



    def _GenerateComponent(self, file, hdrname, component,
                           IdentifierDict, MetaDict):
        header = """
// autogenerated file --- DO NOT EDIT ---
#include "%(hdrname)s"

#include <boost/bind.hpp>
#include <sstream>

#include "base/autogen_util.h"
#include "db/db.h"
#include "ifmap/client/config_json_parser.h"
#include "ifmap/ifmap_%(comp)s_table.h"
#include "ifmap/ifmap_%(comp)s_parser.h"

using namespace std;

namespace autogen {

""" % {'hdrname': hdrname, 'comp': component.lower()}
        file.write(header)

        for idn in IdentifierDict.values():
            if not idn._xelement:
                # cross-ref'd id from another file
                continue
            generator = IFMapGenIdentifier(self._cTypeDict, idn)
            generator.TableClassDefn(file, component)
            generator.TableClassImpl(file, component)

        for meta in MetaDict.values():
            if type(meta) is IFMapLinkAttr:
                generator = IFMapGenLinkAttr(self, meta)
                generator.TableClassDefn(file, component)
                generator.TableClassImpl(file, component)

        file.write('}  // namespace autogen\n')

        self._GenerateGraphFilter(file, hdrname, component, IdentifierDict,
                             MetaDict)
        self._GenerateWrapperPropertyDetails(file, hdrname, component, IdentifierDict)

        self._GenerateObjectTypeList(file, hdrname, component, IdentifierDict)

        cdecl = """
void %(module)s_%(comp)s_ModuleInit(DB *db, DBGraph *graph) {
    DBTable *table;
""" % { 'module': self._module_name, 'comp': component}
        file.write(cdecl)

        for tbl in self._DBTableList:
            cdecl = """
    table = autogen::DBTable_%(impl)s_%(class)s::CreateTable(
        db, "__ifmap__.%(tablename)s.0", graph);
    db->AddTable(table);
""" % {'impl': component, 'tablename': tbl[0], 'class':tbl[1]}
            file.write(cdecl)

        file.write('}\n')

    def GenerateServer(self, file, hdrname, IdentifierDict, MetaDict):
        self._GenerateComponent(file, hdrname, 'Server',
                                IdentifierDict, MetaDict)

    def GenerateClient(self, file, hdrname, IdentifierDict, MetaDict):
        self._GenerateComponent(file, hdrname, 'Client',
                                IdentifierDict, MetaDict)

    def GenerateAgent(self, file, hdrname, IdentifierDict, MetaDict):
        self._GenerateComponent(file, hdrname, 'Agent',
                                IdentifierDict, MetaDict)
