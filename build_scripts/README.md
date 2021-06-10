# Overview

### Directory Structure

```
.github                                        # github templates and workflows
build_scripts                                  # to build pipelines
config                                         # logstash configs
   |-- enrichments                             # enrichment configs
   |   |-- 00_input.conf                       # gets input for enrichment pipeline
   |   |-- *.conf                              # various enrichments
   |   |-- 999_output.conf                     # forwards to output pipelines
   |-- inputs                                  # input pipelines
   |   |-- azure                               
   |   |   |-- *.conf                          # azure eventhub inputs
   |   |-- kafka                               
   |   |   |-- 1_kafka_input_template.conf     # kafka input pipeline template
   |-- outputs                                 # output pipelines
   |   |-- elastic_output.conf                 # to elastic
   |   |-- s3_output.conf                      # to aws s3 bucket
   |-- processors                              # all parsing configs
   |   |-- *.conf                              
   |-- cisco_ios.json                          # used for cisco mnemonic translation
   |-- cisco_ios_facility_categories.csv       # used for cisco facility translation
   |-- iana_protocols.csv                      # used for iana protocol enrichment
   |-- kafka_jaas.conf                         # credential template used for kafka inputs
   |-- mitre_subtechnique.json                 # used by mitre enrichment
   |-- mitre_tatics.json                       # used by mitre enrichment
   |-- mitre_technique.json                    # used by mitre enrichment
   |-- pipelines.yml                           # pipelines.yml template
doc                                            
   |-- README.md                               
   |-- api_collection_programs                 # api log collection scripts
   |-- elastic_common_schema                   # modified schema
   |-- enrichments                             # doc explaining enrichments and how to disable
   |-- log_configurations                      # setup configs/script for log sources
   |-- templates                               # ecs templates for elastic
.gitignore                                     
CONTRIBUTING.md                                
LICENSE                                        
README.md                                      
```

----------

## Pipelines

