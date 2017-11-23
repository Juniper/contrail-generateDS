In this document, we describe how to convert JSON Schema to XML and vise versa.

# How to use utility

## Convert XMLSchema to JSON Schema

```shell 
 python generateDS.py -f -o $DESTINATION_DIR -g contrail-json-schema $PATH_TO_XMLSCHEMA 
```

We will have types.json and $RESOURCE_NAME_schema.json In $DESTINATION_DIR.
types.json contains sub types.

## Convert JSON Schema to XMLSchema. 

```shell 
 python json_schema_convert.py $PATH_TO_JSONSCHEMA_DIR \
    json_schema_template/xmlschema.tmpl > $PATH_TO_XMLSCHEMA 
```

json_schema_convert.py accepts jinja2 template, so you can also generate codes using
jinja2 template. 

# Contrail JSON schema

In order to generate code and database model, we extend JSON Schema using 
following additional properties.

- id resource ID
- singular singular form of the resource
- plural plural form of the resource
- api_type generated API style
- extends schema inheritance
- references references for another resource
- parents parents resources
- schema JSON Schema

# Limitation
Comments, Annotaion informations and description for enum element in the original schemas lost in JSONSchema output.