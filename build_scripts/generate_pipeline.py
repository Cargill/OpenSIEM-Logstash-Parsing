import hashlib
import json
import os
import re
import sys
from pathlib import Path


def get_logger():
    import logging
    from logging.handlers import TimedRotatingFileHandler
    from logging.handlers import RotatingFileHandler

    logger = logging.getLogger('my_app')
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
        self.my_index = int(os.environ['MY_INDEX'])
        self.sub_my_ip = os.environ['SUB_MY_IP']
        self.elastic_user, self.elastic_pwd = self.__get_elastic_creds()
        self.elastic_servers = self.__get_elastic_servers()
        self.kafka_servers = self.__get_kafka_servers()
        self.kafka_user, self.kafka_pwd = self.__get_kafka_creds()
        self.logstash_api_secrets = self.__get_logstash_api_secret()
        self.bucket_name = self.__get_bucket_name()
        self.high_volume_logs = self.__get_high_volume_logs()
        self.prod_only_logs = self.__get_prod_only_logs()
        self.clear_lag_logs = self.__clear_lag_logs()

    def __get_elastic_creds(self):
        elastic_master_secret = os.environ['ELASTIC_MASTER_SECRET']
        elastic_master_json = jsonise(elastic_master_secret)
        elastic_user = 'admin'
        if self.deploy_env == 'dev':
            elastic_pwd = elastic_master_json['admin_no_encryption']
        else:
            elastic_pwd = elastic_master_json['admin']
        return elastic_user, elastic_pwd

    def __get_elastic_servers(self):
        elastic_worker_secret = os.environ['ELASTIC_WORKERS_SECRET']
        elastic_worker_json = jsonise(elastic_worker_secret)
        worker_hot_ips = elastic_worker_json['worker_hot_ips'].split(',')
        return worker_hot_ips

    def __get_kafka_servers(self):
        kafka_ips_secret = os.environ['KAFKA_IPS_SECRET']
        kafka_ips_json = jsonise(kafka_ips_secret)
        return kafka_ips_json['kafka_ips'].split(',')

    def __get_kafka_creds(self):
        kafka_creds_secret = os.environ['KAFKA_CREDS_SECRET']
        kafka_creds_json = jsonise(kafka_creds_secret)
        return kafka_creds_json['ZOO_SERVER_USER'], kafka_creds_json['ZOO_SERVER_PASSWORD']

    def __get_logstash_api_secret(self):
        logstash_api_sec = os.environ['LOGSTASH_API_SECRET']
        return jsonise(logstash_api_sec)

    def __get_bucket_name(self):
        if self.deploy_env == 'dev':
            return 'acap-archives-dev'
        elif self.deploy_env == 'prod':
            return 'acap-archives-prod'
        else:
            return 'acap-archives-test'

    def __clear_lag_logs(self):
        '''
        CAUTION: when you add config here, don't forget to update the value of
        num_nodes_for_clear_lag
        and consumer_threads for clear lag accordingly
        '''
        clear_lag_logs = [
            'log_network_aws.vpcflow_daily',
        ]
        # reversing the list as it is distributed in reverse order
        clear_lag_logs.reverse()
        return clear_lag_logs

    def __get_high_volume_logs(self):
        high_volume_log_names = [
            'log_audit_checkpoint.fw_cnet_gl_vpn_daily',
            'log_audit_citrix.netscaler_daily',
            'log_audit_checkpoint.fw_cnet_na_internet_daily',
            'log_security_mcafee.mcp_daily',
            'log_security_mcafee.mwg_na_daily',
            'log_security_mcafee.mwg_eu_daily',
            'log_security_mcafee.mwg_la_daily',
            'log_security_mcafee.mwg_ap_daily',
            'log_audit_infoblox_daily',
            'log_audit_checkpoint.fw_plant_daily',
            'log_audit_windows.events_server_eu_daily',
            'log_audit_windows.events_dc_na_daily',
            'log_audit_windows.events_server_na_daily',
            'log_audit_windows.events_dc_eu_daily',
            'log_audit_cisco.router_weekly',
        ]
        # reversing the list as it is distributed in reverse order
        high_volume_log_names.reverse()
        return high_volume_log_names

    def __get_prod_only_logs(self):
        api_logs = [
            'log_audit_azure.event_hub_audit_weekly',
            'log_audit_azure.event_hub_operational_weekly',
            'log_audit_azure.event_hub_signin_weekly',
            'log_audit_o365.msg.trkg_weekly',
            'log_security_azure.event_hub_tcs',
            'log_audit_o365.activity_weekly',
            'log_audit_okta_weekly',
            'log_security_proofpoint.siem.api_daily'
        ]
        return api_logs

    def __get_enrichments(self):
        enrichment_path = f'{self.logstash_dir}/pipeline/enrichments'
        enrichment_list = os.listdir(enrichment_path)
        enrichment_list.sort()
        enrichment_list = list(
            filter(lambda file_name: file_name.endswith('.conf'), enrichment_list))
        all_enrichments = ''
        for enrichment_file in enrichment_list:
            with open(f'{enrichment_path}/{enrichment_file}') as enrichment_conf:
                all_enrichments += enrichment_conf.read() + '\n'
        return all_enrichments

    def __get_output_block(self):
        output_path = f'{self.logstash_dir}/pipeline/output.conf'
        output_str = ''
        with open(output_path) as output_conf:
            output_str = output_conf.read()
        return output_str

    def __add_enrichments_and_output(self, conf_dir: str, conf_list: list):
        enrichments = self.__get_enrichments()
        output_block = self.__get_output_block()
        for conf_file_name in conf_list:
            file_contents = None
            with open(f'{conf_dir}/{conf_file_name}', encoding='UTF-8') as config:
                file_contents = config.read()
            if self.deploy_env == 'test':
                if 'VAR_ENRICHMENTS' not in file_contents:
                    raise ValueError(
                        f'config {conf_file_name} does not contain VAR_ENRICHMENTS variable')
                if 'VAR_OUTPUT' not in file_contents:
                    raise ValueError(
                        f'config {conf_file_name} does not contain VAR_OUTPUT variable')
            file_contents = file_contents.replace('# VAR_OUTPUT', output_block)
            file_contents = file_contents.replace(
                '# VAR_ENRICHMENTS', enrichments)
            with open(f'{conf_dir}/{conf_file_name}', 'w', encoding='UTF-8') as config:
                config.write(file_contents)

    def __tweak_kafka_settings(self, file_as_str, max_poll_records):
        # tweaking these values
        file_as_str = file_as_str.replace(
            'max_poll_records => "500"', f'max_poll_records => "{max_poll_records}"')
        return file_as_str

    def replace_vars(self):
        conf_dir = f'{self.logstash_dir}/pipeline/confs'
        conf_list = os.listdir(conf_dir)
        conf_list = list(
            filter(lambda file_name: file_name.endswith('.conf'), conf_list))
        # add enrichments and output to every file
        self.__add_enrichments_and_output(conf_dir, conf_list)

        kafka_servers_str = ':9092,'.join(self.kafka_servers) + ':9092'
        elastic_servers_str = '"' + \
            ':9200", "'.join(self.elastic_servers) + ':9200"'
        date = '%{+xxxx.MM.dd}'
        month = '%{+xxxx.MM}'
        week = '%{+xxxx.ww}'
        vars_dict = {
            'KAFKA_JAAS_PATH': '/usr/share/logstash/config/kafka_jaas.conf',
            'KAFKA_CLIENT_TRUSTSTORE': '/usr/share/logstash/config/kafka_client_truststore.jks',
            'KAFKA_TRUSTSTORE_PASSWORD': 'changeit',
            'KAFKA_BOOTSTRAP_SERVERS': kafka_servers_str,
            'LOGSTASH_PLUGIN_ID': f'logstash_kafka-{self.sub_my_ip}',
            'ELASTIC_SERVERS': elastic_servers_str,
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
            'PROOFPOINT_AUTH': self.logstash_api_secrets['proofpoint_auth'],
            'OKTA_AUTH': self.logstash_api_secrets['okta_auth'],
            'BUCKET_NAME': self.bucket_name,
            'BITSIGHT_AUTH': self.logstash_api_secrets['bitsight_auth'],
            'NC4_API_KEY': self.logstash_api_secrets['nc4_api_key'],
            'NC4_API_URI': self.logstash_api_secrets['nc4_api_uri'],
            'AZURE_ATP_CONSUMER': self.logstash_api_secrets['azure_atp_consumer'],
            'AZURE_ATP_CONN': self.logstash_api_secrets['azure_atp_conn'],
        }

        unknown_var_regexp = re.compile("VAR_.\w*")
        for conf_file in conf_list:
            config_name = conf_file.split('.conf')[0]
            log_type = config_name.split('_')[-1]

            if log_type == 'daily':
                index_name = f'{config_name.lower()}_{date}'
                consumer_threads = 16
            elif log_type == 'weekly':
                index_name = f'{config_name.lower()}_{week}'
                consumer_threads = 4
            else:
                # monthly or anything else
                index_name = f'{config_name.lower()}_{month}'
                consumer_threads = 4

            # treat test configs as low volume, they are not priority
            if config_name.startswith('test_'):
                consumer_threads = 4
                max_poll_records = 100

            # reduce consumer_threads for high volume logs as they would be processed on 2 nodes
            if config_name in self.high_volume_logs:
                consumer_threads = 8
            if config_name in self.clear_lag_logs:
                consumer_threads = 4

            vars_dict['KAFKA_TOPIC'] = config_name
            vars_dict['KAFKA_GROUP_ID'] = config_name
            vars_dict['KAFKA_CLIENT_ID'] = f'{config_name}-{self.sub_my_ip}-input'
            vars_dict['ELASTIC_INDEX'] = index_name
            vars_dict['CONSUMER_THREADS'] = consumer_threads
            vars_dict['MAX_POLL_RECORDS'] = max_poll_records
            s3_date_pattern = '%{+xxxx/MM/dd}'
            vars_dict['S3_PREFIX'] = f'{config_name}/{s3_date_pattern}'

            file_contents = None
            with open(f'{conf_dir}/{conf_file}', encoding='UTF-8') as config:
                file_contents = config.read()
            for var in vars_dict.keys():
                file_contents = file_contents.replace(
                    f'VAR_{var}', f'{vars_dict[var]}')

            unknown_vars = unknown_var_regexp.findall(file_contents)
            if len(unknown_vars) > 0:
                raise ValueError(
                    f'Unknown variable/s {unknown_vars} in config {conf_file}.')

            # for all logs update these settings
            file_contents = self.__tweak_kafka_settings(
                file_contents, max_poll_records)

            with open(f'{conf_dir}/{conf_file}', 'w', encoding='UTF-8') as config:
                config.write(file_contents)

    def __get_log_distribution(self, num_logs: int, num_servers: int, arr_idx: int, logs: list):
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

    def generate_pipeline(self, deployed_conf_dir, pipeline_file_path):
        '''
            Generate pipelines.yml and write to pipeline_file_path.
            Use deployed_conf_dir to add absolute paths of the configs in pipelines.yml

            Get configs list from pipeline/confs directory and try to do a fair distribution of configs
            while generated pipelines file.
        '''
        conf_list = os.listdir(f'{self.logstash_dir}/pipeline/confs')
        conf_list.sort()
        conf_list = list(
            filter(lambda file_name: file_name.endswith('.conf'), conf_list))
        conf_names = list(
            map(lambda file_name: file_name.split('.conf')[0], conf_list))

        self.prod_only_logs = self.__get_matched_items(
            conf_names, self.prod_only_logs)
        self.high_volume_logs = self.__get_matched_items(
            conf_names, self.high_volume_logs)
        self.clear_lag_logs = self.__get_matched_items(
            conf_names, self.clear_lag_logs)

        daily_logs = []
        weekly_logs = []
        monthly_logs = []
        for config_file in conf_names:
            if config_file in self.high_volume_logs:
                continue
            if config_file in self.clear_lag_logs:
                continue
            if self.deploy_env == 'dev' and config_file in self.prod_only_logs:
                continue
            log_type = config_file.split('_')[-1]
            # treat test configs as low volume, they are not a priority
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

        log_path_names = []
        arr_idx = self.my_index - 1
        num_servers = len(self.logstash_servers)

        # process each clear lag log on this many nodes
        num_nodes_for_clear_lag = 4
        clear_number = len(self.clear_lag_logs)
        num_servers_for_clear_lag = clear_number*num_nodes_for_clear_lag
        if clear_number > 0:
            normalized_index = arr_idx % clear_number
            clear_lag_conf = self.__get_log_distribution(
                clear_number, num_servers, normalized_index, self.clear_lag_logs)
        else:
            clear_lag_conf = []
        if arr_idx < num_servers_for_clear_lag:
            log_path_names = clear_lag_conf
        else:
            num_servers = num_servers - num_servers_for_clear_lag
            arr_idx = arr_idx - num_servers_for_clear_lag

            for logs in [daily_logs, weekly_logs, monthly_logs]:
                num_logs = len(logs)
                log_path_names = log_path_names + \
                    self.__get_log_distribution(
                        num_logs, num_servers, arr_idx, logs)

            # distribute high volume logs on this many nodes
            high_number = len(self.high_volume_logs)
            if high_number > 0:
                normalized_index = arr_idx % high_number
                high_vol_conf = self.__get_log_distribution(
                    high_number, num_servers, normalized_index, self.high_volume_logs)
            else:
                high_vol_conf = []
            if arr_idx+1 > high_number*2:
                # don't process high volume logs on more than 2 nodes
                high_vol_conf = []
            log_path_names = log_path_names + high_vol_conf

        file_contents = ''
        for log_source_name in log_path_names:
            log_type = log_source_name.split('_')[-1]
            # treat test configs as low volume, they are not a priority
            if log_source_name.startswith('test_'):
                log_type = 'monthly'

            if log_type == 'daily':
                pipeline_workers = 32
                batch_size = 1000
                batch_delay = 50
            elif log_type == 'weekly':
                pipeline_workers = 8
                batch_size = 150
                batch_delay = 50
            elif log_type == 'monthly':
                pipeline_workers = 4
                batch_size = 150
                batch_delay = 50
            else:
                pipeline_workers = 4
                batch_size = 150
                batch_delay = 50

            if log_source_name in self.high_volume_logs or log_source_name in self.clear_lag_logs:
                pipeline_workers = 64
                batch_size = 1000

            config_file_path = f'{deployed_conf_dir}{log_source_name}.conf'
            pipeline_entry = f'- pipeline.id: {log_source_name}\n' + \
                             f'  pipeline.batch.delay: {batch_delay}\n' + \
                             f'  pipeline.batch.size: {batch_size}\n' + \
                             f'  path.config: \"{config_file_path}\"\n' + \
                             f'  pipeline.workers: {pipeline_workers}\n'


            file_contents = file_contents + pipeline_entry

        with open(pipeline_file_path, 'w', encoding='UTF-8') as pipeline:
            pipeline.write(file_contents)

        return log_path_names

    def substitute_jaas_with_values(self):
        '''
            Substitute variables in kafka_jaas.conf
        '''
        jaas_file_path = f'{self.logstash_dir}/pipeline/kafka_jaas.conf'
        jaas_file_str = ''
        with open(jaas_file_path) as jaas_file:
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
        log_file_path = f'{self.logstash_dir}/pipeline/log4j2.properties'
        log_file_str = ''
        with open(log_file_path) as jaas_file:
            log_file_str = jaas_file.read()
        import socket
        hostname = socket.gethostname()
        log_file_str = log_file_str.replace(
            'VAR_HOSTNAME', hostname)
        with open(log_file_path, 'w', encoding='UTF-8') as jaas_file:
            jaas_file.write(log_file_str)


