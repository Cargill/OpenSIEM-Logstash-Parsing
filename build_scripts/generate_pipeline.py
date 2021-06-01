'''
This script sets up the configs and creates pipelines.yml based on settings.json.
It's intended to be used on each of the logstash instance so they can get fair share of processing. 
You are supposed to write your own logic to generate pipelines.yml if this strategy does not works well for you.
'''
import hashlib
import json
import os
import re
import sys
from pathlib import Path


def get_logger():
    import logging
    from logging.handlers import RotatingFileHandler

    logger = logging.getLogger()
    # set default logging as lowest level
    # handlers get logs after filtered by this level
    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s LINE:%(lineno)d %(message)s', datefmt='%Y-%m-%d:%H:%M:%S')

    console_hdlr = logging.StreamHandler()
    console_hdlr.setLevel(logging.INFO)
    console_hdlr.setFormatter(formatter)

    Path('/data').mkdir(parents=True, exist_ok=True)
    file_hdlr = RotatingFileHandler(
        '/data/generate_pipeline.log', maxBytes=1024)
    file_hdlr.setFormatter(formatter)
    file_hdlr.setLevel(logging.INFO)

    logger.addHandler(file_hdlr)
    logger.addHandler(console_hdlr)
    return logger


logger = get_logger()


def jsonise(json_as_str: str):
    return json.loads(json_as_str)