We are using [pipeline to pipeline communication](https://www.elastic.co/guide/en/logstash/current/pipeline-to-pipeline.html) so that parsing logic can be modularized and the community can use it with ease.

**Logflow overview**

![openSIEM_logflow](https://github.com/Cargill/OpenSIEM-Logstash-Parsing/blob/master/doc/_resources/openSIEM_logflow.jpg)

Each input pipeline sends logs to its respective processor config pipeline (for example, McAfee or Symantec). All of the processor pipelines forward logs to the enrichment pipeline. Enrichments are applied sequentially and then the processed and enriched log is sent to its designated output(s). Log outputs also run sequentially by how they are defined in its [enrichment output section](https://github.com/Cargill/OpenSIEM-Logstash-Parsing/blob/master/config/enrichments/999_output.conf). The reason why we did not parallelize outputs is because if we have 3 outputs, then
  1. It would lead to increased memory need by 67% since each event is cloned for parallel processing. 
  2. It does not offer any practical parallelism advantages because if any of the downstream output pipelines are blocked, it chokes up the upper pipelines after its batch size is full.

**Log Flow in Detail**

![logflow_detailed](https://github.com/Cargill/OpenSIEM-Logstash-Parsing/blob/master/doc/_resources/logflow_detailed.jpg)



## Working

To process logs we need to create pipelines.yml file. We start with defining enrichments and output pipelines(common for all log sources). Then we add input and processor pipelines only for the logs we process. [settings.json](#settingsjson) is the file where we define the log sources we want to process. The file [general.json](#generaljson) provides specs such as how many nodes we need to process a particular log source. With these settings files and numerous environment variables, [generate_pipelines.py](#generate_pipelinespy) script generates a `pipelines.yml` for a specific Logstash node. If you want to process all configs on all Logstash nodes you just need to run the generate script with `num_indexers` set to 1 in `general.json`.

**Note:** We gather all the logs in Kafka through various log collection agents for temporary storage. We process logs from Kafka and Azure Eventhub and output to Elastic. You can tweak these configuration files and the pipeline generation script for your custom use cases, especially if they fall outside of our scope. We do not process all configs on all nodes because we faced performance problems associated with Kafka and Logstash kafka-input plugin.

### **Pipeline Generation**

The pipeline generation script (generate_pipelines.py):
 1. reads in settings files and environment variables
 2. takes the pipelines.yml from the config directory as a template
 3. adds input and processor pipelines to it, enabling the processing of those log sources.

**Note** The script also replaces variables defined in different conf files with values taken from environment. See environment variables section.

![pipeline_generation](https://github.com/Cargill/OpenSIEM-Logstash-Parsing/blob/master/doc/_resources/pipeline_generation.jpg)


Individual input files and the script are explained below.

### **pipelines.yml template**

Lies in the config directory root. See inline comments.

```yml
################# ENRICHMENTS #################
- pipeline.id: enrichments
  # default delay
  pipeline.batch.delay: 50
  # increased batch size because enrichments would be shared for all the processors
  pipeline.batch.size: 1000
  # increased worker threads
  pipeline.workers: 64
  # grabs all files ending with .conf and stiches into a single config and that's why their order matters
  path.config: "${LOGSTASH_HOME}/config/enrichments/{*}.conf"

################# OUTPUTS #################
- pipeline.id: elastic_output
  path.config: "${LOGSTASH_HOME}/config/outputs/elastic_output.conf"
  pipeline.batch.delay: 50
  pipeline.batch.size: 2000
  # A larger batch size because all logs go to elastic.
  # The batch is limited to 20MB by the plugin
  # pipeline.workers is set to number of processors
- pipeline.id: s3_output
  path.config: "${LOGSTASH_HOME}/config/outputs/s3_output.conf"
  pipeline.batch.delay: 50
  pipeline.batch.size: 2000
  # upload workers count and upload file queue size are configurable by the plugin
  # pipeline.workers is set to number of processors

############### INPUTS & PROCESSORS ###############
```
### **settings.json**

This is the most useful file which gives you flexibility to stitch an input, processor and output together. See inline comments.

```json
{
  "UNIQUE LOG SOURCE NAME (if using kafka input, kafka topic name is assigned this value. If using other inputs this should be the input file name.)": {
    "log_source": "must be same as parent key (UNIQUE LOG SOURCE NAME)",
    "config": "PROCESSOR CONFIG FILE NAME WITHOUT .conf",
    "elastic_index": "INDEX NAME FOR ELASTIC OUTPUT PLUGIN (date patterns can also be used)",
    "ignore_enrichments": ["THESE ARE TAGS THAT ARE ADDED AND ENRICHMENTS CHECK FOR THEM"],
    "output_list": [
      "LIST OF THE OUTPUTS TO SEND PROCESSED LOGS TO"
    ],
    "kafka_input": {
      "codec": "CODEC FOR KAFKA INPUT LOGS (default is plain if not specified)"
    }
  },
  ...
}
```

### **general.json**

This adds capability to process a config explicitly on logstash nodes. Logs can be restricted to be run in only non dev environments. Json file is explained below.

```json
{
    "num_indexers" : NUMBER OF LOGSTASH NODES IN THE CLUSTER,
    "prod_only_logs": [
        "LIST OF LOGS WHICH WON'T BE ADDED IN PIPELINES IF ENVIRONMENT VARIABLE DEPLOY_ENV=dev (list should be made of log_source values from settings.json)"
    ],
    "processing_config" : {
        "LOG_SOURCE VALUE FROM SETTINGS.JSON" : {
            "kafka_partitions" : NUMBER OF KAFKA PARTITIONS FOR THIS PARTICULAR LOG SOURCE(this valuse is used to generate number of workers for the kafka input plugin i.e. kafka_partitions/nodes),
            "nodes" : NUMBER OF NODES ON WHICH THIS LOG SOURCE WOULD BE EXPLICITLY PROCESSED
        },
        ...
    }
}
```

### **pipelines and code**

Each input config looks like this
```ruby
input {
  #... more details here
}
filter {
  mutate {
    # VAR_CUSTOM_FIELDS
  }
}
output {
  pipeline { send_to => [VAR_PIPELINE_NAME]}
  # notice the same pipeline name variable in both input config and the processor config
}
```

_VAR_CUSTOM_FIELDS_ is replaced with add_field and add_tag section taken from `settings.json` so an example input becomes like this

```ruby
input {
  #... more details here
}
filter {
  mutate {
    add_field => {
      # log source name. Not necessarily used.
      "[@metadata][index]" => "checkpoint"
      # config name that would process this input. This tag is not used though.
      "[@metadata][config]" => "syslog_log_audit_checkpoint.fw"
      # Is used for elastic output
      "[@metadata][output]" => "checkpoint_%{+xxxx.MM.dd}"
      # determines where to output logs to
      "[@metadata][output_pipelines]" => [elastic_output,s3_output]
    }
    # tags are added from ignore_enrichments section in the settings.json file
    # these are checked by enrichments to apply or ignore
    add_tag => [ "disable_misp_enrichment" ]
    }
  }
}
output {
  pipeline { send_to => [VAR_PIPELINE_NAME]}
  # notice the same pipeline name variable in both input config and the processor config
}
```

Each processor looks like this

```ruby
input {
  pipeline {
    address => VAR_PIPELINE_NAME
    # when pipeline name variable is replaced with same value in both input and processor configs,
    # logs forwarded from the input pipeline are received here
  }
}
filter {
  #... processing logic goes here
}
output {
  pipeline { send_to => [enrichments] }
  # notice that each processor forwards the event to `enrichments` pipeline
}
```

Enrichment config is splitted in multiple ordered files. When it is loaded in logstash it looks like this

```ruby
input {
  pipeline { address => enrichments }
  # hardcoded name for pipeline
  # so events forwarded by processor config are received here
}
filter {
  # enrichments are applied in sequential order
  # enrichment 1
  # enrichment 2
  # ...
}
output {
  # [@metadata][output_pipelines] field becomes very important here. It was added in the input config via VAR_CUSTOM_FIELDS
  # These are hardcode rules so if you want to add or remove outputs you need to change here
  if "elastic_output" in [@metadata][output_pipelines] {
    pipeline { send_to =>  "elastic_output" }
  }
  if "s3_output" in [@metadata][output_pipelines] {
    pipeline { send_to =>  "s3_output" }
  }
}
```

An output config e.g. elastic out looks like this

```ruby
input {
  pipeline { address => elastic_output }
  # name of the pipeline `elastic_output` is hardcoded
}
output {
  elasticsearch {
    # ... more details here
  }
}
```

### **generate_settings.py**

Generates a sample settings.json file with all processors and dummy kafka inputs so that all configs can be tested for syntax errors in the test environment.

### **generate_pipelines.py**

This assumes that you download this repo in some other directory and run logstash in `/usr/share/logstash` directory. You run this script from the base directory. And when it runs successfully it you can copy over the config directory to `/usr/share/logstash`. A bash command would like this
```sh
cp -r config/* /usr/share/logstash/config/
```
When the script runs, it does the following:
1. Generate required files e.g. 
    - kafka input files from template
    - if a processor is shared between multiple inputs, a copy is created with log_source name(from settings.json) to be able to map an input pipeline to a processor pipeline one to one. e.g. If you have regional collection of a log source foo, and would like to keep those regional logs in different indices. In this case, the parsing of all regions of "foo" would be the same, despite having different inputs, so each of these regional log sources (foo_region1, foo_region2, etc) would be defined in settings.json with the same processing config (foo_processor). The script would make a copy for each of these log sources so each input can get it's own processor.
    ```diff
    ! Note that, it treats every log source as kafka input if it's not azure. You need to override that logic if you want to work with other inputs.
    ```
2. Replace variables starting with VAR_ e.g.
    - in input configs
    - in output files
    - in enrichments (misp, dns)
    ```diff
    + This is where a parsing config is tied to an input config as VAR_PIPELINE_NAME in both are replaced with actual common value. And the final output and the enrichments to ignore are also decided at this step.
    ```
3. Replace variables in Kafka jaas file with actual creds
4. Variable VAR_HOSTNAME in logstash _log4j.properties_ file is substituted with current hostname. This is handy for identifying logstash logs if you add the variable in a logging pattern. This step is optional. 
4. Generate pipelines.yml file.
    - Based on the volume of log sources we name them like [NAME OF THE LOGSOURCE]_daily, [NAME OF THE LOGSOURCE]_weekly and [NAME OF THE LOGSOURCE]_monthly
    - So based on this logic this script sets the number of pipeline workers as 8, 4 and 2 respectively. If the log source is defined in processing_config section of general.json workers is set to 16.
5. Checks if changes were made between deployed directory `/usr/share/logstash` and the current directory. And changes the file `/data/should_redeploy` file. A program can look for changes on this file and can trigger redeploy on logstash.

### Environment Variables 

The [generate pipeline script](generate_pipeline.py) uses environment variables which are mandatory to set. Setup your environment as following.

```
DEPLOY_ENV: test/dev/prod
MY_INDEX: index of this logtash node in the cluster
SUB_MY_IP: some unique value added to plugin ids
ELASTIC_USER: elastic username
ELASTIC_PASSWORD: elastic password
ELASTIC_CONNECTION_STRING: '"127.0.0.1:9200", "127.0.0.2:9200"' (elastic workers)
KAFKA_CONNECTION_STRING: kafkahost:9000 (kafka address)
KAFKA_USER: kafka username for jaas file
KAFKA_PASSWORD: kafka password for jaas file
RACK_ID: kafka rack id
S3_BUCKET_NAME: bucket name to send logs to for s3 out plugin
LOGSTASH_API_SECRET: '{"azure_audit_conn" : "Endpoint=sb://dummy.com/;SharedAccessKeyName=dum;SharedAccessKey=key=;EntityPath=path",  "azure_operational_conn" : "Endpoint=sb://dummy.com/;SharedAccessKeyName=dum;SharedAccessKey=key=;EntityPath=path",  "azure_signin_conn" : "Endpoint=sb://dummy.com/;SharedAccessKeyName=dum;SharedAccessKey=key=;EntityPath=path",  "azure_o365_conn" : "Endpoint=sb://dummy.com/;SharedAccessKeyName=dum;SharedAccessKey=key=;EntityPath=path",  "azure_tcs_security_conn" : "Endpoint=sb://dummy.com/;SharedAccessKeyName=dum;SharedAccessKey=key=;EntityPath=path",  "azure_o365_dlp_conn" : "Endpoint=sb://dummy.com/;SharedAccessKeyName=dum;SharedAccessKey=key=;EntityPath=path",  "azure_audit_consumer" : "azure_audit_consumer",  "azure_operational_consumer" : "azure_operational_consumer",  "azure_signin_consumer" : "azure_signin_consumer",  "azure_o365_consumer" : "azure_o365_consumer",  "azure_tcs_security_consumer" : "azure_o365_consumer",  "azure_o365_dlp_consumer" : "cg-production-operation",  "azure_storage_conn" : "DefaultEndpointsProtocol=https;AccountName=dummyname;AccountKey=key;EndpointSuffix=core.windows.net",  "azure_atp_consumer" : "azure_atp_consumer",  "azure_atp_conn" : "Endpoint=sb://dummy.com/;SharedAccessKeyName=dum;SharedAccessKey=key=;EntityPath=path",  "memcached_address" : "\"127.0.0.1\",\"127.0.0.2\"",  "dns_server" : "\"127.0.0.1\",\"127.0.0.2\""}'
```

The last variable, LOGSTASH_API_SECRET is used to capture additional values that are not explicitly codified.
```diff
! Due to a current issue you have to set all with dummy values else script breaks. 
```
Explaining these below.

```json
{
  "azure_audit_conn" : "ENDPOINT FOR AZURE AUDIT",
  "azure_operational_conn" : "ENDPOINT FOR AZURE OPERATIONAL",
  "azure_signin_conn" : "ENDPOINT FOR AZURE SIGNIN",
  "azure_o365_conn" :"ENDPOINT FOR AZURE O365",
  "azure_tcs_security_conn" : "ENDPOINT FOR AZURE TCS",
  "azure_o365_dlp_conn" : "ENDPOINT FOR AZURE DLP",
  "azure_atp_conn" : "ENDPOINT FOR AZURE ATP",
  "azure_audit_consumer" : "CONSUMER NAME FOR AZURE AUDIT",
  "azure_operational_consumer" : "CONSUMER NAME FOR AZURE OPERATIONAL",
  "azure_signin_consumer" : "CONSUMER NAME FOR AZURE SIGNIN",
  "azure_o365_consumer" : "CONSUMER NAME FOR AZURE O365",
  "azure_tcs_security_consumer" : "CONSUMER NAME FOR AZURE TCS",
  "azure_o365_dlp_consumer" : "CONSUMER NAME FOR DLP",
  "azure_atp_consumer" : "CONSUMER NAME FOR AZURE ATP",
  "azure_storage_conn" : "STORAGE CONNECTION FOR AZURE",
  "memcached_address" : "SERVERS FOR THE MISP ENRICHMENT AND MISP PROCESSOR CONFIG e.g. \"127.0.0.1\",\"127.0.0.2\"",
  "dns_server" : "SERVERS FOR THE DNS ENRICHMENT e.g. \"127.0.0.1\",\"127.0.0.2\""
}
```

## Getting started

These files need to exist for Logstash to load the geoip enrichment.
```
/mnt/s3fs_geoip/GeoLite2-City.mmdb
/mnt/s3fs_geoip/GeoLitePrivate2-City.mmdb
```
Either remove geoip enrichment file if you don't want to use it or just touch these files if you are disabling the enrichment from settings.json. If you want to use this enrichment you need to add geoip files. For more information see [using the Geoip filter](https://www.elastic.co/guide/en/logstash/current/plugins-filters-geoip.html).

- Create _/data_ dir as the script uses it to write logs and create a change file.
- Update settings.json file.
- Update general.json file.
- Set the environment variables as [above](#environment-variables).
- Run  python build_scripts/generate_pipeline.py
- Copy over the config directory to `/usr/share/logstash` and start logstash.

An example can be found in github [workflow](https://github.com/Cargill/OpenSIEM-Logstash-Parsing/blob/master/.github/workflows/main.yml#L90).

In the workflow, you will also find script to install logstash and add required plugins to it.
