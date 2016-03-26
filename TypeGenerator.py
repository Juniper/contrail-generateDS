import os
import time
import logging
import textwrap
from pprint import pformat

class TypeGenerator(object):
    def __init__(self, parser_generator):
        self._PGenr = parser_generator
        self._genStandAlone = True

    def setLanguage(self, lang):
        if (lang == 'py'):
            self._LangGenr = PyGenerator(self._PGenr)
        elif (lang == 'c++'):
            self._LangGenr = CppGenerator(self._PGenr)

    def generate(self, root, infile, outfileName, genStandAlone = True):
        self._genStandAlone = genStandAlone
        # Create an output file.
        # Note that even if the user does not request an output file,
        #   we still need to go through the process of generating classes
        #   because it produces data structures needed during generation of
        #   subclasses.
        outfile = None
        if outfileName:
            outfile = self._PGenr.makeFile(outfileName)
        if not outfile:
            outfile = os.tmpfile()
        wrt = outfile.write
        processed = []

        if genStandAlone:
            self._LangGenr.generateHeader(wrt, self._PGenr.prefix)
        #generateSimpleTypes(outfile, prefix, SimpleTypeDict)
        self._PGenr.DelayedElements = []
        self._PGenr.DelayedElements_subclass = []
        elements = root.getChildren()
        outfile.write('"""\n')
        outfile.write("This module defines the classes for types defined in :doc:`vnc_cfg.xsd`\n")
        outfile.write('"""\n')
        outfile.write("import json\n")
        outfile.write("from generatedssuper import *\n")
        self._generateFromTree(wrt, self._PGenr.prefix, elements, processed)
        while 1:
            if len(self._PGenr.DelayedElements) <= 0:
                break
            element = self._PGenr.DelayedElements.pop()
            name = element.getCleanName()
            if name not in processed:
                processed.append(name)
                self._generateClasses(wrt, prefix, element, 1)
        #
        # Generate the elements that were postponed because we had not
        #   yet generated their base class.
        while 1:
            if len(self._PGenr.PostponedExtensions) <= 0:
                break
            element = self._PGenr.PostponedExtensions.pop()
            parentName, parent = self._PGenr.getParentName(element)
            if parentName:
                if (parentName in self._PGenr.AlreadyGenerated or 
                    parentName in self._PGenr.SimpleTypeDict.keys()):
                    self._generateClasses(wrt, prefix, element, 1)
                else:
                    self._PGenr.PostponedExtensions.insert(0, element)
        #
        # Disable the generation of SAX handler/parser.
        # It failed when we stopped putting simple types into ElementDict.
        # When there are duplicate names, the SAX parser probably does
        #   not work anyway.
        #NN self._generateMain(outfile, self._PGenr.prefix, root)
        if genStandAlone:
            self._LangGenr.generateMain(outfile, self._PGenr.prefix, root)
        outfile.close()
        if self._PGenr.subclassFilename:
            self._generateSubclasses(root, self._PGenr.subclassFilename, behaviorFilename,
                prefix, superModule)

        # Generate __all__.  When using the parser as a module it is useful
        # to isolate important classes from internal ones. This way one
        # can do a reasonably safe "from parser import *"
        if outfileName: 
            exportableClassList = ['"%s"' % self._PGenr.mapName(self._PGenr.cleanupName(name)) 
                for name in self._PGenr.AlreadyGenerated]
            exportableClassList.sort()
            exportableClassNames = ',\n    '.join(exportableClassList)
            exportLine = "\n__all__ = [\n    %s\n    ]\n" % exportableClassNames
            outfile = open(outfileName, "a")
            outfile.write(exportLine)
            outfile.close()

    def _generateMain(self, outfile, prefix, root):
        name = self._PGenr.RootElement or root.getChildren()[0].getName()
        elType = self._PGenr.cleanupName(root.getChildren()[0].getType())
        if self._PGenr.RootElement:
            rootElement = self._PGenr.RootElement
        else:
            rootElement = elType
        params = {
            'prefix': prefix,
            'cap_name': self._PGenr.cleanupName(self._PGenr.make_gs_name(name)),
            'name': name,
            'cleanname': self._PGenr.cleanupName(name),
            'module_name': os.path.splitext(os.path.basename(outfile.name))[0],
            'root': rootElement,
            'namespacedef': self._PGenr.Namespacedef,
            }
        s1 = self._PGenr.TEMPLATE_MAIN % params
        outfile.write(s1)

    def _generateFromTree(self, wrt, prefix, elements, processed):
        for element in elements:
            name = element.getCleanName()
            if 1:     # if name not in processed:
                processed.append(name)
                self._generateClasses(wrt, prefix, element, 0)
                children = element.getChildren()
                if children:
                    self._generateFromTree(wrt, prefix, element.getChildren(), processed)

    def _generateClasses(self, wrt, prefix, element, delayed):
        if not element.isComplex() or not element.complexType:
            return
        logging.debug("Generating class for: %s" % element)
        parentName, base = self._PGenr.getParentName(element)
        logging.debug("Element base: %s" % base)
        if not element.isExplicitDefine():
            logging.debug("Not an explicit define, returning.")
            return
        # If this element is an extension (has a base) and the base has
        #   not been generated, then postpone it.
        if parentName:
            if (parentName not in self._PGenr.AlreadyGenerated and
                parentName not in self._PGenr.SimpleTypeDict.keys()):
                self._PGenr.PostponedExtensions.append(element)
                return
        if element.getName() in self._PGenr.AlreadyGenerated:
            return
        self._PGenr.AlreadyGenerated.append(element.getName())
        if element.getMixedExtensionError():
            err_msg('*** Element %s extension chain contains mixed and non-mixed content.  Not generated.\n' % (
                element.getName(), ))
            return
        self._PGenr.ElementsForSubclasses.append(element)
        name = element.getCleanName()
        self._LangGenr.generateClassDefLine(wrt, parentName, prefix, name)
        # If this element has documentation, generate a doc-string.
        if element.documentation:
            self._LangGenr.generateElemDoc(wrt, element)
        if self._PGenr.UserMethodsModule or self._PGenr.MemberSpecs:
            self._LangGenr.generateMemberSpec(wrt, element)
        #LG wrt('    subclass = None\n')
        parentName, parent = self._PGenr.getParentName(element)
        superclass_name = 'None'
        if parentName and parentName in self._PGenr.AlreadyGenerated:
            superclass_name = self._PGenr.mapName(self._PGenr.cleanupName(parentName))
        self._LangGenr.generateSubSuperInit(wrt, superclass_name)
        self._LangGenr._generateAttrMetadata(wrt, element)
        s4 = self._LangGenr.generateCtor(wrt, element)
        self._LangGenr.generateFactory(wrt, prefix, name)
        self._generateGettersAndSetters(wrt, element)
        self._LangGenr.generateComparators(wrt, element)
        self._LangGenr._generateTestHelpers (wrt, element)
        if self._PGenr.Targetnamespace in self._PGenr.NamespacesDict:
            namespace = self._PGenr.NamespacesDict[self._PGenr.Targetnamespace]
        else:
            namespace = ''
        self._generateExportFn(wrt, prefix, element, namespace)
        self._generateExportLiteralFn(wrt, prefix, element)
        self._generateExportDictFn(wrt, prefix, element)
        self._generateBuildFn(wrt, prefix, element, delayed)
        self._generateUserMethods(wrt, element)
        self._LangGenr.generateEnd(wrt, name, s4)
    # end _generateClasses

    def _generateGettersAndSetters(self, wrt, element):
        generatedSimpleTypes = []
        childCount = self._PGenr.countChildren(element, 0)
        for child in element.getChildren():
            if child.getType() == self._PGenr.AnyTypeIdentifier:
                self._LangGenr.generateGetterAnyType(wrt)
                self._LangGenr.generateSetterAnyType(wrt)
                if child.getMaxOccurs() > 1:
                    self._LangGenr.generateAdderAnyType(wrt)
                    self._LangGenr.generateInserterAnyType(wrt)
            else:
                name = self._PGenr.cleanupName(child.getCleanName())
                unmappedName = self._PGenr.cleanupName(child.getName())
                capName = self._PGenr.make_gs_name(unmappedName)
                getMaxOccurs = child.getMaxOccurs()
                childType = child.getType()
                self._LangGenr.generateGetter(wrt, capName, name, childType)
                self._LangGenr.generateSetter(wrt, capName, name, childType)
                if child.getMaxOccurs() > 1:
                    self._LangGenr.generateAdder(wrt, capName, name)
                    self._LangGenr.generateInserter(wrt, capName, name)
                    self._LangGenr.generateDeleter(wrt, capName, name)
                if self._PGenr.GenerateProperties:
                    self._LangGenr.generateProperty(wrt, unmappedName, capName, name)
                #
                # If this child is defined in a simpleType, then generate
                #   a validator method.
                typeName = None
                name = self._PGenr.cleanupName(child.getName())
                mappedName = self._PGenr.mapName(name)
                childType = child.getType()
                childType1 = child.getSimpleType()
                if not child.isComplex() and childType1 and childType1 in self._PGenr.SimpleTypeDict:
                  childType = self._PGenr.SimpleTypeDict[childType1].getBase()
                elif mappedName in self._PGenr.ElementDict:
                  childType = self._PGenr.ElementDict[mappedName].getType()
                typeName = child.getSimpleType()
                if (typeName and
                    typeName in self._PGenr.SimpleTypeDict and
                    typeName not in generatedSimpleTypes):
                    generatedSimpleTypes.append(typeName)
                    self._LangGenr.generateValidator(wrt, typeName)
        attrDefs = element.getAttributeDefs()
        for key in attrDefs:
            attrDef = attrDefs[key]
            name = self._PGenr.cleanupName(attrDef.getName().replace(':', '_'))
            mappedName = self._PGenr.mapName(name)
            gsName = self._PGenr.make_gs_name(name)
            self._LangGenr.generateGetter(wrt, gsName, mappedName)
            self._LangGenr.generateSetter(wrt, gsName, mappedName)
            if self._PGenr.GenerateProperties:
                self._LangGenr.generateProperty(wrt, name, gsName, gsName)
            typeName = attrDef.getType()
            if (typeName and
                typeName in self._PGenr.SimpleTypeDict and
                typeName not in generatedSimpleTypes):
                generatedSimpleTypes.append(typeName)
                self._LangGenr.generateValidator(wrt, typeName)
    
        #LG TODO put in lang specific parts for these if needed
        if element.getSimpleContent() or element.isMixed():
            wrt('    def get%s_(self): return self.valueOf_\n' % (
                self._PGenr.make_gs_name('valueOf'), ))
            wrt('    def set%s_(self, valueOf_): self.valueOf_ = valueOf_\n' % (
                self._PGenr.make_gs_name('valueOf'), ))
        if element.getAnyAttribute():
            wrt('    def get%s_(self): return self.anyAttributes_\n' % (
                self._PGenr.make_gs_name('anyAttributes'), ))
            wrt('    def set%s_(self, anyAttributes_): self.anyAttributes_ = anyAttributes_\n' % (
                self._PGenr.make_gs_name('anyAttributes'), ))
        if element.getExtended():
            wrt('    def get%s_(self): return self.extensiontype_\n' % (
                self._PGenr.make_gs_name('extensiontype'), ))
            wrt('    def set%s_(self, extensiontype_): self.extensiontype_ = extensiontype_\n' % (
                self._PGenr.make_gs_name('extensiontype'), ))

    def _generateSubclasses(root, subclassFilename, behaviorFilename,
            prefix, superModule='xxx'):
        name = root.getChildren()[0].getName()
        subclassFile = makeFile(subclassFilename)
        wrt = subclassFile.write
        if subclassFile:
            # Read in the XMLBehavior file.
            xmlbehavior = None
            behaviors = None
            baseUrl = None
            if behaviorFilename:
                try:
                    # Add the currect working directory to the path so that
                    #   we use the user/developers local copy.
                    sys.path.insert(0, '.')
                    import xmlbehavior_sub as xmlbehavior
                except ImportError:
                    err_msg('*** You have requested generation of extended methods.\n')
                    err_msg('*** But, no xmlbehavior module is available.\n')
                    err_msg('*** Generation of extended behavior methods is omitted.\n')
                if xmlbehavior:
                    behaviors = xmlbehavior.parse(behaviorFilename)
                    behaviors.make_class_dictionary(self._PGenr.cleanupName)
                    baseUrl = behaviors.getBase_impl_url()
            wrt = subclassFile.write
            tstamp = (not NoDates and time.ctime()) or ''
            if NoVersion:
                version = ''
            else:
                version = ' version %s' % VERSION
            wrt(TEMPLATE_SUBCLASS_HEADER % (tstamp, version,
                superModule, ExternalEncoding, ))
            for element in self._PGenr.ElementsForSubclasses:
                generateSubclass(wrt, element, prefix, xmlbehavior, behaviors, baseUrl)
            name = root.getChildren()[0].getName()
            elType = self._PGenr.cleanupName(root.getChildren()[0].getType())
            if self._PGenr.RootElement:
                rootElement = self._PGenr.RootElement
            else:
                rootElement = elType
            params = {
                'cap_name': self._PGenr.make_gs_name(self._PGenr.cleanupName(name)),
                'name': name,
                'cleanname': self._PGenr.cleanupName(name),
                'module_name': os.path.splitext(os.path.basename(subclassFilename))[0],
                'root': rootElement,
                'namespacedef': Namespacedef,
                'super': superModule,
                }
            wrt(TEMPLATE_SUBCLASS_FOOTER % params)
            subclassFile.close()

    def _generateExportFn(self, wrt, prefix, element, namespace):
        self._LangGenr.generateExport(wrt, namespace, element)
        self._LangGenr.generateExportAttributesFn(wrt, namespace, element)
        self._LangGenr.generateExportChildrenFn(wrt, namespace, element)

    def _generateExportLiteralFn(self, wrt, prefix, element):
        base = element.getBase()
        wrt("    def exportLiteral(self, outfile, level, name_='%s'):\n" % element.getName())
        wrt("        level += 1\n")
        wrt("        self.exportLiteralAttributes(outfile, level, [], name_)\n")
        wrt("        if self.hasContent_():\n")
        wrt("            self.exportLiteralChildren(outfile, level, name_)\n")
        childCount = self._PGenr.countChildren(element, 0)
        if element.getSimpleContent() or element.isMixed():
            wrt("        showIndent(outfile, level)\n")
            wrt("        outfile.write('valueOf_ = \"\"\"%s\"\"\",\\n' % (self.valueOf_,))\n")
        wrt("    def exportLiteralAttributes(self, outfile, level, already_processed, name_):\n")
        count = 0
        attrDefs = element.getAttributeDefs()
        for key in attrDefs:
            attrDef = attrDefs[key]
            count += 1
            name = attrDef.getName()
            cleanName = self._PGenr.cleanupName(name)
            capName = self._PGenr.make_gs_name(cleanName)
            mappedName = mapName(cleanName)
            data_type = attrDef.getData_type()
            attrType = attrDef.getType()
            if attrType in self._PGenr.SimpleTypeDict:
                attrType = self._PGenr.SimpleTypeDict[attrType].getBase()
            if attrType in self._PGenr.SimpleTypeDict:
                attrType = self._PGenr.SimpleTypeDict[attrType].getBase()
            wrt("        if self.%s is not None and '%s' not in already_processed:\n" % (
                mappedName, mappedName, ))
            wrt("            already_processed.append('%s')\n" % (
                mappedName, ))
            wrt("            showIndent(outfile, level)\n")
            if attrType in self._PGenr.StringType or \
                attrType in self._PGenr.IDTypes or \
                attrType == self._PGenr.TokenType or \
                attrType == self._PGenr.DateTimeType or \
                attrType == self._PGenr.TimeType or \
                attrType == self._PGenr.DateType or \
                attrType == self._PGenr.NCNameType:
                wrt("            outfile.write('%s = \"%%s\",\\n' %% (self.%s,))\n" % \
                    (mappedName, mappedName,))
            elif attrType in self._PGenr.IntegerType or \
                attrType == self._PGenr.PositiveIntegerType or \
                attrType == self._PGenr.NonPositiveIntegerType or \
                attrType == self._PGenr.NegativeIntegerType or \
                attrType == self._PGenr.NonNegativeIntegerType:
                wrt("            outfile.write('%s = %%d,\\n' %% (self.%s,))\n" % \
                    (mappedName, mappedName,))
            elif attrType == self._PGenr.BooleanType:
                wrt("            outfile.write('%s = %%s,\\n' %% (self.%s,))\n" % \
                    (mappedName, mappedName,))
            elif attrType == self._PGenr.FloatType or \
                attrType == self._PGenr.DecimalType:
                wrt("            outfile.write('%s = %%f,\\n' %% (self.%s,))\n" % \
                    (mappedName, mappedName,))
            elif attrType == self._PGenr.DoubleType:
                wrt("            outfile.write('%s = %%e,\\n' %% (self.%s,))\n" % \
                    (mappedName, mappedName,))
            else:
                wrt("            outfile.write('%s = %%s,\\n' %% (self.%s,))\n" % \
                    (mappedName, mappedName,))
        if element.getAnyAttribute():
            count += 1
            wrt('        for name, value in self.anyAttributes_.items():\n')
            wrt('            showIndent(outfile, level)\n')
            wrt("            outfile.write('%s = \"%s\",\\n' % (name, value,))\n")
        parentName, parent = self._PGenr.getParentName(element)
        if parentName:
            count += 1
            elName = element.getCleanName()
            wrt("        super(%s, self).exportLiteralAttributes(outfile, level, already_processed, name_)\n" % \
                (elName, ))
        if count == 0:
            wrt("        pass\n")
        wrt("    def exportLiteralChildren(self, outfile, level, name_):\n")
        parentName, parent = self._PGenr.getParentName(element)
        if parentName:
            elName = element.getCleanName()
            wrt("        super(%s, self).exportLiteralChildren(outfile, level, name_)\n" % \
                (elName, ))
        for child in element.getChildren():
            name = child.getName()
            name = self._PGenr.cleanupName(name)
            mappedName = self._PGenr.mapName(name)
            if element.isMixed():
                wrt("        showIndent(outfile, level)\n")
                wrt("        outfile.write('content_ = [\\n')\n")
                wrt('        for item_ in self.content_:\n')
                wrt('            item_.exportLiteral(outfile, level, name_)\n')
                wrt("        showIndent(outfile, level)\n")
                wrt("        outfile.write('],\\n')\n")
            else:
                # fix_abstract
                type_element = None
                abstract_child = False
                type_name = child.getAttrs().get('type')
                if type_name:
                    type_element = self._PGenr.ElementDict.get(type_name)
                if type_element and type_element.isAbstract():
                    abstract_child = True
                if abstract_child:
                    pass
                else:
                    type_name = name
                if child.getMaxOccurs() > 1:
                    if child.getType() == self._PGenr.AnyTypeIdentifier:
                        wrt("        showIndent(outfile, level)\n")
                        wrt("        outfile.write('anytypeobjs_=[\\n')\n")
                        wrt("        level += 1\n")
                        wrt("        for anytypeobjs_ in self.anytypeobjs_:\n")
                        wrt("            anytypeobjs_.exportLiteral(outfile, level)\n")
                        wrt("        level -= 1\n")
                        wrt("        showIndent(outfile, level)\n")
                        wrt("        outfile.write('],\\n')\n")
                    else:
                        wrt("        showIndent(outfile, level)\n")
                        wrt("        outfile.write('%s=[\\n')\n" % (mappedName, ))
                        wrt("        level += 1\n")
                        wrt("        for %s_ in self.%s:\n" % (name, mappedName))
                        self._generateExportLiteralFn_2(wrt, child, name, '    ')
                        wrt("        level -= 1\n")
                        wrt("        showIndent(outfile, level)\n")
                        wrt("        outfile.write('],\\n')\n")
                else:
                    self._generateExportLiteralFn_1(wrt, child, type_name, '')
        if childCount == 0 or element.isMixed():
            wrt("        pass\n")

    def _generateExportLiteralFn_1(self, wrt, child, name, fill):
        cleanName = self._PGenr.cleanupName(name)
        mappedName = self._PGenr.mapName(cleanName)
        childType = child.getType()
        if childType == self._PGenr.AnyTypeIdentifier:
            wrt('%s        if self.anytypeobjs_ is not None:\n' % (fill, ))
            wrt('%s            showIndent(outfile, level)\n' % fill)
            wrt("%s            outfile.write('anytypeobjs_=model_.anytypeobjs_(\\n')\n" % \
                (fill, ))
            wrt("%s            self.anytypeobjs_.exportLiteral(outfile, level)\n" % (
                fill, ))
            wrt('%s            showIndent(outfile, level)\n' % fill)
            wrt("%s            outfile.write('),\\n')\n" % (fill, ))
        else:
            wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
            if childType in self._PGenr.StringType or \
                childType in self._PGenr.IDTypes or \
                childType == self._PGenr.TokenType or \
                childType == self._PGenr.DateTimeType or \
                childType == self._PGenr.TimeType or \
                childType == self._PGenr.DateType:
        #        wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
                wrt('%s            showIndent(outfile, level)\n' % fill)
                if (child.getSimpleType() in self._PGenr.SimpleTypeDict and 
                    self._PGenr.SimpleTypeDict[child.getSimpleType()].isListType()):
                    wrt("%s            if self.%s:\n" % (fill, mappedName, ))
                    wrt("%s                outfile.write('%s=%%s,\\n' %% quote_python(' '.join(self.%s)).encode(ExternalEncoding)) \n" % \
                        (fill, mappedName, mappedName, ))
                    wrt("%s            else:\n" % (fill, ))
                    wrt("%s                outfile.write('%s=None,\\n')\n" % \
                        (fill, mappedName, ))
                else:
                    wrt("%s            outfile.write('%s=%%s,\\n' %% quote_python(self.%s).encode(ExternalEncoding))\n" % \
                        (fill, mappedName, mappedName, ))
            elif childType in self._PGenr.IntegerType or \
                childType == self._PGenr.PositiveIntegerType or \
                childType == self._PGenr.NonPositiveIntegerType or \
                childType == self._PGenr.NegativeIntegerType or \
                childType == self._PGenr.NonNegativeIntegerType:
        #        wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
                wrt('%s            showIndent(outfile, level)\n' % fill)
                wrt("%s            outfile.write('%s=%%d,\\n' %% self.%s)\n" % \
                    (fill, mappedName, mappedName, ))
            elif childType == self._PGenr.BooleanType:
        #        wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
                wrt('%s            showIndent(outfile, level)\n' % fill)
                wrt("%s            outfile.write('%s=%%s,\\n' %% self.%s)\n" % \
                    (fill, mappedName, mappedName, ))
            elif childType == self._PGenr.FloatType or \
                childType == self._PGenr.DecimalType:
        #        wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
                wrt('%s            showIndent(outfile, level)\n' % fill)
                wrt("%s            outfile.write('%s=%%f,\\n' %% self.%s)\n" % \
                    (fill, mappedName, mappedName, ))
            elif childType == self._PGenr.DoubleType:
        #        wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
                wrt('%s            showIndent(outfile, level)\n' % fill)
                wrt("%s            outfile.write('%s=%%e,\\n' %% self.%s)\n" % \
                    (fill, name, mappedName, ))
            else:
        #        wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
                wrt('%s            showIndent(outfile, level)\n' % fill)
                wrt("%s            outfile.write('%s=model_.%s(\\n')\n" % \
                    (fill, mappedName, self._PGenr.mapName(self._PGenr.cleanupName(child.getType()))))
                if name == child.getType():
                    s1 = "%s            self.%s.exportLiteral(outfile, level)\n" % \
                        (fill, mappedName)
                else:
                    s1 = "%s            self.%s.exportLiteral(outfile, level, name_='%s')\n" % \
                        (fill, mappedName, name)
                wrt(s1)
                wrt('%s            showIndent(outfile, level)\n' % fill)
                wrt("%s            outfile.write('),\\n')\n" % (fill, ))

    def _generateExportLiteralFn_2(self, wrt, child, name, fill):
        cleanName = self._PGenr.cleanupName(name)
        mappedName = self._PGenr.mapName(cleanName)
        childType = child.getType()
        wrt('%s        showIndent(outfile, level)\n' % fill)
        if childType in self._PGenr.StringType or \
            childType == self._PGenr.TokenType or \
            childType == self._PGenr.DateTimeType or \
            childType == self._PGenr.TimeType or \
            childType == self._PGenr.DateType:
            wrt("%s        outfile.write('%%s,\\n' %% quote_python(%s_).encode(ExternalEncoding))\n" % \
                (fill, name))
        elif childType in self._PGenr.IntegerType or \
            childType == self._PGenr.PositiveIntegerType or \
            childType == self._PGenr.NonPositiveIntegerType or \
            childType == self._PGenr.NegativeIntegerType or \
            childType == self._PGenr.NonNegativeIntegerType:
            wrt("%s        outfile.write('%%d,\\n' %% %s)\n" % (fill, name))
        elif childType == self._PGenr.BooleanType:
            wrt("%s        outfile.write('%%s,\\n' %% %s)\n" % (fill, name))
        elif childType == self._PGenr.FloatType or \
            childType == self._PGenr.DecimalType:
            wrt("%s        outfile.write('%%f,\\n' %% %s_)\n" % (fill, name))
        elif childType == self._PGenr.DoubleType:
            wrt("%s        outfile.write('%%e,\\n' %% %s)\n" % (fill, name))
        else:
            name1 = self._PGenr.mapName(self._PGenr.cleanupName(child.getType()))
            wrt("%s        outfile.write('model_.%s(\\n')\n" % (fill, name1, ))
            if name == child.getType():
                s1 = "%s        %s_.exportLiteral(outfile, level)\n" % (
                    fill, self._PGenr.cleanupName(child.getType()), )
            else:
                s1 = "%s        %s_.exportLiteral(outfile, level, name_='%s')\n" % \
                    (fill, name, child.getType(), )
            wrt(s1)
            wrt('%s        showIndent(outfile, level)\n' % fill)
            wrt("%s        outfile.write('),\\n')\n" % (fill, ))

    def _generateExportDictFn(self, wrt, prefix, element):
        self._LangGenr.generateExportDict(wrt, element)

    def generateSubclass(self, wrt, element, prefix, xmlbehavior,  behaviors, baseUrl):
        self._LangGenr.generateSubclass()
        if not element.isComplex():
            return
        if element.getName() in AlreadyGenerated_subclass:
            return
        AlreadyGenerated_subclass.append(element.getName())
        name = element.getCleanName()
        wrt('class %s%s%s(supermod.%s):\n' % (prefix, name, SubclassSuffix, name))
        childCount = self._PGenr.countChildren(element, 0)
        s1 = buildCtorArgs_multilevel(element, childCount)
        wrt('    def __init__(self%s):\n' % s1)
        args = buildCtorParams(element, element, childCount)
        s1 = ''.join(args)
        if len(args) > 254:
            wrt('        arglist_ = (%s)\n' % (s1, ))
            wrt('        super(%s%s%s, self).__init__(*arglist_)\n' % (prefix, name, SubclassSuffix, ))
        else:
            #wrt('        supermod.%s%s.__init__(%s)\n' % (prefix, name, s1))
            wrt('        super(%s%s%s, self).__init__(%s)\n' % (prefix, name, SubclassSuffix, s1, ))
        if xmlbehavior and behaviors:
            wrt('\n')
            wrt('    #\n')
            wrt('    # XMLBehaviors\n')
            wrt('    #\n')
            # Get a list of behaviors for this class/subclass.
            classDictionary = behaviors.get_class_dictionary()
            if name in classDictionary:
                classBehaviors = classDictionary[name]
            else:
                classBehaviors = None
            if classBehaviors:
                generateClassBehaviors(wrt, classBehaviors, baseUrl)
        wrt('supermod.%s.subclass = %s%s\n' % (name, name, SubclassSuffix))
        wrt('# end class %s%s%s\n' % (prefix, name, SubclassSuffix))
        wrt('\n\n')

    def _generateBuildFn(self, wrt, prefix, element, delayed):
        self._LangGenr.generateBuild(wrt, element)
        self._LangGenr.generateBuildAttributesFn(wrt, element)
        self._LangGenr.generateBuildChildren(wrt, element, prefix, delayed)

    def _generateUserMethods(self, wrt, element):
        if not self._PGenr.UserMethodsModule:
            return
        specs = self._PGenr.UserMethodsModule.METHOD_SPECS
        name = self._PGenr.cleanupName(element.getCleanName())
        values_dict = {'class_name': name, }
        for spec in specs:
            if spec.match_name(name):
                source = spec.get_interpolated_source(values_dict)
                wrt(source)
