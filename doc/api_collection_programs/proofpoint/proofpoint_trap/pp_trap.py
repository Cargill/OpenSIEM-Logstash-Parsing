#!/usr/bin/env python3
import logging
import datetime
import os
import time
import json

import prod
import secret
from logging.handlers import RotatingFileHandler
import requests
import sns
import kafka_producer

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


def pull_pp_trap_logs(minutes_before, cluster):
    logger.info('retrieving secrets for pp_trap')
    current_time = datetime.datetime.utcnow()
    if minutes_before > 0:
        current_time = current_time - \
                       datetime.timedelta(minutes=minutes_before)

    fifteen_minutes_ago = (current_time - datetime.timedelta(minutes=15)).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-4] + "Z"
    twenty_minutes_ago = (current_time - datetime.timedelta(minutes=20)).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-4] + "Z"

    qs = {"created_after": twenty_minutes_ago, "created_before": fifteen_minutes_ago, "expand_events": "false"}
    try:
        r = requests.get(f'{cluster}/api/incidents', params=qs,
                         headers={'Authorization': prod.pp_trap_api_key}, verify=False)
        print(r.status_code)

        json_object = r.json()
        print(json_object)
        return json_object

    except Exception as e:
        sns.generate_sns("proofpoint_trap")
        logger.error(f"Error for TRAP API call: {str(e)}")


if __name__ == "__main__":
    minutes_before = 0 * 60
    minutes_before_file = os.path.join(os.getcwd(), 'minutes_before')
    if os.path.exists(minutes_before_file):
        with open(minutes_before_file, 'r') as minutes_file:
            line = minutes_file.readline()
            line = line.strip()
            minutes_before = int(line)

    while True:
        """
        Query TRAP API (JSON format) starting from minutes_before
        send logs to kafka
        reduce minutes_before in next iteration and repeat
        when iteration reaches now -20 minutes
        run the job once every 5 minutes
        """
        logger.info(f'minutes before: {minutes_before}')
        if minutes_before <= 0:
            logger.info('waiting for 5 minutes')
            time.sleep(300)

        logger.info('TRAP query started')
        secrets = secret.get_secret('ngsiem-aca-logstash-api',
                                    ['pp_trap_cluster'])
        logs = pull_pp_trap_logs(minutes_before, secrets['pp_trap_cluster'])
        logger.info('TRAP query finished')
        minutes_before = minutes_before - 5

        if logs:
            logger.info('TRAP_produce started')
            kafka_producer.run_kafka_producer_job()
            kafka_producer.run_kafka_producer_job(logs, 'test_log_security_proofpoint.trap_weekly')
            logger.info('TRAP_produce finished')
        else:
            logger.info("No logs for TRAP call.")
        with open(minutes_before_file, 'w') as minutes_file:
            minutes_before = 0 if minutes_before < 0 else minutes_before
            minutes_file.write(str(minutes_before))