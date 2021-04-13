#!/usr/bin/env python3
import datetime
import logging
import os
from logging.handlers import RotatingFileHandler

import requests

import secret
import kafka_producer
import base64

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


def delete_files(directory):
    logs_directory = os.getcwd() + directory
    logger.info(f"deleting _read files in: {logs_directory}")
    filtered_files = [file for file in os.listdir(
        logs_directory) if file.endswith("read")]
    for file in filtered_files:
        path_to_file = os.path.join(logs_directory, file)
        logger.info(f"deleting {path_to_file}")
        os.remove(path_to_file)


def get_logs(token, file, directory, date):
    command3_url = f"https://data.syncplicity.com/v2/files?syncpoint_id={file['SyncpointId']}&file_version_id={file['LatestVersionId']}"
    command3_headers = {
        'AppKey': syncplicity_secrets["syncplicity_app_key"],
        'Authorization': f'Bearer {token}'
    }
    try:
        name = os.getcwd() + directory + "syncplicity_admin_" + str(date) + ".csv"
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
    return filenames

'''
This filenames is a json object that contains the key "SyncpointId" and "LatestVersionId"
for each filename, brian creates a path to the filename (I guess it creates the file there)
so the curl -o is telling the name of the file that should receive the data for that specific filename
if the filename is like "Audit administrator actions*" then you run this command
'''


def get_access_token(syncplicity_secrets):
    url = "https://api.syncplicity.com/oauth/token"
    auth = base64.b64encode((syncplicity_secrets["syncplicity_client_id"] + ":" + syncplicity_secrets["syncplicity_secret"]).encode('ascii')).decode('utf8')

    headers = {'Authorization': f'Basic {syncplicity_secrets["syncplicity_token"]}',
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
    kafka_producer.set_creds()
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    yesterday.strftime('%yyyy-%mm-%dd')
    syncplicity_secrets = secret.get_secret(
        'ngsiem-aca-logstash-api',
        ['syncplicity_app_key', 'syncplicity_client_id', 'syncplicity_secret', 'syncplicity_token'])

    directory = '/syncplicity_admin/'
    token = get_access_token(syncplicity_secrets)
    # print(token)
    if token is not None:
        filenames = get_filenames(token, syncplicity_secrets)
        for file in filenames:
            if "Audit administrator actions" in file["Filename"] and str(yesterday) in file["Filename"]:
                logger.info(f"Found this file: {file['Filename']}")
                get_logs(token, file, directory, yesterday)
                kafka_producer.produce_csv_to_kafka("log_audit_syncplicity.adm_monthly", directory)
                delete_files(directory)