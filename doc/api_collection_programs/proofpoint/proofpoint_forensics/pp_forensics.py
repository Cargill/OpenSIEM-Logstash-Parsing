#!/usr/bin/env python3
import logging
import os
import time
import json
from logging.handlers import RotatingFileHandler

import requests
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
        'ngsiem-aca-kafka-config', ['username', 'password'])
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



def query_forensics_api(principal, password, list_threatIds):
    forensic_logs = []
    headers = {'content-type': 'application/json', 'Accept': 'application/json'}
    for threat in list_threatIds:
        qs = {"threatId": threat, "format": "JSON"}
        r = requests.get('https://tap-api-v2.proofpoint.com/v2/forensics', auth=(principal, password), headers=headers,
                     params=qs)
        logger.info(f'Outcome of forensics API: {str(r.json())}')
        for report_objects in r.json()['reports']:
            forensic_logs.append(json.dumps(report_objects))
    logger.info(f'Here are the forensics report logs: {forensic_logs}')
    return forensic_logs


def parse_for_threatIds(response):
    threatIDs = []

    # Getting threatIds from clicksPermitted
    if response["clicksPermitted"]:
        for item in response["clicksPermitted"]:
            threatIDs.append(item["threatID"])

    # Getting threatIds from clicksBlocked
    if response["clicksBlocked"]:
        for item in response["clicksBlocked"]:
            threatIDs.append(item["threatID"])

    # Getting threatIds from messagesDelivered
    if response["messagesDelivered"]:
        for item in response["messagesDelivered"]:
            for inner_map_item in item["threatsInfoMap"]:
                threatIDs.append(inner_map_item["threatID"])

    # Getting threatIds from messagesBlocked
    if response["messagesBlocked"]:
        for item in response["messagesBlocked"]:
            for inner_map_item in item["threatsInfoMap"]:
                threatIDs.append(inner_map_item["threatID"])

    return threatIDs


def query_siem_api(principal, password, seconds):
    headers = {'content-type': 'application/json', 'Accept': 'application/json'}
    qs = {"sinceSeconds": seconds, "format": "JSON"}
    r = requests.get('https://tap-api-v2.proofpoint.com/v2/siem/all', auth=(principal, password), headers=headers, params=qs)
    logger.info(f"Output from the SIEM API: {str(r.json())}")
    return r.json()


if __name__ == "__main__":
    while True:
        time.sleep(299)
        secrets = secret.get_secret('ngsiem-aca-logstash-api',
                                        ['proofpoint_tap_user', 'proofpoint_tap_password', 'sns_api_error_arn'])
        siem_logs = query_siem_api(secrets['proofpoint_tap_user'], secrets['proofpoint_tap_password'], 300)
        threat_ids = parse_for_threatIds(siem_logs)
        unique_ids = tuple(threat_ids)
        forensics_logs = query_forensics_api(secrets["proofpoint_tap_user"], secrets["proofpoint_tap_password"], unique_ids)
        if forensics_logs["forensics"]:
            run_kafka_producer_job(forensics_logs, "test_log_security_proofpoint.forensics_api_monthly")
        logger.info(f"pp_forensics produce finished")