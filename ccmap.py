#
# Copyright (c) 2013 Juniper Networks, Inc. All rights reserved.
#

import idl_parser
from ifmap_model import IFMapIdentifier, IFMapMetadata, ElementXsdType
from ifmap_classgen import IFMapClassGenerator, IFMapImplGenerator
from ifmap_parser import IFMapParserGenerator
from ifmap_frontend import IFMapApiGenerator
from java_api import JavaApiGenerator
from device_api import DeviceApiGenerator
from golang_api import GoLangApiGenerator
from json_schemagen import JsonSchemaGenerator
from contrail_json_schemagen import ContrailJsonSchemaGenerator
from copy import deepcopy


class IFMapGenerator(object):
    """ IFMap generator
        Step 1. Build a list of data structures to be generated.
        Step 2. Generate C++ classes.
        Step 3. Generate C++ decoder
        Step 4. Generate xsd corresponding to data structures.
    """

    def __init__(self, parser, genCategory):
        self._Parser = parser
        self._idl_parser = None
        self._Identifiers = {}
        self._Metadata = {}
        # elements to be processed after first pass
        self._DeferredElements = []
        self._cTypesDict = {}
        self._genCategory = genCategory

    def _BuildDataModel(self, children):
        for child in children:
            if not child.complexType:
                self._ProcessElement(child)

        # Handle 'all' and any other deferred metadata
        for defer_info in self._DeferredElements:
            (element, annotation) = defer_info
            if self._idl_parser.IsAllProperty(annotation):
                meta = self._MetadataLocate(element, annotation)
                meta.SetSchemaElement(element)
                meta.setParent('all')
                for identifier in self._Identifiers.values():
                    identifier.SetProperty(meta)
            elif self._idl_parser.IsAllLink(annotation):
                (from_name, to_name, attrs) = \
                    self._idl_parser.GetLinkInfo(element.getName())
                to_ident = self._IdentifierLocate(to_name)
                for from_ident in self._Identifiers.values():
                    ann_copy = deepcopy(annotation)
                    ann_copy[0].name = '%s-%s' % (from_ident.getName(),
                                                  to_ident.getName())
                    meta = self.MetadataLocate(
                        ann_copy[0].name, None, ann_copy)
                    meta.SetSchemaElement(element)
                    from_ident.addLinkInfo(meta, to_ident, attrs)
                    to_ident.addBackLinkInfo(meta, from_ident, attrs)

        for idn in self._Identifiers.values():
            idn.Resolve(self._Parser.ElementDict, self._cTypesDict)

        for meta in self._Metadata.values():
            meta.Resolve(self._Parser.ElementDict, self._cTypesDict)

    def _ProcessElement(self, element):
        """ Process an element from the schema. This can be either an
            identifier or meta-data element.
        """
        if element.getSchemaType() == 'IdentityType':
            self._ProcessIdentifier(element)
        else:
            annotation = self._idl_parser.Find(element.getName())
            self._ProcessMetadata(element, annotation)

    def _ProcessIdentifier(self, element):
        identifier = self._IdentifierLocate(element.getName())
        identifier.SetSchemaElement(element)

    def _ProcessMetadata(self, element, annotation):
        if not annotation:
            print "WARNING: no annotation for element " + str(element)
            return

        if self._idl_parser.IsAllProperty(annotation):
            self._DeferredElements.append((element, annotation))
            return
        elif self._idl_parser.IsAllLink(annotation):
            self._DeferredElements.append((element, annotation))
            return

        meta = self._MetadataLocate(element, annotation)
        meta.SetSchemaElement(element)
        if self._idl_parser.IsProperty(annotation):
            for ident_name in annotation[1]:
                identifier = self._IdentifierLocate(ident_name)
                meta.setParent(identifier)
                identifier.SetProperty(meta)
        else:
            (from_name, to_name, attrs) = \
                self._idl_parser.GetLinkInfo(element.getName())
            from_ident = self._IdentifierLocate(from_name)
            to_ident = self._IdentifierLocate(to_name)
            from_ident.addLinkInfo(meta, to_ident, attrs)
            to_ident.addBackLinkInfo(meta, from_ident, attrs)

    def _IdentifierLocate(self, name):
        if name in self._Identifiers:
            return self._Identifiers[name]
        identifier = IFMapIdentifier(name)
        self._Identifiers[name] = identifier
        return identifier

    def _MetadataLocate(self, element, annotation):
        name = element.getName()
        if name in self._Metadata:
            return self._Metadata[name]
        typename = ElementXsdType(element)
        return self.MetadataLocate(name, typename, annotation)

    def MetadataLocate(self, name, typename, annotation):
        if name in self._Metadata:
            return self._Metadata[name]
        # generate a link in case this is an empty complex type.
        if typename and typename in self._Parser.ElementDict:
            xtype = self._Parser.ElementDict[typename]
            if xtype and xtype.isComplex() and len(xtype.getChildren()) == 0:
                typename = None

        meta = IFMapMetadata.Create(name,
                                    self._idl_parser.IsProperty(annotation),
                                    annotation, typename)
        self._Metadata[name] = meta
        return meta

    def _GenerateBackendClassDefinitions(self):
        hfilename = self._Parser.outFilename + '_types.h'
        hfile = self._Parser.makeFile(hfilename)
        classgen = IFMapClassGenerator(self._cTypesDict)
        classgen.Generate(hfile, self._Identifiers, self._Metadata)

    def _GenerateBackendClassImpl(self):
        hfilename = self._Parser.outFilename + '_types.h'
        filename = self._Parser.outFilename + '_types.cc'
        cfile = self._Parser.makeFile(filename)
        classgen = IFMapImplGenerator(self._cTypesDict)
        classgen.Generate(cfile, hfilename, self._Identifiers, self._Metadata)
        filename = self._Parser.outFilename + '_server.cc'
        sfile = self._Parser.makeFile(filename)
        classgen.GenerateServer(sfile, hfilename,
                                self._Identifiers, self._Metadata)
        filename = self._Parser.outFilename + '_client.cc'
        clntfile = self._Parser.makeFile(filename)
        classgen.GenerateClient(clntfile, hfilename,
                                self._Identifiers, self._Metadata)
        filename = self._Parser.outFilename + '_agent.cc'
        clntfile = self._Parser.makeFile(filename)
        classgen.GenerateAgent(clntfile, hfilename,
                               self._Identifiers, self._Metadata)

    def _GenerateBackendParsers(self):
        hfilename = self._Parser.outFilename + '_types.h'
        cfilename = self._Parser.outFilename + '_parser.cc'
        cfile = self._Parser.makeFile(cfilename)
        parsergen = IFMapParserGenerator(self._cTypesDict)
        parsergen.Generate(cfile, hfilename, self._Identifiers, self._Metadata)
        sfilename = self._Parser.outFilename + '_server.cc'
        sfile = open(sfilename, 'a')
        parsergen.GenerateServer(sfile, self._Metadata)
        sfilename = self._Parser.outFilename + '_agent.cc'
        sfile = open(sfilename, 'a')
        parsergen.GenerateAgent(sfile, self._Identifiers, self._Metadata)

    def _GenerateFrontendClassDefinitions(self, xsd_root):
        apigen = IFMapApiGenerator(self._Parser, xsd_root,
                                   self._Identifiers, self._Metadata)
        apigen.Generate(self._Parser.outFilename)

    def _GenerateJavaApi(self, xsd_root):
        apigen = JavaApiGenerator(self._Parser, self._cTypesDict,
                                  self._Identifiers, self._Metadata)
        apigen.Generate(self._Parser.outFilename)

    def _GenerateDeviceApi(self, xsd_root):
        apigen = DeviceApiGenerator(self._Parser, xsd_root,
                                    self._Identifiers, self._Metadata)
        apigen.Generate(self._Parser.outFilename)

    def _GenerateGoLangApi(self, xsd_root):
        apigen = GoLangApiGenerator(self._Parser, self._cTypesDict,
                                    self._Identifiers, self._Metadata)
        apigen.Generate(self._Parser.outFilename)

    def _GenerateJsonSchema(self, xsd_root):
        apigen = JsonSchemaGenerator(self._Parser, self._cTypesDict,
                                     self._Identifiers, self._Metadata)
        apigen.Generate(self._Parser.outFilename)

    def _GenerateContrailJsonSchema(self, xsd_root):
        apigen = ContrailJsonSchemaGenerator(self._Parser, self._cTypesDict,
                                             self._Identifiers, self._Metadata)
        apigen.Generate(self._Parser.outFilename)

    def setLanguage(self, lang):
        pass

    def generate(self, root, infile, outFilename):
        self._idl_parser = idl_parser.IDLParser()
        self._idl_parser.Parse(infile)
        children = root.getChildren()
        self._BuildDataModel(children)
        if self._genCategory == 'ifmap-backend':
            self._GenerateBackendClassDefinitions()
            self._GenerateBackendClassImpl()
            self._GenerateBackendParsers()
        elif self._genCategory == 'ifmap-frontend':
            self._GenerateFrontendClassDefinitions(root)
        elif self._genCategory == 'java-api':
            self._GenerateJavaApi(root)
        elif self._genCategory == 'device-api':
            self._GenerateDeviceApi(root)
        elif self._genCategory == 'golang-api':
            self._GenerateGoLangApi(root)
        elif self._genCategory == 'contrail-json-schema':
            self._GenerateContrailJsonSchema(root)
        elif self._genCategory == 'json-schema':
            self._GenerateJsonSchema(root)
