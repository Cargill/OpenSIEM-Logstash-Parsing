# Overview

### Directory Structure

```
.github                                        #github templates and workflows
build_scripts                                  #to build pipelines
config                                         #logstash configs
   |-- enrichments                             #enrichment configs
   |   |-- 00_input.conf                       #gets input for enrichment pipeline
   |   |-- *.conf                              #various enrichments
   |   |-- 999_output.conf                     #forwards to output pipelines
   |-- inputs                                  #input pipelines
   |   |-- azure                               
   |   |   |-- *.conf                          
   |   |-- kafka                               
   |   |   |-- 1_kafka_input_template.conf     #kafka input pipeline template
   |-- outputs                                 #output pipeline
   |   |-- elastic_output.conf                 #to elastic
   |   |-- nc4_output.conf                     #to nc4 API
   |   |-- s3_output.conf                      #to aws s3 bucket
   |-- processors                              #all parsing configs
   |   |-- *.conf                              
   |-- cisco_ios.json                          #used for cisco mnemonic translation
   |-- cisco_ios_facility_categories.csv       #used for cisco facility translation
   |-- iana_protocols.csv                      #used for iana protocol enrichment
   |-- kafka_jaas.conf                         #credential template used for kafka inputs
   |-- mitre_subtechnique.json                 #used by mitre enrichment
   |-- mitre_tatics.json                       #used by mitre enrichment
   |-- mitre_technique.json                    #used by mitre enrichment
   |-- pipelines.yml                           #pipelines.yml template
doc                                            
   |-- README.md                               
   |-- api_collection_programs                 #api log collection scripts
   |-- elastic_common_schema                   #modified schema
   |-- enrichments                             #doc explaining enrichments and how to disable
   |-- log_configurations                      #setup configs/script for log sources
   |-- templates                               #ecs templates for elastic
.gitignore                                     
CONTRIBUTING.md                                
LICENSE                                        
README.md                                      
```

----------

## Pipelines

