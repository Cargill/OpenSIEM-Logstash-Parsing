import os
import ssl
import secret
import logging
import json
from logging import StreamHandler
from logging.handlers import RotatingFileHandler

from kafka import KafkaConsumer, KafkaProducer, TopicPartition
from kafka.producer.future import RecordMetadata

logger = logging.getLogger()
logger.setLevel('INFO')
log_path = 'log_' + os.path.basename(__file__).split('.')[0] + '.log'
handler = RotatingFileHandler(
    log_path, maxBytes=1000000, backupCount=0)
handler = StreamHandler()
formatter = logging.Formatter(
    "[%(asctime)s] - %(message)s")
handler.setLevel(logging.INFO)
handler.setFormatter(formatter)
logger.addHandler(handler)


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
        self.producer.send(self.topic_name, message).add_callback(
                on_send_success).add_errback(on_send_error)

    def close(self):
        self.producer.flush()
        logger.info('flushed')
        self.producer.close()
        logger.info('closed')


class PollingException(Exception):
    def __init__(self, message):
        self.message = message


def set_creds():
    secrets = secret.get_secret('kafka_tgrc_team_producer',
                                    ['KAFKA_USERNAME', 'KAFKA_PASSWORD', 'BOOTSTRAP_URL'])
    os.environ['KAFKA_USERNAME'] = secrets['KAFKA_USERNAME']
    os.environ['KAFKA_PASSWORD'] = secrets['KAFKA_PASSWORD']
    os.environ['KAFKA_HOSTS'] = secrets['BOOTSTRAP_URL']


def produce_csv_to_kafka(topic_name, directory):
    logs_directory = os.getcwd() + directory
    producer = Producer(topic=topic_name)
    logger.info('producer created')
    try:
        for file in os.listdir(logs_directory):
            if file.endswith('.csv') and os.path.getsize(logs_directory + file) > 0:
                logger.info(f'opening file {file}')
                with open(logs_directory + file, 'r') as csv_file:
                    # skip the csv header
                    header = csv_file.readline()
                    for row in csv_file:
                        producer.produce_message(row.encode())
                logger.info(f"completed read of file {file}")
                logger.info('renaming file to _read')
                os.rename(logs_directory + file, logs_directory + file + "_read")
    except Exception as e:
        logger.info(f"Error gathering the file or producing to Kafka: {e}")
        raise e

    finally:
        producer.close()


def run_kafka_producer_job(logs, topic_name):
    set_creds()
    producer = Producer(topic=topic_name)
    logger.info(f'producer created for topic {topic_name}')
    try:
        import json
        for l in logs:
            to_send = json.dumps(l)
            producer.produce_message(to_send.encode())
    except Exception as e:
        logger.info(f"Error gathering the file or producing to Kafka: {str(e)}")
    finally:
        logger.info('sent')
        producer.close()