#
# Generators for Language specific parts
#
class PyGenerator(object):
    def __init__(self, parser_generator):
        self._PGenr = parser_generator

    def generateHeader(self, wrt, prefix):
        tstamp = (not self._PGenr.NoDates and time.ctime()) or ''
        if self._PGenr.NoVersion:
            version = ''
        else:
            version = ' version %s' % self._PGenr.Version
        s1 = self._PGenr.TEMPLATE_HEADER % (tstamp, version, self._PGenr.ExternalEncoding, )
        wrt(s1)

    def generateClassDefLine(self, wrt, parentName, prefix, name):
        if parentName:
            s1 = 'class %s%s(%s):\n' % (prefix, name, parentName,)
        else:
            s1 = 'class %s%s(GeneratedsSuper):\n' % (prefix, name)

        wrt(s1)
        wrt('    """\n')
        for child in self._PGenr.ElementDict[name].children:
            if child.attrs.get('required'):
                if child.attrs['required'] != 'system-only':
                    if child.attrs['required'].lower() == 'true':
                        created_by = 'User (required)'
                    else:
                        created_by = 'User (optional)'
                else:
                    created_by = 'System'
            wrt('    * %s\n' %(child.name.replace('-', '_')))
            wrt('        Type: ')
            child_schema_type = child.getSchemaType()
            if child_schema_type in self._PGenr.SimpleTypeDict:
                r_base = self._PGenr.SimpleTypeDict[child_schema_type]
                python_type = self._PGenr.SchemaToPythonTypeMap[r_base.base]
                wrt('          %s, *one-of* %s\n\n' %(python_type, r_base.values))
            elif child_schema_type in self._PGenr.SchemaToPythonTypeMap:
                # simple primitive type
                python_type = self._PGenr.SchemaToPythonTypeMap[child_schema_type]
                wrt('          %s\n\n' %(python_type))
            else: # complex type and not restriction on simple
                wrt('          :class:`.%s`\n\n' %(child_schema_type))
            if child.attrs.get('required'):
                wrt('        Created By: ')
                wrt('          %s\n\n' %(created_by))
            if child.attrs.get('description'):
                wrt('        Description:\n')
                wrt('          %s\n\n' %(child.attrs['description']))
        wrt('    """\n')

    def generateSubclass(self):
        if not element.isComplex():
            return
        if element.getName() in AlreadyGenerated_subclass:
            return
        AlreadyGenerated_subclass.append(element.getName())
        name = element.getCleanName()
        wrt('class %s%s%s(supermod.%s):\n' % (prefix, name, SubclassSuffix, name))
        childCount = self._PGenr.countChildren(element, 0)
        s1 = buildCtorArgs_multilevel(element, childCount)
        wrt('    def __init__(self%s):\n' % s1)
        args = buildCtorParams(element, element, childCount)
        s1 = ''.join(args)
        if len(args) > 254:
            wrt('        arglist_ = (%s)\n' % (s1, ))
            wrt('        super(%s%s%s, self).__init__(*arglist_)\n' % (prefix, name, SubclassSuffix, ))
        else:
            #wrt('        supermod.%s%s.__init__(%s)\n' % (prefix, name, s1))
            wrt('        super(%s%s%s, self).__init__(%s)\n' % (prefix, name, SubclassSuffix, s1, ))
        if xmlbehavior and behaviors:
            wrt('\n')
            wrt('    #\n')
            wrt('    # XMLBehaviors\n')
            wrt('    #\n')
            # Get a list of behaviors for this class/subclass.
            classDictionary = behaviors.get_class_dictionary()
            if name in classDictionary:
                classBehaviors = classDictionary[name]
            else:
                classBehaviors = None
            if classBehaviors:
                generateClassBehaviors(wrt, classBehaviors, baseUrl)
        wrt('supermod.%s.subclass = %s%s\n' % (name, name, SubclassSuffix))
        wrt('# end class %s%s%s\n' % (prefix, name, SubclassSuffix))
        wrt('\n\n')

    def gen_populate_str (self, name, child):
        child_type = child.getType()
        if child.getMaxOccurs() > 1:
            if child_type.startswith ('xsd:'):
                return '[obj.populate_%s ("%s")]' % (child_type.replace (
                            'xsd:', ''), name)
            else:
                return '[%s.populate ()]' % child_type
        else: # not array
            if child_type.startswith ('xsd:'):
                return 'obj.populate_%s ("%s")' % (child_type.replace (
                            'xsd:', ''), name)
            else:
                return '%s.populate ()' % child_type

    def _generateAttrMetadata(self, wrt, element):
        generated_simple_types = []
        child_count = self._PGenr.countChildren(element, 0)
        attr_fields = []
        attr_field_type_vals = {}
        for child in element.getChildren():
            name = self._PGenr.cleanupName(child.getCleanName())
            unmapped_name = self._PGenr.cleanupName(child.getName())
            cap_name = self._PGenr.make_gs_name(unmapped_name)
            restrictions = None
            if child.getSchemaType() in self._PGenr.SimpleTypeDict:
                restrictions = self._PGenr.SimpleTypeDict[
                    child.getSchemaType()].values
            get_max_occurs = child.getMaxOccurs()
            attr_fields.append(name)
            is_array = child.getMaxOccurs() > 1
            is_complex = child.isComplex()
            attr_type = child.getType().replace('xsd:', '')
            attr_field_type_vals[name] = {'is_complex': is_complex,
                                          'restrictions': restrictions,
                                          'is_array': is_array,
                                          'attr_type': attr_type}

        wrt('    attr_fields = %s\n' %(attr_fields))
        wrt('    attr_field_type_vals = %s\n' %(attr_field_type_vals))


    def _generateTestHelpers (self, wrt, element):
        generated_simple_types = []
        child_count = self._PGenr.countChildren(element, 0)
        wrt('    @classmethod\n')
        wrt('    def populate (cls, *a, **kwa):\n')
        wrt('        obj = cls (*a, **kwa)\n')
        for child in element.getChildren():
            name = self._PGenr.cleanupName(child.getCleanName())
            unmapped_name = self._PGenr.cleanupName(child.getName())
            cap_name = self._PGenr.make_gs_name(unmapped_name)
            get_max_occurs = child.getMaxOccurs()
            astr = '        obj.set_%s (%s)\n' % (name,
                    self.gen_populate_str (name, child))

            wrt('%s' % astr)
        wrt('        return obj\n')
                    
    # end _generateTestHelpers

    def generateFactory(self, wrt, prefix, name):
        wrt('    def factory(*args_, **kwargs_):\n')
        wrt('        if %s%s.subclass:\n' % (prefix, name))
        wrt('            return %s%s.subclass(*args_, **kwargs_)\n' % (prefix, name))
        wrt('        else:\n')
        wrt('            return %s%s(*args_, **kwargs_)\n' % (prefix, name))
        wrt('    factory = staticmethod(factory)\n')

    def generateElemDoc(self, wrt, element):
        s2 = ' '.join(element.documentation.strip().split())
        s2 = s2.encode('utf-8')
        s2 = textwrap.fill(s2, width=68, subsequent_indent='    ')
        if s2[0] == '"' or s2[-1] == '"':
            s2 = '    """ %s """\n' % (s2, )
        else:
            s2 = '    """%s"""\n' % (s2, )

        wrt(s2)

    #
    # Generate a class variable whose value is a list of tuples, one
    #   tuple for each member data item of the class.
    #   Each tuble has 3 elements: (1) member name, (2) member data type,
    #   (3) container/list or not (maxoccurs > 1).
    def generateMemberSpec(wrt, element):
        generateDict = MemberSpecs and MemberSpecs == 'dict'
        if generateDict:
            content = ['    member_data_items_ = {']
        else:
            content = ['    member_data_items_ = [']
        add = content.append
        for attrName, attrDef in element.getAttributeDefs().items():
            item1 = attrName
            item2 = attrDef.getType()
            item3 = 0
            if generateDict:
                item = "        '%s': MemberSpec_('%s', '%s', %d)," % (
                    item1, item1, item2, item3, )
            else:
                item = "        MemberSpec_('%s', '%s', %d)," % (
                    item1, item2, item3, )
            add(item)
        for child in element.getChildren():
            name = self._PGenr.cleanupName(child.getCleanName())
            item1 = name
            simplebase = child.getSimpleBase()
            if simplebase:
                if len(simplebase) == 1:
                    item2 = "'%s'" % (simplebase[0], )
                else:
                    item2 = simplebase
            else:
                element1 = self._PGenr.ElementDict.get(name)
                if element1:
                    item2 = "'%s'" % element1.getType()
                else:
                    item2 = "'%s'" % (child.getType(), )
            if child.getMaxOccurs() > 1:
                item3 = 1
            else:
                item3 = 0
            if generateDict:
                item = "        '%s': MemberSpec_('%s', %s, %d)," % (
                    item1, item1, item2, item3, )
            else:
                #item = "        ('%s', '%s', %d)," % (item1, item2, item3, )
                item = "        MemberSpec_('%s', %s, %d)," % (
                    item1, item2, item3, )
            add(item)
        simplebase = element.getSimpleBase()
        childCount = self._PGenr.countChildren(element, 0)
        if element.getSimpleContent() or element.isMixed():
            if len(simplebase) == 1:
                simplebase = "'%s'" % (simplebase[0], )
            if generateDict:
                item = "        'valueOf_': MemberSpec_('valueOf_', %s, 0)," % (
                    simplebase, )
            else:
                item = "        MemberSpec_('valueOf_', %s, 0)," % (
                    simplebase, )
            add(item)
        elif element.isMixed():
            if generateDict:
                item = "        'valueOf_': MemberSpec_('valueOf_', '%s', 0)," % (
                    'xs:string', )
            else:
                item = "        MemberSpec_('valueOf_', '%s', 0)," % (
                    'xs:string', )
            add(item)
        if generateDict:
            add('        }')
        else:
            add('        ]')
        wrt('\n'.join(content))
        wrt('\n')

    def generateSubSuperInit(self, wrt, superclass_name):
        wrt('    subclass = None\n')
        wrt('    superclass = %s\n' % (superclass_name, ))

    def generateCtor(self, wrt, element):
        elName = element.getCleanName()
        childCount = self._PGenr.countChildren(element, 0)
        s2 = self.buildCtorArgs_multilevel(element, childCount)
        wrt('    def __init__(self%s, **kwargs):\n' % s2)
        base = element.getBase()
        parentName, parent = self._PGenr.getParentName(element)
        if parentName:
            if parentName in self._PGenr.AlreadyGenerated:
                args = self.buildCtorParams(element, parent, childCount)
                s2 = ''.join(args)
                if len(args) > 254:
                    wrt('        arglist_ = (%s)\n' % (s2, ))
                    wrt('        super(%s, self).__init__(*arglist_)\n' % (elName, ))
                else:
                    wrt('        super(%s, self).__init__(%s)\n' % (elName, s2, ))
        attrDefs = element.getAttributeDefs()
        for key in attrDefs:
            attrDef = attrDefs[key]
            mappedName = self._PGenr.cleanupName(attrDef.getName())
            mappedName = mapName(mappedName)
            logging.debug("Constructor attribute: %s" % mappedName)
            pythonType = self._PGenr.SchemaToPythonTypeMap.get(attrDef.getType())
            attrVal = "_cast(%s, %s)" % (pythonType, mappedName)
            wrt('        self.%s = %s\n' % (mappedName, attrVal))
            member = 1
        # Generate member initializers in ctor.
        member = 0
        nestedElements = 0
        for child in element.getChildren():
            name = self._PGenr.cleanupName(child.getCleanName())
            logging.debug("Constructor child: %s" % name)
            logging.debug("Dump: %s" % child.__dict__)
            if child.getType() == self._PGenr.AnyTypeIdentifier:
                if child.getMaxOccurs() > 1:
                    wrt('        if anytypeobjs_ is None:\n')
                    wrt('            self.anytypeobjs_ = []\n')
                    wrt('        else:\n')
                    wrt('            self.anytypeobjs_ = anytypeobjs_\n')
                else:
                    wrt('        self.anytypeobjs_ = anytypeobjs_\n')
            else:
                if child.getMaxOccurs() > 1:
                    child_type = child.getType()
                    wrt('        if (%s is None) or (%s == []):\n' % (name, name))
                    wrt('            self.%s = []\n' % (name, ))
                    wrt('        else:\n')
                    if (child.isComplex()):
                        wrt('            if isinstance(%s[0], dict):\n' %(name))
                        wrt('                objs = [%s(**elem) for elem in %s]\n' \
                                                     %(child_type, name))
                        wrt('                self.%s = objs\n' % (name))
                        wrt('            else:\n')
                        wrt('                self.%s = %s\n' % (name, name))
                    else:
                        wrt('            self.%s = %s\n' % (name, name))
                else:
                    typeObj = self._PGenr.ElementDict.get(child.getType())
                    if (child.getDefault() and
                        typeObj is not None and
                        typeObj.getSimpleContent()):
                        wrt('        if %s is None:\n' % (name, ))
                        wrt("            self.%s = globals()['%s']('%s')\n" % (name,
                            child.getType(), child.getDefault(), ))
                        wrt('        else:\n')
                        wrt('            self.%s = %s\n' % (name, name))
                    else:
                        child_type = child.getType()
                        if (child.isComplex()):
                            wrt('        if isinstance(%s, dict):\n' %(name))
                            wrt('            obj = %s(**%s)\n' %(child_type, name))
                            wrt('            self.%s = obj\n' % (name))
                            wrt('        else:\n')
                            wrt('            self.%s = %s\n' % (name, name))
                        else:
                            wrt('        self.%s = %s\n' % (name, name))
            member = 1
            nestedElements = 1
        eltype = element.getType()
        if (element.getSimpleContent() or
            element.isMixed() or
            eltype in self._PGenr.SimpleTypeDict or
            self._PGenr.CurrentNamespacePrefix + eltype in self._PGenr.OtherSimpleTypes
            ):
            wrt('        self.valueOf_ = valueOf_\n')
            member = 1
        if element.getAnyAttribute():
            wrt('        self.anyAttributes_ = {}\n')
            member = 1
        if element.getExtended():
            wrt('        self.extensiontype_ = extensiontype_\n')
            member = 1
        if not member:
            wrt('        pass\n')
        if element.isMixed():
            wrt(MixedCtorInitializers)
    # end generateCtor

    def buildCtorArgs_multilevel(self, element, childCount):
        content = []
        addedArgs = {}
        add = content.append
        self.buildCtorArgs_multilevel_aux(addedArgs, add, element)
        eltype = element.getType()
        if (element.getSimpleContent() or
            element.isMixed() or
            eltype in self._PGenr.SimpleTypeDict or
            self._PGenr.CurrentNamespacePrefix + eltype in self._PGenr.OtherSimpleTypes
            ):
            print "SimpleContent()"
            add(", valueOf_=None")
        if element.isMixed():
            print "Mixed"
            add(', mixedclass_=None')
            add(', content_=None')
        if element.getExtended():
            print "Extended"
            add(', extensiontype_=None')
        s1 = ''.join(content)
        return s1
    
    
    def buildCtorArgs_multilevel_aux(self, addedArgs, add, element):
        parentName, parentObj = self._PGenr.getParentName(element)
        if parentName:
            self.buildCtorArgs_multilevel_aux(addedArgs, add, parentObj)
        self.buildCtorArgs_aux(addedArgs, add, element)
    
    def getMappedDefault(self, etype, default):
        if not default:
            return 'None'
        types = self._PGenr
        if etype in types.IntegerType + (types.FloatType, \
                     types.DoubleType, types.DecimalType):
            return default
        elif etype in types.StringType + (types.TokenType, \
                       types.DateTimeType, types.TimeType, types.DateType):
            escape_default = self.escape_string(default)
            return "\'" + escape_default + "\'"
        elif etype == types.BooleanType:
            if default in ('false', '0'):
                 return "False"
            elif default in ('true', '1'):
                 return "True"
        else:
            return "\'" + default + "\'"
    
    def buildCtorArgs_aux(self, addedArgs, add, element):
        attrDefs = element.getAttributeDefs()
        for key in attrDefs:
            attrDef = attrDefs[key]
            name = attrDef.getName()
            default = attrDef.getDefault()
            mappedName = name.replace(':', '_')
            mappedName = self._PGenr.cleanupName(mapName(mappedName))
            if mappedName in addedArgs:
                continue
            addedArgs[mappedName] = 1
            try:
                atype = attrDef.getData_type()
            except KeyError:
                atype = self._PGenr.StringType
            mappedDefault = self.getMappedDefault(atype, default)
            add(', %s=%s' % (mappedName, mappedDefault))

        nestedElements = 0
        for child in element.getChildren():
            cleanName = child.getCleanName()
            if cleanName in addedArgs:
                continue
            addedArgs[cleanName] = 1
            default = child.getDefault()
            nestedElements = 1
            if child.getType() == self._PGenr.AnyTypeIdentifier:
                add(', anytypeobjs_=None')
            elif child.getMaxOccurs() > 1:
                add(', %s=None' % cleanName)
            else:
                childType = child.getType()
                mappedDefault = self.getMappedDefault(childType, default)
                add(', %s=%s' % (cleanName, mappedDefault))
    # end buildCtorArgs_aux
                    
    def generateEnd(self, wrt, name, s4):
        wrt('# end class %s\n' % name)
        wrt('\n\n')

    def generateGetterAnyType(self, wrt):
        wrt('    def get_anytypeobjs_(self): return self.anytypeobjs_\n')

    def generateSetterAnyType(self, wrt):
        wrt('    def set_anytypeobjs_(self, anytypeobjs_): self.anytypeobjs_ = anytypeobjs_\n')

    def generateAdderAnyType(self, wrt):
        wrt('    def add_anytypeobjs_(self, value): self.anytypeobjs_.append(value)\n')

    def generateInserterAnyType(self, wrt):
        wrt('    def insert_anytypeobjs_(self, index, value): self._anytypeobjs_[index] = value\n')

    def generateGetter(self, wrt, capName, name, childType):
        wrt('    def get%s(self): return self.%s\n' % (capName, name))

    def generateSetter(self, wrt, capName, name, childType):
        wrt('    def set%s(self, %s): self.%s = %s\n' % 
                (capName, name, name, name))


    def generateAdder(self, wrt, capName, name):
        wrt('    def add%s(self, value): self.%s.append(value)\n' % 
            (capName, name))

    def generateInserter(self, wrt, capName, name):
        wrt('    def insert%s(self, index, value): self.%s[index] = value\n' % 
            (capName, name))

    def generateDeleter(self, wrt, capName, name):
        wrt('    def delete%s(self, value): self.%s.remove(value)\n' % 
            (capName, name))

    def generateProperty(self, wrt, unmappedName, capName, name):
        wrt('    %sProp = property(get%s, set%s)\n' % 
            (unmappedName, capName, capName))

    def generateValidator(self, wrt, typeName):
        wrt('    def validate_%s(self, value):\n' % (typeName, ))
        if typeName in self._PGenr.SimpleTypeDict:
            stObj = self._PGenr.SimpleTypeDict[typeName]
            wrt('        # Validate type %s, a restriction on %s.\n' % (
                typeName, stObj.getBase(), ))
        else:
            wrt('        # validate type %s\n' % (typeName, ))
        wrt(self._getValidatorBody(typeName))
