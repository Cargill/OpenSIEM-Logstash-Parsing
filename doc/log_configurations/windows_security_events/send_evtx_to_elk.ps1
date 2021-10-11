 function mail($msg, $scriptpath, $subject){
    $scriptserver = $env:computername
    $fromserver = "`r`nScript Ran from Server " + $scriptserver
    $frompath = "`r`nPath " + $scriptpath
    $frompath
    $body = $msg + $fromserver + $frompath
    $email_sender = '<REDACTED>'
    $email_subject = $subject
    $email_smtp = "<REDACTED>"
    $email_recipients = '<REDACTED>'
    $email_cc= '<REDACTED>'
    if($istest -ne "y"){
        Send-MailMessage -To $email_recipients -Cc $email_cc -From $email_sender -Subject $email_subject -SmtpServer "<REDACTED>" -Body ($body | out-string)
    }
}

$path = "<REDACTED>"
$filenames = Get-ChildItem D:\SOC_CSIRT\Win_Log_Import -Filter *.evtx
foreach ($filename in $filenames){
    $destination = "<REDACTED>\in_progress\" + $filename
    Copy-Item -Path $filename -Destination $destination
    $transform = '<REDACTED>\EvtxExplorer\EvtxECmd.exe -f ${destination} --json "<REDACTED>\in_progress"'
    Invoke-Expression $transform
    if($?) {
        Remove-Item -force <REDACTED>\*.evtx
    }
    else {
        mail "The .evtx-to-json command-line tool did not work." "<REDACTED>" "EVTX Script unsuccessful"
    }
}

Get-ChildItem <REDACTED>\in_progress -Filter *.json | Copy-Item -Destination <REDACTED>\for_logstash_collection -Force -PassThru
$done = Dir <REDACTED>\for_logstash_collection\*.json | rename-item -newname { [io.path]::ChangeExtension($_.name, "log") }
if($?)
{
Remove-Item <REDACTED>\in_progress\*.json
Remove-Item <REDACTED>\in_progress\*.evtx
}
else {
    mail "Turning JSON .evtx files into .log files did not work." "<REDACTED>" "EVTX Script unsuccessful"
}
$email_cc