class LogstashHelper(object):

    def __init__(self, logstash_dir):
        self.logstash_dir = logstash_dir
        self.deploy_env = os.environ['DEPLOY_ENV']
        self.logstash_servers = os.environ['LOGSTASH_SERVERS'].split(',')
        # index of this instance in the array of all logstash instances
        self.my_index = int(os.environ['MY_INDEX'])
        self.sub_my_ip = os.environ['SUB_MY_IP']
        self.elastic_user, self.elastic_pwd = os.environ['ELASTIC_USER'], os.environ['ELASTIC_PASSWORD']
        self.elastic_connection_str = os.environ['ELASTIC_CONNECTION_STRING']
        self.kafka_connection_str = os.environ['KAFKA_CONNECTION_STRING']
        self.kafka_user, self.kafka_pwd = os.environ['KAFKA_USER'], os.environ['KAFKA_PASSWORD']
        self.rack_id = os.environ['RACK_ID']
        self.logstash_api_secrets = self.__get_logstash_api_secret()
        self.bucket_name = os.environ['S3_BUCKET_NAME']
        self.prod_only_logs = self.__get_prod_only_logs()
        self.num_indexers = self.__get_num_indexers()

    def __get_logstash_api_secret(self):
        logstash_api_sec = os.environ['LOGSTASH_API_SECRET']
        return jsonise(logstash_api_sec)

    def __get_num_indexers(self):
        general_settings = load_general_settings(self.logstash_dir)
        indexers = general_settings['num_indexers']
        return indexers

    def __get_prod_only_logs(self):
        general_settings = load_general_settings(self.logstash_dir)
        return general_settings['prod_only_logs']

    def __add_custom_input_field(self, conf_file: str, config):
        comma_separated_outputs = ','.join(config["output_list"])
        tags_line = ''
        if config["ignore_enrichments"]:
            tags = '[ "{}" ]'.format('", "'.join(config["ignore_enrichments"]))
            # if the list is empty it produces [""] which might break config
            tags_line = f'\n   add_tag => {tags}'
        add_fields_block = 'add_field => {\n' + \
            f'      "[@metadata][index]" => "{config["log_source"]}"\n' + \
            f'      "[@metadata][config]" => "{config["config"]}"\n' + \
            f'      "[@metadata][output]" => "{config["elastic_index"]}"\n' + \
            f'      "[@metadata][output_pipelines]" => [{comma_separated_outputs}]\n' + \
            '    }' +\
            f'{tags_line}'

        file_contents = None
        with open(conf_file, encoding='UTF-8') as config:
            file_contents = config.read()
        if self.deploy_env == 'test':
            if 'VAR_CUSTOM_FIELDS' not in file_contents:
                raise ValueError(
                    f'config {conf_file} does not contain VAR_CUSTOM_FIELDS')
        file_contents = file_contents.replace(
            '# VAR_CUSTOM_FIELDS', add_fields_block)
        with open(conf_file, 'w', encoding='UTF-8') as config:
            config.write(file_contents)

    def __replace_vars(self, conf_file_path, vars_dict):
        unknown_var_regexp = re.compile(r'VAR_.\w*')
        # get the part after last slash and then the part before .conf
        config_name = conf_file_path.split('/')[-1].split('.conf')[0]
        log_type = config_name.split('_')[-1]
        max_poll_records = 200
        consumer_threads = 2
        if log_type == 'daily':
            # default consumer threads to 18 partitions being processed on one node each in 3 regions
            #   18/3=6
            consumer_threads = 6

        general_settings = load_general_settings(self.logstash_dir)
        processing_config = general_settings['processing_config']
        if config_name in processing_config.keys():
            # needs special treatment
            num_nodes = int(processing_config[config_name]['nodes'])
            try:
                # kafka_partitions key won't exist for non kafka logs
                # for a kafka log use default consumer_threads value if the key is not found
                num_partitions = int(processing_config[config_name]['kafka_partitions'])
                consumer_threads = 1 if num_nodes > num_partitions else int(num_partitions/num_nodes)
            except KeyError:
                pass

        vars_dict['KAFKA_TOPIC'] = config_name
        vars_dict['KAFKA_GROUP_ID'] = config_name
        vars_dict['KAFKA_CLIENT_ID'] = f'{config_name}-{self.sub_my_ip}-input'
        vars_dict['CONSUMER_THREADS'] = consumer_threads
        vars_dict['MAX_POLL_RECORDS'] = max_poll_records
        s3_date_pattern = '%{+xxxx/MM/dd}'
        vars_dict['S3_PREFIX'] = f'{config_name}/{s3_date_pattern}'

        file_contents = None

        with open(conf_file_path, encoding='UTF-8') as config:
            file_contents = config.read()
        for var in vars_dict.keys():
            file_contents = file_contents.replace(
                f'VAR_{var}', f'{vars_dict[var]}')

        unknown_vars = unknown_var_regexp.findall(file_contents)
        if len(unknown_vars) > 0:
            raise ValueError(
                f'Unknown variable/s {unknown_vars} in config {conf_file_path}.')

        with open(conf_file_path, 'w', encoding='UTF-8') as config:
            config.write(file_contents)

    def replace_vars(self):
        vars_dict = {
            'KAFKA_JAAS_PATH': '/usr/share/logstash/config/kafka_jaas.conf',
            'KAFKA_CLIENT_TRUSTSTORE': '/usr/share/logstash/config/kafka_client_truststore.jks',
            'KAFKA_TRUSTSTORE_PASSWORD': 'changeit',
            'KAFKA_BOOTSTRAP_SERVERS': self.kafka_connection_str,
            'RACK_ID': self.rack_id,
            'LOGSTASH_PLUGIN_ID': f'logstash_kafka-{self.sub_my_ip}',
            'ELASTIC_SERVERS': self.elastic_connection_str,
            'ELASTIC_USER': self.elastic_user,
            'ELASTIC_PASSWORD': self.elastic_pwd,
            'AZURE_AUDIT_CONN': self.logstash_api_secrets['azure_audit_conn'],
            'AZURE_STORAGE_CONN': self.logstash_api_secrets['azure_storage_conn'],
            'AZURE_OPERATIONAL_CONN': self.logstash_api_secrets['azure_operational_conn'],
            'AZURE_SIGNIN_CONN': self.logstash_api_secrets['azure_signin_conn'],
            'AZURE_O365_CONN': self.logstash_api_secrets['azure_o365_conn'],
            'AZURE_TCS_SECURITY_CONN': self.logstash_api_secrets['azure_tcs_security_conn'],
            'AZURE_O365_DLP_CONN': self.logstash_api_secrets['azure_o365_dlp_conn'],
            'AZURE_AUDIT_CONSUMER': self.logstash_api_secrets['azure_audit_consumer'],
            'AZURE_OPERATIONAL_CONSUMER': self.logstash_api_secrets['azure_operational_consumer'],
            'AZURE_SIGNIN_CONSUMER': self.logstash_api_secrets['azure_signin_consumer'],
            'AZURE_O365_CONSUMER': self.logstash_api_secrets['azure_o365_consumer'],
            'AZURE_TCS_SECURITY_CONSUMER': self.logstash_api_secrets['azure_tcs_security_consumer'],
            'AZURE_O365_DLP_CONSUMER': self.logstash_api_secrets['azure_o365_dlp_consumer'],
            'BUCKET_NAME': self.bucket_name,
            'NC4_API_KEY': self.logstash_api_secrets['nc4_api_key'],
            'NC4_API_URI': self.logstash_api_secrets['nc4_api_uri'],
            'AZURE_ATP_CONSUMER': self.logstash_api_secrets['azure_atp_consumer'],
            'AZURE_ATP_CONN': self.logstash_api_secrets['azure_atp_conn'],
            'MEMCACHED_ADDRESS': self.logstash_api_secrets['memcached_address'],
            'DNS_SERVER': self.logstash_api_secrets['dns_server'],
        }
        azure_inputs_dir = os.path.join(
            self.logstash_dir, 'config', 'inputs', 'azure')
        kafka_input_dir = os.path.join(
            self.logstash_dir, 'config', 'inputs', 'kafka')
        processor_dir = os.path.join(self.logstash_dir, 'config', 'processors')
        output_dir = os.path.join(self.logstash_dir, 'config', 'outputs')
        enrichment_dir = os.path.join(self.logstash_dir, 'config', 'enrichments')

        settings = self.load_settings()
        azure_inputs = os.listdir(azure_inputs_dir)
        azure_inputs = list(filter(lambda file_name:file_name.endswith('.conf'), azure_inputs))
        for input_name in azure_inputs:
            try:
                config = settings[input_name[:-5]]  # stripping .conf
            except KeyError:
                # User doesn't want to process that log and that's okay
                continue
            if self.deploy_env == 'dev' and config in self.prod_only_logs:
                continue
            vars_dict['PIPELINE_NAME'] = '"' + config['log_source'] + '"'
            self.__add_custom_input_field(
                f'{azure_inputs_dir}/{input_name}', config)
            self.__replace_vars(f'{azure_inputs_dir}/{input_name}', vars_dict)
        kafka_inputs = os.listdir(kafka_input_dir)
        kafka_inputs = list(filter(lambda file_name:file_name.endswith('.conf'), kafka_inputs))
        for input_name in kafka_inputs:
            if input_name == '1_kafka_input_template.conf':
                continue
            config = settings[input_name[:-5]]  # stripping .conf
            if self.deploy_env == 'dev' and config in self.prod_only_logs:
                continue
            self.__add_custom_input_field(
                f'{kafka_input_dir}/{input_name}', config)
            vars_dict['PIPELINE_NAME'] = '"' + config['log_source'] + '"'
            codec = 'plain'
            try:
                # overwrite default if provided
                codec = config['kafka_input']['codec']
            except KeyError:
                pass
            vars_dict['CODEC'] = codec
            self.__replace_vars(f'{kafka_input_dir}/{input_name}', vars_dict)
        processsors = os.listdir(processor_dir)
        processsors = list(filter(lambda file_name:file_name.endswith('.conf'), processsors))
        for processor_name in processsors:
            config = processor_name[:-5]  # stripping .conf
            if self.deploy_env == 'dev' and config in self.prod_only_logs:
                continue
            vars_dict['PIPELINE_NAME'] = '"' + config + '"'
            self.__replace_vars(f'{processor_dir}/{processor_name}', vars_dict)
        outputs = os.listdir(output_dir)
        outputs = list(filter(lambda file_name:file_name.endswith('.conf'), outputs))
        for output_name in outputs:
            self.__replace_vars(f'{output_dir}/{output_name}', vars_dict)
        enrichments = os.listdir(enrichment_dir)
        enrichments = list(filter(lambda file_name:file_name.endswith('.conf'), enrichments))
        for enrichment_name in enrichments:
            self.__replace_vars(f'{enrichment_dir}/{enrichment_name}', vars_dict)

    def __get_log_distribution(self, num_logs: int, num_servers: int, arr_idx: int, logs: list):
        '''
        with the current approach first few servers get all the unfairly allocated logs
        and last in the list get none
        # TODO change the algo to keep track on different unfair logs and distribute them evenly
        # this change is out of scope of this method so this has to go probably.
        '''
        fair_allocation = int(num_logs / num_servers)
        unfair_allocation = num_logs % num_servers
        start_index = arr_idx*fair_allocation
        distributed_logs = logs[start_index: start_index+fair_allocation]
        if arr_idx < unfair_allocation:
            distributed_logs.append(logs[-(arr_idx+1)])
        return distributed_logs

    def __get_matched_items(self, big_array: list, small_array: list):
        '''
            returns small array with only those items which exist in big array
        '''
        small_array = list(filter(lambda item: item in big_array, small_array))
        return small_array

    def get_selected_log_sources(self):
        settings = self.load_settings()
        conf_names = settings.keys()
        general_settings = load_general_settings(self.logstash_dir)
        processing_config = general_settings['processing_config']

        self.prod_only_logs = self.__get_matched_items(
            conf_names, self.prod_only_logs)
        self.special_logs = self.__get_matched_items(
            conf_names, processing_config.keys())

        # calculating number of nodes needed for special logs
        num_servers_for_special_logs = 0
        for _,v in processing_config.items():
            num_servers_for_special_logs += v['nodes']
        
        special_confs = []
        num_servers = len(self.logstash_servers)
        # if there are not enough servers for special logs process them like any other
        if num_servers < num_servers_for_special_logs:
            # cannot process clear lag logs explicitly.
            # treat them like high volume logs
            self.special_logs = []
            num_servers_for_special_logs = 0
        
        daily_logs = []
        weekly_logs = []
        monthly_logs = []
        # filter daily, weekly and monthly logs which do not need special treatment
        for config_file in conf_names:
            if config_file in self.special_logs:
                continue
            if self.deploy_env == 'dev' and config_file in self.prod_only_logs:
                continue
            log_type = config_file.split('_')[-1]
            # treat test settings as low volume, they are not a priority
            if config_file.startswith('test_'):
                log_type = 'monthly'
            if log_type == 'daily':
                daily_logs.append(config_file)
            elif log_type == 'weekly':
                weekly_logs.append(config_file)
            elif log_type == 'monthly':
                monthly_logs.append(config_file)
            else:
                monthly_logs.append(config_file)

        # initialise selected config list for this node
        selected_log_sources = []
        # subtract it by one as it starts from 1
        arr_idx = self.my_index - 1

        # if list is non empty which means we have enough instances
        if self.special_logs:
            # Process special lag confs explicitly
            # sequentially allocate a special log
            special_confs = []
            if arr_idx < num_servers_for_special_logs:
                cumulative_nodes = 0
                for k,v in processing_config.items():
                    cumulative_nodes += v['nodes']
                    if arr_idx < cumulative_nodes:
                        special_confs.append(k)
                        break
            selected_log_sources = special_confs
        
        if not selected_log_sources:
            # for rest of the instances that does not contain special confs
            # adjust num_servers and arr_idx after fully using special lag servers
            num_servers = num_servers - num_servers_for_special_logs
            arr_idx = arr_idx - num_servers_for_special_logs

            for logs in [daily_logs, weekly_logs, monthly_logs]:
                num_logs = len(logs)
                selected_log_sources = selected_log_sources + \
                    self.__get_log_distribution(
                        num_logs, num_servers, arr_idx, logs)

        return selected_log_sources

    def generate_pipeline(self, pipeline_file_path):
        '''
            Generate pipelines.yml and write to pipeline_file_path.

            Get settings list from pipeline/confs directory and try to do a fair distribution of settings
            while generated pipelines file.
        '''
        selected_log_sources = self.get_selected_log_sources()

        root_dir = self.logstash_dir
        azure_inputs_dir = os.path.join(root_dir, 'config', 'inputs', 'azure')
        kafka_input_dir = os.path.join(root_dir, 'config', 'inputs', 'kafka')
        azure_input_list = os.listdir(azure_inputs_dir)
        azure_input_list = list(filter(lambda file_name:file_name.endswith('.conf'), azure_input_list))
        kafka_input_list = os.listdir(kafka_input_dir)
        kafka_input_list = list(filter(lambda file_name:file_name.endswith('.conf'), kafka_input_list))
        file_contents = ''
        for log_source in selected_log_sources:
            log_source_input_conf = f'{log_source}.conf'
            # create a pipeline for input
            # if input is azure
            if log_source_input_conf in azure_input_list:
                input_config_file_path = '${LOGSTASH_HOME}' + \
                    f'/config/inputs/azure/{log_source_input_conf}'
            # if input is kafka
            elif log_source_input_conf in kafka_input_list:
                input_config_file_path = '${LOGSTASH_HOME}' + \
                    f'/config/inputs/kafka/{log_source_input_conf}'
            else:
                raise ValueError(
                    f'config {log_source_input_conf} does not have an input')
            # and log_source name for id
            input_pipeline_id = f'input_{log_source}'
            # create a pipeline for processor
            # use the config name for file path
            processor_config_file_path = '${LOGSTASH_HOME}' + \
                f'/config/processors/{log_source_input_conf}'
            # and config name for id
            processor_pipeline_id = f'proc_{log_source}'

            log_type = log_source.split('_')[-1]
            # treat test settings as low volume, they are not a priority
            if log_source.startswith('test_'):
                log_type = 'monthly'
            if log_type == 'daily':
                pipeline_workers = 8
            elif log_type == 'weekly':
                pipeline_workers = 4
            elif log_type == 'monthly':
                pipeline_workers = 2
            else:
                pipeline_workers = 2

            if log_source in self.special_logs:
                pipeline_workers = 16

            batch_size = 200
            processor_pipeline_entry = ''
            processor_pipeline_entry = f'- pipeline.id: {processor_pipeline_id}\n' + \
                f'  pipeline.batch.delay: 50\n' + \
                f'  pipeline.batch.size: {batch_size}\n' + \
                f'  path.config: \"{processor_config_file_path}\"\n' + \
                f'  pipeline.workers: {pipeline_workers}\n'
            input_pipeline_entry = f'- pipeline.id: {input_pipeline_id}\n' + \
                f'  pipeline.batch.delay: 150\n' + \
                f'  pipeline.batch.size: {batch_size}\n' + \
                f'  path.config: \"{input_config_file_path}\"\n' + \
                f'  pipeline.workers: {pipeline_workers}\n'

            file_contents = file_contents + input_pipeline_entry + processor_pipeline_entry

        with open(pipeline_file_path, 'a', encoding='UTF-8') as pipeline:
            pipeline.write(file_contents)

    def substitute_jaas_with_values(self):
        '''
            Substitute variables in kafka_jaas.conf
        '''
        jaas_file_path = f'{self.logstash_dir}/config/kafka_jaas.conf'
        jaas_file_str = ''
        with open(jaas_file_path, encoding='UTF-8') as jaas_file:
            jaas_file_str = jaas_file.read()
        jaas_file_str = jaas_file_str.replace(
            'VAR_KAFKA_USER', self.kafka_user)
        jaas_file_str = jaas_file_str.replace(
            'VAR_KAFKA_PASSWORD', self.kafka_pwd)
        with open(jaas_file_path, 'w', encoding='UTF-8') as jaas_file:
            jaas_file.write(jaas_file_str)

    def substitute_logger_with_values(self):
        '''
            Substitute variables in log4j2.properties
        '''
        log_file_path = f'{self.logstash_dir}/config/log4j2.properties'
        log_file_str = ''
        # return if user does not want to use custom log4j2.properties
        if not os.path.exists(log_file_path):
            return
        with open(log_file_path, 'r', encoding='UTF-8') as log_settings:
            log_file_str = log_settings.read()
        import socket
        hostname = socket.gethostname()
        log_file_str = log_file_str.replace(
            'VAR_HOSTNAME', hostname)
        with open(log_file_path, 'w', encoding='UTF-8') as log_settings:
            log_settings.write(log_file_str)

    def load_settings(self):
        settings = {}
        settings_file_path = os.path.join(
            self.logstash_dir, 'build_scripts', 'settings.json')
        with open(settings_file_path, 'r', encoding='UTF-8') as settings_file:
            settings = json.load(settings_file)
        return settings

    def generate_files(self):
        root_dir = self.logstash_dir
        azure_inputs_dir = os.path.join(root_dir, 'config', 'inputs', 'azure')
        kafka_input_dir = os.path.join(root_dir, 'config', 'inputs', 'kafka')
        processor_dir = os.path.join(root_dir, 'config', 'processors')
        azure_input_list = os.listdir(azure_inputs_dir)
        azure_input_list = list(filter(lambda file_name:file_name.endswith('.conf'), azure_input_list))

        # cleanup kafka inputs if any
        for root, _, files in os.walk(kafka_input_dir):
            for file in files:
                if file != '1_kafka_input_template.conf':
                    os.remove(os.path.join(root, file))
        
        settings = self.load_settings()
        # cleanup generated processors if any
        generated_processors = [k for k,v in settings.items() if v['config']!= v['log_source']]
        for root, _, files in os.walk(processor_dir):
            for file in files:
                if file[:-5] in generated_processors:
                    os.remove(os.path.join(root, file))
        
        for key in settings.keys():
            setting = settings[key]
            log_source_conf = f'{setting["log_source"]}.conf'
            # generate inputs
            if log_source_conf not in azure_input_list:
                # it's a kafka input, generate an input conf
                with open(os.path.join(kafka_input_dir, '1_kafka_input_template.conf'), 'r', encoding='UTF-8') as base_input_file:
                    input_file_path = os.path.join(
                        kafka_input_dir, log_source_conf)
                    with open(input_file_path, 'w', encoding='UTF-8') as kafka_input_file:
                        kafka_input_file.write(base_input_file.read())
            # generate required processors
            config = f'{setting["config"]}.conf'
            if config != log_source_conf:
                file_contents = ''
                with open(os.path.join(processor_dir, config), 'r', encoding='UTF-8') as config_file:
                    file_contents = config_file.read()
                processor_file_path = os.path.join(
                    processor_dir, log_source_conf)
                with open(processor_file_path, 'w', encoding='UTF-8') as processor_file:
                    processor_file.write(file_contents)

    def generate_checksum(self, dir_path):
        '''
            Generates checksums for all files in
                dir_path/inputs/* & dir_path/processors/* (logstash configs)
                AND
                dir_path (common setting files)
            and returns dictonaries settings_checksum_dict and conf_checksum_dict respectively.
            Each dict contains file name as key and it's md5 hash as value.
        '''
        selected_log_sources = self.get_selected_log_sources()
        settings = self.load_settings()
        selected_log_processors = [settings[log_source]['config']
                                   for log_source in selected_log_sources]

        conf_files = []
        setting_files = []
        for root, _, files in os.walk(dir_path):
            if root == dir_path:
                setting_files = [os.path.join(root, file_name)
                                 for file_name in files]
                continue
            for file_name in files:
                file_path = str(os.path.join(root, file_name))
                if 'inputs' in root and file_name.split('.conf')[0] not in selected_log_sources:
                    continue
                if 'processors' in root and file_name.split('.conf')[0] not in selected_log_processors:
                    continue
                conf_files.append(file_path)

        logger.info(f'generating checksum for common files')
        settings_checksum_dict = {}
        for setting_file_path in setting_files:
            with open(setting_file_path, 'rb') as setting_file:
                settings_checksum_dict[setting_file_path.split(dir_path)[1]] = hashlib.md5(
                    setting_file.read()).hexdigest()

        logger.info(f'generating checksum for other files')
        conf_checksum_dict = {}
        for conf_file_name in conf_files:
            with open(conf_file_name, 'rb') as conf_file:
                # get the path after config and make it the key
                conf_checksum_dict[conf_file_name.split(dir_path)[1]] = hashlib.md5(
                    conf_file.read()).hexdigest()

        return settings_checksum_dict, conf_checksum_dict

    def test_for_change(self, last_deployed_dir, current_deployable_dir):
        '''
            Compare the checksums to see if something changed between existing deployment and ongoing deployment
            If something did change, write 'changed' to file /data/should_redeploy .
            Chef client keeps checking this file and triggers redeploy of logstash if it was modified.
        '''
        old_settings_checksum_dict, old_conf_checksum_dict = self.generate_checksum(
            last_deployed_dir)
        new_settings_checksum_dict, new_conf_checksum_dict = self.generate_checksum(
            current_deployable_dir)
        changed = False
        if len(new_settings_checksum_dict.keys()) == len(old_settings_checksum_dict.keys()):
            # check settings checksum
            for k in new_settings_checksum_dict.keys():
                if new_settings_checksum_dict[k] != old_settings_checksum_dict.get(k, ''):
                    logger.info(f'checksum different for {k}')
                    changed = True
                    break
            # check conf files checksum
            for k in new_conf_checksum_dict.keys():
                if new_conf_checksum_dict[k] != old_conf_checksum_dict.get(k, ''):
                    logger.info(f'checksum different for {k}')
                    changed = True
                    break
        else:
            changed = True
            logger.info('checksum settings dict are unequal in length')
        if changed:
            contents = ''
            try:
                with open('/data/should_redeploy', 'r', encoding='UTF-8') as change_file:
                    contents = change_file.read()
            except FileNotFoundError:
                pass
            with open('/data/should_redeploy', 'w', encoding='UTF-8') as change_file:
                new_content = '1' if contents == '0' else '0'
                change_file.write(new_content)
            logger.info("settings changed")

