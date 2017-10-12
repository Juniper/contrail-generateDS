# coding:utf-8
# Simple utility to convert json schema using jinja2 template
import argparse
import glob
import os
import json
import yaml

import jinja2

THIS_DIR = os.path.dirname(os.path.abspath(__file__))


def process_data(schemas, definitions, schema):
    data_types = schema.get("definitions")
    if data_types:
        definitions.update(data_types)
        return

    if schema.get("schema"):
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
