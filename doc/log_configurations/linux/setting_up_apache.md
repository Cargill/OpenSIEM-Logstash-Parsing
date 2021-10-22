
# Centos apache virtualhost setup

1. vi /etc/httpd/conf.d/web-example.conf
and add following details
```
<VirtualHost *:80>
    ServerName alb-ue1-lwr-aca-kafka-mngr-dev-1774144759.us-east-1.elb.amazonaws.com
    ServerAlias example.com
    DocumentRoot /var/www/example.com/html
    LogFormat "%h %l %u %t \"%r\" %>s %b \"%{Referer}i\" \"%{User-Agent}i\" \"%{X-Forwarded-For}i\"" proxied
    ErrorLog /var/www/example.com/log/error.log
    CustomLog /var/www/example.com/log/requests.log proxied
</VirtualHost>
```
2. mkdir -p /var/www/example.com/html
3. mkdir -p /var/www/example.com/log
4. vi /var/www/example.com/html/index.html
and add below 
```
<html>
  <head>
    <title>Welcome to Apache!</title>
  </head>
  <body>
    <h1>Success! The virtual host is working!</h1>
  </body>
</html>
```
5. chcon -R -t httpd_sys_content_t /var/www/example.com/html
6. semanage fcontext -a -t httpd_log_t "/var/www/example.com/log(/.*)?"
7. restorecon -R -v /var/www/example.com/log


### Troubleshooting:

If apache is not working. Most probably it's a permissions issue. Maybe httpd is not able to read files from document root or maybe it's not able to write logs. Below is an example for checking the log permissions.

Check selinux permissions

```ls -dlZ /var/www/example.com/log/```

Sample output:

```shell
drwx------. root root unconfined_u:object_r:httpd_log_t:s0 /var/www/example.com/html/log/
```

If the output contains httpd_log_t that means apache can write logs to the directory else apply httpd_log_t context and make it persist over reboots by executing below commands.

```shell
semanage fcontext -a -t httpd_log_t "/var/www/example.com/log/(/.*)?"
restorecon -R -v /var/www/example.com/log/
```

### Setting up XFF header

Add LogFormat in virtualhost to use xff header

```
LogFormat "%h %l %u %t \"%r\" %>s %b \"%{Referer}i\" \"%{User-Agent}i\" \"%{X-Forwarded-For}i\"" proxied
```

## Recommendations:
1. Use BufferedLogs: 
On some systems, this may result in more efficient disk access and hence higher performance. 
It may be set only once for the entire server;
it cannot be configured per virtual-host.
This directive should be used with caution as a crash might cause loss of logging data.
https://httpd.apache.org/docs/current/mod/mod_log_config.html#bufferedlogs
2. Use single access log file for all sites/hosts on the server and 
log name of the virtual host in each request to keep file descriptors low.

This has a drawback. In case one wants to do a custom logging for a virtual host then buffered logging would be suppressed.
https://httpd.apache.org/docs/2.4/logs.html#virtualhost

Apache allows us to rotate logs by piping logs to rotatelogs tool
https://httpd.apache.org/docs/2.4/logs.html#rotation

Apache can also send Error logs directly to syslog. Access log would have to be sent to files only.
