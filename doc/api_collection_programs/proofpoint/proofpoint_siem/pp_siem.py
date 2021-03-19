#!/usr/bin/env python3
import logging
import os
import time
import json
from logging.handlers import RotatingFileHandler

import requests
import sns
import secret
from kafka import KafkaProducer


logger = logging.getLogger()
logger.setLevel('INFO')
log_path = os.path.basename(__file__).split('.')[0] + '.log'

handler = RotatingFileHandler(
    log_path, maxBytes=1000000, backupCount=5)
formatter = logging.Formatter(
    "[%(asctime)s] {%(pathname)s:%(lineno)d} %(levelname)s - %(message)s")
handler.setLevel(logging.DEBUG)
handler.setFormatter(formatter)
logger.addHandler(handler)


class Producer():
    def __init__(self, topic):
        kafka_uname = os.environ['KAFKA_USERNAME']
        kafka_pwd = os.environ['KAFKA_PASSWORD']
        kafka_hosts = os.environ['KAFKA_HOSTS']
        ssl_truststore_file = '/opt/scripts/ca-cert.cer'

        self.topic_name = topic

        self.producer = KafkaProducer(
            bootstrap_servers=kafka_hosts,
            acks=1,
            compression_type='snappy',
            retries=5,
            linger_ms=200,
            batch_size=1000,
            sasl_plain_username=kafka_uname,
            sasl_plain_password=kafka_pwd,
            security_protocol="SASL_SSL",
            sasl_mechanism="PLAIN",
            # sasl_mechanism="SCRAM-SHA-512",
            ssl_cafile=ssl_truststore_file,
            api_version=(0, 10, 1)
        )

    def produce_message(self, message):
        self.producer.send(self.topic_name, message)

    def close(self):
        self.producer.flush()
        self.producer.close()
        logger.info('closed')


def set_creds():
    secrets = secret.get_secret(
        'ngsiem-aca-kafka-config', ['username', 'password', 'kafka_hosts'])
    os.environ['KAFKA_USERNAME'] = secrets['username']
    os.environ['KAFKA_PASSWORD'] = secrets['password']
    os.environ['KAFKA_HOSTS'] = secrets["kafka_hosts"]


def run_kafka_producer_job(logs, topic_name):
    set_creds()
    producer = Producer(topic=topic_name)
    logger.info('producer created')
    try:
        for l in logs:
            to_send = json.dumps(l)
            producer.produce_message(to_send.encode())
    except Exception as e:
        logger.info(f'Error gathering the file or producing to Kafka: {str(e)}')
        raise e

    finally:
        producer.close()


def pull_pp_siem_logs():
    url = 'https://tap-api-v2.proofpoint.com/v2/siem/all'
    headers = {'content-type': 'application/json', 'Accept': 'application/json'}
    qs = {"sinceSeconds": 300, "format": "JSON"}

    logger.info('retrieving secrets for pp_siem')
    secrets = secret.get_secret('ngsiem-aca-logstash-api',
                                    ['proofpoint_tap_user', 'proofpoint_tap_password', 'sns_api_error_arn'])


    try:
        r = requests.get(url,
                     auth=(secrets['proofpoint_tap_user'],
                           secrets['proofpoint_tap_password']),
                     headers=headers,
                         params=qs)
        return r.json()

    except Exception as e:
        sns.generate_sns("proofpoint_siem")
        logger.error(f"Error for SIEM API call: {str(e)}")


def parse_clicks(logs, endpoint):
    list_dicts = []
    for msg in logs:
        final_dict = dict(msg)
        final_dict['event.dataset'] = endpoint
        list_dicts.append(final_dict)

    return list_dicts


def parse_messages(logs, endpoint):
    list_dicts = []

    for msg in logs:
        final_dict = dict(msg)
        final_dict['event.dataset'] = endpoint
        threat_ids = []
        threat_statuses = []
        classifications = []
        threat_urls = []
        file_hashes = []
        file_names = []

        for threat in msg['threatsInfoMap']:
            threat_ids.append(threat['threatID'])
            threat_statuses.append(threat['threatStatus'])
            classifications.append(threat['classification'])
            threat_urls.append(threat['threatUrl'])
        for part in msg['messageParts']:
            file_hashes.append(part['md5'])
            file_names.append(part['filename'])

        final_dict['threat_ids'] = threat_ids
        final_dict['threat_statuses'] = threat_statuses
        final_dict['classifications'] = classifications
        final_dict['threat_urls'] = threat_urls
        final_dict['file_hashes'] = file_hashes
        final_dict['file_names'] = file_names

        del final_dict['threatsInfoMap']
        del final_dict['messageParts']
        list_dicts.append(final_dict)

    return list_dicts


if __name__ == "__main__":
    '''
    The pp_siem API is JSON. You do not generate the timestamp, but rather search over the last 5 minutes of logs. 
    The data output is small enough to be handled in an array and passed into the kafka producer function.
    *Important - since the messages and clicks endpoints have the same log structure, there needs to be a way to
        differentiate the logs. So, a dict is being wrapped around each response clarifying from what endpoint the logs 
        are coming from. So, additional parsing will need to be done to remove the outermost dict. 
    '''

    while True:
        """
        Query pp_siem API (JSON format) from last 5 minutes
        send logs to kafka
        """
        time.sleep(299)
        logs = pull_pp_siem_logs()
        if logs["clicksPermitted"]:
            endpoint = "test_log_security_proofpoint.siem_api_clicks_monthly"
            clicks_permitted = parse_clicks(logs["clicksPermitted"], "clicksPermitted")
            run_kafka_producer_job(clicks_permitted, endpoint)

        if logs["clicksBlocked"]:
            endpoint = "test_log_security_proofpoint.siem_api_clicks_monthly"
            clicks_blocked = parse_clicks(logs["clicksBlocked"], "clicksBlocked")
            run_kafka_producer_job(clicks_blocked, endpoint)

        if logs['messagesDelivered']:
            endpoint = "test_log_security_proofpoint.siem_api_messages_monthly"
            messages_delivered = parse_messages(logs['messagesDelivered'], "messagesDelivered")
            run_kafka_producer_job(messages_delivered, endpoint)

        if logs['messagesBlocked']:
            endpoint = "test_log_security_proofpoint.siem_api_messages_monthly"
            messages_blocked = parse_messages(logs['messagesBlocked'], "messagesBlocked")
            run_kafka_producer_job(messages_blocked, endpoint)

        logger.info(f'pp_siem_produce finished')
