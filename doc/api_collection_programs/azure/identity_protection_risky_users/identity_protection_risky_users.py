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
            kafka_producer.run_kafka_producer_job(logs, "log_security_azure.graph_identity_protection_api_monthly")