def setup_test_env():
    '''
        Setup dummy values in environment variables.
    '''
    os.environ['LOGSTASH_SERVERS'] = ','.join(['1'])
    os.environ['ELASTIC_MASTER_SECRET'] = json.dumps({
        'admin': 'admin'
    })
    os.environ['ELASTIC_WORKERS_SECRET'] = json.dumps({
        'worker_hot_ips': '0.0.0.1,0.0.0.2,0.0.0.3,0.0.0.4'
    })
    os.environ['KAFKA_IPS_SECRET'] = json.dumps({
        'kafka_ips': '0.0.0.1,0.0.0.2,0.0.0.3,0.0.0.4'
    })
    os.environ['KAFKA_CREDS_SECRET'] = json.dumps({
        'ZOO_SERVER_USER': 'kafka_username',
        'ZOO_SERVER_PASSWORD': 'kafka_password',
    })
    os.environ['LOGSTASH_API_SECRET'] = json.dumps({
        'azure_audit_conn': 'Endpoint=sb://dummy.com/;SharedAccessKeyName=dum;SharedAccessKey=key=;EntityPath=path',
        'azure_operational_conn': 'Endpoint=sb://dummy.com/;SharedAccessKeyName=dum;SharedAccessKey=key=;EntityPath=path',
        'azure_signin_conn': 'Endpoint=sb://dummy.com/;SharedAccessKeyName=dum;SharedAccessKey=key=;EntityPath=path',
        'azure_o365_conn': 'Endpoint=sb://dummy.com/;SharedAccessKeyName=dum;SharedAccessKey=key=;EntityPath=path',
        'azure_tcs_security_conn': 'Endpoint=sb://dummy.com/;SharedAccessKeyName=dum;SharedAccessKey=key=;EntityPath=path',
        'azure_o365_dlp_conn': 'Endpoint=sb://dummy.com/;SharedAccessKeyName=dum;SharedAccessKey=key=;EntityPath=path',
        'azure_audit_consumer': 'azure_audit_consumer',
        'azure_operational_consumer': 'azure_operational_consumer',
        'azure_signin_consumer': 'azure_signin_consumer',
        'azure_o365_consumer': 'azure_o365_consumer',
        'azure_tcs_security_consumer': 'azure_o365_consumer',
        'azure_o365_dlp_consumer': 'cg-production-operation',
        'azure_storage_conn': 'DefaultEndpointsProtocol=https;AccountName=dummyname;AccountKey=key;EndpointSuffix=core.windows.net',
        'proofpoint_auth': 'proofpoint_auth',
        'okta_auth': 'okta_auth',
        'bitsight_auth': 'byeKS!!',
        'nc4_api_key': 'nc4_api_key',
        'nc4_api_uri': 'nc4_api_uri',
        'azure_atp_consumer': 'conn',
        'azure_atp_conn': 'conn',
    })
    os.environ['MY_INDEX'] = '1'
    os.environ['SUB_MY_IP'] = '10615222'


