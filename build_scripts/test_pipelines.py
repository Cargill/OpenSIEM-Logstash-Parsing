'''
Tests if generate_pipeline script works as intended
'''
import json
import os

import yaml

from generate_pipeline import LogstashHelper, setup_test_env, load_general_settings

cur_file_path = os.path.abspath(__file__)
build_scripts_dir = os.path.dirname(cur_file_path)
logstash_dir = os.path.dirname(build_scripts_dir)
pipeline_dir = f'{logstash_dir}/ignore/pipeline'
os.makedirs(pipeline_dir, exist_ok=True)


def setup():
    # remove exisiting generated pipelines
    for root, _, files in os.walk(pipeline_dir):
        for file in files:
            os.remove(os.path.join(root, file))
    
    os.environ['DEPLOY_ENV'] = 'test'
    num_indexers = load_general_settings(logstash_dir)['num_indexers']
    server_ips = [f'192.168.15.{i}' for i in range(0, num_indexers)]
    setup_test_env()
    os.environ['LOGSTASH_SERVERS'] = ','.join(server_ips)
    helper = LogstashHelper(logstash_dir)
    helper.generate_files()
    # os.environ['MY_INDEX'] = str(1)
    # helper.replace_vars()
    # logger.info('Variables replaced')
    # helper.substitute_jaas_with_values()
    # logger.info('Kafka jaas file substituted')
    # helper.substitute_logger_with_values()
    # logger.info('logger configuration substituted')

    # generate a pipelines{i}.yml file for each logstash indexer
    base_pipeline_str = ''
    base_pipeline = os.path.join(logstash_dir, 'config', 'pipelines.yml')
    with open(base_pipeline, 'r') as base_pipeline_file:
        base_pipeline_str = base_pipeline_file.read()
    for i in range(0, num_indexers):
        os.environ['MY_INDEX'] = str(i+1)
        helper = LogstashHelper(logstash_dir)
        pipeline_file_path = f'{pipeline_dir}/pipelines{i+1}.yml'
        with open(pipeline_file_path, 'w') as pipeline_file:
            pipeline_file.write(base_pipeline_str)
        helper.generate_pipeline(pipeline_file_path)
    print(f'{i+1} pipelines generated')
    # cleanup kafka inputs
    for root, _, files in os.walk(os.path.join(logstash_dir, 'config', 'inputs', 'kafka')):
        for file in files:
            if file != '1_kafka_input_template.conf':
                os.remove(os.path.join(root, file))
    settings = helper.load_settings()
    # cleanup generated processors if any
    generated_processors = [k for k,v in settings.items() if v['config']!= v['log_source']]
    for root, _, files in os.walk(os.path.join(logstash_dir, 'config', 'processors')):
        for file in files:
            if file[:-5] in generated_processors:
                os.remove(os.path.join(root, file))

def test_pipelines():
    helper = LogstashHelper(logstash_dir)
    settings = helper.load_settings()
    conf_names = settings.keys()

    pipeline_file_names = os.listdir(pipeline_dir)
    pipeline_file_names = list(
        filter(lambda file_name: file_name.endswith('.yml'), pipeline_file_names))

    pipelines = []
    for pipeline_file_name in pipeline_file_names:
        with open(f'{pipeline_dir}/{pipeline_file_name}', encoding='UTF-8') as pipeline:
            pipeline_yaml = yaml.unsafe_load(pipeline)
            pipelines.extend(pipeline_yaml)

    assert len(pipelines) >= len(conf_names)

    pipeline_ids = list(map(lambda setting: setting['pipeline.id'], pipelines))
    pipeline_ids.sort()
    # There would be an input and processor pipeline for each log source
    # Few log sources may be processed on multiple nodes
    assert len(pipeline_ids) >= 2*len(conf_names)
    
    # There would be an input pipeline for a corresponding proc pipeline
    input_pipeline_ids = list(filter(lambda id: id[:6]=='input_', pipeline_ids))
    proc_pipeline_ids = list(filter(lambda id: id[:5]=='proc_', pipeline_ids))
    len(proc_pipeline_ids) == len(input_pipeline_ids)
    for id in input_pipeline_ids:
        assert 'proc_' + id[6:] in proc_pipeline_ids

    id_count_map = {}
    for pipeline_id in proc_pipeline_ids:
        pipeline_id = pipeline_id[5:]
        count = id_count_map.get(pipeline_id, 0)
        id_count_map[pipeline_id] = count+1
    assert len(conf_names) == len(id_count_map.keys())

    high_volume_ids = dict(
        filter(lambda item: item[1] > 1, id_count_map.items()))

    if len(high_volume_ids) != len(helper.high_volume_logs) + len(helper.clear_lag_logs):
        print('Warning: not all configured high volume logs are processed on more than one nodes')
    for log_name in helper.high_volume_logs:
        print(f'{log_name} is parsed on {id_count_map[log_name]} nodes')
    for log_name in helper.clear_lag_logs:
        print(f'{log_name} is parsed on {id_count_map[log_name]} nodes')


if __name__ == "__main__":
    setup()
    test_pipelines()
