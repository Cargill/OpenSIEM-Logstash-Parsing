import logging
import os
import json
from logging.handlers import RotatingFileHandler
from requests_oauthlib import OAuth2Session
import datetime
import secret
import msal
import ssl
import kafka_producer

logger = logging.getLogger()
logger.setLevel('INFO')
log_path = 'log' + os.path.basename(__file__).split('.')[0] + '.log'

handler = RotatingFileHandler(
    log_path, maxBytes=1000000, backupCount=5)
formatter = logging.Formatter(
    "[%(asctime)s] {%(pathname)s:%(lineno)d} %(levelname)s - %(message)s")
handler.setLevel(logging.DEBUG)
handler.setFormatter(formatter)
logger.addHandler(handler)


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
        kafka_producer.run_kafka_producer_job(logs["value"], "log_security_azure.graph_identity_protection_api_monthly")
