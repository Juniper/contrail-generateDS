#
# Copyright (c) 2013 Juniper Networks, Inc. All rights reserved.
#

import idl_parser
from type_model import ComplexType, ComplexTypeLocate
from type_classgen import TypeClassGenerator, TypeImplGenerator
from type_parser import TypeParserGenerator

class TypeGenerator(object):
    """ Type generator
        Step 1. Build a list of data structures to be generated.
        Step 2. Generate C++ classes.
        Step 3. Generate C++ decoder
        Step 4. Generate xsd corresponding to data structures.
    """
    def __init__(self, parser):
        self._Parser = parser
        self._idl_parser = None
        self._cTypesDict = {}

    def _BuildDataModel(self, children):
        for child in children:
            xtypename = child.getType()
            self._complexType = ComplexTypeLocate(self._Parser.ElementDict, self._cTypesDict, xtypename)

    def _GenerateClassDefinitions(self):
        hfilename = self._Parser.outFilename + '_types.h'
        hfile = self._Parser.makeFile(hfilename)
        classgen = TypeClassGenerator(self._cTypesDict)
        classgen.Generate(hfile, self._complexType)

    def _GenerateClassImpl(self):
        hfilename = self._Parser.outFilename + '_types.h'
        cfilename = self._Parser.outFilename + '_types.cc'
        cfile = self._Parser.makeFile(cfilename)
        classimpl = TypeImplGenerator(self._cTypesDict)
        classimpl.Generate(hfilename, cfile)

    def _GenerateParsers(self):
        hfilename = self._Parser.outFilename + '_types.h'
        cfilename = self._Parser.outFilename + '_parser.cc'
        cfile = self._Parser.makeFile(cfilename)
        parsergen = TypeParserGenerator(self._cTypesDict)
        parsergen.Generate(cfile, hfilename)
        
    def setLanguage(self, lang):
        pass

    def generate(self, root, infile, outFilename):
        children = root.getChildren()
        self._BuildDataModel(children)
        self._GenerateClassDefinitions()
        self._GenerateClassImpl()
        self._GenerateParsers()
