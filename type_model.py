#
# Copyright (c) 2013 Juniper Networks, Inc. All rights reserved.
#

import logging
import re

from ifmap_global import getCppType, getJavaType, IsGeneratedType, CamelCase

def CppVariableName(varname):
    keywords = ['static']
    if varname in keywords:
        varname = '_' + varname;
    return varname
        
class MemberInfo(object):
    def __init__(self):
        self.ctypename = ''
        self.jtypename = ''
        self.membername = ''
        self.isSequence = False
        self.isComplex = False
        self.xsd_object = None
        self.sequenceType = None
        self.default = None

class ComplexType(object):
    def __init__(self, name):
        self._name = name
        self._is_attribute = False
        self._data_types = []
        self._data_members = []

    def getName(self):
        return self._name

    def getCIdentifierName(self):
        expr = re.compile(r'\B[A-Z]')
        name = expr.sub(lambda x: '_' + x.group().lower(), self._name)
        return name.lower()

    def getDependentTypes(self):
        return self._data_types

    def getDataMembers(self):
        return self._data_members

    def Build(self, xsdTypeDict, cTypeDict):
        self._xsd_type = xsdTypeDict[self._name]

        children = self._xsd_type.getChildren()
        if children:
            for child in children:
                if child.isComplex():
                    descendent = ComplexTypeLocate(xsdTypeDict, cTypeDict, child.getType())
                    self._data_types.append(descendent)
                    cpptype = child.getType()
                    jtype = child.getType()
                    cppname = child.getCleanName()
                else:
                    cpptype = getCppType(child.getType())
                    jtype = getJavaType(child.getType())
                    if cpptype == 'void':
                        logger = logging.getLogger('type_model')
                        logger.warning('simpleType %s: unknown' % child.getType())
                    cppname = child.getCleanName()

                member = MemberInfo()
                member.elementname = child.getName()
                member.membername = CppVariableName(cppname)
                member.xsd_object = child
                member.isComplex = child.isComplex()
                if child.getMaxOccurs() > 1:
                    member.membername = cppname# + '_list'
                    member.sequenceType = cpptype
                    cpptype = 'std::vector<%s>' % cpptype
                    jtype = 'List<%s>' % jtype
                    member.isSequence = True

                member.ctypename = cpptype
                member.jtypename = jtype
                member.default = child.getDefault()
                self._data_members.append(member)
        else:
            attributes = self._xsd_type.getAttributeDefs().values()
            if attributes:
                self._is_attribute = True
            for attribute in attributes:
                cpptype = getCppType(attribute.getType())
                jtype = getJavaType(attribute.getType())
                if cpptype == 'void':
                    logger = logging.getLogger('type_model')
                    logger.warning('simpleType %s: unknown' % attribute.getType())
                cppname = attribute.getCleanName()
                member = MemberInfo()
                member.elementname = attribute.getName()
                member.membername = CppVariableName(cppname)
                member.xsd_object = attribute
                member.isComplex = False
                member.ctypename = cpptype
                member.jtypename = jtype
                member.default = attribute.getDefault()
                self._data_members.append(member)


def ComplexTypeLocate(xsdTypeDict, cTypeDict, xtypename):
    if xtypename in cTypeDict:
        return cTypeDict[xtypename]

    if not xtypename in xsdTypeDict:
        return None

    ctype = ComplexType(xtypename)
    ctype.Build(xsdTypeDict, cTypeDict)
    cTypeDict[xtypename] = ctype
    return ctype