def load_general_settings(root_dir):
    general_settings = {}
    general_settings_path = os.path.join(
        root_dir, 'build_scripts', 'general.json')
    with open(general_settings_path, 'r') as general_settings_file:
        general_settings = json.load(general_settings_file)
    return general_settings


if __name__ == "__main__":
    '''        
        Generates pipelines.yml for a given node and notifies Chef(through /data/should_redeploy) if logstash re-deployment should happen or not.

        On every node the git repo is downloded in /opt/logstash
        and logstash is deployed in /usr/share/logstash .

        Chef gets proper values from secrets manager and sets them as environment variables and launches this script.
        The script replaces variables from all files(logstash settings, kafka_jaas, log4j2.properties etc) present in the repo
        and generates pipelines.yml file for logstash
    '''
    try:
        logger.info('##########################starting script##########################')
        cur_file_path = os.path.abspath(__file__)
        build_scripts_dir = os.path.dirname(cur_file_path)
        logstash_dir = os.path.dirname(build_scripts_dir)
        pipeline_file_path = os.path.join(
            logstash_dir, 'config', 'pipelines.yml')

        helper = LogstashHelper(logstash_dir)
        helper.generate_files()

        helper.replace_vars()
        logger.info('Variables replaced')
        helper.substitute_jaas_with_values()
        logger.info('Kafka jaas file substituted')
        helper.substitute_logger_with_values()
        logger.info('logger configuration substituted')
        helper.generate_pipeline(pipeline_file_path)
        logger.info(f'Pipeline generated in {os.getenv("DEPLOY_ENV")}')

        last_deployed_dir = '/usr/share/logstash'
        current_deployable_dir = os.path.join(logstash_dir, 'config')
        helper.test_for_change(last_deployed_dir, current_deployable_dir)
    except KeyError as k:
        logger.error(f'Could not find key {k}')
        logger.exception(k)
        logger.error(f'Exiting abruptly')
        sys.exit(-1)
    except Exception as e:
        logger.exception(e)
        logger.error(f'Exiting abruptly')
        sys.exit(-1)
