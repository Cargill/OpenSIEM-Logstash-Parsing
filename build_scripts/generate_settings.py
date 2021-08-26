'''
Generates a sample settings.json file with all configs so tha they can be tested for syntax errors in a CI environment
'''
import os, json

cur_file_path = os.path.abspath(__file__)
build_scripts_dir = os.path.dirname(cur_file_path)
logstash_dir = os.path.dirname(build_scripts_dir)
settings = {}
settings_file_path = os.path.join(
    logstash_dir, 'build_scripts', 'settings.json')
processor_dir = os.path.join(logstash_dir, 'config', 'processors')
kafka_input_dir = os.path.join(logstash_dir, 'config', 'inputs', 'kafka')

# creating a settings file that has definitions for all processing configs
processors = []
for root, _, files in os.walk(processor_dir):
    for file in files:
        processors.append(file[:-5])

for processor in processors:
    settings[processor] = {
        "log_source": processor,
        "config": processor,
        "elastic_index": processor,
        "ignore_enrichments": [],
        "output_list": [
            "elastic_output",
        ],
        "kafka_input": {
            "codec": "json"
        }
    }

with open(settings_file_path, 'w') as settings_file:
    json.dump(settings, settings_file, indent=2)

# Creating a general settings file that tells to generate pipelines that should run on single node
general_settings_file_path = os.path.join(
    logstash_dir, 'build_scripts', 'general.json')

test_general_json = {
    "num_indexers" : 1,
    "prod_only_logs": [
    ],
    "processing_config" : {
    }
}

with open(general_settings_file_path, 'w') as general_settings_file:
    json.dump(test_general_json, general_settings_file, indent=2)