## Getting started
This example is a walk through for parsing `A10 audit logs`.  The logs will be ingested from kafka topic `a10_proxy` and parsed using [syslog_log_audit_a10.proxy](./config/processors/syslog_log_audit_a10.proxy.conf) config.

Below section is written assuming you ingest logs from kafka and want to use our script to generate pipelines. For a manual process and/or for deeper understanding skip to the [Detailed Setup](#detailed_setup) section.

It is also assumed that you are using logstash on linux and it's installed at _/usr/share/logstash_ location.


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

    [99_geoip.conf](./config/enrichments/99_geoip.conf) uses GeoLite databases for public and private GeoIP encrichments. If you plan to use this enrichment then you should have geoip files at below locations.
    ```
    /mnt/s3fs_geoip/GeoLite2-City.mmdb
    /mnt/s3fs_geoip/GeoLitePrivate2-City.mmdb
    ```
    Either remove the enrichment file if you don't want to use it or just touch above files if you are disabling the enrichment from [settings.json](./build_scripts#settings.json). If you want to use this enrichment you need to add geoip files. For more information see [using the Geoip filter](https://www.elastic.co/guide/en/logstash/current/plugins-filters-geoip.html). 

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

To fetch logs from kafka you should have a kafka cluster with access and credentials ready. Also you should have logs on `a10_proxy` topic. A typical kafka input config would look like this. This is taken from [kafka input template](./config/inputs/kafka/1_kafka_input_template.conf) file.

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
1. Create a `settings.json` file in [build_scripts](./build_scripts) directory with below content.
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
2. Create a `general.json` file in [build_scripts](./build_scripts) directory with below content.
```
{
    "num_indexers" : 1,
    "prod_only_logs": [
    ],
    "processing_config" : {
    }
}
```
3. Set the environment variables as explained in [environment variable section](./build_scripts#environment-variables) of README.md. Replace all below values with your actual values.
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
1. Install logstash with required plugins following above pre-requisite section of logstash.

2. Clone the repo
```
git clone https://github.com/Cargill/OpenSIEM-Logstash-Parsing
```

3. Assuming your logstash config directory is _/usr/share/logstash/config_ do
```
cp -r OpenSIEM-Logstash-Parsing/config/* /usr/share/logstash/config/
```

4. Cleanup
Remove kafka and azure input directories. We'll create a file input for this example.
```
# remove input directories
rm -rf /usr/share/logstash/config/inputs/*
rm -rf /usr/share/logstash/config/outputs/*
```

dns enrichment needs a dns server.
geoip enrichment needs a geoip database file.
memcache/misp enrichment needs a memcache server.
For the sake of simplicity let's not use these. So do
```
rm -f /usr/share/logstash/config/enrichments/09_dns.conf
rm -f /usr/share/logstash/config/enrichments/99_geoip.conf
rm -f /usr/share/logstash/config/enrichments/100_misp.conf
```
If you want to use these enrichments then you need to do the needful so they can work. e.g. you need to replace the variable with actual values in dns and misp.

5. Let's create our input config.
Open _/usr/share/logstash/config/inputs/a10_input.conf_ in editor and add below.
```
input {
  file {
    path => "/tmp/a10_audit.log"
  }
}
filter {
  mutate {
    add_field => {
      "[@metadata][output_file]" => "a10_%{+xxxx.MM.dd}"
      "[@metadata][output_pipelines]" => [file_output]
    }
  }
}
output {
  pipeline { send_to => [a10_processor]}
}
```
Make sure the path defined has a10 logs. This config creates an input source from the file path. Adds 2 metadata fields to specify the output file name and the output pipelines. Output pipelines is the name of pipelines where the logs would be sent after processing and enriching. This comes handy when we have multiple conditional outputs. After adding metadata fields this config forwards the event to `a10_processor` pipeline.

6. Update processor file.
Open _/usr/share/logstash/config/processors/syslog_log_audit_a10.proxy.conf_
in editor. Replace `VAR_PIPELINE_NAME` with `a10_processor`. All processors forward events to _enrichments_ pipeline.

7. Setup enrichment output.
Enrichment input _00_input.conf_ is defined as `enrichments` pipeline, so the logs from processors are recieved there. We have to configure output part.
Open _999_output.conf_ and replace the contents with below

```
output {
  if "file_output" in [@metadata][output_pipelines] {
    pipeline { send_to =>  "file_output" }
  }
}
```

8. Create output config
Create _/usr/share/logstash/config/outputs/file_out.conf_ and add below contents.
```
input {
  pipeline { address => file_output }
}
output {
  file {
    path => "/tmp/%{[@metadata][output_file]}"
  }
}
```

9. Create pipeline.yml
Replace _/usr/share/logstash/config/pipelines.yml_ with below contents.
```yml
################# ENRICH #################
- pipeline.id: enrichments
  path.config: "/usr/share/logstash/config/enrichments/{*}.conf"

################# OUTPUT #################
- pipeline.id: output
  path.config: "/usr/share/logstash/config/outputs/file_out.conf"

############### INPUTS & PROCESSORS ###############
- pipeline.id: a10_input
  path.config: "/usr/share/logstash/config/inputs/a10_input.conf"
- pipeline.id: a10_processor
  path.config: "/usr/share/logstash/config/processors/syslog_log_audit_a10.proxy.conf"
```

10. Start logstash
After logstash runs, you should see parsed logs in a file called _/tmp/a10_2021.10.27_ assuming you ran it on _Oct 27 2021_. Note that this is because we defined the output file name to be generated with date pattern by logstash. ("a10_%{+xxxx.MM.dd}" defined in input conf file)