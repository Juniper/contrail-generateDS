#!/usr/bin/env python

import idl_parser
from type_model import ComplexType, ComplexTypeLocate
from ServiceGenerator import ServiceApiGenerator

class ServiceGenerator(object):
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

    def _GenerateClassDefinitions(self, xsd_root):
        if self._LangType == 'py':
            apigen = ServiceApiGenerator(self._Parser, xsd_root)
            apigen.setLanguage(self._LangType)
            apigen.Generate(self._Parser.outFilename)
            #apigen.generate(xsd_root, None, self._Parser.outFilename + ".py",
            #                genStandAlone = False)

    def setLanguage(self, lang):
        self._LangType = lang
        pass

    def generate(self, root, infile, outFilename):
        children = root.getChildren()
        self._BuildDataModel(children)
        self._GenerateClassDefinitions(root)
