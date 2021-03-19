Import-Module WebAdministration

$truncateSize = 52428800
$maxCustomFieldLength = 4096
$maxLogLineLength = 65536
### Get IIS Major verion
$iis_ver =""
$iis_ver_MajorVersion = [String](get-itemproperty HKLM:\SOFTWARE\Microsoft\InetStp\  | select MajorVersion).MajorVersion
$iis_ver_MinorVersion = [String](get-itemproperty HKLM:\SOFTWARE\Microsoft\InetStp\  | select MinorVersion).MinorVersion
$iis_ver = $iis_ver_MajorVersion + "." + $iis_ver_MinorVersion
$LogPath = "" 
## Per Site settings
    if (Test-Path -Path d:) {
        $LogPath = "D:\Logs"
    } else {
        $LogPath = "C:\Logs"
    }

if ($iis_ver -ge 8.5 ) {

# default site     

    ## default IIS logging directory:
        $iis_path = $LogPath + "\iis"
      if ( (Get-WebConfigurationProperty -Filter "System.Applicationhost/Sites/SiteDefaults/logfile" -name "directory.Value") -ne $iis_path ) {
          Set-WebConfigurationProperty -Filter "System.Applicationhost/Sites/SiteDefaults/logfile" -name "directory" -value $iis_path
     }

    ## To change the logging type to w3c
    
        if ( (Get-WebConfigurationProperty -filter "system.applicationHost/sites/siteDefaults/logFile" -name "logFormat.Value" ) -ne "W3C") {
            Set-WebConfigurationProperty -filter "system.applicationHost/sites/siteDefaults/logFile" -name "logFormat" -value "W3C"
        }
   # To change logging frequency:
        if ( (Get-WebConfigurationProperty -Filter "System.Applicationhost/Sites/SiteDefaults/logFile" -name "period.Value" ) -ne "MaxSize") {
           Set-WebConfigurationProperty -filter "system.applicationHost/sites/siteDefaults/logFile" -name "period" -value "MaxSize"
        }
   # set to w3c log file type
        if ( (get-WebConfigurationProperty -filter "system.applicationHost/sites/siteDefaults/logFile" -name "logTargetW3C.Value" ) -ne "File") {
            Set-WebConfigurationProperty -filter "system.applicationHost/sites/siteDefaults/logFile" -name "logTargetW3C" -value "File"
        }
   # log length
        if ( (get-WebConfigurationProperty -filter "system.applicationHost/sites/siteDefaults/logFile" -name "maxLogLineLength.Value" ) -ne $maxLogLineLength ) {
           Set-WebConfigurationProperty -filter "system.applicationHost/sites/siteDefaults/logFile" -name "maxLogLineLength" -value $maxLogLineLength
     }
        # Include logSiteId (may make log format different
     if ( (get-WebConfigurationProperty -filter "system.applicationHost/sites/siteDefaults/logFile" -name "logSiteId.Value" ) -ne "True" ) {
           Set-WebConfigurationProperty -filter "system.applicationHost/sites/siteDefaults/logFile" -name "logSiteId" -value "True"
     }
     if ( (get-WebConfigurationProperty -filter "system.applicationHost/sites/siteDefaults/logFile/customFields" -name "maxCustomFieldLength.value" ) -ne $maxCustomFieldLength ) {
           Set-WebConfigurationProperty -filter "system.applicationHost/sites/siteDefaults/logFile/customFields" -name "maxCustomFieldLength" -value $maxCustomFieldLength
     }      
     # set to logformat to utf-8
     if ( (get-WebConfigurationProperty -filter "system.applicationHost/log" -name "logInUTF8.Value" ) -ne "True") {
           Set-WebConfigurationProperty -filter "system.applicationHost/log" -name "logInUTF8" -value "True"
     }
      # Log truncateSize
     if ( (get-WebConfigurationProperty -filter "system.applicationHost/sites/siteDefaults/logFile" -name "truncateSize.Value" ) -ne $truncateSize ) {
           Set-WebConfigurationProperty -filter "system.applicationHost/sites/siteDefaults/logFile" -name "truncateSize" -value $truncateSize
     }
     # enable logging
     if ( (get-WebConfigurationProperty -filter "system.applicationHost/sites/siteDefaults/logFile" -name "enabled.Value" ) -ne "True" ) {
           Set-WebConfigurationProperty -filter "system.applicationHost/sites/siteDefaults/logFile" -name "enabled" -value "True"
     }
     if ( (Get-WebConfigurationProperty -filter "system.applicationHost/log" -name "centralLogFileMode" ) -ne "Site" ) {
           Set-WebConfigurationProperty -filter "system.applicationHost/log" -name "centralLogFileMode" -value "Site"
     }
     
    ### Set fields for site default
        $fields = @("Date", "Time", "ClientIP", "UserName", "SiteName", "ComputerName", "ServerIP", "ServerPort", "Method", "UriStem", "UriQuery", "HttpStatus", "HttpSubStatus", "Win32Status", "BytesSent", "BytesRecv", "TimeTaken", "ProtocolVersion", "Host", "UserAgent", "Cookie", "Referer")
        $default_fields = GET-WebConfigurationProperty -Filter System.Applicationhost/Sites/SiteDefaults/logfile -Name LogExtFileFlags
        $missing = 0
    $fields | ForEach-Object {
        if (($default_fields -split ",") -notcontains $_) {
            $missing++
        }
    }
    if ($missing -gt 0 ) {
        Set-WebConfigurationProperty -Filter System.Applicationhost/Sites/SiteDefaults/logfile -Name LogExtFileFlags -Value "Date,Time,ClientIP,UserName,SiteName,ComputerName,ServerIP,ServerPort,Method,UriStem,UriQuery,HttpStatus,HttpSubStatus,Win32Status,BytesSent,BytesRecv,TimeTaken,ProtocolVersion,Host,UserAgent,Cookie,Referer"
    }
    ### X-Forwarded-For Site Default 
     $SiteLogFileCustom = Get-WebConfigurationProperty -Filter "System.Applicationhost/Sites/SiteDefaults/logFile/customFields" -Name 'Collection'

     if ($SiteLogFileCustom.logFieldName -notmatch 'X-Forwarded-For') {
        Set-WebConfigurationProperty -filter "system.applicationHost/sites/siteDefaults/logFile/customFields" -name "." -value @{logFieldName='X-Forwarded-For';sourceName='X-Forwarded-For';sourceType='RequestHeader'}
            }

  ### centralW3CLogFile
     if ( (get-WebConfigurationProperty -filter "system.applicationHost/log/centralW3CLogFile" -name "enabled.value" ) -ne "True" ) {
           Set-WebConfigurationProperty -filter "system.applicationHost/log/centralW3CLogFile" -name "enabled" -value "True"
     }
     $w3c_path = $LogPath + "\w3c"
     if ( (get-WebConfigurationProperty -filter "system.applicationHost/log/centralW3CLogFile" -name "directory.value" ) -ne $w3c_path ) {
           Set-WebConfigurationProperty -filter "system.applicationHost/log/centralW3CLogFile" -name "directory" -value $w3c_path
     }
     if ( (get-WebConfigurationProperty -filter "system.applicationHost/log/centralW3CLogFile" -name "period.value" ) -ne "Weekly" ) {
           Set-WebConfigurationProperty -filter "system.applicationHost/log/centralW3CLogFile" -name "period" -value "Weekly"
     }  
     if ( (get-WebConfigurationProperty -filter "system.applicationHost/log/centralW3CLogFile" -name "truncateSize.value" ) -ne 20971521 ) {
           Set-WebConfigurationProperty -filter "system.applicationHost/log/centralW3CLogFile" -name "truncateSize" -value 20971521
     }  
     if ( (get-WebConfigurationProperty -filter "system.applicationHost/log/centralW3CLogFile" -name "localTimeRollover.value" ) -ne "True" ) {
           Set-WebConfigurationProperty -filter "system.applicationHost/log/centralW3CLogFile" -name "localTimeRollover" -value "True"
     }
 ### Set logging on exsisting sites   
    foreach($site in (dir iis:\sites\*)) {
       
        # Encooding
        if ( (Get-WebConfigurationProperty -filter "system.applicationHost/sites/site[@name='$($site.Name)']/logFile" -name "directory.Value.encoding )" ) -ne "UTF-8") {
            Set-WebConfigurationProperty -filter "system.applicationHost/sites/site[@name='$($site.Name)']" -Name loencoding -Value UTF-8
        }

      ### add fields if any missing to sites                
        $missing = 0
        $site_fields = Get-WebConfigurationProperty -filter "system.applicationHost/sites/site[@name='$($site.Name)']/logFile" -Name 'LogExtFileFlags'
        $fields | ForEach-Object {
            if (($default_fields -split ",") -notcontains $_) {
                $missing++
            }
        }
        if ($missing -gt 0 ) {
            Set-WebConfigurationProperty -filter "system.applicationHost/sites/site[@name='$($site.Name)']/logFile" -Name 'LogExtFileFlags' -Value " Date,Time,ClientIP,UserName,SiteName,ComputerName,ServerIP,ServerPort,Method,UriStem,UriQuery,HttpStatus,HttpSubStatus,Win32Status,BytesSent,BytesRecv,TimeTaken,ProtocolVersion,Host,UserAgent,Cookie,Referer"
        }

    ### Varify X-Forwarded-For foreach site
   
    
        $SiteLogFileCustom = Get-WebConfigurationProperty -filter "system.applicationHost/sites/site[@name=$($site.Name)']/logFile/customFields" -Name 'Collection'
        Get-WebConfigurationProperty -filter "system.applicationHost/sites/site/logFile/customFields" -Name 'Collection'
        $SiteLogFileCustom = Get-WebConfigurationProperty -filter "system.applicationHost/sites/siteDefaults/logFile/customFields" -name "."
        Add-WebConfigurationProperty -pspath 'MACHINE/WEBROOT/APPHOST' -filter "system.applicationHost/sites/siteDefaults/logFile/customFields" -name "Collection" -value @{logFieldName='X-Forwarded-For';sourceName='X-Forwarded-For';sourceType='RequestHeader'}

        $SiteLogFileCustom.Attributes 
        if ($SiteLogFileCustom.logFieldName -match 'X-Forwarded-For') {
            write-output "Match!"
        } else {
            Set-WebConfigurationProperty -filter "system.applicationHost/sites/site[@name='$site.name']/logFile/customFields" -name "." -value @{logFieldName='X-Forwarded-For';sourceName='X-Forwarded-For';sourceType='RequestHeader'}
        }
    }
###### IIS 7-8.4 ####
    } elseif ($iis_ver -ge 7 ) {

# Install advanced logging add on
# msiexec.exe /i C:\data\AdvancedLogging64.msi /passive /log C:\Data\advancedlogging.log
# Start-Sleep -Seconds 10

#grant permission to IIS_IUSERS group to the log directory
    $Command = "icacls" + $FilePath + " /grant BUILTIN\IIS_IUSRS:(OI)(CI)RXMW"
    cmd.exe /c $Command


# Disables http logging module

    $dontlog = GET-WebConfigurationProperty -Filter system.webServer/httpLogging -PSPath machine/webroot/apphost -Name dontlog
    if ( $dontlog.Value -ne 'True') { 
        Set-WebConfigurationProperty -Filter system.webServer/httpLogging -PSPath machine/webroot/apphost -Name dontlog -Value true
    }
# Enable Advanced Logging
    $advancedLogging = Get-WebConfigurationProperty -Filter system.webServer/advancedLogging/server -PSPath machine/webroot/apphost -Name enabled
    if ( $advancedLogging.Value -ne 'True') {
        Set-WebConfigurationProperty -Filter system.webServer/advancedLogging/server -PSPath machine/webroot/apphost -Name enabled -Value true
    }
# Set log directory at server level
    $directory = Get-WebConfigurationProperty -Filter system.applicationHost/advancedLogging/serverLogs -PSPath machine/webroot/apphost -Name directory
    if ( $directory.Value -ne  $LogPath) {
        Set-WebConfigurationProperty -Filter system.applicationHost/advancedLogging/serverLogs -PSPath machine/webroot/apphost -Name directory -Value $LogPath
    }

# Set log directory at site default level
    $directory_def = Get-WebConfigurationProperty -Filter system.applicationHost/sites/siteDefaults/advancedLogging -PSPath machine/webroot/apphost -Name directory
    if ( $directory_def.Value -ne  $LogPath) {
        Set-WebConfigurationProperty -Filter system.applicationHost/sites/siteDefaults/advancedLogging -PSPath machine/webroot/apphost -Name directory -Value $LogPath
    }



# Adds AWS ELB aware X-Forwarded-For logging field
    $X_Forwarded_For = get-WebConfiguration "system.webServer/advancedLogging/server/fields" 
    $availableFields_For = $adv_fields.Collection | Where-Object {$_.id -in "X-Forwarded-For"}
    if ($availableFields_For.id -ne "X-Forwarded-For"){
        Add-WebConfiguration "system.webServer/advancedLogging/server/fields" -value @{id="X-Forwarded-For";sourceName="X-Forwarded-For";sourceType="RequestHeader";logHeaderName="X-Forwarded-For";category="Default";loggingDataType="TypeLPCSTR"}
    }



function AdvancedLogging-GenerateAppCmdScriptToConfigureAndRun()
{
    param([string] $site) 

    #Get current powershell execution folder
    $currentLocation = Get-Location

 #Create an empty bat which will be populated with appcmd instructions
    $stream = [System.IO.StreamWriter] "$currentLocation\$site.bat"

 #Create site specific log definition
    $stream.WriteLine("C:\windows\system32\inetsrv\appcmd.exe set config `"$site`" -section:system.webServer/advancedLogging/server /+`"logDefinitions.[baseFileName='$site',enabled='True',logRollOption='Schedule',schedule='Daily',publishLogEvent='False']`" /commit:apphost")

 #Get all available fields for logging
    $availableFields = $adv_fields.Collection | Where-Object {$_.id -in "Bytes Received", "Bytes Sent", "Client-IP", "Cookie", "Date-UTC", "Host", "Method", "Protocol Version", "Referer", "Server Name", "Server Port", "Server-IP", "Site Name", "Status", "Substatus", "Time Taken", "Time-UTC", "URI-Querystring", "URI-Stem", "User Agent", "UserName", "Win32Status", "X-Forwarded-For"}
#Add appcmd instruction to add all the selected fields above to be logged as part of the logging
#The below section can be extended to filter out any unwanted fields
foreach ($item in $availableFields.Collection) 
    {
        $stream.WriteLine("C:\windows\system32\inetsrv\appcmd.exe set config `"$site`" -section:system.webServer/advancedLogging/server /+`"logDefinitions.[baseFileName='$site'].selectedFields.[id='$($item.id)',logHeaderName='$($item.logHeaderName)']`" /commit:apphost")
    }

    $stream.close()

    # execute the batch file create to configure the site specific Advanced Logging
        Start-Process -FilePath $currentLocation\$site.bat
        Start-Sleep -Seconds 10
    }
    #Call the above method by passing in the IIS site names
        $sites = (dir iis:\sites\*)

        foreach($site in $sites ){
            AdvancedLogging-GenerateAppCmdScriptToConfigureAndRun $site.Name
        }
}

##################################################################################
# log_audit_iis.<region>_weekly

$RegPath = "HKLM:\SYSTEM\CurrentControlSet\Services\Netlogon\Parameters"
$RegValue = "DynamicSiteName"
$Region = $null

#Verify AD Site Key Exists
if (Test-RegistryValue -Path $RegPath -Value $RegValue)
    {
    $AdSite = Get-ItemProperty -Path $RegPath | Select-Object -ExpandProperty $RegValue
    if ($AdSite.ToUpper() -match "NA-")
        {
        $topic = "log_audit_iis.na_weekly"
        }
    elseif ($AdSite.ToUpper() -match "AP-")
        {
        $topic = "log_audit_iis.ap_weekly"
        }
    elseif ($AdSite.ToUpper() -match "EU-")
        {
            $topic = "log_audit_iis.eu_weekly"
        }
    elseif ($AdSite.ToUpper() -match "LA-")
        {
            $topic = "log_audit_iis.la_weekly"
        }
    else
        {
        $Region = "Unknown"
        Write-Output "Unable to determine what region this IIS Server is in, exit 9999. You will need to manually configure the filebeat.yml." | Out-File -FilePath $Logfile -Append
        Exit 9999
        }

    }
Else
    {
    $Region = "Unknown"
    Write-Output "Unable to determine what region this IIS Server is in, exit 9999. You will need to manually configure the filebeat.yml."  | Out-File -FilePath $Logfile -Append
    Exit 9999
    }

    $filebeat_file = 'filebeat.inputs:
    - type: log
      paths:
        - '+ $iis_path + '
    queue.mem:
      events: 8092
      flush.timeout: 1000ms
      flush.min_events: 2000
      fields:
        organization.name: "Add your org here"
    output.kafka:
      hosts: ["10.6.101.249:9092","10.6.103.232:9092","10.6.101.250:9092","10.6.99.250:9092","10.6.99.249:9092"]
      topic: "' + $topic + '"
      partition.round_robin:
      reachable_only: true
      required_acks: 1
      compression: snappy
      max_message_bytes: 1000000
      bulk_max_size: 3200
      channel_buffer_size: 6400
      workers: 5
      username: "admin"
      password: "<password>"
      ssl.verification_mode: none
      codec.json:
        pretty: false
        escape_html: false'
    
    Out-File -FilePath .\filebeat -Encoding utf8 -InputObject $filebeat_file
     
    Get-Service -Name iis_filebeat | Set-Service -StartupType Automatic -Status Running
