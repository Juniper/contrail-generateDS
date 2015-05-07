#
# Copyright (c) 2013 Juniper Networks, Inc. All rights reserved.
#

import os
import re
import sys

from ifmap_global import CamelCase, getGoLangType


class GoLangApiGenerator(object):
    def __init__(self, parser, type_map, identifiers, metadata):
        self._parser = parser
        self._type_map = type_map
        self._identifier_map = identifiers
        self._metadata_map = metadata
        self._top_level_map = {}
        self._type_count = {}

    def _GenerateTypeMap(self, dirname):
        file = self._parser.makeFile(os.path.join(dirname, 'types.go'))
        decl = """
package types

import (
        "reflect"

        "github.com/Juniper/contrail-go-api"
)

var (
        TypeMap = map[string]reflect.Type {
"""
        file.write(decl)
        for ident in self._identifier_map.values():
            decl = '\t\t"%s": reflect.TypeOf(%s{}),\n' % \
                   (ident.getName(), ident.getCppName())
            file.write(decl)

        decl = """
        }
)

func init() {
        contrail.RegisterTypeMap(TypeMap)
}
"""
        file.write(decl)

    def _GenerateObject(self, ident, filename):
        """ Generate the class corresponding to an IF-MAP Identifier
        defined in the schema.
        """
        file = self._parser.makeFile(filename)

        header = """//
// Automatically generated. DO NOT EDIT.
//

package types

import (
        "encoding/json"

        "github.com/Juniper/contrail-go-api"
)
"""
        file.write(header)
        self._GenerateConstFlags(ident, file)
        self._GenerateObjectStruct(ident, file)
        self._GenerateGenericMethods(ident, file)
        self._GeneratePropertyMethods(ident, file)
        self._GenerateChildrenMethods(ident, file)
        self._GenerateRefsMethods(ident, file)
        self._GenerateBackRefsMethods(ident, file)
        self._GenerateMarshalJSON(ident, file)
        self._GenerateUnmarshalJSON(ident, file)
        self._GenerateUpdate(ident, file)
        self._GenerateUpdateReferences(ident, file)
        self._GenerateClientAuxMethods(ident, file)

    # end _GenerateObject

    def _GenerateStructType(self, ctype, filename):
        file = self._parser.makeFile(filename)
        header = """//
// Automatically generated. DO NOT EDIT.
//

package types
"""
        file.write(header)

        self._GenerateCType(ctype, file)

    # end _GenerateStructType

    def _GenerateCType(self, ctype, file):
        for deptype in ctype.getDependentTypes():
            if deptype.getName() in self._top_level_map:
                continue
            self._GenerateCType(deptype, file)

        decl = """
type %(camel)s struct {
""" % {'camel': ctype.getName()}
        file.write(decl)
        for member in ctype.getDataMembers():
            camel = CamelCase(member.membername)
            ptrType = False
            if member.isComplex:
                mtype = member.xsd_object.getType()
                if not member.isSequence:
                    ptrType = True
            else:
                mtype = getGoLangType(member.xsd_object.getType())
            if member.isSequence:
                mtype = '[]' + mtype
            decl = '\t%s %s%s `json:"%s,omitempty"`\n' % \
                   (camel, '*' if ptrType else '', mtype, member.membername)
            file.write(decl)
        file.write('}\n')

        # Generate methods (add/delete/clear/set) for sequence fields
        for member in ctype.getDataMembers():
            if not member.isSequence:
                continue
            membertype = member.xsd_object.getType()
            if not member.isComplex:
                membertype = getGoLangType(membertype)
            decl = """
func (obj *%(typecamel)s) Add%(fieldcamel)s(value %(ptr)s%(fieldtype)s) {
        obj.%(member)s = append(obj.%(member)s, %(ptr)svalue)
}
""" \
            % {'typecamel': ctype.getName(),
               'fieldcamel': CamelCase(member.membername),
               'fieldtype': membertype,
               'ptr': '*' if member.isComplex else '',
               'member': CamelCase(member.membername),
               }
            file.write(decl)

    # end _GenerateCType

    def _ExamineInnerTypes(self, inner_type_map, top_level, ctype):
        """ Examine all the dependent types of a given top_level type
        (recursivly) in order to determine which types are referred to
        more than once.
        The ones that are get promoted to top-level.
        """
        for deptype in ctype.getDependentTypes():
            mtype = deptype.getName()
            if mtype in inner_type_map:
                xset = inner_type_map[mtype]
                if top_level not in xset:
                    xset.append(top_level)
            else:
                inner_type_map[mtype] = [top_level]

            self._ExamineInnerTypes(inner_type_map, top_level, deptype)

    def _PromoteInnerTypes(self):
        inner_type_map = {}

        for ctype in self._top_level_map.values():
            self._ExamineInnerTypes(inner_type_map, ctype, ctype)

        while True:
            promoted = []
            for itype, typeset in inner_type_map.iteritems():
                if len(typeset) == 1:
                    continue

                # print "promote %s" % itype
                # for typ in typeset:
                #     print "    %s" % typ.getName()
                self._top_level_map[itype] = self._type_map[itype]
                promoted.append(itype)

            if len(promoted) == 0:
                break

            for itype in promoted:
                del inner_type_map[itype]
                ctype = self._type_map[itype]
                self._ExamineInnerTypes(inner_type_map, ctype, ctype)

    def _IdentifierLinks(self, ident):
        """ Returns the list of all the links (children, refs, back_refs)
        of a specific identifier.
        """
        fields = []
        for link_info in ident.getLinksInfo():
            if ident.isLinkRef(link_info):
                suffix = '_refs'
            elif ident.isLinkHas(link_info):
                suffix = 's'
            else:
                suffix = '_refs'
            link_to = ident.getLinkTo(link_info)
            fields.append(link_to.getCIdentifierName() + suffix)
        for back_link in ident.getBackLinksInfo():
            link_from = ident.getBackLinkFrom(back_link)
            fields.append(link_from.getCIdentifierName() + '_back_refs')

        return fields

    def _GenerateConstFlags(self, ident, file):
        """ Emit a const declaration with a flag per struct field used to
            record which fields have been modified.
        """
        file.write("\nconst (")

        first = True
        fields = [prop.getCIdentifierName() for prop in ident.getProperties()]
        fields.extend(self._IdentifierLinks(ident))

        for field in fields:
            file.write("\n\t%s_%s" % (ident.getCIdentifierName(), field))
            if first:
                file.write(" uint64 = 1 << iota")
                first = False
        file.write("\n)\n")
    # end _GenerateConstFlags

    def _GenerateObjectStruct(self, ident, file):
        """ Generate the golang struct type definition for an Identifier.
        """
        decl = """
type %(camel)s struct {
        contrail.ObjectBase
""" % {"camel": ident.getCppName()}
        file.write(decl)

        for prop in ident.getProperties():
            decl = '\t%s %s\n' % \
                   (prop.getCIdentifierName(), prop.getGoLangTypename())
            file.write(decl)
            ctype = prop.getCType()
            if ctype:
                ctypename = ctype.getName()
                self._top_level_map[ctypename] = self._type_map[ctypename]

        for link_info in ident.getLinksInfo():
            if ident.isLinkHas(link_info):
                child = ident.getLinkTo(link_info)
                decl = '\t%ss contrail.ReferenceList\n' % \
                       child.getCIdentifierName()
                file.write(decl)
            else:
                link_to = ident.getLinkTo(link_info)
                decl = '\t%s_refs contrail.ReferenceList\n' % \
                       link_to.getCIdentifierName()
                file.write(decl)
                datatype = self._getAttrType(ident, link_info)
                if datatype:
                    self._top_level_map[datatype] = self._type_map[datatype]

        for back_link in ident.getBackLinksInfo():
            link_from = ident.getBackLinkFrom(back_link)
            decl = '\t%s_back_refs contrail.ReferenceList\n' % \
                   link_from.getCIdentifierName()
            file.write(decl)

        decl = """        valid uint64
        modified uint64
        originalMap map[string]contrail.ReferenceList
}
"""
        file.write(decl)
    # end _GenerateObjectStruct

    def _GenerateGenericMethods(self, ident, file):
        """ Methods that do not iterate through the Identifier's fields.
        """
        parent_fqn = ""
        parent_type = ""
        parents = ident.getParents()
        if parents:
            (parent, meta) = parents[0]
            quoted_list = map(lambda x: '"%s"' % x, parent.getDefaultFQName())
            parent_fqn = ', '.join(quoted_list)
            parent_type = parent.getName()

        decl = """
func (obj *%(camel)s) GetType() string {
        return "%(typename)s"
}

func (obj *%(camel)s) GetDefaultParent() []string {
        name := []string{%(parent_fqn)s}
        return name
}

func (obj *%(camel)s) GetDefaultParentType() string {
        return "%(parent_type)s"
}

func (obj *%(camel)s) SetName(name string) {
        obj.VSetName(obj, name)
}

func (obj *%(camel)s) SetParent(parent contrail.IObject) {
        obj.VSetParent(obj, parent)
}

func (obj *%(camel)s) addChange(
        name string, refList contrail.ReferenceList) {
        if obj.originalMap == nil {
                obj.originalMap = make(map[string]contrail.ReferenceList)
        }
        var refCopy contrail.ReferenceList
        copy(refCopy, refList)
        obj.originalMap[name] = refCopy
}

func (obj *%(camel)s) UpdateDone() {
        obj.modified = 0
        obj.originalMap = nil
}

""" \
        % {"camel": ident.getCppName(),
           "typename": ident.getName(),
           "parent_fqn": parent_fqn,
           "parent_type": parent_type
           }
        file.write(decl)
    # _GenerateGenericMethods

    def _GeneratePropertyMethods(self, ident, file):
        for prop in ident.getProperties():
            decl = """
func (obj *%(typecamel)s) Get%(fieldcamel)s() %(fieldtype)s {
        return obj.%(fieldid)s
}

func (obj *%(typecamel)s) Set%(fieldcamel)s(value %(ptr)s%(fieldtype)s) {
        obj.%(fieldid)s = %(ptr)svalue
        obj.modified |= %(typeid)s_%(fieldid)s
}
""" \
            % {'typecamel': ident.getCppName(),
               'typeid': ident.getCIdentifierName(),
               'fieldcamel': prop.getCppName(),
               'fieldid': prop.getCIdentifierName(),
               'fieldtype': prop.getGoLangTypename(),
               'ptr': '*' if prop.getCType() else ''
               }
            file.write(decl)
    # end _GeneratePropertyMethods

    def _GenerateChildrenMethods(self, ident, file):
        for link_info in ident.getLinksInfo():
            if not ident.isLinkHas(link_info):
                continue
            child = ident.getLinkTo(link_info)
            self._GenerateReferenceRead(ident, child, 's', file)
            self._GenerateReferenceAccessor(ident, child, "s", file)

    # end _GenerateChildrenMethods

    def _GenerateRefsMethods(self, ident, file):
        for link_info in ident.getLinksInfo():
            if not ident.isLinkRef(link_info):
                continue
            link_to = ident.getLinkTo(link_info)
            self._GenerateReferenceRead(ident, link_to, '_refs', file)
            self._GenerateReferenceAccessor(ident, link_to, '_refs', file)
            self._GenerateReferenceModifiers(ident, link_info, file)

    # end _GenerateRefsMethods

    def _GenerateBackRefsMethods(self, ident, file):
        for back_link in ident.getBackLinksInfo():
            link_from = ident.getBackLinkFrom(back_link)
            self._GenerateReferenceRead(ident, link_from, '_back_refs', file)
            self._GenerateReferenceAccessor(ident, link_from, '_back_refs',
                                            file)
    # end _GenerateBackRefsMethods

    def _MethodSuffix(self, suffix):
        expr = re.compile(r'_([a-z])')
        return expr.sub(lambda x: x.group(1).upper(), suffix)

    def _GenerateReferenceRead(self, ident, ref, suffix, file):
        decl = """
func (obj *%(typecamel)s) read%(fieldcamel)s%(methodsuffix)s() error {
        if !obj.IsTransient() &&
                (obj.valid & %(typeid)s_%(fieldid)s%(suffix)s == 0) {
                err := obj.GetField(obj, "%(fieldid)s%(suffix)s")
                if err != nil {
                        return err
                }
        }
        return nil
}
""" \
        % {'typecamel': ident.getCppName(),
           'fieldcamel': ref.getCppName(),
           'typeid': ident.getCIdentifierName(),
           'fieldid': ref.getCIdentifierName(),
           'methodsuffix': self._MethodSuffix(suffix),
           'suffix': suffix
           }
        file.write(decl)

    # end _GenerateReferenceRead

    def _GenerateReferenceAccessor(self, ident, ref, suffix, file):
        decl = """
func (obj *%(typecamel)s) Get%(fieldcamel)s%(methodsuffix)s() (
        contrail.ReferenceList, error) {
        err := obj.read%(fieldcamel)s%(methodsuffix)s()
        if err != nil {
                return nil, err
        }
        return obj.%(fieldid)s%(suffix)s, nil
}
""" \
        % {'typecamel': ident.getCppName(),
           'fieldcamel': ref.getCppName(),
           'fieldid': ref.getCIdentifierName(),
           'methodsuffix': self._MethodSuffix(suffix),
           'suffix': suffix,
           }
        file.write(decl)
    # end _GenerateReferenceAccessor

    def _getAttrType(self, ident, link_info):
        xlink = ident.getLink(link_info)
        if xlink.getXsdType():
            ctype = xlink.getCType()
            if ctype is not None:
                return ctype.getName()
        return None

    def _GenerateReferenceModifiers(self, ident, link_info, file):
        """ Generate add/delete/clear and set methods.
        """
        datatype = self._getAttrType(ident, link_info)
        link_to = ident.getLinkTo(link_info)

        decl = """
func (obj *%(typecamel)s) Add%(fieldcamel)s(
        rhs *%(fieldcamel)s%(datatype)s) error {
        err := obj.read%(fieldcamel)sRefs()
        if err != nil {
                return err
        }

        if obj.modified & %(typeid)s_%(fieldid)s_refs == 0 {
                obj.addChange("%(fieldname)s", obj.%(fieldid)s_refs)
        }

        ref := contrail.Reference {
                rhs.GetFQName(), rhs.GetUuid(), rhs.GetHref(), %(data)s}
        obj.%(fieldid)s_refs = append(obj.%(fieldid)s_refs, ref)
        obj.modified |= %(typeid)s_%(fieldid)s_refs
        return nil
}

func (obj *%(typecamel)s) Delete%(fieldcamel)s(uuid string) error {
        err := obj.read%(fieldcamel)sRefs()
        if err != nil {
                return err
        }

        if obj.modified & %(typeid)s_%(fieldid)s_refs == 0 {
                obj.addChange("%(fieldname)s", obj.%(fieldid)s_refs)
        }

        for i, ref := range obj.%(fieldid)s_refs {
                if ref.Uuid == uuid {
                        obj.%(fieldid)s_refs = append(
                                obj.%(fieldid)s_refs[:i],
                                obj.%(fieldid)s_refs[i+1:]...)
                        break
                }
        }
        obj.modified |= %(typeid)s_%(fieldid)s_refs
        return nil
}

func (obj *%(typecamel)s) Clear%(fieldcamel)s() {
        if obj.valid & %(typeid)s_%(fieldid)s_refs != 0 {
                obj.addChange("%(fieldname)s", obj.%(fieldid)s_refs)
        } else {
                obj.addChange("%(fieldname)s", contrail.ReferenceList{})
        }
        obj.%(fieldid)s_refs = make([]contrail.Reference, 0)
        obj.valid |= %(typeid)s_%(fieldid)s_refs
        obj.modified |= %(typeid)s_%(fieldid)s_refs
}

func (obj *%(typecamel)s) Set%(fieldcamel)sList(
        refList []contrail.ReferencePair) {
        obj.Clear%(fieldcamel)s()
        obj.%(fieldid)s_refs = make([]contrail.Reference, len(refList))
        for i, pair := range refList {
                obj.%(fieldid)s_refs[i] = contrail.Reference {
                        pair.Object.GetFQName(),
                        pair.Object.GetUuid(),
                        pair.Object.GetHref(),
                        pair.Attribute,
                }
        }
}

""" \
        % {'typecamel': ident.getCppName(),
           'typeid': ident.getCIdentifierName(),
           'fieldcamel': link_to.getCppName(),
           'fieldid': link_to.getCIdentifierName(),
           'fieldname': link_to.getName(),
           'datatype': ', data %s' % datatype if datatype else '',
           'data': 'data' if datatype else 'nil',
           }
        file.write(decl)
    # end _GenerateReferenceModifiers

    def _GenerateMarshalJSON(self, ident, file):
        decl = """
func (obj *%(camel)s) MarshalJSON() ([]byte, error) {
        msg := map[string]*json.RawMessage {
        }
        err := obj.MarshalCommon(msg)
        if err != nil {
                return nil, err
        }
""" % {'camel': ident.getCppName()}
        file.write(decl)

        for prop in ident.getProperties():
            decl = """
        if obj.modified & %(typeid)s_%(fieldid)s != 0 {
                var value json.RawMessage
                value, err := json.Marshal(&obj.%(fieldid)s)
                if err != nil {
                        return nil, err
                }
                msg["%(fieldid)s"] = &value
        }
""" \
            % {'typeid': ident.getCIdentifierName(),
               'fieldid': prop.getCIdentifierName()}
            file.write(decl)

        for link_info in ident.getLinksInfo():
            if not ident.isLinkRef(link_info):
                continue
            link_to = ident.getLinkTo(link_info)
            decl = """
        if len(obj.%(fieldid)s_refs) > 0 {
                var value json.RawMessage
                value, err := json.Marshal(&obj.%(fieldid)s_refs)
                if err != nil {
                        return nil, err
                }
                msg["%(fieldid)s_refs"] = &value
        }
""" % {'fieldid': link_to.getCIdentifierName()}
            file.write(decl)

        decl = """
        return json.Marshal(msg)
}
"""
        file.write(decl)

    # end _GenerateMarshalJSON

    def _GenerateUnmarshalJSON(self, ident, file):
        decl = """
func (obj *%(camel)s) UnmarshalJSON(body []byte) error {
        var m map[string]json.RawMessage
        err := json.Unmarshal(body, &m)
        if err != nil {
                return err
        }
        err = obj.UnmarshalCommon(m)
        if err != nil {
                return err
        }
        for key, value := range m {
                switch key {""" % {'camel': ident.getCppName()}
        file.write(decl)

        fields = [prop.getCIdentifierName() for prop in ident.getProperties()]
        typedrefs = []
        for link_info in ident.getLinksInfo():
            if ident.isLinkRef(link_info):
                suffix = '_refs'
            elif ident.isLinkHas(link_info):
                suffix = 's'
            else:
                suffix = '_refs'
            link_to = ident.getLinkTo(link_info)
            name = link_to.getCIdentifierName() + suffix
            attrtype = self._getAttrType(ident, link_info)
            if attrtype:
                typedrefs.append((name, attrtype))
            else:
                fields.append(name)

        for back_link in ident.getBackLinksInfo():
            link_from = ident.getBackLinkFrom(back_link)
            name = link_from.getCIdentifierName() + '_back_refs'
            attrtype = self._getAttrType(ident, back_link)
            if attrtype:
                typedrefs.append((name, attrtype))
            else:
                fields.append(name)

        for field in fields:
            decl = """
                case "%(field)s":
                        err = json.Unmarshal(value, &obj.%(field)s)
                        if err == nil {
                                obj.valid |= %(typeid)s_%(field)s
                        }
                        break""" % {'typeid': ident.getCIdentifierName(),
                                    'field': field}
            file.write(decl)

        for field, attrtype in typedrefs:
            decl = """
                case "%(field)s": {
                        type ReferenceElement struct {
                                To []string
                                Uuid string
                                Href string
                                Attr %(typename)s
                        }
                        var array []ReferenceElement
                        err = json.Unmarshal(value, &array)
                        if err != nil {
                            break
                        }
                        obj.valid |= %(typeid)s_%(field)s
                        obj.%(field)s = make(contrail.ReferenceList, 0)
                        for _, element := range array {
                                ref := contrail.Reference {
                                        element.To,
                                        element.Uuid,
                                        element.Href,
                                        element.Attr,
                                }
                                obj.%(field)s = append(obj.%(field)s, ref)
                        }
                        break
                }""" % {'typeid': ident.getCIdentifierName(),
                        'field': field, 'typename': attrtype}
            file.write(decl)

        decl = """
                }
                if err != nil {
                        return err
                }
        }
        return nil
}
"""
        file.write(decl)
    # end _GenerateUnmarshalJSON

    def _GenerateUpdate(self, ident, file):
        """
        """
        decl = """
func (obj *%(camel)s) UpdateObject() ([]byte, error) {
        msg := map[string]*json.RawMessage {
        }
        err := obj.MarshalId(msg)
        if err != nil {
                return nil, err
        }
""" % {'camel': ident.getCppName()}
        file.write(decl)

        for prop in ident.getProperties():
            decl = """
        if obj.modified & %(typeid)s_%(fieldid)s != 0 {
                var value json.RawMessage
                value, err := json.Marshal(&obj.%(fieldid)s)
                if err != nil {
                        return nil, err
                }
                msg["%(fieldid)s"] = &value
        }
""" \
            % {'typeid': ident.getCIdentifierName(),
               'fieldid': prop.getCIdentifierName()}
            file.write(decl)

        for link_info in ident.getLinksInfo():
            if not ident.isLinkRef(link_info):
                continue
            link_to = ident.getLinkTo(link_info)
            decl = """
        if obj.modified & %(typeid)s_%(fieldid)s_refs != 0 {
                if len(obj.%(fieldid)s_refs) == 0 {
                        var value json.RawMessage
                        value, err := json.Marshal(
                                          make([]contrail.Reference, 0))
                        if err != nil {
                                return nil, err
                        }
                        msg["%(fieldid)s_refs"] = &value
                } else {
                        prev := obj.originalMap["%(fieldname)s"]
                        if len(prev) == 0 {
                                var value json.RawMessage
                                value, err := json.Marshal(
                                        &obj.%(fieldid)s_refs)
                                if err != nil {
                                        return nil, err
                                }
                                msg["%(fieldid)s_refs"] = &value
                        }
                }
        }

""" \
            % {'typeid': ident.getCIdentifierName(),
               'fieldid': link_to.getCIdentifierName(),
               'fieldname': link_to.getName()}
            file.write(decl)

        decl = """
        return json.Marshal(msg)
}
"""
        file.write(decl)

    # end _GenerateUpdate

    def _GenerateUpdateReferences(self, ident, file):
        """ Method that triggers the generation of ref-update requests.

        For any reference list marked as modified, generate the delta
        between current and original data via ObjectBase.UpdateReference.
        """
        decl = """
func (obj *%(camel)s) UpdateReferences() error {
""" % {'camel': ident.getCppName()}
        file.write(decl)
        for link_info in ident.getLinksInfo():
            if not ident.isLinkRef(link_info):
                continue
            link_to = ident.getLinkTo(link_info)
            decl = """
        if obj.modified & %(typeid)s_%(fieldid)s_refs != 0 {
                err := obj.UpdateReference(
                        obj, "%(fieldname)s",
                        obj.%(fieldid)s_refs,
                        obj.originalMap["%(fieldname)s"])
                if err != nil {
                        return err
                }
        }
""" \
            % {'typeid': ident.getCIdentifierName(),
               'fieldid': link_to.getCIdentifierName(),
               'fieldname': link_to.getName()}
            file.write(decl)

        decl = """
        return nil
}
"""
        file.write(decl)

    # end _GenerateUpdateReferences

    def _GenerateClientAuxMethods(self, ident, file):
        """
        ApiClient methods that return a struct type rather than an interface.
        """
        decl = """
func %(camel)sByName(c contrail.ApiClient, fqn string) (*%(camel)s, error) {
    obj, err := c.FindByName("%(typeid)s", fqn)
    if err != nil {
        return nil, err
    }
    return obj.(*%(camel)s), nil
}

func %(camel)sByUuid(c contrail.ApiClient, uuid string) (*%(camel)s, error) {
    obj, err := c.FindByUuid("%(typeid)s", uuid)
    if err != nil {
        return nil, err
    }
    return obj.(*%(camel)s), nil
}
""" % {'camel': ident.getCppName(), 'typeid': ident.getName()}
        file.write(decl)
    # end _GenerateClientAuxMethods

    def Generate(self, dirname):
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        elif not os.path.isdir(dirname):
            print "-o option must specify directory"
            sys.exit(1)

        self._GenerateTypeMap(dirname)

        for ident in self._identifier_map.values():
            filename = os.path.join(
                dirname, ident.getCIdentifierName() + ".go")
            self._GenerateObject(ident, filename)

        self._PromoteInnerTypes()

        for ctype in self._top_level_map.values():
            filename = os.path.join(
                dirname, ctype.getCIdentifierName() + ".go")
            self._GenerateStructType(ctype, filename)
