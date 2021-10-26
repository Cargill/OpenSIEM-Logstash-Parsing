## Getting started
This example is a walk through for parsing `A10 audit logs`.  The logs will be ingested from kafka topic `a10_proxy` and parsed using [syslog_log_audit_a10.proxy](../config/processors/syslog_log_audit_a10.proxy.conf) config.

Below section is written assuming you ingest logs from kafka and want to use our script to generate pipelines. For a manual process and/or for deeper understanding skip to the [Detailed Setup](#detailed_setup) section.


### Pre-requisites
1. Install LogStash >= 7.12
2. Below plugins which do not come out of box. Install them by executing
```
logstash-plugin install \
        logstash-input-okta_system_log \
        logstash-filter-json_encode \
        logstash-filter-tld
```
3. Setting up Enrichments
    1. Geoip enrichment

    [99_geoip.conf](../config/enrichments/99_geoip.conf) uses GeoLite databases for public and private GeoIP encrichments. If you plan to use this enrichment then you should have geoip files at below locations.
    ```
    /mnt/s3fs_geoip/GeoLite2-City.mmdb
    /mnt/s3fs_geoip/GeoLitePrivate2-City.mmdb
    ```
    Either remove the enrichment file if you don't want to use it or just touch above files if you are disabling the enrichment from [settings.json](./#settings.json). If you want to use this enrichment you need to add geoip files. For more information see [using the Geoip filter](https://www.elastic.co/guide/en/logstash/current/plugins-filters-geoip.html). 

    In this example it is asummed that geoip enrichment would not be used.
    
    2. dns enrichment
      09_dns.conf has variable VAR_DNS_SERVER for nameserver definition.
      Add server address like this in LOGSTASH_API_SECRET json.
      ```sh
      export LOGSTASH_API_SECRET='{"dns_server" : "\"127.0.0.1\",\"127.0.0.2\""}'
      ```
      Here 127.0.0.1 and 127.0.0.2 are nameservers. Make sure you add yours.
      Remove the enrichment file if you won't be using it.

    3. memcached/misp enrichment
      09_dns.conf has variable VAR_DNS_SERVER for nameserver definition.
      Add server address like this in LOGSTASH_API_SECRET json.
      ```sh
      export LOGSTASH_API_SECRET='{"memcached_address" : "\"127.0.0.1\",\"127.0.0.2\""}'
      ```
      Here 127.0.0.1 and 127.0.0.2 are memcached endpoints. Make sure you add yours.
      Remove the enrichment file if you won't be using it.



4. Kafka

To fetch logs from kafka you should have a kafka cluster with access and credentials ready. Also you should have logs on `a10_proxy` topic. A typical kafka input config would look like this. This is taken from [kafka input template](../config/inputs/kafka/1_kafka_input_template.conf) file.

```ruby
input {
  kafka {
    bootstrap_servers => "VAR_KAFKA_BOOTSTRAP_SERVERS" # server address
    client_id => "VAR_KAFKA_CLIENT_ID" # id for kafka client
    group_id => "VAR_KAFKA_GROUP_ID" # consumer group id
    consumer_threads => VAR_CONSUMER_THREADS # number of consumer threads to be assigned
    ssl_truststore_location => "VAR_KAFKA_CLIENT_TRUSTSTORE" # truststore file path, trust your server signing certificate in this file
    ssl_truststore_password => "VAR_KAFKA_TRUSTSTORE_PASSWORD" # ssl truststore password
    jaas_path => "VAR_KAFKA_JAAS_PATH" # path to kafka jaas credentials
    client_rack => "VAR_RACK_ID" # client rack id
    topics => ["VAR_KAFKA_TOPIC"] # topic name
    id => "VAR_LOGSTASH_PLUGIN_ID" # just an id for this plugin
    max_poll_records => VAR_MAX_POLL_RECORDS # number of max records to be polled each time
    codec => "VAR_CODEC"
    partition_assignment_strategy => "cooperative_sticky"
    security_protocol => "SASL_SSL" # Kafka security protocol, assuming you are using SASL_SSL else change this
    sasl_mechanism => "SCRAM-SHA-512" # kafka sasl mechanism, assuming you are using this mechanism else change this
  }
}
```
All the VAR* fields are mandatory and need to be passed from environment variable without VAR_ prefix. e.g. a key `VAR_KAFKA_GROUP_ID` should be passed as 
```sh
export KAFKA_GROUP_ID=logstash_consumer_group
```

### Steps

1. Execute
```
touch /mnt/s3fs_geoip/GeoLite2-City.mmdb
touch /mnt/s3fs_geoip/GeoLitePrivate2-City.mmdb
```
1. Create a `settings.json` file in [build_scripts](./) directory with below content.
`a10_proxy` is the topic name in Kafka. Topic name should be key of the parsing definition and `log_source` value should also be same as topic name. elastic_index
```json
{
  "a10_proxy": {
    "log_source": "a10_proxy",
    "config": "syslog_log_audit_a10.proxy",
    "elastic_index": "a10_proxy_audit_index",
    "ignore_enrichments": ["disable_geoip_enrichment"],
    "output_list": [
      "elastic_output",
    ],
    "kafka_input": {
      "codec": "json"
    }
  }
}
```
2. Create a `general.json` file in [build_scripts](./) directory with below content.
```
{
    "num_indexers" : 1,
    "prod_only_logs": [
    ],
    "processing_config" : {
    }
}
```
3. Set the environment variables as explained in [environment variable section](./#environment-variables) of README.md. Replace all below values with your actual values.
```sh
export DEPLOY_ENV=test
export MY_INDEX='1'
export SUB_MY_IP=hostname_or_ip_without_dots_to_identify_instance
export ELASTIC_USER=your_elastic_user
export ELASTIC_PASSWORD=your_elastic_pass
export ELASTIC_CONNECTION_STRING='"127.0.0.1:9200", "127.0.0.2:9200"'
export KAFKA_CONNECTION_STRING=kafkahost:9000
export KAFKA_USER=your_kafka_uname
export KAFKA_PASSWORD=your_kafka_pwd
export RACK_ID=your_kafka_rack_id
export LOGSTASH_API_SECRET='{"memcached_address" : "\"127.0.0.1\",\"127.0.0.2\"",  "dns_server" : "\"127.0.0.1\",\"127.0.0.2\""}'
```
4. Run  python build_scripts/generate_pipeline.py
5. The script generates logs at /data dir. The script would fail if it cannot create that directory.
6. Copy over the config directory to `/usr/share/logstash`
7. start logstash.


### Detailed Setup
