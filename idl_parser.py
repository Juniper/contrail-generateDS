"""
idl_parser.py

Parse IDL statements embedded in a XML schema file.

Copyright (c) 2013 Contrail Systems. All rights reserved.
"""

import logging
import os
import re
import string
import sys

class IDLParser(object):
    def __init__(self):
        self._ElementDict = {}

    def Parse(self, infile):
        xml_comment = re.compile(r'<!--\s*#IFMAP-SEMANTICS-IDL(.*?)-->',
                                 re.DOTALL)
        file_matches = xml_comment.findall(infile.read())
        # Remove whitespace(incl newline), split at stmt boundary
        matches = [re.sub('\s', '', match).split(';') for match in file_matches]
        for statements in matches:
            for stmt in statements:
                # Oper in idl becomes method
                try:
                    eval("self._%s" %(stmt))
                except TypeError:
                    logger = logging.getLogger('idl_parser')
                    logger.debug('ERROR statement: %s', stmt)
                    import pdb; pdb.set_trace()
                #self._ParseExpression(stmt)

    def Find(self, element):
        if element in self._ElementDict:
            return self._ElementDict[element]
        else:
            return None

    def IsProperty(self, annotation):
        if type(annotation) is tuple:
            return False
        return True

    def IsLink(self, annotation):
        if type(annotation) is tuple:
            return true
        return false

    def GetLinkInfo(self, link_name):
        if link_name in self._ElementDict:
            return (self._ElementDict[link_name][0],
                    self._ElementDict[link_name][1],
                    self._ElementDict[link_name][2])
        else:
            return (None, None, None)

    def _Type(self, type_name, attrs):
        logger = logging.getLogger('idl_parser')
        logger.debug('Type(%s, %s)', type_name, attrs)

    def _Property(self, prop_name, ident_name):
        logger = logging.getLogger('idl_parser')
        logger.debug('Property(%s, %s)', prop_name, ident_name)
        self._ElementDict[prop_name] = ident_name 

    def _Exclude(self, elem_name, excluded):
        logger = logging.getLogger('idl_parser')
        logger.debug('Exclude(%s, %s)', elem_name, excluded)

    def _Link(self, link_name, from_name, to_name, attrs):
        logger = logging.getLogger('idl_parser')

        mch = re.match(r'(.*):(.*)', from_name)
        if mch:
            from_ns = mch.group(1)
            from_name = mch.group(2)

        mch = re.match(r'(.*):(.*)', to_name)
        if mch:
            to_ns = mch.group(1)
            to_name = mch.group(2)

        # TODO store and handle namespace in identifiers

        logger.debug('Link(%s, %s, %s)', from_name, to_name, attrs)
        self._ElementDict[link_name] = (from_name, to_name, attrs)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit('Usage: %s schema.xsd' % sys.argv[0])
    if not os.path.exists(sys.argv[1]):
        sys.exit('Error: %s not found' % sys.argv[1])
    idl_parser = IDLParser()
    idl_parser.Parse(sys.argv[1])
