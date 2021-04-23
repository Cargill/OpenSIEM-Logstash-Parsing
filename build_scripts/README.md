# Setup
The [genreate pipeline script](generate_pipeline.py) uses environment variables which are mandatory to set. Setup your environment as following.
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
LOGSTASH_API_SECRET: '{"azure_audit_conn" : "Endpoint=sb://dummy.com/;SharedAccessKeyName=dum;SharedAccessKey=key=;EntityPath=path",  "azure_operational_conn" : "Endpoint=sb://dummy.com/;SharedAccessKeyName=dum;SharedAccessKey=key=;EntityPath=path",  "azure_signin_conn" : "Endpoint=sb://dummy.com/;SharedAccessKeyName=dum;SharedAccessKey=key=;EntityPath=path",  "azure_o365_conn" : "Endpoint=sb://dummy.com/;SharedAccessKeyName=dum;SharedAccessKey=key=;EntityPath=path",  "azure_tcs_security_conn" : "Endpoint=sb://dummy.com/;SharedAccessKeyName=dum;SharedAccessKey=key=;EntityPath=path",  "azure_o365_dlp_conn" : "Endpoint=sb://dummy.com/;SharedAccessKeyName=dum;SharedAccessKey=key=;EntityPath=path",  "azure_audit_consumer" : "azure_audit_consumer",  "azure_operational_consumer" : "azure_operational_consumer",  "azure_signin_consumer" : "azure_signin_consumer",  "azure_o365_consumer" : "azure_o365_consumer",  "azure_tcs_security_consumer" : "azure_o365_consumer",  "azure_o365_dlp_consumer" : "cg-production-operation",  "azure_storage_conn" : "DefaultEndpointsProtocol=https;AccountName=dummyname;AccountKey=key;EndpointSuffix=core.windows.net",  "nc4_api_key" : "nc4_api_key",  "nc4_api_uri" : "nc4_api_uri",  "azure_atp_consumer" : "azure_atp_consumer",  "azure_atp_conn" : "Endpoint=sb://dummy.com/;SharedAccessKeyName=dum;SharedAccessKey=key=;EntityPath=path",  "memcached_address"  :"\"127.0.0.1\",\"127.0.0.2\""}'
```

More documentation to follow.