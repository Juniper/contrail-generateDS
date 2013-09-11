#
# Copyright (c) 2013 Juniper Networks, Inc. All rights reserved.
#

CppTypeMap = {
    'string': 'std::string',
    'xsd:string': 'std::string',
    'xsd:integer': 'int',
    'xsd:unsignedInt': 'uint32_t',
    'xsd:boolean': 'bool',
    'xsd:unsignedLong' : 'uint64_t',
    'xsd:dateTime': 'time_t',
    'xsd:time': 'time_t'
}

JavaTypeMap = {
    'string': 'String',
    'xsd:string': 'String',
    'xsd:integer': 'Integer',
    'xsd:unsignedInt': 'Integer',
    'xsd:boolean': 'boolean',
    'xsd:unsignedLong' : 'Long',
    'xsd:dateTime': 'java.util.Date',
    'xsd:time': 'Long'
}

def getCppType(xsd_simple_type):
    if not xsd_simple_type in CppTypeMap:
        return 'void'
    return CppTypeMap[xsd_simple_type]

def getJavaType(xsd_simple_type):
    if not xsd_simple_type in JavaTypeMap:
        return 'Object'
    return JavaTypeMap[xsd_simple_type]

def IsGeneratedType(ctype):
    for xtype in CppTypeMap.values():
        if ctype == xtype:
            return False
    return True

def CamelCase(input):
    words = input.replace('_', '-').split('-')
    name = ''
    for w in words:
        name += w.capitalize()
    return name

def GetModuleName(file, suffix):
    path_arr = file.name.split('/')
    filename = path_arr[len(path_arr) - 1]
    mod_name = filename[:filename.find(suffix)]
    mod_name = mod_name.replace('-', '_')
    return mod_name