We are using pipeline to pipeline communication [pipeline-to-pipeline
architecture](https://www.elastic.co/guide/en/logstash/current/pipeline-to-pipeline.html) so that parsing logic can be modularised and community can use it with ease. To process logs we need to create pipelines.yml file. We start with defining enrichments and output pipelines(common for all log sources). Then we add input and processor pipelines only for the logs we process. [settings.json](#settingsjson) is the file where we define the log sources we want to process. We have [general.json](#generaljson) file to specify more specifics like on how many nodes we need to process a particular log source. With these setting files and numerous environment variables [generate_pipelines.py](#generate_pipelinespy) script generates a `pipelines.yml` for a specific node. If you want to process all configs on all nodes you just need to run the generate script with `num_indexers` set to 1 in `general.json`.

We do not process all configs on all nodes because of performance problems associated with kafka and logstash.

Logflow overview:

![openSIEM_logflow](https://user-images.githubusercontent.com/6766061/120641277-0948cc80-c491-11eb-933e-8e07ac90ab01.jpg)

Logflow detailed:

![logflow_detailed](https://user-images.githubusercontent.com/6766061/120799243-1da5cb80-c55c-11eb-853f-5a7048bda591.jpg)


Each input pipeline sends logs to its respective processor config pipeline. All the processor pipelines forward logs to the enrichment pipeline. Enrichments are applied sequentially and then the processed and enriched log is send to designated outputs.


## Working

The pipeline generation script reads settings json files and the environment variables, takes the pipelines.yml from the config directory as a template and adds input and processor pipelines to it enabling processing of those log sources.

![pipeline_generation](https://user-images.githubusercontent.com/6766061/120667299-fb07aa00-c4aa-11eb-9e58-fb1b0c6b9dd0.jpg)


### pipelines.yml template

Lies in the config directory root. Added below with detailed comments.
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
  # pipeline.workers is set to number of processors
- pipeline.id: s3_output
  path.config: "${LOGSTASH_HOME}/config/outputs/s3_output.conf"
  pipeline.batch.delay: 50
  pipeline.batch.size: 2000
  # pipeline.workers is set to number of processors
- pipeline.id: nc4_output
  path.config: "${LOGSTASH_HOME}/config/outputs/nc4_output.conf"
  # it's a low volume api so not wasting resources
  pipeline.workers: 1

############### INPUTS & PROCESSORS ###############
```
## settings.json

```
{
  "UNIQUE LOG SOURCE NAME (if using kafka input, kafka topic name is assigned this value)": {
    "log_source": "UNIQUE LOG SOURCE NAME (if using kafka input, kafka topic name is assigned this value)",
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

## generate_settings.py
Generates a sample settings.json file so that all configs can be tested for syntax errors in the test environment.

## general.json


## generate_pipelines.py


# Setup
The [generate pipeline script](generate_pipeline.py) uses environment variables which are mandatory to set. Setup your environment as following.
If you are not using azure configs then please delete the .conf files in [azure input directory](../config/inputs/azure).

```
DEPLOY_ENV: test
LOGSTASH_SERVERS: 127.0.0.1
MY_INDEX: '1'
SUB_MY_IP: abc
ELASTIC_USER: elastic_user
ELASTIC_PASSWORD: elastic_pass
ELASTIC_CONNECTION_STRING: '"127.0.0.1:9200", "127.0.0.2:9200"'
KAFKA_CONNECTION_STRING: kafkahost:9000
KAFKA_USER: kafka_uname
KAFKA_PASSWORD: kafka_pwd
RACK_ID: some_id
S3_BUCKET_NAME: some_name
LOGSTASH_API_SECRET: '{"azure_audit_conn" : "Endpoint=sb://dummy.com/;SharedAccessKeyName=dum;SharedAccessKey=key=;EntityPath=path",  "azure_operational_conn" : "Endpoint=sb://dummy.com/;SharedAccessKeyName=dum;SharedAccessKey=key=;EntityPath=path",  "azure_signin_conn" : "Endpoint=sb://dummy.com/;SharedAccessKeyName=dum;SharedAccessKey=key=;EntityPath=path",  "azure_o365_conn" : "Endpoint=sb://dummy.com/;SharedAccessKeyName=dum;SharedAccessKey=key=;EntityPath=path",  "azure_tcs_security_conn" : "Endpoint=sb://dummy.com/;SharedAccessKeyName=dum;SharedAccessKey=key=;EntityPath=path",  "azure_o365_dlp_conn" : "Endpoint=sb://dummy.com/;SharedAccessKeyName=dum;SharedAccessKey=key=;EntityPath=path",  "azure_audit_consumer" : "azure_audit_consumer",  "azure_operational_consumer" : "azure_operational_consumer",  "azure_signin_consumer" : "azure_signin_consumer",  "azure_o365_consumer" : "azure_o365_consumer",  "azure_tcs_security_consumer" : "azure_o365_consumer",  "azure_o365_dlp_consumer" : "cg-production-operation",  "azure_storage_conn" : "DefaultEndpointsProtocol=https;AccountName=dummyname;AccountKey=key;EndpointSuffix=core.windows.net",  "nc4_api_key" : "nc4_api_key",  "nc4_api_uri" : "nc4_api_uri",  "azure_atp_consumer" : "azure_atp_consumer",  "azure_atp_conn" : "Endpoint=sb://dummy.com/;SharedAccessKeyName=dum;SharedAccessKey=key=;EntityPath=path",  "memcached_address" : "\"127.0.0.1\",\"127.0.0.2\"",  "dns_server" : "\"127.0.0.1\",\"127.0.0.2\""}'
```

More documentation to follow.

## FAQ
  1. How to add/remove an output pipeline?
  2. How to add/remove an input pipeline?
  3. How to use only selected log processor configs?
  4. How to disable an enrichment?
  5. Why is an enrichment loaded (and breaks if it does not finds dependent files e.g. geoip) even if I'm disabling it?