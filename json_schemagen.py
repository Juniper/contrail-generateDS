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
        self._objectsList = []

    #For mapping the js data type given the ctype or jtype
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
            if simple_type:
                 subJson = self.generateRestrictions (simple_type, subJson)
            try:
                subJson["description"] = prop.getDescription()
            except ValueError as detail:
                pass
            propertiesJSON[self._convertHyphensToUnderscores(prop._name)] = subJson

#       Now look for the links and generate respective schema, exclude the children (has relationship) objects
        for link_info in ident.getLinksInfo():
            if ident.isLinkRef(link_info):
                link_to = ident.getLinkTo(link_info)
                linktype = link_info[0]._xelement.type
                if  self._json_type_map.get(linktype):
                    toField = {"type":"array","items":{"type":"string"}}
                    stringField = {"type":"string"}
                    refitems = {"type":"object", "properties":{"to":toField, "href":stringField,"uuid":stringField,"attr":{"type":"object","properties":self._json_type_map[linktype]["properties"]}}}
                    propertiesJSON[link_to.getCIdentifierName()+"_refs"] = {"type":"array", "url" : "/" + link_to.getName() + "s","items":refitems}
                else :
                    propertiesJSON[link_to.getCIdentifierName()+"_refs"] = {"type":"array", "url" : "/" + link_to.getName() + "s"}
#       Then look for back links and create back_ref schema if required

        jsonSchema = {"type":"object", "properties":{ ident._name:{ "type": "object", "properties" : propertiesJSON}}}
        file.write(json.dumps(jsonSchema,indent=4))

    def _getSubJS (self,type,dataMember):
        if (type.lower() == "string" or type.lower() == 'std::string') :
            return {"type":"string"}
        elif (type.lower() == "integer" or type.lower() == "int" or type.lower() == "number") :
            return {"type":"number"}
        elif (type.lower() == "boolean" or type.lower() == "bool") :
            return {"type":"boolean"}
        elif (type.lower().startswith("list")) :
            ret = {"type":"array"}
            if(dataMember.sequenceType == "std::string"):
                ret["items"] = {"type":"string"}
            elif(self._type_map.get(dataMember.sequenceType)) :
                ret["items"] = self._GenerateTypeMap(self._type_map.get(dataMember.sequenceType))
            else:
                ret["items"] = {"type":"string"}
            return ret
        elif (type.lower() == "java.util.date"):
            return {"type":"string"}
        elif (type.lower() == "long"):
            return {"type":"number"}
        else :
            ret = {}
            ret = self._GenerateTypeMap(self._type_map.get(type))
            return ret

    def _GenerateTypeMap(self,ctype):
        self._json_type_map[ctype.getName()] = {"type": "object","properties":{}}
        typeDataMembers = ctype._data_members
        for dataMember in typeDataMembers:
            subJson = self._getSubJS(dataMember.jtypename, dataMember)
            simple_type = dataMember.xsd_object.simpleType
            if(simple_type):
                subJson = self.generateRestrictions (simple_type, subJson)
            if(dataMember.xsd_object.description):
                subJson['description'] = dataMember.xsd_object.description
            if(dataMember.xsd_object.required):
                subJson['required'] = dataMember.xsd_object.required 
            self._json_type_map[ctype.getName()]["properties"][dataMember.membername] = subJson
        return self._json_type_map[ctype.getName()]

    def generateRestrictions (self, simple_type, subJson):
        restrictions = None
        if(self._parser.SimpleTypeDict.get(simple_type)):
            restrictions = self._parser.SimpleTypeDict[simple_type].values
            if (restrictions and len(restrictions) > 0):
                if(type(restrictions[0]) is dict):
                # If it is a dict we assume it to be min max type
                    subJson["minimum"] = restrictions[0]["minimum"]
                    subJson["maximum"] = restrictions[1]["maximum"]
                else:
                    # else they are enum
                    if(subJson["type"] == "array"):
                        if(subJson.get("items")):
                            subJson["items"]["enum"] = restrictions
                        else:
                            subJson["items"] = {}
                            subJson["items"]["enum"] = restrictions
                    else:
                        subJson["enum"] = restrictions
        return subJson

    def Generate(self, dirname):
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        elif not os.path.isdir(dirname):
            print "-o option must specify directory"
            sys.exit(1)
        for ctype in self._type_map.values():
            self._GenerateTypeMap(ctype)
        for ident in self._identifier_map.values():
            self._objectsList.append(ident._name)
            filename = os.path.join(dirname, ident._name + "-schema.json")
            self._GenerateJavascriptSchema(ident, filename)
        #Generate the file containing the list of all identfiers/objects
        objFileName = os.path.join(dirname, "objectList.json")
        objFile = self._parser.makeFile(objFileName)
        objJson = {"objects":self._objectsList}
        objFile.write(json.dumps(objJson,indent=4))
        print "Done!"
        print "Schemas generated under directory: " + dirname

