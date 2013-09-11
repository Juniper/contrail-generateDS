#
# Copyright (c) 2013 Juniper Networks, Inc. All rights reserved.
#

import os
import re

from ifmap_global import CamelCase

def getLinkInfoType(ident, link_info):
    xlink = ident.getLink(link_info)
    if xlink.getXsdType():
        return xlink.getCType().getName()
    return 'ApiPropertyBase'
    
class JavaApiGenerator(object):
    def __init__(self, parser, type_map, identifiers, metadata):
        self._parser = parser
        self._type_map = type_map
        self._top_level_map = {
            'SubnetType': self._type_map['SubnetType']
            }
        self._identifier_map = identifiers
        self._metadata_map = metadata
        self._type_count = {}

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
        self._GenerateType(ctype, file, 0, {})

    def _GenerateType(self, ctype, file, indent_level, inner_map):

        if inner_map.get(ctype.getName()):
            return
        inner_map[ctype.getName()] = ctype

        if indent_level and self._top_level_map.get(ctype.getName()):
            return

        count = self._type_count.get(ctype)
        if count:
            self._type_count[ctype] = count + 1
        else:
            self._type_count[ctype] = 1

        if indent_level:
            file.write(' ' * indent_level)

        file.write('public ')
        if indent_level:
            file.write('static ')
        file.write('class %s ' % ctype.getName())
        if indent_level == 0:
            file.write('extends ApiPropertyBase ')
        file.write('{\n')
        indent_level += 4

        for dep in ctype.getDependentTypes():
            self._GenerateType(dep, file, indent_level, inner_map)

        for member in ctype.getDataMembers():
            file.write(' ' * indent_level)
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

        self._GenerateTypePropertyAccessors(file, ctype, indent_level);
        self._GenerateTypePropertyConvinience(file, ctype, indent_level)

        indent_level -= 4
        if indent_level > 0:
            file.write(' ' * indent_level)
        file.write('}\n')
    # _GenerateType

    def _InnerPropertyArgument(self, inner, member):
        decl = ''
        if member.isComplex and not self._top_level_map.get(member.jtypename):
            decl = inner.getName() + '.'
        decl += member.jtypename
        decl += ' ' + member.membername
        return decl

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
                        map(lambda x: self._InnerPropertyArgument(inner, x),
                            inner.getDataMembers())),
       'arglist': ', '.join(
                        map(lambda x: x.membername, inner.getDataMembers()))
       
       }
                self._FileWrite(file, decl, indent_level)

    # _GenerateTypePropertyConvinience

    def _GenerateClass(self, ident, filename):
        file = self._parser.makeFile(filename)

        header = """//
// Automatically generated.
//
package net.juniper.contrail.api.types;

import java.util.List;
import java.util.ArrayList;
import com.google.common.collect.ImmutableList;

import net.juniper.contrail.api.ApiObjectBase;
import net.juniper.contrail.api.ApiPropertyBase;
import net.juniper.contrail.api.ObjectReference;

public class %(cls)s extends ApiObjectBase {
""" % {'cls': ident.getCppName() }
        file.write(header)

        parents = ident.getParents()
        if parents:
            decl = """
    private transient String parent_name;
    private transient String parent_uuid;
"""
            file.write(decl)

        for prop in ident.getProperties():
            if prop.getName() == 'id-perms':
                continue
            decl = '    private %s %s;\n' % (prop.getJavaTypename(), prop.getCIdentifierName())
            file.write(decl)
            ctype = prop.getCType()
            if ctype:
                ctypename = ctype.getName()
                self._top_level_map[ctypename] = self._type_map[ctypename]

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
        self._GenerateDefaultParent(file, ident)
        self._GenerateDefaultParentType(file, ident)

        self._GeneratePropertyAccessors(file, ident, 4)

        for link_info in ident.getLinksInfo():
            if ident.isLinkRef(link_info):
                self._GenerateLinkRefAccessors(file, ident, link_info)
            elif ident.isLinkHas(link_info):
                self._GenerateLinkHasAccessors(file, ident, link_info)

        for back_link in ident.getBackLinksInfo():
            self._GenerateBackRefAccessors(file, ident, back_link)

        file.write('}')

    def _GenerateTypename(self, file, ident):
        decl = """
    @Override
    public String getType() {
        return "%s";
    }
""" % ident.getName()
        file.write(decl)

    # _GenerateTypename

    def _GenerateDefaultParent(self, file, ident):
        fq_name = ''
        parents = ident.getParents()
        if parents:
            (parent, meta) = parents[0]
            quoted_list = map(lambda x: '"%s"' % x, parent.getDefaultFQName())
            fq_name = ', '.join(quoted_list)

        decl = """
    @Override
    public List<String> getDefaultParent() {
        return ImmutableList.of(%s);
    }
""" % fq_name
        file.write(decl)

    # _GenerateDefaultParent

    def _GenerateDefaultParentType(self, file, ident):
        def quote(s):
            return '"' + s + '"'

        typename = 'null';
        parents = ident.getParents()
        if parents:
            (parent, meta) = parents[0]
            typename = quote(parent.getName())

        decl = """
    @Override
    public String getDefaultParentType() {
        return %s;
    }
""" % typename
        file.write(decl)

    # _GenerateDefaultParentType

    def _GeneratePropertyAccessors(self, file, ident, indent_level):
        for prop in ident.getProperties():
            if prop.getName() == 'id-perms':
                continue
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
            self._top_level_map[attrtype] = self._type_map[attrtype]

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

    public void clear%(caml)s() {
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
    public void clear%(caml)s() {
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

    def Generate(self, dirname):
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        elif not os.path.isdir(dirname):
            print "-o option must specify directory"
            sys.exit(1)

        for ident in self._identifier_map.values():
            filename = os.path.join(dirname, ident.getCppName() + ".java")
            self._GenerateClass(ident, filename)

        for ctype in self._top_level_map.values():
            filename = os.path.join(dirname, ctype.getName() + ".java")
            self._GenerateTypeClass(ctype, filename)

        for cname, count in self._type_count.items():
            if count > 1:
                print 'type %s count: %d' % (cname.getName(), count)
