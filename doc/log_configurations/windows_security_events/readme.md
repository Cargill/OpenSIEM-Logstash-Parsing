The "send_evtx_to_elk.ps1" is a short collection script that converts .evtx Windows Security Event logs into JSON
using Eric Zimmerman's evtx helper library:

https://github.com/EricZimmerman/evtx

After installing the evtx helper tool, the ps1 file does the following:
1. Copies the file to the "in_progess"" folder
2. Transforms the .evtx file into json
3. Puts the .json file into the "for_logstash_collection" folder
4. If successful, the program finally deletes the original .evtx and .json

This program is meant to be run on an ad-hoc basis. Our customers drop a file and then run the ps1 file (we turned into
an executable.)

Finally, we have Logstash running and listening to the "for_logstash_collection" folder. When a new file is copied there,
Logstash picks it up and forwards it where it needs to go. 