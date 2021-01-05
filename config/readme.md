If we combine multiple files in one pipeline definition that creates one config.

Generate separate input files for individual log sources or just add topic names?
    If we just add multiple topics, a new consumer group has to be created and would reprocess existing logs.

Have to set `queue.drain` to true in the pipeline definition in order to clear the queue before shutodown. This is important because config may change node on re-deployment.

`pipeline.workers` setting:
    The number of workers that will, in parallel, execute the filter and output stages of the pipeline.
    https://www.elastic.co/guide/en/logstash/current/logstash-settings-file.html

All inputs would have custom fields
```
add_field => {
  "[@metadata][index]" => ""
  "[@metadata][config]" => ""
  "[@metadata][output]" => ""
}
```

the values would be loaded from a setting file
```
{
    "name.index" : "wef_na.dc",
    "name.config" : "wef",
    "name.output" : "wef_na.dc",
    "name.ignore_enrichments": [disable_enrichments]
},
{
    "name.index" : "wef_ap.dc",
    "name.config" : "wef",
    "name.output" : "wef_ap.dc"
}
```

the outputs can be used as below with the above defined fields
```
elasticsearch {
  id => "beats-pipeline"
  hosts => ["https://siem-elasticsearch-01:9200"]
  ilm_enabled => true
  manage_template => false
  index => "%{[@metadata][beat]}-%{[@metadata][version]}"
  pipeline => "%{[@metadata][pipeline]}"
  user => beats_ingest
  password => *******
  cacert => "/etc/logstash/ca.crt"
  ssl => true
}
```