#
# Attempt to retrieve the body (implementation) of a validator
#   from a directory containing one file for each simpleType.
#   The name of the file should be the same as the name of the
#   simpleType with and optional ".py" extension.
    def _getValidatorBody(self, stName):
        retrieved = 0
        if self._PGenr.ValidatorBodiesBasePath:
            found = 0
            path = '%s%s%s.py' % (self._PGenr.ValidatorBodiesBasePath, os.sep, stName, )
            if os.path.exists(path):
                found = 1
            else:
                path = '%s%s%s' % (self._PGenr.ValidatorBodiesBasePath, os.sep, stName, )
                if os.path.exists(path):
                    found = 1
            if found:
                infile = open(path, 'r')
                lines = infile.readlines()
                infile.close()
                lines1 = []
                for line in lines:
                    if not line.startswith('##'):
                        lines1.append(line)
                s1 = ''.join(lines1)
                retrieved = 1
        if not retrieved:
            st = self._PGenr.SimpleTypeDict.get(stName)
            if st and st.getBase() == "xsd:string" and st.values:
                s1 = '        error = False\n'
                s1+= '        if isinstance(value, list):\n'
                s1+= '            error = set(value) - set(' + str(st.values) +')\n'
                s1+= '        else:\n'
                s1+= '            error = value not in ' + str(st.values) + '\n'
                s1+= '        if error:\n'
                errorStr = stName + ' must be one of ' + str(st.values)
                s1+= '            raise ValueError("' + errorStr + '")\n'
            elif st and st.getBase() == "xsd:integer" and st.values:
                s1 = '        error = False\n'
                s1+= '        if isinstance(value, list):\n'
                s1+= '            v_int = map(int, value)\n'
                s1+= '            v1, v2 = min(v_int), max(v_int)\n'
                s1+= '        else:\n'
                s1+= '            v1, v2 = int(value), int(value)\n'
                if st.values[0]:
                    s1+= '        error = (%s > v1)\n' % st.values[0]
                if st.values[1]:
                    s1+= '        error |= (v2 > %s)\n' % st.values[1]
                errorStr = (stName + ' must be in the range %s-%s' %
                            (st.values[0], st.values[1]))
                s1+= '        if error:\n'
                s1+= '            raise ValueError("' + errorStr + '")\n'
            else:
                s1 = '        pass\n'
        return s1

    def generateExport(self, wrt, namespace, element):
        childCount = self._PGenr.countChildren(element, 0)
        name = element.getName()
        base = element.getBase()
        wrt("    def export(self, outfile, level=1, namespace_='%s', name_='%s', namespacedef_='', pretty_print=True):\n" % \
            (namespace, name, ))
        wrt('        if pretty_print:\n')
        wrt("            eol_ = '\\n'\n")
        wrt('        else:\n')
        wrt("            eol_ = ''\n")
        wrt('        showIndent(outfile, level, pretty_print)\n')
        wrt("        outfile.write('<%s%s%s' % (namespace_, name_, namespacedef_ and ' ' + namespacedef_ or '', ))\n")
        wrt("        already_processed = []\n")
        wrt("        self.exportAttributes(outfile, level, already_processed, namespace_, name_='%s')\n" % \
            (name, ))
        # fix_abstract
        if base and base in self._PGenr.ElementDict:
            base_element = self._PGenr.ElementDict[base]
            # fix_derived
            if base_element.isAbstract():
                pass
        if childCount == 0 and element.isMixed():
            wrt("        outfile.write('>')\n")
            wrt("        self.exportChildren(outfile, level + 1, namespace_, name_, pretty_print=pretty_print)\n")
            wrt("        outfile.write('</%s%s>%s' % (namespace_, name_, eol_))\n")
        else:
            wrt("        if self.hasContent_():\n")
            # Added to keep value on the same line as the tag no children.
            if element.getSimpleContent():
                wrt("            outfile.write('>')\n")
                if not element.isMixed():
                    wrt("            outfile.write(str(self.valueOf_).encode(ExternalEncoding))\n")
            else:
                wrt("            outfile.write('>%s' % (eol_, ))\n")
            wrt("            self.exportChildren(outfile, level + 1, namespace_, name_, pretty_print=pretty_print)\n")
            # Put a condition on the indent to require children.
            if childCount != 0:
                wrt('            showIndent(outfile, level, pretty_print)\n')
            wrt("            outfile.write('</%s%s>%s' % (namespace_, name_, eol_))\n")
            wrt("        else:\n")
            wrt("            outfile.write('/>%s' % (eol_, ))\n")

    def generateExportAttributesFn(self, wrt, namespace, element):
        name = element.getName()
        wrt("    def exportAttributes(self, outfile, level, already_processed, namespace_='%s', name_='%s'):\n" % \
            (namespace, name, ))
        hasAttributes = 0
        if element.getAnyAttribute():
            wrt("        unique_counter = 0\n")
            wrt('        for name, value in self.anyAttributes_.items():\n')
            wrt("            xsinamespaceprefix = 'xsi'\n")
            wrt("            xsinamespace1 = 'http://www.w3.org/2001/XMLSchema-instance'\n")
            wrt("            xsinamespace2 = '{%s}' % (xsinamespace1, )\n")
            wrt("            if name.startswith(xsinamespace2):\n")
            wrt("                name1 = name[len(xsinamespace2):]\n")
            wrt("                name2 = '%s:%s' % (xsinamespaceprefix, name1, )\n")
            wrt("                if name2 not in already_processed:\n")
            wrt("                    already_processed.append(name2)\n")
            wrt("                    outfile.write(' %s=%s' % (name2, quote_attrib(value), ))\n")
            wrt("            else:\n")
            wrt("                mo = re_.match(Namespace_extract_pat_, name)\n")
            wrt("                if mo is not None:\n")
            wrt("                    namespace, name = mo.group(1, 2)\n")
            wrt("                    if name not in already_processed:\n")
            wrt("                        already_processed.append(name)\n")
            wrt("                        if namespace == 'http://www.w3.org/XML/1998/namespace':\n")
            wrt("                            outfile.write(' %s=%s' % (name, quote_attrib(value), ))\n")
            wrt("                        else:\n")
            wrt("                            unique_counter += 1\n")
            wrt("                            outfile.write(' xmlns:yyy%d=\"%s\"' % (unique_counter, namespace, ))\n")
            wrt("                            outfile.write(' yyy%d:%s=%s' % (unique_counter, name, quote_attrib(value), ))\n")
            wrt("                else:\n")
            wrt("                    if name not in already_processed:\n")
            wrt("                        already_processed.append(name)\n")
            wrt("                        outfile.write(' %s=%s' % (name, quote_attrib(value), ))\n")
        parentName, parent = self._PGenr.getParentName(element)
        if parentName:
            hasAttributes += 1
            elName = element.getCleanName()
            wrt("        super(%s, self).exportAttributes(outfile, level, already_processed, namespace_, name_='%s')\n" % \
                (elName, name, ))
        hasAttributes += self.generateExportAttributes(wrt, element, hasAttributes)
        if hasAttributes == 0:
            wrt("        pass\n")

    def generateExportAttributes(self, wrt, element, hasAttributes):
        if len(element.getAttributeDefs()) > 0:
            hasAttributes += 1
            attrDefs = element.getAttributeDefs()
            for key in attrDefs.keys():
                attrDef = attrDefs[key]
                name = attrDef.getName()
                cleanName = mapName(self._PGenr.cleanupName(name))
                capName = self._PGenr.make_gs_name(cleanName)
                if True:            # attrDef.getUse() == 'optional':
                    wrt("        if self.%s is not None and '%s' not in already_processed:\n" % (
                        cleanName, cleanName, ))
                    wrt("            already_processed.append('%s')\n" % (
                        cleanName, ))
                    indent = "    "
                else:
                    indent = ""
                if (attrDef.getType() in self._PGenr.StringType or
                    attrDef.getType() in self._PGenr.IDTypes or
                    attrDef.getType() == self._PGenr.TokenType or
                    attrDef.getType() == self._PGenr.DateTimeType or
                    attrDef.getType() == self._PGenr.TimeType or
                    attrDef.getType() == self._PGenr.DateType):
                    s1 = '''%s        outfile.write(' %s=%%s' %% (self.gds_format_string(quote_attrib(self.%s).encode(ExternalEncoding), input_name='%s'), ))\n''' % \
                        (indent, name, cleanName, name, )
                elif attrDef.getType() in self._PGenr.IntegerType or \
                    attrDef.getType() == self._PGenr.PositiveIntegerType or \
                    attrDef.getType() == self._PGenr.NonPositiveIntegerType or \
                    attrDef.getType() == self._PGenr.NegativeIntegerType or \
                    attrDef.getType() == self._PGenr.NonNegativeIntegerType:
                    s1 = '''%s        outfile.write(' %s="%%s"' %% self.gds_format_integer(self.%s, input_name='%s'))\n''' % (
                        indent, name, cleanName, name, )
                elif attrDef.getType() == BooleanType:
                    s1 = '''%s        outfile.write(' %s="%%s"' %% self.gds_format_boolean(self.gds_str_lower(str(self.%s)), input_name='%s'))\n''' % (
                        indent, name, cleanName, name, )
                elif attrDef.getType() == FloatType or \
                    attrDef.getType() == DecimalType:
                    s1 = '''%s        outfile.write(' %s="%%s"' %% self.gds_format_float(self.%s, input_name='%s'))\n''' % (
                        indent, name, cleanName, name)
                elif attrDef.getType() == DoubleType:
                    s1 = '''%s        outfile.write(' %s="%%s"' %% self.gds_format_double(self.%s, input_name='%s'))\n''' % (
                        indent, name, cleanName, name)
                else:
                    s1 = '''%s        outfile.write(' %s=%%s' %% (quote_attrib(self.%s), ))\n''' % (
                        indent, name, cleanName, )
                wrt(s1)
        if element.getExtended():
            wrt("        if self.extensiontype_ is not None and 'xsi:type' not in already_processed:\n")
            wrt("            already_processed.append('xsi:type')\n")
            wrt("            outfile.write(' xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\"')\n")
            wrt('''            outfile.write(' xsi:type="%s"' % self.extensiontype_)\n''')
        return hasAttributes
    # end generateExportAttributes

    def generateExportChildrenFn(self, wrt, namespace, element):
        childCount = self._PGenr.countChildren(element, 0)
        name = element.getName()
        wrt("    def exportChildren(self, outfile, level, namespace_='%s', name_='%s', fromsubclass_=False, pretty_print=True):\n" % \
            (namespace, name, ))
        hasChildren = 0
        # Generate call to exportChildren in the superclass only if it is
        #  an extension, but *not* if it is a restriction.
        parentName, parent = self._PGenr.getParentName(element)
        if parentName and not element.getRestrictionBaseObj():
            hasChildren += 1
            elName = element.getCleanName()
            wrt("        super(%s, self).exportChildren(outfile, level, namespace_, name_, True, pretty_print=pretty_print)\n" % (elName, ))
        hasChildren += self._generateExportChildren(wrt, element, hasChildren, namespace)
        if childCount == 0:   # and not element.isMixed():
            wrt("        pass\n")
        if True or hasChildren > 0 or element.isMixed():
            self._generateHascontentMethod(wrt, element)

    def _generateHascontentMethod(self, wrt, element):
        childCount = self._PGenr.countChildren(element, 0)
        wrt('    def hasContent_(self):\n')
        wrt('        if (\n')
        firstTime = True
        for child in element.getChildren():
            if child.getType() == self._PGenr.AnyTypeIdentifier:
                name = 'anytypeobjs_'
            else:
                name = self._PGenr.mapName(self._PGenr.cleanupName(child.getName()))
            if not firstTime:
                wrt(' or\n')
            firstTime = False
            if child.getMaxOccurs() > 1:
                wrt('            self.%s' % (name, ))
            else:
                wrt('            self.%s is not None' % (name, ))
        if element.getSimpleContent() or element.isMixed():
            if not firstTime:
                wrt(' or\n')
            firstTime = False
            wrt('            self.valueOf_')
        parentName, parent = self._PGenr.getParentName(element)
        if parentName:
            elName = element.getCleanName()
            if not firstTime:
                wrt(' or\n')
            firstTime = False
            wrt('            super(%s, self).hasContent_()' % (elName, ))
        wrt('\n            ):\n')
        wrt('            return True\n')
        wrt('        else:\n')
        wrt('            return False\n')

    def _generateExportChildren(self, wrt, element, hasChildren, namespace):
        fill = '        '
        if len(element.getChildren()) > 0:
            hasChildren += 1
            if element.isMixed():
                wrt('%sif not fromsubclass_:\n' % (fill, ))
                wrt("%s    for item_ in self.content_:\n" % (fill, ))
                wrt("%s        item_.export(outfile, level, item_.name, namespace_, pretty_print=pretty_print)\n" % (
                    fill, ))
            else:
                wrt('%sif pretty_print:\n' % (fill, ))
                wrt("%s    eol_ = '\\n'\n" % (fill, ))
                wrt('%selse:\n' % (fill, ))
                wrt("%s    eol_ = ''\n" % (fill, ))
                any_type_child = None
                for child in element.getChildren():
                    unmappedName = child.getName()
                    name = self._PGenr.mapName(self._PGenr.cleanupName(child.getName()))
                    # fix_abstract
                    type_element = None
                    abstract_child = False
                    type_name = child.getAttrs().get('type')
                    if type_name:
                        type_element = self._PGenr.ElementDict.get(type_name)
                    if type_element and type_element.isAbstract():
                        abstract_child = True
                    if child.getType() == self._PGenr.AnyTypeIdentifier:
                        any_type_child = child
                    else:
                        if abstract_child and child.getMaxOccurs() > 1:
                            wrt("%sfor %s_ in self.get%s():\n" % (fill,
                                name, self._PGenr.make_gs_name(name),))
                            wrt("%s    %s_.export(outfile, level, namespace_, name_='%s', pretty_print=pretty_print)\n" % (
                                fill, name, name, ))
                        elif abstract_child:
                            wrt("%sif self.%s is not None:\n" % (fill, name, ))
                            wrt("%s    self.%s.export(outfile, level, namespace_, name_='%s', pretty_print=pretty_print)\n" % (
                                fill, name, name, ))
                        elif child.getMaxOccurs() > 1:
                            self._generateExportFn_2(wrt, child, unmappedName, namespace, '    ')
                        else:
                            if (child.getOptional()):
                                self._generateExportFn_3(wrt, child, unmappedName, namespace, '')
                            else:
                                self._generateExportFn_1(wrt, child, unmappedName, namespace, '')
                if any_type_child is not None:
                    if any_type_child.getMaxOccurs() > 1:
                        wrt('        for obj_ in self.anytypeobjs_:\n')
                        wrt("            obj_.export(outfile, level, namespace_, pretty_print=pretty_print)\n")
                    else:
                        wrt('        if self.anytypeobjs_ is not None:\n')
                        wrt("            self.anytypeobjs_.export(outfile, level, namespace_, pretty_print=pretty_print)\n")
        return hasChildren

    def _generateExportFn_1(self, wrt, child, name, namespace, fill):
        cleanName = self._PGenr.cleanupName(name)
        mappedName = self._PGenr.mapName(cleanName)
        child_type = child.getType()
        if child_type in self._PGenr.StringType or \
            child_type == self._PGenr.TokenType or \
            child_type == self._PGenr.DateTimeType or \
            child_type == self._PGenr.TimeType or \
            child_type == self._PGenr.DateType:
            wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
            wrt('%s            showIndent(outfile, level, pretty_print)\n' % fill)
            # fixlist
            if (child.getSimpleType() in self._PGenr.SimpleTypeDict and
                self._PGenr.SimpleTypeDict[child.getSimpleType()].isListType()):
                s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_string(quote_xml(' '.join(self.%s)).encode(ExternalEncoding), input_name='%s'), namespace_, eol_))\n" % \
                    (fill, name, name, mappedName, name, )
            else:
                s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_string(quote_xml(self.%s).encode(ExternalEncoding), input_name='%s'), namespace_, eol_))\n" % \
                    (fill, name, name, mappedName, name, )
            wrt(s1)
        elif child_type in self._PGenr.IntegerType or \
            child_type == self._PGenr.PositiveIntegerType or \
            child_type == self._PGenr.NonPositiveIntegerType or \
            child_type == self._PGenr.NegativeIntegerType or \
            child_type == self._PGenr.NonNegativeIntegerType:
            wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
            wrt('%s            showIndent(outfile, level, pretty_print)\n' % fill)
            if child.isListType():
                s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_integer_list(self.%s, input_name='%s'), namespace_, eol_))\n" % \
                    (fill, name, name, mappedName, name, )
            else:
                s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_integer(self.%s, input_name='%s'), namespace_, eol_))\n" % \
                    (fill, name, name, mappedName, name, )
            wrt(s1)
        elif child_type == self._PGenr.BooleanType:
            wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
            wrt('%s            showIndent(outfile, level, pretty_print)\n' % fill)
            if child.isListType():
                s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_boolean_list(self.gds_str_lower(str(self.%s)), input_name='%s'), namespace_, eol_))\n" % \
                    (fill, name, name, mappedName, name, )
            else:
                s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_boolean(self.gds_str_lower(str(self.%s)), input_name='%s'), namespace_, eol_))\n" % \
                    (fill, name, name, mappedName, name, )
            wrt(s1)
        elif child_type == self._PGenr.FloatType or \
            child_type == self._PGenr.DecimalType:
            wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
            wrt('%s            showIndent(outfile, level, pretty_print)\n' % fill)
            if child.isListType():
                s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_float_list(self.%s, input_name='%s'), namespace_, eol_))\n" % \
                    (fill, name, name, mappedName, name, )
            else:
                s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_float(self.%s, input_name='%s'), namespace_, eol_))\n" % \
                    (fill, name, name, mappedName, name, )
            wrt(s1)
        elif child_type == self._PGenr.DoubleType:
            wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
            wrt('%s            showIndent(outfile, level, pretty_print)\n' % fill)
            if child.isListType():
                s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_double_list(self.%s, input_name='%s'), namespace_, eol_))\n" % \
                    (fill, name, name, mappedName, name, )
            else:
                s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_double(self.%s, input_name='%s'), namespace_, eol_))\n" % \
                    (fill, name, name, mappedName, name, )
            wrt(s1)
        else:
            wrt("%s        if self.%s is not None:\n" % (fill, mappedName))
            # name_type_problem
            if False:        # name == child.getType():
                s1 = "%s            self.%s.export(outfile, level, namespace_, pretty_print=pretty_print)\n" % \
                    (fill, mappedName)
            else:
                s1 = "%s            self.%s.export(outfile, level, namespace_, name_='%s', pretty_print=pretty_print)\n" % \
                    (fill, mappedName, name)
            wrt(s1)
    # end _generateExportFn_1


    def _generateExportFn_2(self, wrt, child, name, namespace, fill):
        cleanName = self._PGenr.cleanupName(name)
        mappedName = self._PGenr.mapName(cleanName)
        child_type = child.getType()
        # fix_simpletype
        wrt("%s    for %s_ in self.%s:\n" % (fill, cleanName, mappedName, ))
        if child_type in self._PGenr.StringType or \
            child_type == self._PGenr.TokenType or \
            child_type == self._PGenr.DateTimeType or \
            child_type == self._PGenr.TimeType or \
            child_type == self._PGenr.DateType:
            wrt('%s        showIndent(outfile, level, pretty_print)\n' % fill)
            wrt("%s        outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_string(quote_xml(%s_).encode(ExternalEncoding), input_name='%s'), namespace_, eol_))\n" %
                (fill, name, name, cleanName, name,))
        elif child_type in self._PGenr.IntegerType or \
            child_type == self._PGenr.PositiveIntegerType or \
            child_type == self._PGenr.NonPositiveIntegerType or \
            child_type == self._PGenr.NegativeIntegerType or \
            child_type == self._PGenr.NonNegativeIntegerType:
            wrt('%s        showIndent(outfile, level, pretty_print)\n' % fill)
            if child.isListType():
                s1 = "%s        outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_integer_list(%s_, input_name='%s'), namespace_, eol_))\n" % \
                    (fill, name, name, cleanName, name, )
            else:
                s1 = "%s        outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_integer(%s_, input_name='%s'), namespace_, eol_))\n" % \
                    (fill, name, name, cleanName, name, )
            wrt(s1)
        elif child_type == self._PGenr.BooleanType:
            wrt('%s        showIndent(outfile, level, pretty_print)\n' % fill)
            if child.isListType():
                s1 = "%s        outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_boolean_list(self.gds_str_lower(str(%s_)), input_name='%s'), namespace_, eol_))\n" % \
                    (fill, name, name, cleanName, name, )
            else:
                s1 = "%s        outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_boolean(self.gds_str_lower(str(%s_)), input_name='%s'), namespace_, eol_))\n" % \
                    (fill, name, name, cleanName, name, )
            wrt(s1)
        elif child_type == self._PGenr.FloatType or \
            child_type == self._PGenr.DecimalType:
            wrt('%s        showIndent(outfile, level, pretty_print)\n' % fill)
            if child.isListType():
                s1 = "%s        outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_float_list(%s_, input_name='%s'), namespace_, eol_))\n" % \
                    (fill, name, name, cleanName, name, )
            else:
                s1 = "%s        outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_float(%s_, input_name='%s'), namespace_, eol_))\n" % \
                    (fill, name, name, cleanName, name, )
            wrt(s1)
        elif child_type == self._PGenr.DoubleType:
            wrt('%s        showIndent(outfile, level, pretty_print)\n' % fill)
            if child.isListType():
                s1 = "%s        outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_double_list(%s_, input_name='%s'), namespace_, eol_))\n" % \
                    (fill, name, name, cleanName, name, )
            else:
                s1 = "%s        outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_double(%s_, input_name='%s'), namespace_, eol_))\n" % \
                    (fill, name, name, cleanName, name, )
            wrt(s1)
        else:
            # name_type_problem
            if False:        # name == child.getType():
                s1 = "%s        %s_.export(outfile, level, namespace_, pretty_print=pretty_print)\n" % (fill, cleanName)
            else:
                wrt("%s        if isinstance(%s_, dict):\n" %(fill, cleanName))
                wrt("%s            %s_ = %s(**%s_)\n" %(fill, cleanName, child_type, cleanName))
                s1 = "%s        %s_.export(outfile, level, namespace_, name_='%s', pretty_print=pretty_print)\n" % \
                    (fill, cleanName, name)
            wrt(s1)
    # end generateExportFn_2

    def _generateExportFn_3(self, wrt, child, name, namespace, fill):
        cleanName = self._PGenr.cleanupName(name)
        mappedName = self._PGenr.mapName(cleanName)
        child_type = child.getType()
        # fix_simpletype
        if child_type in self._PGenr.StringType or \
            child_type == self._PGenr.TokenType or \
            child_type == self._PGenr.DateTimeType or \
            child_type == self._PGenr.TimeType or \
            child_type == self._PGenr.DateType:
            wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
            wrt('%s            showIndent(outfile, level, pretty_print)\n' % fill)
            # fixlist
            if (child.getSimpleType() in self._PGenr.SimpleTypeDict and
                self._PGenr.SimpleTypeDict[child.getSimpleType()].isListType()):
                s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_string(quote_xml(' '.join(self.%s)).encode(ExternalEncoding), input_name='%s'), namespace_, eol_))\n" % \
                    (fill, name, name, mappedName, name, )
            else:
                s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_string(quote_xml(self.%s).encode(ExternalEncoding), input_name='%s'), namespace_, eol_))\n" % \
                    (fill, name, name, mappedName, name, )
            wrt(s1)
        elif child_type in self._PGenr.IntegerType or \
            child_type == self._PGenr.PositiveIntegerType or \
            child_type == self._PGenr.NonPositiveIntegerType or \
            child_type == self._PGenr.NegativeIntegerType or \
            child_type == self._PGenr.NonNegativeIntegerType:
            wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
            wrt('%s            showIndent(outfile, level, pretty_print)\n' % fill)
            if child.isListType():
                s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_integer_list(self.%s, input_name='%s'), namespace_, eol_))\n" % \
                    (fill, name, name, mappedName, name, )
            else:
                s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_integer(self.%s, input_name='%s'), namespace_, eol_))\n" % \
                    (fill, name, name, mappedName, name, )
            wrt(s1)
        elif child_type == self._PGenr.BooleanType:
            wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
            wrt('%s            showIndent(outfile, level, pretty_print)\n' % fill)
            if child.isListType():
                s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_boolean_list(self.gds_str_lower(str(self.%s)), input_name='%s'), namespace_, eol_))\n" % \
                    (fill, name, name, mappedName, name )
            else:
                s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_boolean(self.gds_str_lower(str(self.%s)), input_name='%s'), namespace_, eol_))\n" % \
                    (fill, name, name, mappedName, name )
            wrt(s1)
        elif child_type == self._PGenr.FloatType or \
            child_type == self._PGenr.DecimalType:
            wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
            wrt('%s            showIndent(outfile, level, pretty_print)\n' % fill)
            if child.isListType():
                s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_float_list(self.%s, input_name='%s'), namespace_, eol_))\n" % \
                    (fill, name, name, mappedName, name, )
            else:
                s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_float(self.%s, input_name='%s'), namespace_, eol_))\n" % \
                    (fill, name, name, mappedName, name, )
            wrt(s1)
        elif child_type == self._PGenr.DoubleType:
            wrt('%s        if self.%s is not None:\n' % (fill, mappedName, ))
            wrt('%s            showIndent(outfile, level, pretty_print)\n' % fill)
            if child.isListType():
                s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_double_list(self.%s, input_name='%s'), namespace_, eol_))\n" % \
                    (fill, name, name, mappedName, name, )
            else:
                s1 = "%s            outfile.write('<%%s%s>%%s</%%s%s>%%s' %% (namespace_, self.gds_format_double(self.%s, input_name='%s'), namespace_, eol_))\n" % \
                    (fill, name, name, mappedName, name, )
            wrt(s1)
        else:
            wrt("%s        if self.%s is not None:\n" % (fill, mappedName))
            # name_type_problem
            if False:        # name == child.getType():
                s1 = "%s            self.%s.export(outfile, level, namespace_, pretty_print=pretty_print)\n" % \
                    (fill, mappedName)
            else:
                s1 = "%s            self.%s.export(outfile, level, namespace_, name_='%s', pretty_print=pretty_print)\n" % \
                    (fill, mappedName, name)
            wrt(s1)
    # end generateExportFn_3

    def generateExportDict(self, wrt, element):
        name = element.getName()
        base = element.getBase()
        wrt("    def exportDict(self, name_='%s'):\n" % (name, ))
        wrt('        # do obj->json->dict to handle nested complextype in object\n')
        wrt('        obj_json = json.dumps(self, default=lambda o: dict((k, v) for k, v in o.__dict__.iteritems()))\n')
        wrt('        obj_dict = json.loads(obj_json)\n')
        wrt('        if name_:\n')
        wrt('            return {name_: obj_dict}\n')
        wrt('        return obj_dict\n')

    def generateBuild(self, wrt, element):
        base = element.getBase()
        wrt('    def build(self, node):\n')
        wrt('        self.buildAttributes(node, node.attrib, [])\n')
        childCount = self._PGenr.countChildren(element, 0)
        if element.isMixed() or element.getSimpleContent():
            wrt("        self.valueOf_ = get_all_text_(node)\n")
        if element.isMixed():
            wrt("        if node.text is not None:\n")
            wrt("            obj_ = self.mixedclass_(MixedContainer.CategoryText,\n")
            wrt("                MixedContainer.TypeNone, '', node.text)\n")
            wrt("            self.content_.append(obj_)\n")
        wrt('        for child in node:\n')
        wrt("            nodeName_ = Tag_pattern_.match(child.tag).groups()[-1]\n")
        wrt("            self.buildChildren(child, node, nodeName_)\n")

    def generateBuildAttributesFn(self, wrt, element):
        wrt('    def buildAttributes(self, node, attrs, already_processed):\n')
        hasAttributes = 0
        hasAttributes = self._generateBuildAttributes(wrt, element, hasAttributes)
        parentName, parent = self._PGenr.getParentName(element)
        if parentName:
            hasAttributes += 1
            elName = element.getCleanName()
            wrt('        super(%s, self).buildAttributes(node, attrs, already_processed)\n' % (
                elName, ))
        if hasAttributes == 0:
            wrt('        pass\n')

    def _generateBuildAttributes(self, wrt, element, hasAttributes):
        attrDefs = element.getAttributeDefs()
        for key in attrDefs:
            attrDef = attrDefs[key]
            hasAttributes += 1
            name = attrDef.getName()
            cleanName = self._PGenr.cleanupName(name)
            mappedName = self._PGenr.mapName(cleanName)
            atype = attrDef.getType()
            if atype in self._PGenr.SimpleTypeDict:
                atype = self._PGenr.SimpleTypeDict[atype].getBase()
            self._LangGenr.generateBuildAttributeForType(wrt, element, atype, name, mappedName)
        hasAttributes += self._generateBuildAttributeForAny(wrt, element)
        hasAttributes += self._generateBuildAttributeForExt(wrt, element)
        return hasAttributes

    def _generateBuildAttributeForType(self, wrt, element, atype, name, mappedName):
        if atype in self._PGenr.IntegerType or \
            atype == self._PGenr.PositiveIntegerType or \
            atype == self._PGenr.NonPositiveIntegerType or \
            atype == self._PGenr.NegativeIntegerType or \
            atype == self._PGenr.NonNegativeIntegerType:
            wrt("        value = find_attr_value_('%s', node)\n" % (name, ))
            wrt("        if value is not None and '%s' not in already_processed:\n" % (
                name, ))
            wrt("            already_processed.append('%s')\n" % (name, ))
            wrt('            try:\n')
            wrt("                self.%s = int(value)\n" % (mappedName, ))
            wrt('            except ValueError, exp:\n')
            wrt("                raise_parse_error(node, 'Bad integer attribute: %s' % exp)\n")
            if atype == self._PGenr.PositiveIntegerType:
                wrt('            if self.%s <= 0:\n' % mappedName)
                wrt("                raise_parse_error(node, 'Invalid PositiveInteger')\n")
            elif atype == self._PGenr.NonPositiveIntegerType:
                wrt('            if self.%s > 0:\n' % mappedName)
                wrt("                raise_parse_error(node, 'Invalid NonPositiveInteger')\n")
            elif atype == self._PGenr.NegativeIntegerType:
                wrt('            if self.%s >= 0:\n' % mappedName)
                wrt("                raise_parse_error(node, 'Invalid NegativeInteger')\n")
            elif atype == self._PGenr.NonNegativeIntegerType:
                wrt('            if self.%s < 0:\n' % mappedName)
                wrt("                raise_parse_error(node, 'Invalid NonNegativeInteger')\n")
        elif atype == self._PGenr.BooleanType:
            wrt("        value = find_attr_value_('%s', node)\n" % (name, ))
            wrt("        if value is not None and '%s' not in already_processed:\n" % (
                name, ))
            wrt("            already_processed.append('%s')\n" % (name, ))
            wrt("            if value in ('true', '1'):\n")
            wrt("                self.%s = True\n" % mappedName)
            wrt("            elif value in ('false', '0'):\n")
            wrt("                self.%s = False\n" % mappedName)
            wrt('            else:\n')
            wrt("                raise_parse_error(node, 'Bad boolean attribute')\n")
        elif atype == self._PGenr.FloatType or atype == self._PGenr.DoubleType or atype == self._PGenr.DecimalType:
            wrt("        value = find_attr_value_('%s', node)\n" % (name, ))
            wrt("        if value is not None and '%s' not in already_processed:\n" % (
                name, ))
            wrt("            already_processed.append('%s')\n" % (name, ))
            wrt('            try:\n')
            wrt("                self.%s = float(value)\n" % \
                (mappedName, ))
            wrt('            except ValueError, exp:\n')
            wrt("                raise ValueError('Bad float/double attribute (%s): %%s' %% exp)\n" % \
                (name, ))
        elif atype == self._PGenr.TokenType:
            wrt("        value = find_attr_value_('%s', node)\n" % (name, ))
            wrt("        if value is not None and '%s' not in already_processed:\n" % (
                name, ))
            wrt("            already_processed.append('%s')\n" % (name, ))
            wrt("            self.%s = value\n" % (mappedName, ))
            wrt("            self.%s = ' '.join(self.%s.split())\n" % \
                (mappedName, mappedName, ))
        else:
            # Assume attr['type'] in StringType or attr['type'] == DateTimeType:
            wrt("        value = find_attr_value_('%s', node)\n" % (name, ))
            wrt("        if value is not None and '%s' not in already_processed:\n" % (
                name, ))
            wrt("            already_processed.append('%s')\n" % (name, ))
            wrt("            self.%s = value\n" % (mappedName, ))
        typeName = attrDef.getType()
        if typeName and typeName in self._PGenr.SimpleTypeDict:
            wrt("            self.validate_%s(self.%s)    # validate type %s\n" % (
                typeName, mappedName, typeName, ))

    def _generateBuildAttributeForAny(self, wrt, element):
        hasAttributes = 0
        if element.getAnyAttribute():
            hasAttributes += 1
            wrt('        self.anyAttributes_ = {}\n')
            wrt('        for name, value in attrs.items():\n')
            wrt("            if name not in already_processed:\n")
            wrt('                self.anyAttributes_[name] = value\n')
        return hasAttributes

    def _generateBuildAttributeForExt(self, wrt, element):
        hasAttributes = 0
        if element.getExtended():
            hasAttributes += 1
            wrt("        value = find_attr_value_('xsi:type', node)\n")
            wrt("        if value is not None and 'xsi:type' not in already_processed:\n")
            wrt("            already_processed.append('xsi:type')\n")
            wrt("            self.extensiontype_ = value\n")
        return hasAttributes
    
    def generateBuildChildren(self, wrt, element, prefix, delayed):
        wrt('    def buildChildren(self, child_, node, nodeName_, fromsubclass_=False):\n')
        keyword = 'if'
        hasChildren = 0
        if element.isMixed():
            hasChildren = self._generateBuildMixed(wrt, prefix, element, keyword,
                delayed, hasChildren)
        else:      # not element.isMixed()
            hasChildren = self._generateBuildStandard(wrt, prefix, element, keyword,
                delayed, hasChildren)
        # Generate call to buildChildren in the superclass only if it is
        #  an extension, but *not* if it is a restriction.
        base = element.getBase()
        if base and not element.getSimpleContent():
            elName = element.getCleanName()
            wrt("        super(%s, self).buildChildren(child_, node, nodeName_, True)\n" % (elName, ))
        eltype = element.getType()
        if hasChildren == 0:
            wrt("        pass\n")

    def _generateBuildStandard(self, wrt, prefix, element, keyword, delayed, hasChildren):
        any_type_child = None
        for child in element.getChildren():
            if child.getType() == self._PGenr.AnyTypeIdentifier:
                any_type_child = child
            else:
                self._generateBuildStandard_1(wrt, prefix, child, child,
                    element, keyword, delayed)
                hasChildren += 1
                keyword = 'elif'
                # Does this element have a substitutionGroup?
                #   If so generate a clause for each element in the substitutionGroup.
                childName = child.getName()
                if childName in self._PGenr.SubstitutionGroups:
                    for memberName in transitiveClosure(self._PGenr.SubstitutionGroups, childName):
                        memberName = self._PGenr.cleanupName(memberName)
                        if memberName in self._PGenr.ElementDict:
                            member = self._PGenr.ElementDict[memberName]
                            self._generateBuildStandard_1(wrt, prefix, member, child,
                                element, keyword, delayed)
    
        hasChildren += self._generateBuildAnyType(wrt, element, any_type_child)
        return hasChildren

    def _generateBuildStandard_1(self, wrt, prefix, child, headChild,
            element, keyword, delayed):
        origName = child.getName()
        name = self._PGenr.cleanupName(child.getName())
        mappedName = self._PGenr.mapName(name)
        headName = self._PGenr.cleanupName(headChild.getName())
        attrCount = len(child.getAttributeDefs())
        childType = child.getType()
        base = child.getBase()
        self._generateBuildStandard_1_ForType(wrt, prefix, child, headChild, keyword, delayed)
        #
        # If this child is defined in a simpleType, then generate
        #   a validator method.
        self._generateBuildValidator(wrt, child)

    def _generateBuildMixed(wrt, prefix, element, keyword, delayed, hasChildren):
        for child in element.getChildren():
            self._generateBuildMixed_1(wrt, prefix, child, child, keyword, delayed)
            hasChildren += 1
            keyword = 'elif'
            # Does this element have a substitutionGroup?
            #   If so generate a clause for each element in the substitutionGroup.
            if child.getName() in self._PGenr.SubstitutionGroups:
                for memberName in self._PGenr.SubstitutionGroups[child.getName()]:
                    if memberName in self._PGenr.ElementDict:
                        member = self._PGenr.ElementDict[memberName]
                        self._generateBuildMixed_1(wrt, prefix, member, child,
                            keyword, delayed)
        wrt("        if not fromsubclass_ and child_.tail is not None:\n")
        wrt("            obj_ = self.mixedclass_(MixedContainer.CategoryText,\n")
        wrt("                MixedContainer.TypeNone, '', child_.tail)\n")
        wrt("            self.content_.append(obj_)\n")
    ##    base = element.getBase()
    ##    if base and base in ElementDict:
    ##        parent = ElementDict[base]
    ##        hasChildren = generateBuildMixed(wrt, prefix, parent, keyword, delayed, hasChildren)
        return hasChildren

    def _generateBuildMixed_1(wrt, prefix, child, headChild, keyword, delayed):
        nestedElements = 1
        origName = child.getName()
        name = child.getCleanName()
        headName = self._PGenr.cleanupName(headChild.getName())
        childType = child.getType()
        mappedName = self._PGenr.mapName(name)
        base = child.getBase()
        if childType in self._PGenr.StringType or \
            childType == self._PGenr.TokenType or \
            childType == self._PGenr.DateTimeType or \
            childType == self._PGenr.TimeType or \
            childType == self._PGenr.DateType:
            wrt("        %s nodeName_ == '%s' and child_.text is not None:\n" % (
                keyword, origName, ))
            wrt("            valuestr_ = child_.text\n")
            if childType == TokenType:
                wrt('            valuestr_ = re_.sub(String_cleanup_pat_, " ", valuestr_).strip()\n')
            wrt("            obj_ = self.mixedclass_(MixedContainer.CategorySimple,\n")
            wrt("                MixedContainer.TypeString, '%s', valuestr_)\n" % \
                origName)
            wrt("            self.content_.append(obj_)\n")
        elif childType in self._PGenr.IntegerType or \
            childType == self._PGenr.PositiveIntegerType or \
            childType == self._PGenr.NonPositiveIntegerType or \
            childType == self._PGenr.NegativeIntegerType or \
            childType == self._PGenr.NonNegativeIntegerType:
            wrt("        %s nodeName_ == '%s' and child_.text is not None:\n" % (
                keyword, origName, ))
            wrt("            sval_ = child_.text\n")
            wrt("            try:\n")
            wrt("                ival_ = int(sval_)\n")
            wrt("            except (TypeError, ValueError), exp:\n")
            wrt("                raise_parse_error(child_, 'requires integer: %s' % exp)\n")
            if childType == self._PGenr.PositiveIntegerType:
                wrt("            if ival_ <= 0:\n")
                wrt("                raise_parse_error(child_, 'Invalid positiveInteger')\n")
            if childType == self._PGenr.NonPositiveIntegerType:
                wrt("            if ival_ > 0:\n")
                wrt("                raise_parse_error(child_, 'Invalid nonPositiveInteger)\n")
            if childType == self._PGenr.NegativeIntegerType:
                wrt("            if ival_ >= 0:\n")
                wrt("                raise_parse_error(child_, 'Invalid negativeInteger')\n")
            if childType == self._PGenr.NonNegativeIntegerType:
                wrt("            if ival_ < 0:\n")
                wrt("                raise_parse_error(child_, 'Invalid nonNegativeInteger')\n")
            wrt("            obj_ = self.mixedclass_(MixedContainer.CategorySimple,\n")
            wrt("                MixedContainer.TypeInteger, '%s', ival_)\n" % (
                origName, ))
            wrt("            self.content_.append(obj_)\n")
        elif childType == self._PGenr.BooleanType:
            wrt("        %s nodeName_ == '%s' and child_.text is not None:\n" % (
                keyword, origName, ))
            wrt("            sval_ = child_.text\n")
            wrt("            if sval_ in ('true', '1'):\n")
            wrt("                ival_ = True\n")
            wrt("            elif sval_ in ('false', '0'):\n")
            wrt("                ival_ = False\n")
            wrt("            else:\n")
            wrt("                raise_parse_error(child_, 'requires boolean')\n")
            wrt("        obj_ = self.mixedclass_(MixedContainer.CategorySimple,\n")
            wrt("            MixedContainer.TypeInteger, '%s', ival_)\n" % \
                origName)
            wrt("        self.content_.append(obj_)\n")
        elif childType == self._PGenr.FloatType or \
            childType == self._PGenr.DoubleType or \
            childType == self._PGenr.DecimalType:
            wrt("        %s nodeName_ == '%s' and child_.text is not None:\n" % (
                keyword, origName, ))
            wrt("            sval_ = child_.text\n")
            wrt("            try:\n")
            wrt("                fval_ = float(sval_)\n")
            wrt("            except (TypeError, ValueError), exp:\n")
            wrt("                raise_parse_error(child_, 'requires float or double: %s' % exp)\n")
            wrt("            obj_ = self.mixedclass_(MixedContainer.CategorySimple,\n")
            wrt("                MixedContainer.TypeFloat, '%s', fval_)\n" % \
                origName)
            wrt("            self.content_.append(obj_)\n")
        else:
            # Perhaps it's a complexType that is defined right here.
            # Generate (later) a class for the nested types.
            type_element = None
            abstract_child = False
            type_name = child.getAttrs().get('type')
            if type_name:
                type_element = self._PGenr.ElementDict.get(type_name)
            if type_element and type_element.isAbstract():
                abstract_child = True
            if not delayed and not child in self._PGenr.DelayedElements:
                self._PGenr.DelayedElements.append(child)
                self._PGenr.DelayedElements_subclass.append(child)
            wrt("        %s nodeName_ == '%s':\n" % (keyword, origName, ))
            if abstract_child:
                wrt(TEMPLATE_ABSTRACT_CHILD % (mappedName, ))
            else:
                type_obj = self._PGenr.ElementDict.get(childType)
                if type_obj is not None and type_obj.getExtended():
                    wrt("            class_obj_ = self.get_class_obj_(child_, %s%s)\n" % (
                        prefix, self._PGenr.cleanupName(self._PGenr.mapName(childType)), ))
                    wrt("            class_obj_ = %s%s.factory()\n")
                else:
                    wrt("            obj_ = %s%s.factory()\n" % (
                        prefix, self._PGenr.cleanupName(self._PGenr.mapName(childType))))
                wrt("            obj_.build(child_)\n")
    
            wrt("            obj_ = self.mixedclass_(MixedContainer.CategoryComplex,\n")
            wrt("                MixedContainer.TypeNone, '%s', obj_)\n" % \
                origName)
            wrt("            self.content_.append(obj_)\n")
    
            # Generate code to sort mixed content in their class
            # containers
            s1 = "            if hasattr(self, 'add_%s'):\n" % (origName, )
            s1 +="              self.add_%s(obj_.value)\n" % (origName, )
            s1 +="            elif hasattr(self, 'set_%s'):\n" % (origName, )
            s1 +="              self.set_%s(obj_.value)\n" % (origName, )
            wrt(s1)

    def _generateBuildStandard_1_ForType(self, wrt, prefix, child, headChild, keyword, delayed):
        origName = child.getName()
        name = self._PGenr.cleanupName(child.getName())
        mappedName = self._PGenr.mapName(name)
        headName = self._PGenr.cleanupName(headChild.getName())
        childType = child.getType()
        attrCount = len(child.getAttributeDefs())
        if (attrCount == 0 and
            ((childType in self._PGenr.StringType or
                childType == self._PGenr.TokenType or
                childType == self._PGenr.DateTimeType or
                childType == self._PGenr.TimeType or
                childType == self._PGenr.DateType or
                child.isListType()
            ))
            ):
            wrt("        %s nodeName_ == '%s':\n" % (keyword, origName, ))
            wrt("            %s_ = child_.text\n" % name)
            if childType == self._PGenr.TokenType:
                wrt('            %s_ = re_.sub(String_cleanup_pat_, " ", %s_).strip()\n' %(name, name))
            if child.isListType():
                if childType in self._PGenr.IntegerType or \
                    childType == self._PGenr.PositiveIntegerType or \
                    childType == self._PGenr.NonPositiveIntegerType or \
                    childType == self._PGenr.NegativeIntegerType or \
                    childType == self._PGenr.NonNegativeIntegerType:
                    wrt("            %s_ = self.gds_validate_integer_list(%s_, node, '%s')\n" % (
                        name, name, name, ))
                elif childType == self._PGenr.BooleanType:
                    wrt("            %s_ = self.gds_validate_boolean_list(%s_, node, '%s')\n" % (
                        name, name, name, ))
                elif childType == self._PGenr.FloatType or \
                    childType == self._PGenr.DecimalType:
                    wrt("            %s_ = self.gds_validate_float_list(%s_, node, '%s')\n" % (
                        name, name, name, ))
                elif childType == self._PGenr.DoubleType:
                    wrt("            %s_ = self.gds_validate_double_list(%s_, node, '%s')\n" % (
                        name, name, name, ))
            else:
                wrt("            %s_ = self.gds_validate_string(%s_, node, '%s')\n" % (
                    name, name, name, ))
            if child.getMaxOccurs() > 1:
                wrt("            self.%s.append(%s_)\n" % (mappedName, name, ))
            else:
                wrt("            self.%s = %s_\n" % (mappedName, name, ))
        elif childType in self._PGenr.IntegerType or \
            childType == self._PGenr.PositiveIntegerType or \
            childType == self._PGenr.NonPositiveIntegerType or \
            childType == self._PGenr.NegativeIntegerType or \
            childType == self._PGenr.NonNegativeIntegerType:
            wrt("        %s nodeName_ == '%s':\n" % (keyword, origName, ))
            wrt("            sval_ = child_.text\n")
            wrt("            try:\n")
            wrt("                ival_ = int(sval_)\n")
            wrt("            except (TypeError, ValueError), exp:\n")
            wrt("                raise_parse_error(child_, 'requires integer: %s' % exp)\n")
            if childType == self._PGenr.PositiveIntegerType:
                wrt("            if ival_ <= 0:\n")
                wrt("                raise_parse_error(child_, 'requires positiveInteger')\n")
            elif childType == self._PGenr.NonPositiveIntegerType:
                wrt("            if ival_ > 0:\n")
                wrt("                raise_parse_error(child_, 'requires nonPositiveInteger')\n")
            elif childType == self._PGenr.NegativeIntegerType:
                wrt("            if ival_ >= 0:\n")
                wrt("                raise_parse_error(child_, 'requires negativeInteger')\n")
            elif childType == self._PGenr.NonNegativeIntegerType:
                wrt("            if ival_ < 0:\n")
                wrt("                raise_parse_error(child_, 'requires nonNegativeInteger')\n")
            wrt("            ival_ = self.gds_validate_integer(ival_, node, '%s')\n" % (
                name, ))
            if child.getMaxOccurs() > 1:
                wrt("            self.%s.append(ival_)\n" % (mappedName, ))
            else:
                wrt("            self.%s = ival_\n" % (mappedName, ))
        elif childType == self._PGenr.BooleanType:
            wrt("        %s nodeName_ == '%s':\n" % (keyword, origName, ))
            wrt("            sval_ = child_.text\n")
            wrt("            if sval_ in ('true', '1'):\n")
            wrt("                ival_ = True\n")
            wrt("            elif sval_ in ('false', '0'):\n")
            wrt("                ival_ = False\n")
            wrt("            else:\n")
            wrt("                raise_parse_error(child_, 'requires boolean')\n")
            wrt("            ival_ = self.gds_validate_boolean(ival_, node, '%s')\n" % (
                name, ))
            if child.getMaxOccurs() > 1:
                wrt("            self.%s.append(ival_)\n" % (mappedName, ))
            else:
                wrt("            self.%s = ival_\n" % (mappedName, ))
        elif childType == self._PGenr.FloatType or \
            childType == self._PGenr.DoubleType or \
            childType == self._PGenr.DecimalType:
            wrt("        %s nodeName_ == '%s':\n" % (keyword, origName, ))
            wrt("            sval_ = child_.text\n")
            wrt("            try:\n")
            wrt("                fval_ = float(sval_)\n")
            wrt("            except (TypeError, ValueError), exp:\n")
            wrt("                raise_parse_error(child_, 'requires float or double: %s' % exp)\n")
            wrt("            fval_ = self.gds_validate_float(fval_, node, '%s')\n" % (
                name, ))
            if child.getMaxOccurs() > 1:
                wrt("            self.%s.append(fval_)\n" % (mappedName, ))
            else:
                wrt("            self.%s = fval_\n" % (mappedName, ))
        else:
            # Perhaps it's a complexType that is defined right here.
            # Generate (later) a class for the nested types.
            # fix_abstract
            type_element = None
            abstract_child = False
            type_name = child.getAttrs().get('type')
            if type_name:
                type_element = self._PGenr.ElementDict.get(type_name)
            if type_element and type_element.isAbstract():
                abstract_child = True
            if not delayed and not child in self._PGenr.DelayedElements:
                self._PGenr.DelayedElements.append(child)
                self._PGenr.DelayedElements_subclass.append(child)
            wrt("        %s nodeName_ == '%s':\n" % (keyword, origName, ))
            # Is this a simple type?
            base = child.getBase()
            if child.getSimpleType():
                wrt("            obj_ = None\n")
            else:
                # name_type_problem
                # fix_abstract
                if type_element:
                    type_name = type_element.getType()
                elif origName in self._PGenr.ElementDict:
                    type_name = self._PGenr.ElementDict[origName].getType()
                else:
                    type_name = childType
                type_name = self._PGenr.cleanupName(self._PGenr.mapName(type_name))
                if abstract_child:
                    wrt(TEMPLATE_ABSTRACT_CHILD % (mappedName, ))
                else:
                    type_obj = self._PGenr.ElementDict.get(type_name)
                    if type_obj is not None and type_obj.getExtended():
                        wrt("            class_obj_ = self.get_class_obj_(child_, %s%s)\n" % (
                            prefix, type_name, ))
                        wrt("            obj_ = class_obj_.factory()\n")
                    else:
                        wrt("            obj_ = %s%s.factory()\n" % (
                            prefix, type_name, ))
                    wrt("            obj_.build(child_)\n")
            if headChild.getMaxOccurs() > 1:
                substitutionGroup = child.getAttrs().get('substitutionGroup')
                if substitutionGroup is not None:
                    name = substitutionGroup
                else:
                    name = mappedName
                s1 = "            self.%s.append(obj_)\n" % (name, )
            else:
                substitutionGroup = child.getAttrs().get('substitutionGroup')
                if substitutionGroup is not None:
                    name = substitutionGroup
                else:
                    name = headName
                s1 = "            self.set%s(obj_)\n" % (self._PGenr.make_gs_name(name), )
            wrt(s1)

    def _generateBuildValidator(self, wrt, child):
        typeName = None
        childType = child.getType()
        if child.getSimpleType():
            #typeName = child.getSimpleType()
            typeName = self._PGenr.cleanupName(child.getName())
        elif (childType in self._PGenr.ElementDict and 
            self._PGenr.ElementDict[childType].getSimpleType()):
            typeName = self._PGenr.ElementDict[childType].getType()
        # fixlist
        mappedName = self._PGenr.mapName(child.getName())
        cleanupName = self._PGenr.cleanupName(mappedName)
        if (child.getSimpleType() in self._PGenr.SimpleTypeDict and 
            self._PGenr.SimpleTypeDict[child.getSimpleType()].isListType()):
            wrt("            self.%s = self.%s.split()\n" % (
                cleanupName, cleanupName, ))
        typeName = child.getSimpleType()
        if typeName and typeName in self._PGenr.SimpleTypeDict:
            wrt("            self.validate_%s(self.%s)    # validate type %s\n" % (
                typeName, cleanupName, typeName, ))

    def _generateBuildAnyType(self, wrt, element, any_type_child):
        hasChildren = 0
        if any_type_child is not None:
            type_name = element.getType()
            if any_type_child.getMaxOccurs() > 1:
                if keyword == 'if':
                    fill = ''
                else:
                    fill = '    '
                    wrt("        else:\n")
                wrt("        %sobj_ = self.gds_build_any(child_, '%s')\n" % (
                    fill, type_name, ))
                wrt("        %sif obj_ is not None:\n" % (fill, ))
                wrt('            %sself.add_anytypeobjs_(obj_)\n' % (fill, ))
            else:
                if keyword == 'if':
                    fill = ''
                else:
                    fill = '    '
                    wrt("        else:\n")
                wrt("        %sobj_ = self.gds_build_any(child_, '%s')\n" % (
                    fill, type_name, ))
                wrt("        %sif obj_ is not None:\n" % (fill, ))
                wrt('            %sself.set_anytypeobjs_(obj_)\n' % (fill, ))
            hasChildren += 1

        return hasChildren

    def generateMain(self, outfile, prefix, root):
        name = self._PGenr.RootElement or root.getChildren()[0].getName()
        elType = self._PGenr.cleanupName(root.getChildren()[0].getType())
        if self._PGenr.RootElement:
            rootElement = self._PGenr.RootElement
        else:
            rootElement = elType
        params = {
            'prefix': prefix,
            'cap_name': self._PGenr.cleanupName(self._PGenr.make_gs_name(name)),
            'name': name,
            'cleanname': self._PGenr.cleanupName(name),
            'module_name': os.path.splitext(os.path.basename(outfile.name))[0],
            'root': rootElement,
            'namespacedef': self._PGenr.Namespacedef,
            }
        s1 = self._PGenr.TEMPLATE_MAIN % params
        outfile.write(s1)

    def generateComparators(self, wrt, element):
        generatedSimpleTypes = []
        childCount = self._PGenr.countChildren(element, 0)
        comps = []
        for child in element.getChildren():
            if child.getType() == self._PGenr.AnyTypeIdentifier:
                continue
            else:
                name = self._PGenr.cleanupName(child.getCleanName())
                comps.append('self.%s == other.%s' %(name, name))

        if len(comps) == 0:
            wrt('    def __eq__(self, other): return True\n')
            wrt('    def __ne__(self, other): return False\n')
            return

        comp_str = ' and\n                '.join(comps)
        wrt('    def __eq__(self, other):\n')
        wrt('        if isinstance(other, self.__class__):\n')
        wrt('            return (%s)\n' % comp_str)
        wrt('        return NotImplemented\n')
        wrt('    def __ne__(self, other):\n')
        wrt('        if isinstance(other, self.__class__):\n')
        wrt('            return not self.__eq__(other)\n')
        wrt('        return NotImplemented\n')
        wrt('\n')


