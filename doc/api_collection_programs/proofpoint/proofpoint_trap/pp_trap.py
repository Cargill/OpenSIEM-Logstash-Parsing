#!/usr/bin/env python3
import logging
import datetime
import os
import time
import json

import prod
import secret
from logging.handlers import RotatingFileHandler
import requests
import sns
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
            request_timeout_ms=100000,
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


def pull_pp_trap_logs(minutes_before):
    logger.info('retrieving secrets for pp_trap')
    current_time = datetime.datetime.utcnow()
    if minutes_before > 0:
        current_time = current_time - \
                       datetime.timedelta(minutes=minutes_before)

    fifteen_minutes_ago = (current_time - datetime.timedelta(minutes=15)).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-4] + "Z"
    twenty_minutes_ago = (current_time - datetime.timedelta(minutes=20)).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-4] + "Z"

    qs = {"created_after": twenty_minutes_ago, "created_before": fifteen_minutes_ago, "expand_events": "false"}
    try:
        r = requests.get('https://10.47.172.28/api/incidents', params=qs,
                         headers={'Authorization': prod.pp_trap_api_key}, verify=False)
        print(r.status_code)

        json_object = r.json()
        print(json_object)
        return json_object

    except Exception as e:
        sns.generate_sns("proofpoint_trap")
        logger.error(f"Error for TRAP API call: {str(e)}")


if __name__ == "__main__":
    minutes_before = 0 * 60
    minutes_before_file = os.path.join(os.getcwd(), 'minutes_before')
    if os.path.exists(minutes_before_file):
        with open(minutes_before_file, 'r') as minutes_file:
            line = minutes_file.readline()
            line = line.strip()
            minutes_before = int(line)

    while True:
        """
        Query TRAP API (JSON format) starting from minutes_before
        send logs to kafka
        reduce minutes_before in next iteration and repeat
        when iteration reaches now -20 minutes
        run the job once every 5 minutes
        """
        logger.info(f'minutes before: {minutes_before}')
        if minutes_before <= 0:
            logger.info('waiting for 5 minutes')
            time.sleep(300)

        logger.info('TRAP query started')
        logs = pull_pp_trap_logs(minutes_before)
        logger.info('TRAP query finished')
        minutes_before = minutes_before - 5

        if logs:
            logger.info('TRAP_produce started')
            run_kafka_producer_job(logs, 'test_log_security_proofpoint.trap_weekly')
            logger.info('TRAP_produce finished')
        else:
            logger.info("No logs for TRAP call.")
        with open(minutes_before_file, 'w') as minutes_file:
            minutes_before = 0 if minutes_before < 0 else minutes_before
            minutes_file.write(str(minutes_before))