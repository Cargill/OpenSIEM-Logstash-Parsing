from pod_logging.websocket.client import Client
from pod_logging.websocket.config import Config
import select
import errno
import secret
from kafka import KafkaProducer
from logging.handlers import RotatingFileHandler
import os
import logging
import ssl
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


class Producer():
    def __init__(self, topic):
        kafka_secrets = secret.get_secret(
            'ngsiem-aca-kafka-config', ['username', 'password'])

        kafka_uname = kafka_secrets['username']
        kafka_pwd = kafka_secrets['password']
        kafka_hosts = 'kafka1.tgrc.cargill.com:9092,kafka2.tgrc.cargill.com:9092,kafka3.tgrc.cargill.com:9092,kafka4.tgrc.cargill.com:9092,kafka5.tgrc.cargill.com:9092'
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
            api_version=(0, 10, 1),
            ssl_context=ssl._create_unverified_context()
        )

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


if __name__ == '__main__':
    pod_secrets = secret.get_secret('ngsiem-aca-logstash-api',
                                    ['proofpoint_pod_api_key_original_prod', 'proofpoint_websocket_key'])

    PRODUCTION_HOST = 'logstream.proofpoint.com'
    compression = 'permessage-deflate; client_no_context_takeover; server_no_context_takeover'
    filename = "/opt/scripts/proofpoint_client_prod/sample.txt"
    config = Config(PRODUCTION_HOST, websocket_extensions=compression,
        ping_interval=5,
        msg_type="message", trace=True)
    client = KafkaClient(config, ["cargill_hosted2", pod_secrets["proofpoint_pod_api_key_original_prod"]], logger)
    client.run()