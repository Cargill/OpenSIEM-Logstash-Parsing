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
    mcp_secrets = secret.get_secret(
        'ngsiem-aca-kafka-config', ['username', 'password'])
    os.environ['KAFKA_USERNAME'] = mcp_secrets['username']
    os.environ['KAFKA_PASSWORD'] = mcp_secrets['password']
    os.environ['KAFKA_HOSTS'] = 'kafka1.tgrc.cargill.com:9092,kafka2.tgrc.cargill.com:9092,' \
                                'kafka3.tgrc.cargill.com:9092,kafka4.tgrc.cargill.com:9092,' \
                                'kafka5.tgrc.cargill.com:9092'


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


def pull_graph_risky_user_ids(secrets, token):
    default_headers = {'Authorization': f'Bearer {token}'}
    current_time = datetime.datetime.utcnow()
    ten_minutes_ago = (current_time - datetime.timedelta(minutes=500)).strftime("%Y-%m-%dT%H:%M:%S%zZ")

    msgraph = OAuth2Session(secrets["azure_graph_client_id"],
                        scope=secrets["azure_graph_scope"])

    url = f"https://graph.microsoft.com/v1.0/identityProtection/riskyUsers?$filter=riskLastUpdatedDateTime ge {ten_minutes_ago}"

    logs = msgraph.get(url, headers=default_headers).json()
    print(f"Logs: {logs}")
    user_ids = []
    for user in logs["value"]:
        user_ids.append(user["id"])
    return user_ids


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


def pull_history_logs(ids, token):
    default_headers = {'Authorization': f'Bearer {token}'}
    all_logs = []
    msgraph = OAuth2Session(secrets["azure_graph_client_id"],
                            # redirect_uri=config.REDIRECT_URI,
                            scope=secrets["azure_graph_scope"])

    for id in ids:
        url = f"https://graph.microsoft.com/v1.0/identityProtection/riskyUsers/{id}/history"

        logs = msgraph.get(url, headers=default_headers).json()
        for log in logs["value"]:
            all_logs.append(log)
    return all_logs


if __name__ == "__main__":
    secrets = secret.get_secret('ngsiem-aca-logstash-api',
                                    ['azure_graph_secret', 'azure_graph_client_id', 'azure_graph_scope',
                                     'azure_graph_tenant'])
    token = get_auth_token(secrets)
    ids = pull_graph_risky_user_ids(secrets, token)
    if ids:
        logs = pull_history_logs(ids, token)
        print(f"logs: {logs}")
        if logs:
            run_kafka_producer_job(logs, "log_security_azure.graph_identity_protection_api_monthly")