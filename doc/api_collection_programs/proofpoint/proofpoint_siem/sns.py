import logging
import os
import boto3
from logging.handlers import RotatingFileHandler

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


def generate_sns(api):
    sns = boto3.client('sns', region_name='us-east-1')

    try:
        body = f"Error logged when getting logs for the following API: {api}"
        response = sns.publish(
            TopicArn="",
            Message=body,
        )
        return response
    except Exception as e:
        logger.error(f"Exception in trying to send emails about the SNS topic: {str(e)}")
        return None