#
# Copyright (c) 2013 Juniper Networks, Inc. All rights reserved.
#

import logging
import re

from ifmap_global import getCppType, getJavaType, getGoLangType
from ifmap_global import IsGeneratedType, CamelCase
from type_model import ComplexType, ComplexTypeLocate, MemberInfo

def ElementXsdType(xelement):
    if xelement.schema_type:
        typename = xelement.schema_type
    else:
        typename = xelement.getType()
    if typename == xelement.getName():
        return None
    return typename

class IFMapObject(object):
    def __init__(self, name):
        self._name = name
        self._xelement = None

    def getName(self):
        """ The data structure name (e.g. virtual-network) """
        return self._name

    def getCIdentifierName(self):
        """ A valid C identifier name (e.g. virtual_network). """
        if not self._xelement:
            special_chars = [':', '-', '.']
            name = self._name
            for ch in special_chars:
                name = name.replace(ch, '_')
            return name
        return self._xelement.getCleanName()

    def SetSchemaElement(self, xelement):
        self._xelement = xelement

    def getXsdType(self):
        return ElementXsdType(self._xelement)

    def getElement(self):
        return self._xelement

class IFMapIdentifier(IFMapObject):
    """ An identifier and the list of associated properties.
    """
    def __init__(self, name):
        super(IFMapIdentifier, self).__init__(name)
        self._cppname = CamelCase(name)
        self._properties = []   # list of IFMapProperty elements
        self._key_members = []
        self._data_members = []
        self._data_types = []
        self._links = []
        self._back_links = []
        self._parents = None
        self._children = []
        self._references = []
        self._back_references = []
        self._is_derived = False

    def getCppName(self):
        return self._cppname

    def SetProperty(self, meta):
        self._properties.append(meta)

    def getProperties(self):
        return self._properties

    def setParent(self, parent_ident, meta):
        parent_info = {'ident': parent_ident, 'meta': meta}
        if not self._parents:
            self._parents = [parent_info]
        else:
            self._parents.append(parent_info)

    def getParents(self):
        if not self._parents:
            return None

        return [(parent_info['ident'], parent_info['meta']) for parent_info in self._parents]

    def getParentName(self, parent_info):
        return parent_info['ident'].getName()

    def getParentMetaName(self, parent_info):
        return parent_info['meta'].getName()

    def getChildren(self):
        return self._children

    def getReferences(self):
        return self._references

    def getBackReferences(self):
        return self._back_references

    def getDefaultFQName(self, parent_type = None):
        if not self._parents:
            if self._name == 'config-root':
                return []
            else:
                return ['default-%s' %(self._name)]

        if not parent_type and len(self._parents) > 1:
            raise Exception('parent_type should be specified')

        if parent_type:
            parent_ident = None
            for parent in self._parents:
                if parent['ident'].getName() == parent_type:
                    parent_ident = parent['ident']
                    break
        else:
            parent_ident = self._parents[0]['ident']

        fq_name = parent_ident.getDefaultFQName()
        fq_name.append('default-%s' %(self._name))
        return fq_name

    def isDerived(self):
        return self._is_derived

    def addLinkInfo(self, meta, to_ident, attrs):
        link_info = (meta, to_ident, attrs)
        self._links.append(link_info)
        if (self.isLinkHas(link_info)):
            self._children.append(to_ident)

            to_ident.setParent(self, meta)
            if self.isLinkDerived(link_info):
                to_ident._is_derived = True
        elif self.isLinkRef(link_info):
            self._references.append(to_ident)

            # relax back-ref check on delete
            if self.isLinkDerived(link_info):
                self._is_derived = True

    def getLinksInfo(self):
        return self._links

    def getLink(self, link_info):
        return link_info[0]

    def getLinkTo(self, link_info):
        return link_info[1]

    def isLinkHas(self, link_info):
        attrs = link_info[2]
        return 'has' in attrs

    def isLinkRef(self, link_info):
        attrs = link_info[2]
        return 'ref' in attrs

    def isLinkDerived(self, link_info):
        """
        Returns if the 'to' identifier is directly managed by user
        or if it is result of schema transformation
        """
        attrs = link_info[2]
        return 'derived' in attrs

    def addBackLinkInfo(self, meta, from_ident, attrs):
        link_info = (meta, self, attrs)
        back_link_info = (meta, from_ident, attrs)
        if self.isLinkRef(link_info):
            self._back_references.append(from_ident)
            self._back_links.append(back_link_info)

    def getBackLinksInfo(self):
        return self._back_links

    def getBackLink(self, back_link_info):
        return back_link_info[0]

    def getBackLinkFrom(self, back_link_info):
        return back_link_info[1]

    def getKeyMembers(self):
        return self._key_members

    def getDataMembers(self):
        return self._data_members

    def getDataTypes(self):
        return self._data_types

    def _BuildKeySpec(self, TypeDict, decl, typename):
        """ The IFMapIdentifier primary key """
        if not typename:
            return decl

        if typename == 'IdentityType':
            decl.append(('std::string', 'name_'))
            return decl

        return decl

    def _BuildDataMembers(self, xsdTypeDict, cTypeDict):
        for mprop in self._properties:
            mprop.Resolve(xsdTypeDict, cTypeDict)
            if mprop._xelement.isComplex():
                self._BuildProperty(xsdTypeDict, mprop)
            else:
                self._BuildSimpleProperty(mprop)

    def _BuildProperty(self, TypeDict, meta):
        name = meta.getPropertyName() + '_'

        member = MemberInfo()
        member.membername = name
        member.xsd_object = meta._xelement
        member.isComplex = True
        child_data = meta.getDataMembers()
        if len(child_data) == 1:
            cpptype = child_data[0].ctypename
            member.xsd_object = child_data[0].xsd_object
            m = re.match('std::vector<(\S+)>', cpptype)
            if m:
                member.isSequence = True
                meta._isSequence = True
                dtype = m.group(1)
                member.sequenceType = dtype
                if IsGeneratedType(dtype):
                    self._data_types.append(dtype)
            else:
                self._data_types.append(cpptype)
        else:
            cpptype = meta.getCType().getName()
            self._data_types.append(cpptype)

        member.ctypename = cpptype
        meta._memberinfo = member
        self._data_members.append(member)

    def _BuildSimpleProperty(self, prop):
        member = MemberInfo()
        member.membername = prop.getPropertyName() + '_'
        member.xsd_object = prop._xelement
        member.isComplex = False
        member.ctypename = getCppType(prop._xelement.getType())
        prop._memberinfo = member
        self._data_members.append(member)
        
    def Resolve(self, xsdTypeDict, cTypeDict):
        if not self._xelement:
            logger = logging.getLogger('ifmap_model')
            logger.warning('%s not found in xml schema', self.getName())
            return

        self._key_members = self._BuildKeySpec(xsdTypeDict, [],
                                               self.getXsdType())
        self._BuildDataMembers(xsdTypeDict, cTypeDict)

