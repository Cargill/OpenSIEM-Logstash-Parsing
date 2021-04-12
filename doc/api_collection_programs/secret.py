import base64
import json
import logging
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def get_secret(secret_name, list_keys):
    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name='us-east-1'
    )

    try:
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)

        # Decrypts secret using the associated KMS CMK.
        # Depending on whether the secret is a string or binary, one of these fields will be populated.
        if 'SecretString' in get_secret_value_response:
            secret = get_secret_value_response['SecretString']
        else:
            print("made it to the ELSE")
            secret = base64.b64decode(get_secret_value_response['SecretBinary'])
        try:
            response = json.loads(secret)
            if response:
                dict_values = {}
                for item in list_keys:

                    dict_values[item] =response[item]
                return dict_values
            else:
                return response
        except Exception as msg:
            logger.error("Encountered exception in trying to connect to ELK IP: {}".format(msg))
            response = {'status':  'Failed', 'msg': msg}
            return response

    except ClientError as e:
        if e.response['Error']['Code'] == 'DecryptionFailureException':
            logger.error("DecryptionFailureException when getting the secret for lambda: " + str(e))
            response = {'status':  'Failed', 'msg': str(e)}
            return response

        elif e.response['Error']['Code'] == 'InternalServiceErrorException':
            logger.error("InternalServiceErrorException when getting the secret for lambda: " + str(e))
            response = {'status':  'Failed', 'msg': str(e)}
            return response

        elif e.response['Error']['Code'] == 'InvalidParameterException':
            logger.error("InvalidParameterException when getting the secret for lambda: " + str(e))
            response = {'status':  'Failed', 'msg': str(e)}
            return response

        elif e.response['Error']['Code'] == 'InvalidRequestException':
            logger.error("InvalidRequestException when getting the secret for lambda: " + str(e))
            response = {'status':  'Failed', 'msg': str(e)}
            return response

        elif e.response['Error']['Code'] == 'ResourceNotFoundException':
            logger.error("ResourceNotFoundException when getting the secret for lambda: " + str(e))
            response = {'status':  'Failed', 'msg': str(e)}
            return response

