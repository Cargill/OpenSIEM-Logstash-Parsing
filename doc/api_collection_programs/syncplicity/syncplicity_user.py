#!/usr/bin/env python3
import datetime
import logging
import os
from logging.handlers import RotatingFileHandler
import requests
import secret
from kafka import KafkaProducer
import base64

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


def delete_files(directory):
    logs_directory = os.getcwd() + directory
    logger.info(f"deleting _read files in: {logs_directory}")
    filtered_files = [file for file in os.listdir(
        logs_directory) if file.endswith("read")]
    for file in filtered_files:
        path_to_file = os.path.join(logs_directory, file)
        logger.info(f"deleting {path_to_file}")
        os.remove(path_to_file)


def produce_csv_to_kafka(topic_name, directory):
    set_creds()
    logs_directory = os.getcwd() + directory
    producer = Producer(topic=topic_name)
    logger.info('producer created')
    try:
        for file in os.listdir(logs_directory):
            if file.endswith('.csv') and os.path.getsize(logs_directory + file) > 0:
                logger.info(f'opening file {file}')
                # read in the file, for each line in CSV, encode in message batch
                with open(logs_directory + file, 'r') as csv_file:
                    # skip the csv header
                    header = csv_file.readline()
                    for row in csv_file:
                        producer.produce_message(row.encode())
                logger.info(f"completed read of file {file}")
                # rename code
                logger.info('renaming file to _read')
                os.rename(logs_directory + file, logs_directory + file + "_read")
    except Exception as e:
        logger.info(f"Error gathering the file or producing to Kafka: {e}")
        raise e

    finally:
        producer.close()



def get_logs(token, file, directory, date):
    command3_url = f"https://data.syncplicity.com/v2/files?syncpoint_id={file['SyncpointId']}&file_version_id={file['LatestVersionId']}"
    command3_headers = {
        'AppKey': syncplicity_secrets["syncplicity_app_key"],
        'Authorization': f'Bearer {token}'
    }
    try:
        name = os.getcwd() + directory + "syncplicity_user_" + str(date) + ".csv"
        logger.info(f'requesting {file["Filename"]}')
        with requests.get(command3_url, headers=command3_headers, stream=True) as r:
            r.raise_for_status()
            with open(name, 'wb') as local_file:
                logger.info(f'downloading {file["Filename"]} started')
                for chunk in r.iter_content(chunk_size=8192):
                    local_file.write(chunk)
                logger.info(f'downloading {file["Filename"]} finished')
    except Exception as f:
        logger.error(f"The API call for {directory} failed: {str(f)}")
        return None


def get_filenames(token, syncplicity_secrets):
    get_url = "https://api.syncplicity.com/sync/folder_files.svc/8942987/folder/632699416638001/files"
    get_headers = {
        'Accept': 'application/json',
        'AppKey': syncplicity_secrets["syncplicity_app_key"],
        'Authorization': f'Bearer {token}'
    }
    results = requests.get(get_url, headers=get_headers)
    filenames = results.json()
    logger.info(f"Here are the filenames: {filenames}")
    # $fileNames = ($results2 | Sort-Object –Property FileId –Descending | Select-Object –First 2)
    return filenames

'''
This filenames is a json object that contains the key "SyncpointId" and "LatestVersionId"
for each filename, brian creates a path to the filename (I guess it creates the file there)
so the curl -o is telling the name of the file that should receive the data for that specific filename
if the filename is like "audit a user report*" then you run this command
'''


def get_access_token(syncplicity_secrets):
    url = "https://api.syncplicity.com/oauth/token"
    auth = base64.b64encode((syncplicity_secrets["syncplicity_client_id"] + ":" + syncplicity_secrets["syncplicity_secret"]).encode('ascii')).decode('utf8')

    headers = {'Authorization': 'Basic INSERT_TOKEN_HERE',
               'Sync-App-Token': syncplicity_secrets['syncplicity_app_key'],
                'Content-Type': 'application/x-www-form-urlencoded'
                }
    try:
        sync_post = requests.post(url, data='grant_type=client_credentials', headers=headers)
        token = sync_post.json()["access_token"]
        return (token)
    except Exception as e:
        logger.error(f"Exception occurred in get_access_token: {str(e)}")
        return None


if __name__ == "__main__":
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    yesterday.strftime('%yyyy-%mm-%dd')
    syncplicity_secrets = secret.get_secret(
        'ngsiem-aca-logstash-api',
        ['syncplicity_app_key', 'syncplicity_client_id', 'syncplicity_secret'])

    directory = '/syncplicity_user/'
    token = get_access_token(syncplicity_secrets)

    if token is not None:
        filenames = get_filenames(token, syncplicity_secrets)
        for file in filenames:
            if "Audit a user report" in file["Filename"] and str(yesterday) in file["Filename"]:
                logger.info(f"Found this file: {file['Filename']}")
                get_logs(token, file, directory, yesterday)
                produce_csv_to_kafka("log_audit_syncplicity.usr_monthly", directory)
                delete_files(directory)