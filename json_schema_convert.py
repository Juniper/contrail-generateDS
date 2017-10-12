# coding:utf-8
# Simple utility to convert json schema using jinja2 template
import argparse
import glob
import os
import json
import yaml

import jinja2

THIS_DIR = os.path.dirname(os.path.abspath(__file__))


def process_properties(properties):
    if not properties:
        return
    for id, property in properties.items():
        if property.get("xmlType"):
            continue

        ref = property.get("$ref")
        if ref:
            refs = ref.split("/")
            property["xmlType"] = refs[-1]
            continue

        if property["type"] == "object":
            process_schema(property)

        if property.get("relation"):
            ref = property.get("items", {}).get(
                "properties", {}).get("attr", {}).get("$ref")
            if ref:
                refs = ref.split("/")
                property["xmlType"] = refs[-1]
                continue

        if property["type"] == "string":
            if property.get("format") == "date-time":
                property["xmlType"] = "xsd:dateTime"
            else:
                property["xmlType"] = "xsd:string"

        if property["type"] == "boolean":
            property["xmlType"] = "xsd:boolean"

        if property["type"] == "integer":
            property["xmlType"] = "xsd:integer"


def process_schema(schema):
    process_properties(schema.get("properties"))
    process_properties(schema.get("references"))
    process_properties(schema.get("parents"))


def process_data(schemas, definitions, schema):
    data_types = schema.get("definitions")
    if data_types:
        definitions.update(data_types)
        for id, data_type in data_types.items():
            process_schema(data_type)
        return

    if schema.get("schema"):
        process_schema(schema["schema"])
        schemas.append(schema)


def read_schema(src_path):
    definitions = {}
    schemas = []
    data_model = {
        "definitions": definitions,
        "schemas": schemas
    }
    files = glob.glob(src_path + '/*.json')
    for file_path in files:
        file_handler = open(file_path, 'r')
        try:
            schema = json.load(file_handler)
        except:
            continue

        process_data(schemas, definitions, schema)

    files = glob.glob(src_path + '/*.yaml')
    for file_path in files:
        file_handler = open(file_path, 'r')
        try:
            schema = yaml.load(file_handler)
        except:
            continue
        process_data(schemas, definitions, schema)
    return data_model


def output(template_file, data_model):
    # Ensure destination directory created
    j2_env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(THIS_DIR),
        trim_blocks=True)
    print j2_env.get_template(template_file).render(data_model)


def convert():
    parser = argparse.ArgumentParser(
        description='Converter from JSON Schema to XML Schema plus IFMap')

    parser.add_argument('src',
                        action='store',
                        nargs=None,
                        const=None,
                        default=None,
                        type=str,
                        choices=None,
                        help='Directory path where your json schema located.',
                        metavar=None)
    parser.add_argument('template',
                        action='store',
                        nargs=None,
                        const=None,
                        default=None,
                        type=str,
                        choices=None,
                        help='Template file to apply',
                        metavar=None)
    args = parser.parse_args()

    src_path = args.src
    template_path = args.template

    data_model = read_schema(src_path)
    output(template_path, data_model)


if __name__ == '__main__':
    convert()