def generate_checksum(deploy_dir):
    '''
        Generates checksums for all files in
            deploy_dir/confs (logstash configs)
            AND
            deploy_dir (common setting files)
        and returns dictonaries settings_checksum_dict and conf_checksum_dict respectively.
        Each dict contains file name as key and it's md5 hash as value.
    '''
    confs_path = f'{deploy_dir}/confs'
    Path(confs_path).mkdir(parents=True, exist_ok=True)
    conf_list = os.listdir(confs_path)
    conf_list = list(filter(lambda name: Path(
        f'{confs_path}/{name}').is_file(), conf_list))

    settings_path = deploy_dir
    Path(settings_path).mkdir(parents=True, exist_ok=True)
    setting_list = os.listdir(settings_path)
    setting_list = list(filter(lambda name: Path(
        f'{settings_path}/{name}').is_file(), setting_list))

    logger.info(f'generating checksum for files in {confs_path}')
    conf_checksum_dict = {}
    for conf_file_name in conf_list:
        with open(f'{confs_path}/{conf_file_name}', 'rb') as conf_file:
            conf_checksum_dict[conf_file_name] = hashlib.md5(
                conf_file.read()).hexdigest()

    logger.info(f'generating checksum for files in {settings_path}')
    settings_checksum_dict = {}
    for setting_file_name in setting_list:
        with open(f'{settings_path}/{setting_file_name}', 'rb') as setting_file:
            settings_checksum_dict[setting_file_name] = hashlib.md5(
                setting_file.read()).hexdigest()

    return settings_checksum_dict, conf_checksum_dict


