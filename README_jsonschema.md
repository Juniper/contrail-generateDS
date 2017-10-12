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
- schema JSON Schema

```javascript
{
    "singular": "virtual-network", 
    "prefix": "/", 
    "api_style": "contrail", 
    "extends": [
        "base"
    ], 
    "plural": "virtual-network", 
    "id": "virtual-network", 
    "schema": {
        "propertiesOrder": [
            "address_allocation_mode", 
            "pbb_etree_enable", 
            "virtual_network_network_id", 
            "multi_policy_service_chains_enabled", 
            "virtual_network_properties", 
            "provider_properties", 
            "is_shared", 
            "router_external", 
            "pbb_evpn_enable", 
            "flood_unknown_unicast", 
            "layer2_control_word", 
            "external_ipam"
        ], 
        "required": [], 
        "type": "object", 
```

We have following additional properties for each JSON property.

- ifmapOperations IFMap operations used in XMLSchema 
- ifmapPresense IFMap presense used in XMLSchema 
- xmlType XMLType used in XMLSChema 
- relation  object ID related to
- relationType relation type (has or ref)
- ifmapLinkAttr link attribute for IFMap
- ifmapLinkType link attribute type for IFMap

```javascript
            "api_access_list_entries": {
                "ifmapOperations": "CRUD", 
                "ifmapPresense": "required", 
                "xmlType": "RbacRuleEntriesType", 
                "description": "List of rules e.g network.* => admin:CRUD (admin can perform all ops on networks).", 
                "$ref": "#/definitions/RbacRuleEntriesType"
            }
```

```javascript
            "tag_refs": {
                "ifmapLinkAttr": [
                    "ref"
                ], 
                "ifmapOperation": "CRUD", 
                "relation": "tag", 
                "url": "/tags", 
                "items": {
                    "type": "object", 
                    "properties": {
                        "to": {
                            "items": {
                                "type": "string"
                            }, 
                            "type": "array"
                        }, 
                        "href": {
                            "type": "string"
                        }, 
                        "uuid": {
                            "type": "string"
                        }
                    }
                }, 
                "relationType": "ref", 
                "ifmapLinkType": "", 
                "description": "Tag attached to an object - has a type and value", 
                "type": "array", 
                "ifmapPresense": "optional"
            }, 
```

# Limitation
Comments, Annotaion informations and description for enum element in the original schemas lost in JSONSchema output.