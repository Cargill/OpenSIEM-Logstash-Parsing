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
5. Append audit=1 to the GRUB_CMDLINE_LINUX_DEFAULT so it looks like this –
    ```GRUB_CMDLINE_LINUX="console=tty0 crashkernel=auto console=ttyS0,115200 audit=1"```
6. Run 
    ```grub2-mkconfig -o /boot/grub2/grub.cfg```
7. Reboot