class IFMapMetadata(IFMapObject):
    """ Base class for all metadata elements (properties, links)
    """
    def __init__(self, name):
        super(IFMapMetadata, self).__init__(name)
        self._annotation = None

    def Resolve(self, xsdTypeDict, cTypeDict):
        pass

    @staticmethod
    def Create(name, is_property, annotation, typename):
        if not is_property:
            if typename:
                meta = IFMapLinkAttr(name)
            else:
                meta = IFMapLink(name)
        else:
            meta = IFMapProperty(name, annotation)
        return meta

class IFMapProperty(IFMapMetadata):
    """ Property associated with a single identifier
    """
    def __init__(self, name, idl_info):
        super(IFMapProperty, self).__init__(name)
        self._parent = None
        self._cppname = CamelCase(name)
        self._complexType = None
        self._memberinfo = None
        self._idl_info = idl_info

    def getParent(self):
        return self._parent

    def setParent(self, identifier):
        self._parent = identifier

    def getCppName(self):
        return self._cppname

    def getCType(self):
        return self._complexType

    def getCTypename(self):
        if self._xelement.isComplex():
            return self._complexType.getName()
        return getCppType(self._xelement.getType())

    def getJavaTypename(self):
        if self._xelement.isComplex():
            return self._complexType.getName()
        return getJavaType(self._xelement.getType())

    def getGoLangTypename(self):
        if self._xelement.isComplex():
            return self._complexType.getName()
        return getGoLangType(self._xelement.getType())

    def getMemberInfo(self):
        return self._memberinfo

    def getDependentTypes(self):
        return self._complexType._data_types

    def getDataMembers(self):
        return self._complexType._data_members

    def getPropertyName(self):
        name = self.getCIdentifierName()
        if self._parent == 'all':
           return name

        prefix = self._parent.getCIdentifierName() + '_'
        if name.startswith(prefix):
            name = name[len(prefix):]
        return name

    def getPropertyId(self):
        prop = self.getPropertyName()
        return prop.upper()

    def isList(self):
        idl_prop = self._idl_info[0]
        return idl_prop.IsList() or self._xelement.maxOccurs > 1

    def isListUsingWrapper(self):
        idl_prop = self._idl_info[0]
        return idl_prop.IsList()

    def isMap(self):
        idl_prop = self._idl_info[0]
        return idl_prop.IsMap() or self._xelement.maxOccurs > 1

    def isMapUsingWrapper(self):
        idl_prop = self._idl_info[0]
        return idl_prop.IsMap()

    def getMapKeyName(self):
        idl_prop = self._idl_info[0]
        return idl_prop.map_key_name

    def Resolve(self, xsdTypeDict, cTypeDict):
        xtypename = self.getXsdType()
        self._complexType = ComplexTypeLocate(xsdTypeDict, cTypeDict, xtypename)
        # Ensure a prop-list using wrapper for list
        # has only one element in wrapper
        if (self.isListUsingWrapper() and
            (len(xsdTypeDict[xtypename].children) != 1)):
            err_msg = 'ListProperty %s using incorrect wrapper-type %s' %(
                self._name, xtypename)
            raise Exception(err_msg)


class IFMapLink(IFMapMetadata):
    """ Link metadata with no attributes
    """
    def __init__(self, name):
        super(IFMapLink, self).__init__(name)

    def getCType(self):
        return None

class IFMapLinkAttr(IFMapMetadata):
    """ Link metadata with attributes
    """
    def __init__(self, name):
        super(IFMapLinkAttr, self).__init__(name)
        self._cppname = CamelCase(name)
        self._complexType = None

    def getCppName(self):
        return self._cppname

    def getCType(self):
        return self._complexType

    def getCTypename(self):
        if self._xelement.isComplex():
            return self._complexType.getName()
        return getCppType(self._xelement.getType())

    def Resolve(self, xsdTypeDict, cTypeDict):
        if self._xelement.isComplex():
            self._complexType = ComplexTypeLocate(xsdTypeDict, cTypeDict,
                                                  self.getXsdType())
            if not self._complexType:
                logger = logging.getLogger('ifmap_model')
                logger.warning('%s: type \'%s\' not found in xml schema',
                               self.getName(), xtypename)


def SimpleTypeWrapper(info):
    assert type(info) is MemberInfo
    wtype = info.ctypename
    sep = wtype.rfind("::")
    if sep:
        wtype = wtype[sep + 2:]
    return wtype.capitalize() + 'Property'
