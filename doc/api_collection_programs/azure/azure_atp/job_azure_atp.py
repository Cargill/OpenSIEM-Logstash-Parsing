'''
Based on these docs (https://github.com/microsoftgraph/security-api-solutions/tree/master/Queries)
https://graph.microsoft.com/v1.0/security/alerts?$filter=createdDateTime
'''

import logging
import os
import json
from logging.handlers import RotatingFileHandler
import datetime
import requests
import secret
import ssl
import kafka_producer
import msal

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


def pull_atp_alerts(token):
    default_headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json',
                       'Accept': 'application/json'}
    current_time = datetime.datetime.utcnow()
    fifteen_minutes_ago = (current_time - datetime.timedelta(minutes=15)).isoformat() + "Z"
    url = f"https://api.securitycenter.microsoft.com/api/alerts?$filter=alertCreationTime+ge+{fifteen_minutes_ago}"
    logs = requests.get(url, headers=default_headers)
    logger.info(f"Logs: {logs.json()}")
    return logs.json()


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

    result = None
    result = app.acquire_token_for_client(scopes=["https://api.securitycenter.microsoft.com/.default"])
    return result['access_token']


if __name__ == "__main__":
    secrets = secret.get_secret('ngsiem-aca-logstash-api',
                                ['azure_graph_secret', 'azure_graph_client_id', 'azure_graph_scope',
                                 "azure_graph_tenant"])
    logger.info(f"scope: {secrets['azure_graph_scope']}")
    token = get_auth_token(secrets)
    logs = pull_atp_alerts(token)
    try:
        if logs and logs["value"]:
            kafka_producer.run_kafka_producer_job(logs["value"], "test_log_security_azure.atp_api_monthly")
        else:
            logger.info("No logs now.")
    except KeyError as k:
        logger.error(f"Something is wrong with the API: {k}")
    except Exception as e:
        logger.error(f"Unexpected exception: {e}")
