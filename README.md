contrail-generateDS
===================

Contrail XML schema code generator

The contrail XSD generator reads .xsd files containing IF-MAP identities, links and properties
and generates python, c++ and java code used by different modules of the Contrail Virtual Network Controller.

The IDL syntax is the following:

     #IFMAP-SEMANTICS-IDL list-of-statements
     list-of-statements := list-of-statements, statement
     statement  := Link('element', 'identifier', 'identifier', [ref-type-list])|
                   Type('element', [type-list])|
                   Property(element-name identifier-name)|
                   Exclude('element', [generator-list])
     element    := metadata element name
     identifier := identifier element name | "any" | "all"
     ref-type-list:= ref-type-list 'has' |
                  := ref-type-list 'ref' |
                  := 
     ref-type-list:= ref-type-list 'string-enum' |
                  := 
     string-enum  := This command will convert string type restriction to 
                   enum type
     generator-list:= generator-list 'backend'|
                   := generator-list 'frontend'|
                   := 


example:
```
<xsd:element name="virtual-machine" type="ifmap:IdentityType"/>
<xsd:element name="virtual-machine-interface" type="ifmap:IdentityType"/>

<xsd:element name="virtual-machine-virtual-machine-interface"/>
<!--#IFMAP-SEMANTICS-IDL 
     Link('virtual-machine-virtual-machine-interface',
          'virtual-machine', 'virtual-machine-interface', ['has']) -->

<xsd:complexType name='VirtualMachineInterfacePropertiesType'>
    <xsd:all>
        <xsd:element name='service-interface-type' type="ServiceInterfaceType"/>
        <xsd:element name='interface-mirror'  type="InterfaceMirrorType"/>
    </xsd:all>
</xsd:complexType>

<xsd:element name="virtual-machine-interface-properties" 
             type="VirtualMachineInterfacePropertiesType"/>
<!--#IFMAP-SEMANTICS-IDL 
     Property('virtual-machine-interface-properties',
             'virtual-machine-interface') -->

```

The XSD snippet above defines two IFMAP identifiers (virtual-machine and virtual-machine-interface) and the associated
metadata (link between virtual-machine and its interface) as well as properties that can be associated with the identifiers.

The implementation is using generateDS as an XSD parser and to help it create an intermediate model; this intermediate model
is implemented by type_model.py and ifmap_model.py; different backends then generate code for different software modules.