def test_for_change(deploy_dir, logstash_dir):
    '''
        Compare the checksums to see if something changed between existing deployment and ongoing deployment
        If something did change, write 'changed' to file /data/should_redeploy .
        Chef client keeps checking this file and triggers redeploy of logstash if it was modified.
    '''
    old_settings_checksum_dict, old_conf_checksum_dict = generate_checksum(
        deploy_dir)
    new_settings_checksum_dict, new_conf_checksum_dict = generate_checksum(
        logstash_dir)
    changed = False
    if len(new_settings_checksum_dict.keys()) == len(old_settings_checksum_dict.keys()):
        # check settings checksum
        for k in new_settings_checksum_dict.keys():
            if new_settings_checksum_dict[k] != old_settings_checksum_dict.get(k, ''):
                logger.info(f'checksum different for {k}')
                changed = True
                break
        # check conf files checksum
        for log_path_name in log_path_names:
            old_checksum = old_conf_checksum_dict.get(
                f'{log_path_name}.conf', '')
            new_checksum = new_conf_checksum_dict.get(
                f'{log_path_name}.conf', '')
            if old_checksum != new_checksum:
                logger.info(f'checksum different for {log_path_name}')
                changed = True
                break
    else:
        changed = True
        logger.info('checksum settings dict are unequal in length')
    if changed:
        with open('/data/should_redeploy', 'a', encoding='UTF-8') as change_file:
            change_file.write('changed')
            logger.info("configs changed")


