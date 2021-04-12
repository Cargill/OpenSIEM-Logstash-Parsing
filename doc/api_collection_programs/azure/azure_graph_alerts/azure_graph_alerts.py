'''
Based on these docs (https://github.com/microsoftgraph/security-api-solutions/tree/master/Queries)
'''

import logging
import os
import time
import json
from logging.handlers import RotatingFileHandler
from requests_oauthlib import OAuth2Session
import datetime
import uuid
import requests
import secret
import kafka_producer
import msal
import ssl

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


def pull_graph_alerts(secrets, token):
    default_headers = {'Authorization': f'Bearer {token}'}
    current_time = datetime.datetime.utcnow()
    tem_minutes_ago = (current_time - datetime.timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S%zZ")
    msgraph = OAuth2Session(secrets["azure_graph_client_id"],
                        # redirect_uri=config.REDIRECT_URI,
                        scope=secrets["azure_graph_scope"])

    url = f"https://graph.microsoft.com/v1.0/security/alerts?$filter=createdDateTime ge {tem_minutes_ago}"

    logs = msgraph.get(url, headers=default_headers).json()
    print(f"logs: {str(logs)}")
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

    result = None
    result = app.acquire_token_for_client(scopes="https://graph.microsoft.com/.default")
    return result["access_token"]


def flatten_objects(logs):
    '''
    Since Azure Graph has many lists of dicts, this function will flatten all of these into arrays:
    fileSecurityState
    hostSecurityState
    malwareState
    networkConnection
    process
    registryKeyState
    securityResource
    alertTrigger
    userSecurityState
    securityVendorInformation
    vulnerabilityState
    cloudAppSecurityState
    '''
    list_dicts = []

    for log in logs["value"]:
        final_dict = dict(log)
        provider = []
        sub_provider = []
        vendor = []
        print(f"log: {log}")
        provider.append(log["vendorInformation"]["provider"])
        sub_provider.append(log["vendorInformation"]["subProvider"])
        vendor.append(log["vendorInformation"]["vendor"])

        final_dict["provider"] = provider
        final_dict["sub_provider"] = sub_provider
        final_dict["vendor"] = vendor
        del final_dict['vendorInformation']

        destination_service_ip = []
        destination_service_name = []
        for cas in log["cloudAppStates"]:
            destination_service_ip.append(cas["destinationServiceIp"])
            destination_service_name.append(cas["destinationServiceName"])
        final_dict["destination_service_ip"] = destination_service_ip
        final_dict["destination_service_name"] = destination_service_name
        del final_dict['cloudAppStates']

        domain_name = []
        user_principal_name = []
        for us in log["userStates"]:
            domain_name.append(us["domainName"])
            user_principal_name.append(us["userPrincipalName"])
        final_dict["domain_name"] = domain_name
        final_dict["user_principal_name"] = user_principal_name
        del final_dict['userStates']

        list_dicts.append(final_dict)
    return list_dicts

if __name__ == "__main__":
    secrets = secret.get_secret('ngsiem-aca-logstash-api',
                                    ['azure_graph_secret', 'azure_graph_client_id', 'azure_graph_scope',
                                     'azure_graph_tenant'])
    token = get_auth_token(secrets)
    logs = pull_graph_alerts(secrets, token)
    flattened_logs = flatten_objects(logs)
    kafka_producer.run_kafka_producer_job(flattened_logs, "log_security_azure.graph_api_monthly")