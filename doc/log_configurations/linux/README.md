# Linux logging

## syslog

rsyslog is pre installed and running by default on below systems:
- RHEL 5 and above
- Debian 5 and above
- Ubuntu 18 and above

To configure log collection:
- append contents of [rsyslog.conf](./rsyslog/rsyslog.conf) to /etc/rsyslog.conf _after changing last line to respective zone IP._
- Add other [conf files](./rsyslog) to /etc/rsyslog.d 
- If selinux is enabled execute
    ```sh
    semanage permissive -a syslogd_t
    ```
    Ref: https://linux.die.net/man/8/syslogd_selinux
    rsyslog is part of syslogd_t. Above command tells selinux to permit the processes running with this context on everything.
    To check if selinux is enabled, execute `selinuxenabled` command and check for status 0.
- Restart rsyslog daemon
    ```sh
    systemctl restart rsyslog
    ```

## auditd

For configuring auditd to log commands:
1. Login as root
2. Edit /etc/audit/rules.d/audit.rules
3. Add the below two new lines (ordering is important) 
    ```-a exit,always -F arch=b64 -F euid=0 -S execve```
    ```-a exit,always -F arch=b32 -F euid=0 -S execve```
4. Edit /etc/default/grub
5. Append audit=1 to the GRUB_CMDLINE_LINUX_DEFAULT so it looks like this -
    ```GRUB_CMDLINE_LINUX="console=tty0 crashkernel=auto console=ttyS0,115200 audit=1"```
6. Run 
    ```grub2-mkconfig -o /boot/grub2/grub.cfg```
7. Reboot

## Configure apache script
The script is written to be python2 compatible as that comes pre-installed in most systems.
It currently supports only centos. Operating system type has to be passed as the first argument to the script.

To run, do: 
```sh
python configure_apache.py centos
```

Usage help: 
```sh
python configure_apache.py -h
```

**How the script works**
1. It adds access logging and error logging per virtual host.
2. If no virtualhost is defined then logging is configured in root httpd.conf file.
3. Adds logging in below formats
    ```py
    # <%t Time the request was received> <%v The canonical ServerName of the server serving the request.> <%{c}L log id of the connection> <%L Request log ID> <%a Client IP address and port of the request> <%p server port> <%m The request method> <%U The URL path requested> <%q The query string> <%H The request protocol> <%s Status> <%I Bytes received> <%O Bytes sent> <%T The time taken to serve the request, in seconds.>
    TGRC_STD_LOG_PATTERN = '"%t [%v] [%{c}L] [%L] [%a] [%p] %m %U \\"%q\\" %H %s %I %O %T \\"%{Referer}i\\" \\"%{User-Agent}i\\" %{X-Forwarded-For}i"'
    # <%t Time the request was received> <%v The canonical ServerName of the server serving the request.> <%l log level> <%{c}L log id of the connection> <%L Request log ID> <%P pid> <%F Source file name and line number of the log call> <%E APR/OS error status code and string> <%a Client IP address and port of the request>
    TGRC_STD_ERROR_LOG_PATTERN = '"[%-t] [%-v] [%-l] [%-{c}L] [%-L] [pid %-P] [%-F: %-E] [client %-a] %-M"'
    ```

    Sample logs
    ```log
    [12/Oct/2021:13:13:56 +0000] [abc] [3WgonhdVkMA] [YWWKFNNS-kB8QY2RXLp6OwAAAAA] [::1] [80] GET / "" HTTP/1.1 403 73 5149 0 "-" "curl/7.29.0" -
    [Tue Oct 12 13:13:56 2021] [abc] [error] [3WgonhdVkMA] [YWWKFNNS-kB8QY2RXLp6OwAAAAA] [pid 23839] [request.c(1169): (13)Permission denied] [client ::1:39664] AH00035: access to /index.html denied (filesystem path '/var/www/krishna.com/index.html') because search permissions are missing on a component of the path
    ```
4. The paths are log/standard_access.log and log/standard_error.log relative to DocumentRoot/(ServerName or ServerAlias)
5. After the script is run and a change is made, a log is generated which says: _Server restart is required as config files changed: <list of files changed>._ `rsysylog` forwards this log to SIEM and SIEM can notify the admins so they can plan to restart Apache.
6. logs are rotated every 1 hour via logrotate

**References**
- Custom Log Format: https://httpd.apache.org/docs/current/mod/mod_log_config.html#formats
- Error Log Format: https://httpd.apache.org/docs/2.4/mod/core.html#errorlogformat
- Understanding Error Logs: https://stackify.com/apache-error-log-explained/
- Forwarding Apache Logs Using Rsyslog: https://www.rsyslog.com/recipe-apache-logs-rsyslog-parsing-elasticsearch/