def notify_teams(url):
    '''
        Send nodes and confifs mappings to microsoft teams channel via provided webhook url

        MS Teams API Doc:
         https://docs.microsoft.com/en-us/microsoftteams/platform/webhooks-and-connectors/how-to/connectors-using
    '''
    # importing requests module here as it is not needed for general usage of this script
    import requests

    os.environ['DEPLOY_ENV'] = 'test'
    # hardcoded value for number of logstash nodes in prod environment
    num_indexers = 46
    # generate dummy ip list for logstash servers
    server_ips = [f'192.168.15.{i}' for i in range(0, num_indexers)]
    # setup other dummy environment variables
    setup_test_env()
    os.environ['LOGSTASH_SERVERS'] = ','.join(server_ips)

    # facts is the list of name value pairs that teams API understands
    # We'll be using a fact to represent a node and assigned configs to it
    facts = []
    # iterate over num_indexers and generate pipelines.yml for each of them
    for i in range(0, num_indexers):
        os.environ['MY_INDEX'] = str(i+1)
        helper = LogstashHelper(logstash_dir)
        pipeline_file_path = f'{pipeline_dir}/pipelines{i+1}.yml'
        pipelines = helper.generate_pipeline(
            deployed_conf_dir, pipeline_file_path)
        # get the list of configs assigned to the current node and code this information into fact name value pair
        facts.append({
            'name': f'node{os.environ["MY_INDEX"]}',
            'value': ', '.join(pipelines)
        })
    # print the fact list (can be seen in drone build step)
    print(json.dumps(facts))
    # the format that ms teams understands
    json_data = {
        '@type': 'MessageCard',
        '@context': 'http://schema.org/extensions',
        'themeColor': '0076D7',
        'summary': 'Pipeline locations',
        'sections': [{
            'markdown': False,
            'activityTitle': 'Prod deployment',
            'activitySubtitle': 'Current pipeline locations',
            'facts': facts
        }]
    }
    requests.post(url=url, json=json_data)


