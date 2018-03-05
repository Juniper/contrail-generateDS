#
# Copyright (c) 2013 Juniper Networks, Inc. All rights reserved.
#

import os
import re

from ifmap_global import CamelCase
from ifmap_model import AmbiguousParentType

def getLinkInfoType(ident, link_info):
    xlink = ident.getLink(link_info)
    if xlink.getXsdType():
        return xlink.getCType().getName()
    return 'ApiPropertyBase'

def quoted(s):
    return '"%s"' % s

class JavaApiGenerator(object):
    def __init__(self, parser, type_map, identifiers, metadata):
        self._parser = parser
        self._type_map = type_map
        self._identifier_map = identifiers
        self._metadata_map = metadata

    def _FileWrite(self, file, multiline, indent_level):
        lines = multiline.split('\n')
        for line in lines:
            line = ' ' * indent_level + line + '\n'
            file.write(line)

    #end _FileWrite

    def _GenerateTypeClass(self, ctype, filename):
        file = self._parser.makeFile(filename)

        header = """//
// Automatically generated.
//
package net.juniper.contrail.api.types;

import java.util.List;
import java.util.ArrayList;

import net.juniper.contrail.api.ApiPropertyBase;

"""
        file.write(header)
        self._GenerateType(ctype, file)

    def _GenerateType(self, ctype, file):
        file.write('public class %s extends ApiPropertyBase {\n' % ctype.getName())
        indent_level = 4

        for member in ctype.getDataMembers():
            file.write(' ' * indent_level)
            if (member.jtypename == "java.util.Date"):
                file.write('volatile %s %s;\n' % (member.jtypename, member.membername))
            else:
                file.write('%s %s;\n' % (member.jtypename, member.membername))

        # default constructor
        file.write(' ' * indent_level)
        file.write('public %s() {\n' % ctype.getName())
        file.write(' ' * indent_level)
        file.write('}\n')

        # constructor with all properties
        file.write(' ' * indent_level)
        file.write('public %s(' % ctype.getName())
        index = 0
        for member in ctype.getDataMembers():
            if index > 0:
                file.write(', ')
            file.write('%s %s' % (member.jtypename, member.membername))
            index += 1
        file.write(') {\n')

        indent_level += 4
        for member in ctype.getDataMembers():
            file.write(' ' * indent_level)
            file.write('this.%s = %s;\n' %
                       (member.membername, member.membername))

        indent_level -= 4
        file.write(' ' * indent_level)
        file.write('}\n')

        # constructors with default parameters
        param_count = len(ctype.getDataMembers())
        for param_end in range(1, param_count):
            file.write(' ' * indent_level)
            file.write('public %s(' % ctype.getName())
            index = 0
            for member in ctype.getDataMembers()[0:param_end]:
                if index > 0:
                    file.write(', ')
                file.write('%s %s' % (member.jtypename, member.membername))
                index += 1
            file.write(') {\n')

            indent_level += 4
            file.write(' ' * indent_level)
            first = True
            for member in ctype.getDataMembers()[0:param_end]:
                if first:
                    file.write('this(')
                    first = False
                else:
                    file.write(', ')
                file.write(member.membername)
            file.write(', ')
            for member in ctype.getDataMembers()[param_end:]:
                if member.isComplex:
                    file.write('null')
                elif member.jtypename is 'boolean':
                    file.write(member.default or 'false')
                elif member.jtypename is 'String':
                    default = 'null'
                    if member.default:
                        default = quoted(member.default)
                    file.write(default)
                elif member.jtypename in ['Integer', 'Long']:
                    default = 'null'
                    if member.default:
                        default = str(member.default)
                    file.write(default)
                else:
                    file.write('null')
                if member != ctype.getDataMembers()[param_count-1]:
                    file.write(', ')
                else:
                    file.write(');')

            indent_level -= 4
            file.write(' ' * indent_level)
            file.write('}\n')

        self._GenerateTypePropertyAccessors(file, ctype, indent_level)
        self._GenerateTypePropertyConvinience(file, ctype, indent_level)

        file.write('}\n')
    # _GenerateType

    def _InnerPropertyArgument(self, member):
        return member.jtypename + ' ' + member.membername

    def _GenerateTypePropertyAccessors(self, file, ctype, indent_level):
        for prop in ctype.getDataMembers():
            if prop.isSequence:
                continue
            decl = """
public %(type)s get%(caml)s() {
    return %(field)s;
}

public void set%(caml)s(%(type)s %(field)s) {
    this.%(field)s = %(field)s;
}
""" % {'caml': CamelCase(prop.membername), 'type': prop.jtypename,
       'field': prop.membername}
            self._FileWrite(file, decl, indent_level)

    # _GenerateTypePropertyAccessors

    def _GenerateTypePropertyConvinience(self, file, ctype, indent_level):
        for member in ctype.getDataMembers():
            if member.isSequence:
                m = re.search(r'\<(.*)\>', member.jtypename)
                if m:
                    innertype = m.group(1)
                else:
                    print 'Unable to determine inner type for Collection: ' + member.jtypename
                    continue
                methodname = CamelCase(member.membername)
                decl = """
public List<%(typename)s> get%(caml)s() {
    return %(field)s;
}
""" % { 'caml': methodname, 'typename': innertype, 'field': member.membername }
                self._FileWrite(file, decl, indent_level)

                if methodname.endswith('List'):
                    methodname = methodname[:-len('List')]
                decl = """
public void add%(caml)s(%(typename)s obj) {
    if (%(field)s == null) {
        %(field)s = new ArrayList<%(typename)s>();
    }
    %(field)s.add(obj);
}
public void clear%(caml)s() {
    %(field)s = null;
}
""" % {'caml': methodname, 'typename': innertype, 'field': member.membername}
                self._FileWrite(file, decl, indent_level)

                # convinience method that uses the inner type constructor
                # arguments
                inner = self._type_map.get(innertype)
                if not inner or len(inner.getDataMembers()) > 4:
                    continue
                
                decl = """
public void add%(caml)s(%(argdecl)s) {
    if (%(field)s == null) {
        %(field)s = new ArrayList<%(typename)s>();
    }
    %(field)s.add(new %(typename)s(%(arglist)s));
}
""" % {'caml': methodname, 'typename': innertype, 'field': member.membername,
       'argdecl': ', '.join(
                        map(lambda x: self._InnerPropertyArgument(x),
                            inner.getDataMembers())),
       'arglist': ', '.join(
                        map(lambda x: x.membername, inner.getDataMembers()))
       
       }
                self._FileWrite(file, decl, indent_level)

    # _GenerateClass

    def _GenerateClass(self, ident, filename):
        file = self._parser.makeFile(filename)

        self._GenerateHeader(file, ident)

        for prop in ident.getProperties():
            decl = '    private %s %s;\n' % (prop.getJavaTypename(), prop.getCIdentifierName())
            file.write(decl)

        for link_info in ident.getLinksInfo():
            link_type = getLinkInfoType(ident, link_info)
            if ident.isLinkRef(link_info):
                link_to = ident.getLinkTo(link_info)
                decl = '    private List<ObjectReference<%s>> %s_refs;\n' % (link_type, link_to.getCIdentifierName())
                file.write(decl)
            elif ident.isLinkHas(link_info):
                child = ident.getLinkTo(link_info)
                decl = '    private List<ObjectReference<%s>> %ss;\n' % (link_type, child.getCIdentifierName())
                file.write(decl) 

        for back_link in ident.getBackLinksInfo():
            link_from = ident.getBackLinkFrom(back_link)
            link_type = getLinkInfoType(ident, back_link)
            decl = '    private transient List<ObjectReference<%s>> %s_back_refs;\n' % (link_type, link_from.getCIdentifierName())
            file.write(decl)

        self._GenerateTypename(file, ident)
        self._GenerateDefaultParentInfo(file, ident)
        self._GenerateParentSetters(file, ident)

        self._GeneratePropertyAccessors(file, ident, 4)

        for link_info in ident.getLinksInfo():
            if ident.isLinkRef(link_info):
                self._GenerateLinkRefAccessors(file, ident, link_info)
            elif ident.isLinkHas(link_info):
                self._GenerateLinkHasAccessors(file, ident, link_info)

        for back_link in ident.getBackLinksInfo():
            self._GenerateBackRefAccessors(file, ident, back_link)

        file.write('}')

    def _GenerateHeader(self, file, ident):
        header = """//
// Automatically generated.
//
package net.juniper.contrail.api.types;

import java.util.List;
import java.util.ArrayList;
import com.google.common.collect.Lists;

import net.juniper.contrail.api.ApiObjectBase;
import net.juniper.contrail.api.ApiPropertyBase;
import net.juniper.contrail.api.ObjectReference;

public class %s extends ApiObjectBase {
""" % ident.getCppName()
        file.write(header)

    def _GenerateTypename(self, file, ident):
        decl = """
    @Override
    public String getObjectType() {
        return "%s";
    }
""" % ident.getName()
        file.write(decl)

    # _GenerateDefaultParentInfo

    def _GenerateDefaultParentInfo(self, file, ident):
        parent_fq_name = 'null'
        parent_type = 'null'
        try:
            fq_name = ident.getDefaultFQName()
            quoted_list = map(lambda x: quoted(x), fq_name[:-1])
            parent_fq_name = "Lists.newArrayList(%s)" % ', '.join(quoted_list)
            parents = ident.getParents()
            if parents:
                (parent, meta, _) = parents[0]
                parent_type = quoted(parent.getName())
        except AmbiguousParentType as e:
            # Ambiguous types don't have default parent
            pass
        decl = """
    @Override
    public List<String> getDefaultParent() {
        return %(fq_name)s;
    }

    @Override
    public String getDefaultParentType() {
        return %(type)s;
    }
""" % {'fq_name': parent_fq_name, 'type': parent_type }
        file.write(decl)

    # _GenerateParentSetters

    def _GenerateParentSetters(self, file, ident):
        parents = ident.getParents()
        if parents:
            for parent_info in parents:
                (parent, _, _) = parent_info
                typename = parent.getCppName()
    
                decl = """
    public void setParent(%s parent) {
        super.setParent(parent);
    }
""" % typename
                file.write(decl)

    # _GenerateDefaultParentType

    def _GeneratePropertyAccessors(self, file, ident, indent_level):
        for prop in ident.getProperties():
            gsname = prop.getCppName()
            if gsname.startswith(ident.getCppName()):
                gsname = gsname[len(ident.getCppName()):]

            decl = """
public %(type)s get%(caml)s() {
    return %(field)s;
}

public void set%(caml)s(%(type)s %(field)s) {
    this.%(field)s = %(field)s;
}
""" % {'caml': gsname, 'type': prop.getJavaTypename(),
       'field': prop.getCIdentifierName()}
            self._FileWrite(file, decl, indent_level)

    # _GeneratePropertyAccessors

    def _GenerateLinkRefAccessors(self, file, ident, link_info):
        link_to = ident.getLinkTo(link_info)
        getter = """
    public List<ObjectReference<%(attrtype)s>> get%(caml)s() {
        return %(id)s_refs;
    }
""" % {'attrtype': getLinkInfoType(ident, link_info), 'caml': link_to.getCppName(), 'id': link_to.getCIdentifierName() }

        file.write(getter)

        xlink = ident.getLink(link_info)
        if xlink.getXsdType():
            attrtype = xlink.getCType().getName()

            setters = """
    public void set%(caml)s(%(linktype)s obj, %(datatype)s data) {
        %(field)s_refs = new ArrayList<ObjectReference<%(datatype)s>>();
        %(field)s_refs.add(new ObjectReference<%(datatype)s>(obj.getQualifiedName(), data));
    }

    public void add%(caml)s(%(linktype)s obj, %(datatype)s data) {
        if (%(field)s_refs == null) {
            %(field)s_refs = new ArrayList<ObjectReference<%(datatype)s>>();
        }
        %(field)s_refs.add(new ObjectReference<%(datatype)s>(obj.getQualifiedName(), data));
    }

    public void remove%(caml)s(%(linktype)s obj, %(datatype)s data) {
        if (%(field)s_refs != null) {
            %(field)s_refs.remove(new ObjectReference<%(datatype)s>(obj.getQualifiedName(), data));
        }
    }

    public void clear%(caml)s() {
        if (%(field)s_refs != null) {
            %(field)s_refs.clear();
            return;
        }
        %(field)s_refs = null;
    }

""" % {'caml': link_to.getCppName(), 'linktype': link_to.getCppName(),
       'datatype': attrtype, 'field': link_to.getCIdentifierName()}
            file.write(setters)
        else:
            setters = """
    public void set%(caml)s(%(linktype)s obj) {
        %(field)s_refs = new ArrayList<ObjectReference<ApiPropertyBase>>();
        %(field)s_refs.add(new ObjectReference<ApiPropertyBase>(obj.getQualifiedName(), null));
    }
    
    public void add%(caml)s(%(linktype)s obj) {
        if (%(field)s_refs == null) {
            %(field)s_refs = new ArrayList<ObjectReference<ApiPropertyBase>>();
        }
        %(field)s_refs.add(new ObjectReference<ApiPropertyBase>(obj.getQualifiedName(), null));
    }
    
    public void remove%(caml)s(%(linktype)s obj) {
        if (%(field)s_refs != null) {
            %(field)s_refs.remove(new ObjectReference<ApiPropertyBase>(obj.getQualifiedName(), null));
        }
    }

    public void clear%(caml)s() {
        if (%(field)s_refs != null) {
            %(field)s_refs.clear();
            return;
        }
        %(field)s_refs = null;
    }
""" % {'caml': link_to.getCppName(), 'linktype': link_to.getCppName(),
       'field': link_to.getCIdentifierName()}
            file.write(setters)

    # _GenerateLinkRefAccessors

    def _GenerateLinkHasAccessors(self, file, ident, link_info):
        child = ident.getLinkTo(link_info)
        getter = """
    public List<ObjectReference<%(attrtype)s>> get%(caml)ss() {
        return %(id)ss;
    }
""" % {'attrtype': getLinkInfoType(ident, link_info), 'caml': child.getCppName(), 'id': child.getCIdentifierName() }

        file.write(getter)
    # _GenerateLinkHasAccessors

    def _GenerateBackRefAccessors(self, file, ident, back_link):
        link_from = ident.getBackLinkFrom(back_link)
        decl = """
    public List<ObjectReference<%(attrtype)s>> get%(caml)sBackRefs() {
        return %(field)s_back_refs;
    }
""" % {'attrtype': getLinkInfoType(ident, back_link), 'caml': link_from.getCppName(), 'field': link_from.getCIdentifierName()}
        file.write(decl)

    # _GenerateBackRefAccessors

    def _PopulatePropertyTypes(self, ctype, type_set):
        type_set.add(ctype)
        for dep in ctype.getDependentTypes():
            self._PopulatePropertyTypes(dep, type_set)

    def Generate(self, dirname):
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        elif not os.path.isdir(dirname):
            print "-o option must specify directory"
            sys.exit(1)

        for ident in self._identifier_map.values():
            filename = os.path.join(dirname, ident.getCppName() + ".java")
            self._GenerateClass(ident, filename)

        property_types = set([])
        for ctype in self._type_map.values():
            self._PopulatePropertyTypes(ctype, property_types)

        for ctype in property_types:
            filename = os.path.join(dirname, ctype.getName() + ".java")
            self._GenerateTypeClass(ctype, filename)
