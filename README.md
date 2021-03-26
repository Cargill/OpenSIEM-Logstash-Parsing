# LogIndexer Pipeline
Logstash Parsing Configurations for Elastisearch SIEM and OpenDistro for Elasticsearch SIEM


## Why this project exists
The overhead of implementing Logstash parsing and applying Elastic Common Schema (ECS) across audit, security, and 
system logs can be a large drawback when using Elasticsearch as a SIEM (Security Incident and Event Management). The 
Cargill SIEM team has spent significant time on developing quality Logstash parsing processors for many well-known log
vendors and wants to share this work with the community. In addition to Logstash processors, we have also included log 
collection programs for API-based log collection, as well as the setup scripts used to generate our [pipeline-to-pipeline
architecture](https://www.elastic.co/guide/en/logstash/current/pipeline-to-pipeline.html). 


## Quick start Instructions
"Quick start" mostly depends on how your Logstash configuration is set up. If you have your own setup already established,
it might be best to use the processors that apply to your organization's log collection (found in the "config" directory). 
If you are seeking to use the architecture in this repo, consult the README found in the build_scripts directory.
*We will be adding an elaborate setup guide soon.*

## Contributions
We welcome and encourage individual contributions to this repo. Please see the Contribution.md guide in the root of the repo.
Please note that we reserve the right to close pull requests or issues that appear to be out of scope for our project, or 
for other reasons not specified.


## Questions, Comments & Expected Level of Attention
Please create an issue and someone will **try** to respond to your issue within 5 business days. However, it should be
noted that while we will try revisit the repository semi-regularly, we are not held beholden to this response time (life happens).
We welcome other individuals' answers and input as well.

 
## Licensing
Apache-2.0