if __name__ == "__main__":
    '''
        SPECIAL CASE
        (in drone build step when changes are pushed to master branch)
        This script can be run with an optional ms teams webhook url argument,
        it posts node and configs mappings to that ms teams channel and exits.

        GENERAL CASE
        Generates pipelines.yml for a given node and notifies Chef(through /data/should_redeploy) if logstash re-deployment should happen or not.

        On every node the git repo is downloded in /opt/logstash
        and logstash is deployed in /usr/share/logstash .

        Chef gets proper values from secrets manager and sets them as environment variables and launches this script.
        The script replaces variables from all files(logstash configs, kafka_jaas, log4j2.properties etc) present in the repo
        and generates pipelines.yml file for logstash
    '''
    try:
        cur_file_path = os.path.abspath(__file__)
        build_scripts_dir = os.path.dirname(cur_file_path)
        logstash_dir = os.path.dirname(build_scripts_dir)
        deploy_dir = '/usr/share/logstash'
        deployed_conf_dir = f'{deploy_dir}/config/confs/'
        pipeline_dir = f'{logstash_dir}/pipeline'
        pipeline_file_path = f'{pipeline_dir}/pipelines.yml'

        # sys.argv[0] is by default the python script name
        # check if notify was passed, then notify on ms teams
        if len(sys.argv) > 1:
            url = sys.argv[1]
            notify_teams(url)
            sys.exit(0)

        if os.environ['DEPLOY_ENV'] == 'test':
            logger.info('setting up test env')
            setup_test_env()

        helper = LogstashHelper(logstash_dir)
        helper.replace_vars()
        logger.info('Variables replaced')
        helper.substitute_jaas_with_values()
        logger.info('Kafka jaas file substituted')
        helper.substitute_logger_with_values()
        logger.info('logger configuration substituted')
        log_path_names = helper.generate_pipeline(
            deployed_conf_dir, pipeline_file_path)
        logger.info(f'Pipeline generated in {os.getenv("DEPLOY_ENV")}')
        test_for_change(deploy_dir, pipeline_dir)
    except KeyError as k:
        logger.error(f'Could not find key {k}')
        logger.exception(k)
        logger.error(f'Exiting abruptly')
        sys.exit(-1)
    except Exception as e:
        logger.error(e)
        logger.exception(e)
        logger.error(f'Exiting abruptly')
        sys.exit(-1)