class CppGenerator(object):
    def __init__(self, parser_generator):
        self._PGenr = parser_generator

    def generateHeader(self, wrt, prefix):
        pass

    def generateClassDefLine(self, wrt, parentName, prefix, name):
        self._Prefix = prefix
        if parentName:
            s1 = 'class %s%s: public %s {\n' % (prefix, name, parentName,)
            self._ParentName = parentName
        else:
            s1 = 'class %s%s: public GeneratedsSuper {\n' % (prefix, name)
            self._ParentName = 'GeneratedsSuper'

        wrt(s1)

    def generateElemDoc(self, wrt, element):
        pass

    def generateSubSuperInit(self, wrt, superclass_name):
        pass

    def generateCtor(self, wrt, element):
        elName = element.getCleanName()
        childCount = self._PGenr.countChildren(element, 0)
        (s2, s3, s4) = self.buildCtorArgs_multilevel(element, childCount)
        wrt('public:\n')   
        wrt('    %s%s(%s):\n' % (self._Prefix, elName, s2))
        wrt('    %s' % (s3))
        wrt('    {\n')
        wrt('    }\n')
        return (s4)
        #wrt('private:\n')
        #wrt('%s\n' % (s4))

    def buildCtorArgs_multilevel(self, element, childCount):
        content = []
        content_s = []
        content_d = []
        addedArgs = {}
        add = content.append
        add_s = content_s.append
        add_d = content_d.append
        self.buildCtorArgs_multilevel_aux(addedArgs, add, add_s, add_d, element)
        #CHKeltype = element.getType()
        #CHK if (element.getSimpleContent() or
        #CHK     element.isMixed() or
        #CHK     eltype in SimpleTypeDict or
        #CHK     CurrentNamespacePrefix + eltype in OtherSimpleTypes
        #CHK     ):
        #CHK     add(", valueOf_=None")
        #CHK if element.isMixed():
        #CHK     add(', mixedclass_=None')
        #CHK     add(', content_=None')
        #CHK if element.getExtended():
        #CHK     add(', extensiontype_=None')
        s2 = ''.join(content)
        s3 = ''.join(content_s) # Ctor Assign
        s4 = ''.join(content_d) # Ctor Declare
        return (s2,s3,s4)

    def buildCtorArgs_multilevel_aux(self, addedArgs, add, add_s, add_d, element):
        parentName, parentObj = self._PGenr.getParentName(element)
        if parentName:
            self.buildCtorArgs_multilevel_aux(addedArgs, add, add_s, add_d, parentObj)
        self.buildCtorArgs_aux(addedArgs, add, add_s, add_d, element)
    
    def buildCtorArgs_aux(self, addedArgs, add, add_s, add_d, element):
        attrDefs = element.getAttributeDefs()
        for key in attrDefs:
            attrDef = attrDefs[key]
            name = attrDef.getName()
            default = attrDef.getDefault()
    
            mappedName = name.replace(':', '_')
            mappedName = self._PGenr.cleanupName(mapName(mappedName))
            if mappedName in addedArgs:
                continue
            addedArgs[mappedName] = 1
            try:
                atype = attrDef.getData_type()
            except KeyError:
                atype = StringType
            mappedType = SchemaToCppTypeMap.get(atype)
            if atype in StringType or \
                atype == TokenType or \
                atype == DateTimeType or \
                atype == TimeType or \
                atype == DateType:
                if default is None:
                    add("%s %s, " % (mappedType, mappedName))
                else:
                    default1 = escape_string(default)
                    add("%s %s='%s', " % (mappedType, mappedName, default1))
            elif atype in IntegerType:
                if default is None:
                    add('%s %s, ' % (mappedType, mappedName))
                else:
                    add('%s %s=%s, ' % (mappedType, mappedName, default))
            elif atype == PositiveIntegerType:
                if default is None:
                    add('%s %s, ' % (mappedType, mappedName))
                else:
                    add('%s %s=%s, ' % (mappedType, mappedName, default))
            elif atype == NonPositiveIntegerType:
                if default is None:
                    add('%s %s, ' % (mappedType,mappedName))
                else:
                    add('%s %s=%s, ' % (mappedType, mappedName, default))
            elif atype == NegativeIntegerType:
                if default is None:
                    add('%s %s, ' % (mappedType, mappedName))
                else:
                    add('%s %s=%s, ' % (mappedType, mappedName, default))
            elif atype == NonNegativeIntegerType:
                if default is None:
                    add('%s %s, ' % (mappedType, mappedName))
                else:
                    add('%s %s=%s, ' % (mappedType, mappedName, default))
            elif atype == BooleanType:
                if default is None:
                    add('%s %s, ' % (mappedType, mappedName))
                else:
                    if default in ('false', '0'):
                        add('%s %s=%s, ' % (mappedType, mappedName, "false"))
                    else:
                        add('%s %s=%s, ' % (mappedType, mappedName, "true"))
            elif atype == FloatType or atype == DoubleType or atype == DecimalType:
                if default is None:
                    add('%s %s, ' % (mappedType, mappedName))
                else:
                    add('%s %s=%s, ' % (mappedType, mappedName, default))
            else:
                if default is None:
                    add('%s %s, ' % (mappedType, mappedName))
                else:
                    add("%s %s='%s', " % (mappedType, mappedName, default, ))
        nestedElements = 0
        firstChild = 0;
        for child in element.getChildren():
            cleanName = child.getCleanName()
            firstChild = firstChild + 1; 
            if cleanName in addedArgs:
                continue
            addedArgs[cleanName] = 1
            default = child.getDefault()
            nestedElements = 1
            if firstChild > 1:
                add(", ")
                add_s(", ")
            if child.getType() == self._PGenr.AnyTypeIdentifier:
                add('anytypeobjs_=NULL, ')
            elif child.getMaxOccurs() > 1:
                add(", %s %s" % (mappedType, cleanName))
            else:
                childType = child.getType()
                mappedType = self._PGenr.SchemaToCppTypeMap.get(childType)
                if childType in self._PGenr.StringType or \
                    childType == self._PGenr.TokenType or \
                    childType == self._PGenr.DateTimeType or \
                    childType == self._PGenr.TimeType or \
                    childType == self._PGenr.DateType:
                    if default is None:
                        add("%s %s" % (mappedType, cleanName))
                        add_s("%s_(%s)" % (cleanName, cleanName))
                        add_d("    %s %s_;\n" % (mappedType, cleanName))
                    else:
                        default1 = escape_string(default)
                        add("%s %s='%s'" % (mappedType, cleanName, default1, ))
                        add_s("%s_(%s)" % (cleanName_, cleanName))
                        add_d("    %s %s_;\n" % (mappedType, cleanName))
                elif (childType in self._PGenr.IntegerType or
                    childType == self._PGenr.PositiveIntegerType or
                    childType == self._PGenr.NonPositiveIntegerType or
                    childType == self._PGenr.NegativeIntegerType or
                    childType == self._PGenr.NonNegativeIntegerType
                    ):
                    if default is None:
                        add('%s %s' % (mappedType, cleanName))
                        add_s('%s_(%s)' % (cleanName, cleanName))
                        add_d('    %s %s_;\n' % (mappedType, cleanName))
                    else:
                        add('%s %s=%s' % (mappedType, cleanName, default, ))
                        add_s('%s_(%s)' % (cleanName, cleanName))
                        add_d('    %s %s_;\n' % (mappedType, cleanName))
    ##             elif childType in IntegerType:
    ##                 if default is None:
    ##                     add(', %s=-1' % cleanName)
    ##                 else:
    ##                     add(', %s=%s' % (cleanName, default, ))
    ##             elif childType == PositiveIntegerType:
    ##                 if default is None:
    ##                     add(', %s=1' % cleanName)
    ##                 else:
    ##                     add(', %s=%s' % (cleanName, default, ))
    ##             elif childType == NonPositiveIntegerType:
    ##                 if default is None:
    ##                     add(', %s=0' % cleanName)
    ##                 else:
    ##                     add(', %s=%s' % (cleanName, default, ))
    ##             elif childType == NegativeIntegerType:
    ##                 if default is None:
    ##                     add(', %s=-1' % cleanName)
    ##                 else:
    ##                     add(', %s=%s' % (cleanName, default, ))
    ##             elif childType == NonNegativeIntegerType:
    ##                 if default is None:
    ##                     add(', %s=0' % cleanName)
    ##                 else:
    ##                     add(', %s=%s' % (cleanName, default, ))
                elif childType == self._PGenr.BooleanType:
                    if default is None:
                        add('%s %s' % (mappedType, cleanName))
                        add_s('%s_(%s)' % (cleanName, cleanName))
                        add_d('    %s %s_;\n' % (mappedType, cleanName))
                    else:
                        if default in ('false', '0'):
                            add('%s %s=%s' % (mappedType, cleanName, "false", ))
                            add_s("%s_(%s)" % (cleanName_, cleanName))
                            add_d('    %s %s_;\n' % (mappedType, cleanName))
                        else:
                            add('%s %s=%s' % (mappedType, cleanName, "true", ))
                            add_s("%s_(%s)" % (cleanName_, cleanName))
                            add_d('    %s %s_;\n' % (mappedType, cleanName))
                elif childType == self._PGenr.FloatType or \
                    childType == self._PGenr.DoubleType or \
                    childType == self._PGenr.DecimalType:
                    if default is None:
                        add('%s %s' % (mappedType, cleanName))
                        add_s("%s_(%s)" % (cleanName_, cleanName))
                        add_d('    %s %s_;\n' % (mappedType, cleanName))
                    else:
                        add('%s %s;\n' % (mappedType, cleanName))
                        add_s("%s_(%s)" % (cleanName_, cleanName))
                        add_d('    %s %s_;\n' % (mappedType, cleanName))
                else:
                    add('%s %s' % (childType, cleanName))
                    add_s("%s_(%s)" % (cleanName, cleanName))
                    add_d('    %s %s_;\n' % (childType, cleanName))
    # end buildCtorArgs_aux

    def _generateTestHelpers (self, wrt, element):
        pass
    # end _generateTestHelpers

               
    def generateFactory(self, wrt, prefix, name):
        pass

    def generateGetter(self, wrt, capName, name, childType):
        mappedType = self._PGenr.SchemaToCppTypeMap.get(childType)
        if mappedType == None:
            mappedType = childType
        wrt('    %s get_%s() { return %s_; }\n' % (mappedType, name, name))
        pass

    def generateSetter(self, wrt, capName, name, childType):
        mappedType = self._PGenr.SchemaToCppTypeMap.get(childType)
        if mappedType == None:
            mappedType = childType
        wrt('    void set_%s(%s %s) { %s_ = %s; }\n\n' % 
                          (name, mappedType, name, name, name))
        pass

    def generateExport(self, wrt, namespace, element):
        pass

    def generateExportAttributesFn(self, wrt, namespace, element):
        pass

    def generateExportChildrenFn(self, wrt, namespace, element):
        pass

    def generateBuild2_ReadNode(self, wrt, element):
        wrt('    void build(pugi::xml_document *doc) {\n')
        for child in element.getChildren():
            cleanName = child.getCleanName()
            wrt('        std::string str_%s = doc->ReadNode(%s); \n' % (cleanName, cleanName))
            childType = child.getType()
            mappedType = self._PGenr.SchemaToCppTypeMap.get(childType)
            if mappedType == 'int':
                wrt('        %s_ = atoi(%s); \n\n' %(cleanName, cleanName))
            elif mappedType == 'string':
                wrt('        %s_ = %s; \n\n' %(cleanName, cleanName))

        wrt('    }\n\n')
        pass

    def generateBuild(self, wrt, element): 
        #traversal based build element = subnet_type, iq
        wrt('\n\n')
        wrt('    void build(pugi::xml_document *doc) {\n')
        wrt('        struct walker: pugi::xml_tree_walker { \n')
        wrt('            virtual bool for_each(pugi::xml_node& node) { \n')
        wrt('                buildChildren(node);\n')
        wrt('                return true;\n')
        wrt('            }\n')
        wrt('        };\n\n') 
        wrt('        struct walker walker_;\n')
        wrt('        doc.traverse(walker_);\n')
        wrt('    }\n')
        pass

    def generateBuildAttributesFn(self, wrt, element): 
        wrt('\n\n')
        wrt('    void buildAttributes(pugi::xml_node node) {\n')
        wrt('        pugi::xml_attribute att = node.first_attribute(); \n')
        wrt('        while (att != NULL) { \n')
        attrDefs = element.getAttributeDefs()
        for key in attrDefs:
            attrDef = attrDefs[key]
            name = attrDef.getName()
            cleanName = self._PGenr.cleanupName(name)
            atype = attrDef.getType()
            mappedType = self._PGenr.SchemaToCppTypeMap.get(childType)
            wrt('            if (strcmp(att.name(), "%s") == 0) { \n' % (cleanName) )
            if mappedType == 'int':
                wrt('                %s_ = atoi(%s); \n' %(cleanName, cleanName))
            elif mappedType == 'string':
                wrt('                %s_ = %s; \n' %(cleanName, cleanName))
            wrt('            }\n')
        wrt('            att = att.next_attribute(); \n')
        wrt('        }\n')
        wrt('    }\n')
        pass

    def generateBuildChildren(self, wrt, element, prefix, delayed):
        wrt('\n\n')
        wrt('    void buildChildren(pugi::xml_node node) {\n')
        for child in element.getChildren():
            cleanName = child.getCleanName()
            childType = child.getType()
            mappedType = self._PGenr.SchemaToCppTypeMap.get(childType)
            wrt('        if (strcmp(node.name(), "%s") == 0) { \n' % (cleanName) )
            if mappedType == 'int':
                wrt('            %s_ = atoi(%s); \n' %(cleanName, cleanName))
            elif mappedType == 'string':
                wrt('            %s_ = %s; \n' %(cleanName, cleanName))
            wrt('        }\n')    
        wrt('        buildAttributes(node); \n')            
        wrt('        }\n')
        wrt('    }\n')
        pass

    def generateEnd(self, wrt, name, s4):
        wrt('private:\n')
        wrt('%s' % (s4))
        wrt('} // end of class %s' % (name))
        wrt('\n\n\n')
        pass

    def generateMain(self, outfile, prefix, root):
        pass
 
    def generateComparators(self, wrt, element):
        pass
