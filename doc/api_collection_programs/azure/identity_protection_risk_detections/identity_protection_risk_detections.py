import logging
import os
import json
from logging.handlers import RotatingFileHandler
from requests_oauthlib import OAuth2Session
import datetime
import secret
from kafka import KafkaProducer
import msal
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
            api_version=(0, 10, 1),
            ssl_context= ssl._create_unverified_context()
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
            print("sent the log")
    except Exception as e:
        logger.info(f"Error gathering the file or producing to Kafka: {str(e)}")
        raise e
    finally:
        producer.close()


def pull_graph_alerts(secrets, token):
    default_headers = {'Authorization': f'Bearer {token}'}
    current_time = datetime.datetime.utcnow()
    ten_minutes_ago = (current_time - datetime.timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S%zZ")

    msgraph = OAuth2Session(secrets["azure_graph_client_id"],
                        scope=secrets["azure_graph_scope"])

    url = f"https://graph.microsoft.com/v1.0/identityProtection/riskDetections?$filter=detectedDateTime ge {ten_minutes_ago}"

    logs = msgraph.get(url, headers=default_headers).json()
    return logs


def get_auth_token(secrets):
    tenantid = secrets["azure_graph_tenant"]
    authority = "https://login.microsoftonline.com/" + tenantid
    clientid = secrets["azure_graph_client_id"]
    secret = secrets["azure_graph_secret"]

    app = msal.ConfidentialClientApplication(
        clientid,
        authority=authority,
        client_credential=secret,
    )

    result = None  # It is just an initial value. Please follow instructions below.
    result = app.acquire_token_for_client(scopes="https://graph.microsoft.com/.default")
    return result["access_token"]


def flatten_objects(logs):
    '''
    Since Azure Graph has many lists of dicts, this function will flatten all of these into arrays:
    additionalInfo 
    '''
    list_dicts = []

    for log in logs["value"]:
        print(f"LOG WITHOUT FLATTENING: {log}")
        final_dict = dict(log)
        user_agent = []
        additional_info = log["additionalInfo"].strip('][').split(', ')
        for item in additional_info:
            user_agent.append(item["Value"])
        final_dict["user_agent"] = user_agent
        del final_dict['additionalInfo']
        list_dicts.append(final_dict)
        print(f"Log after flattening: {final_dict}")
    return list_dicts


if __name__ == "__main__":
    secrets = secret.get_secret('ngsiem-aca-logstash-api',
                                    ['azure_graph_secret', 'azure_graph_client_id', 'azure_graph_scope',
                                     'azure_graph_tenant'])
    token = get_auth_token(secrets)
    logs = pull_graph_alerts(secrets, token)
    print(f"logs: {logs}")
    if logs["value"]:
        # flattened_logs = flatten_objects(logs)
        run_kafka_producer_job(logs["value"], "log_security_azure.graph_identity_protection_api_monthly")
