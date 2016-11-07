#
# Copyright (c) 2016 Juniper Networks, Inc. All rights reserved.
#

import os
import re
import json

class JsonSchemaGenerator(object):
    def __init__(self, parser, type_map, identifiers, metadata):
        self._parser = parser
        self._type_map = type_map
        self._top_level_map = {
            'SubnetType': self._type_map['SubnetType']
            }
        self._identifier_map = identifiers
        self._metadata_map = metadata
        self._type_count = {}
        #map which will hold the schema for the types which will be generated below
        self._json_type_map = {}


    def _getJSDataType (self,type):
        if (type.lower() == "string" or type.lower() == 'std::string') :
            return "string"
        elif (type.lower() == "integer" or type.lower() == "int") :
            return "number"
        elif (type.lower() == "number") :
            return "number"
        elif (type.lower() == "boolean" or type.lower() == "bool") :
            return "boolean"
        elif (type.lower().startswith("list")) :
            return "array"
        else :
            return "object"


    def _convertHyphensToUnderscores(self, str):
        return str.replace("-", "_")

    def _GenerateJavascriptSchema(self, ident, filename):
        file = self._parser.makeFile(filename)
        propertiesJSON = {}
        #Get the parent type and add to properties
        parents = ident.getParents()
        parent_types = []
        if parents:
            for parent in parents:
                (parnt, meta) = parent
                parent_types.append(parnt.getName())
        propertiesJSON["parent_type"] = {"type":"string","required":"required","enum" : parent_types}
        identProperties = ident.getProperties()
#        First loop through the direct properties and generate the schema
        for prop in identProperties :
            propMemberInfo = prop._memberinfo
            propType = self._getJSDataType(propMemberInfo.ctypename)
            xelementType = prop._xelement.type
            presence = prop.getPresence()
            simple_type = prop.getElement().getSimpleType()
            restrictions = None
            if simple_type:
                restrictions = self._parser.SimpleTypeDict[prop.getElement().getSimpleType()].values
            propSchema = {}
            if propType == "object" :
                if  self._json_type_map.get(xelementType):
                    propSchema = self._json_type_map[xelementType]
                    subJson = propSchema
                else :
                    subJson = {"type" : propType}
            else :
                subJson = {"type" : propType}
            subJson["required"] = presence
            # TODO need to identify the type and restriction and add
            # appropriately
#                 if (restrictions):
#                     subJson["enum"] = restrictions
            try:
                subJson["description"] = prop.getDescription()
            except ValueError as detail:
                print "Warning: Description not found"
            propertiesJSON[self._convertHyphensToUnderscores(prop._name)] = subJson

#       Now look for the links and generate respective schema, exclude the children (has relation) objects
        for link_info in ident.getLinksInfo():
#             link_type = getLinkInfoType(ident, link_info)
            if ident.isLinkRef(link_info):
                link_to = ident.getLinkTo(link_info)
                propertiesJSON[link_to.getCIdentifierName()+"_refs"] = {"type":"array", "url" : "/" + link_to.getName() + "s"}
#       Then look for back links and create back_ref schema if required

        jsonSchema = {"type":"object", "properties":{ ident._name:{ "type": "object", "properties" : propertiesJSON}}}
        file.write(json.dumps(jsonSchema,indent=4))

    def _GenerateTypeMap(self,ctype):
        self._json_type_map[ctype.getName()] = {"type": "object","properties":{}}
        typeDataMembers = ctype._data_members
        for dataMember in typeDataMembers:
            self._json_type_map[ctype.getName()]["properties"][dataMember.membername] = {"type":self._getJSDataType(dataMember.jtypename)}
            if(dataMember.xsd_object.description):
                self._json_type_map[ctype.getName()]["properties"][dataMember.membername]['description'] = dataMember.xsd_object.description
            if(dataMember.xsd_object.required):
                self._json_type_map[ctype.getName()]["properties"][dataMember.membername]['required'] = dataMember.xsd_object.required


    def Generate(self, dirname):
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        elif not os.path.isdir(dirname):
            print "-o option must specify directory"
            sys.exit(1)
        for ctype in self._type_map.values():
                self._GenerateTypeMap(ctype)
        for ident in self._identifier_map.values():
            filename = os.path.join(dirname, ident._name + "-schema.json")
            self._GenerateJavascriptSchema(ident, filename)
        print "Done! Schemas under directory: " + dirname

