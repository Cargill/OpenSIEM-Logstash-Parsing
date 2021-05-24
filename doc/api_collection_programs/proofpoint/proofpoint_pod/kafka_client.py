from pod_logging.websocket.client import Client
from pod_logging.websocket.config import Config
import select
import errno
import secret
from kafka import KafkaProducer
from logging.handlers import RotatingFileHandler
import os
import time
import logging
from kafka.producer.future import RecordMetadata
logger = logging.getLogger()
logger.setLevel('INFO')
log_path = 'log_' + os.path.basename(__file__).split('.')[0] + '.log'

handler = RotatingFileHandler(
    log_path, maxBytes=1000000, backupCount=5)
formatter = logging.Formatter(
    "[%(asctime)s] {%(pathname)s:%(lineno)d} %(levelname)s - %(message)s")
handler.setLevel(logging.DEBUG)
handler.setFormatter(formatter)
logger.addHandler(handler)


class KafkaClient(Client):
    @Client._pinger
    def handle_connection(self, ws):
        producer = Producer(topic="log_security_proofpoint.pod_email_gateway_daily")
        try:
            while ws.connected:
                r, _, _ = select.select((ws.sock,), (), ())
                if r:
                    message = ws.recv()
                    if len(message) < 1:
                        break
                    else:
                        try:
                            run_kafka_producer_job(message, producer)
                        except Exception as e:
                            logger.error(f"Error occurred when trying to produce to Kafka: {e}")
                else:
                    break
        except select.error as e:
            if e[0] != errno.EINTR:
                logger.error('I/O error: %s', e)


def get_absolute_path(relative_path):
    cwd = os.getcwd()
    file_path = os.path.join(cwd, relative_path)
    if not os.path.exists(file_path):
        raise Exception('cannot find file', file_path)
    return file_path


def on_send_success(record_meta_data:RecordMetadata):
    logger.info('success')
    logger.info(record_meta_data)


def on_send_error(arg):
    logger.info('fail')
    logger.info(arg)


class Producer():
    def __init__(self, topic):
        kafka_uname = os.environ['KAFKA_USERNAME']
        kafka_pwd = os.environ['KAFKA_PASSWORD']
        kafka_hosts = os.environ['KAFKA_HOSTS']
        ssl_truststore_file = get_absolute_path('ca-cert.cer')

        self.topic_name = topic

        self.producer = KafkaProducer(
            bootstrap_servers=kafka_hosts,
            acks=1,
            compression_type='snappy',
            retries=1,
            sasl_plain_username=kafka_uname,
            sasl_plain_password=kafka_pwd,
            security_protocol="SASL_SSL",
            sasl_mechanism="SCRAM-SHA-512",
            ssl_cafile=ssl_truststore_file,
            ssl_check_hostname=True,
            api_version=(2,)
        )

    def send_batch(self, messages):
        for message in messages:
            self.producer.send(self.topic_name, message).add_callback(
                on_send_success).add_errback(on_send_error)

    def produce_message(self, message):
        self.producer.send(self.topic_name, message)

    def close(self):
        self.producer.flush()
        self.producer.close()
        logger.info('closed')


def run_kafka_producer_job(log, producer):
    try:
        producer.produce_message(log)
    except Exception as e:
        logger.info(f'Error gathering the file or producing to Kafka: {str(e)}')
        raise e


def set_creds():
    secrets = secret.get_secret('kafka_tgrc_team_producer',
                                    ['KAFKA_USERNAME', 'KAFKA_PASSWORD', 'BOOTSTRAP_URL'])
    os.environ['KAFKA_USERNAME'] = secrets['KAFKA_USERNAME']
    os.environ['KAFKA_PASSWORD'] = secrets['KAFKA_PASSWORD']
    os.environ['KAFKA_HOSTS'] = secrets['BOOTSTRAP_URL']


class PollingException(Exception):
    def __init__(self, message):
        self.message = message



if __name__ == '__main__':
    set_creds()
    pod_secrets = secret.get_secret('ngsiem-aca-logstash-api',
                                    ['proofpoint_pod_api_key_original_prod', 'proofpoint_websocket_key', 'proofpoint_pod_hosted_name'])

    PRODUCTION_HOST = 'logstream.proofpoint.com'
    compression = 'permessage-deflate; client_no_context_takeover; server_no_context_takeover'
    filename = "/opt/scripts/proofpoint_client_prod/sample.txt"
    config = Config(PRODUCTION_HOST, websocket_extensions=compression,
        ping_interval=5,
        msg_type="message", trace=True)
    client = KafkaClient(config, [pod_secrets["proofpoint_pod_hosted_name"], pod_secrets["proofpoint_pod_api_key_original_prod"]], logger)
 #   time.sleep(30)
    client.run()