r'''
About Apache Logging:
CustomLog can be defined multiple times i.e. multiple patterns and multiple log paths (multiple files with logs).
If CustomLog is defined in VirtualHost section it is used. Otherwise, CustomLog is picked up from root httpd.conf
CustomLog can be set in VirtualHost section also.

About this script:
It does not overwrites any predefined logging. So admins can also write logs in desired format to a desired location.
When we add a new definition all we say is to log at a location which we monitor and in format which we enforce.
It adds access logging and error logging per virtual host.
If no virtualhost is defined then logging is configured in root httpd.conf file. This means that requests would be
logged in _two_ error log files and _two_ access log files as there would already be a default log definition.
I.e. since this does not replace the original logging definition everything is logged twice.

Log format:
Virtual host name is also logged so it can be extracted with logstash.
A defined logformat is overwritten with standard log format if it is defined with name ``tgrc_log_format``.

Error Logging:
Error Logs take all the formats defined, so it's hard to determine which format is being used.
https://httpd.apache.org/docs/2.4/mod/core.html#errorlogformat
It's possible to enforce an error logging pattern only by removing all error log formats and using a single standard (for
example, our standard only.) Since that would break any predefined logging, this program adds a standard error logging
pattern and logs to a standard error log location.

Log Location:
The paths are log/standard_access.log and log/standard_error.log relative to DocumentRoot/(ServerName or ServerAlias)
Creates DocumentRoot/(ServerName or ServerAlias)/log if not exists and adds necessary permissions to the directory.
If either of ServerName and ServerAlias are not defined then path is DocumentRoot/logs/log ... I.e:
If DocumentRoot/(ServerName or ServerAlias)/log
means
DocumentRoot/ServerName/log
or
DocumentRoot/ServerAlias/log


Collecting Apache Logs:
Rsyslog can be configured just to read all apache logs and forward them to a centralized location with the tag of apache.
It can also be configured to pre-parse it and send data in structured format.

Tests:
1. Overwrites tgrc_log_format LogFormat with standard one.
2. Inserts tgrc_std_log_format, tgrc_std_custom_log, tgrc_std_error_log if either are absent in Virtual hosts section.
3. Inserts tgrc_std_log_format, tgrc_std_custom_log, tgrc_std_error_log in root config.
4. If DocRoot is changed new ErrorLog is added but old error log path is not removed.
(This is due to the fact that we don't want to remove any predefined error logs. There is no way to identify our enforced error log as error log don't have format specified)

Known Bug:
If we modify ErrorLogFormat it is inserted but since the ErrorLog directive is already set, it does not set it again.
As a result, the new ErrorLogFormat is not picked up.
'''
import argparse
import glob
import io
import json
import logging
import os
import re
from logging.handlers import RotatingFileHandler

logger = logging.getLogger()

# Add more operating systems here
OPTIONS = {
    'centos': {
        'root_path': '/etc/httpd/',
        'script_log_path': '/var/log/configure_apache/script.log',
        'rsyslog_conf_path': '/etc/rsyslog.d/tgrc_apache.conf',
        'rotatelogs': '/sbin/rotatelogs'
    },
    # To be clear, this has NOT been tested by our team.
    'Red Hat': {
        'root_path': '/etc/httpd/',
        'script_log_path': '/var/log/configure_apache/script.log',
        'rsyslog_conf_path': '/etc/rsyslog.d/tgrc_apache.conf',
        'rotatelogs': '/sbin/rotatelogs'
    }
}
# log pattern
# Webshpere log pattern: https://www.ibm.com/docs/en/was-nd/8.5.5?topic=logs-custom-log-file-format
# %Z and %z are invalid patterns for apache. They are websphere specific.
# TGRC_STD_LOG_PATTERN = '"%t %Z %z %v %L %m %U %q %p %a %H %s %I %O %T \\"%{Referer}i\\" \\"%{User-Agent}i\\" %{X-Forwarded-For}i"'

# The patterns behave differently for CustomLog and ErrorLog.
# <%t Time the request was received> <%v The canonical ServerName of the server serving the request.> <%{c}L log id of the connection> <%L Request log ID> <%a Client IP address and port of the request> <%p server port> <%m The request method> <%U The URL path requested> <%q The query string> <%H The request protocol> <%s Status> <%I Bytes received> <%O Bytes sent> <%T The time taken to serve the request, in seconds.>
TGRC_STD_LOG_PATTERN = '"%t [%v] [%{c}L] [%L] [%a] [%p] %m %U \\"%q\\" %H %s %I %O %T \\"%{Referer}i\\" \\"%{User-Agent}i\\" %{X-Forwarded-For}i"'
# <%t Time the request was received> <%v The canonical ServerName of the server serving the request.> <%l log level> <%{c}L log id of the connection> <%L Request log ID> <%P pid> <%F Source file name and line number of the log call> <%E APR/OS error status code and string> <%a Client IP address and port of the request>
TGRC_STD_ERROR_LOG_PATTERN = '"[%-t] [%-v] [%-l] [%-{c}L] [%-L] [pid %-P] [%-F: %-E] [client %-a] %-M"'

def identify_abs_or_relative_path(line, os_type):
    includes_all = ['IncludeOptional', 'Include']
    for i in includes_all:
        if line.startswith(i) and '.conf' in line:
            include_path = line.split(i)[1].strip()
            abs_include_path = ''
            if include_path.startswith('/'):
                # it's an absolute path
                abs_include_path = include_path
            else:
                # it's a relative path
                root_dir = OPTIONS[os_type]['root_path']
                abs_include_path = os.path.join(root_dir, include_path)
            return abs_include_path
    return None


def assign_values(line, config):
    '''We are interested in DocumentRoot, ServerName, ServerAlias, LogFormat, CustomLog, ErrorLog
    We are going to find the relevant fields up until the accompanying </VirtualHost> section
    '''
    relevant_fields = ['DocumentRoot', 'ServerName',
                       'ServerAlias', 'LogFormat', 'CustomLog', 'ErrorLogFormat', 'ErrorLog']
    for field in relevant_fields:
        if line.startswith(field):
            # getting the index of first space character
            # the word before it is the key and everything after is the value
            try:
                key = ''.join(line[:line.index(' ')]).strip()
                value = ''.join(line[line.index(' '):]).strip()
                if field == 'CustomLog':
                    try:
                        custom_logs = config['CustomLog']
                        custom_logs.append(value)
                    except KeyError:
                        # CustomLog is array
                        config['CustomLog'] = [value]
                elif field == 'LogFormat':
                    # rindex is first index of space from right of the string
                    # word after last space character is the log format name
                    # arr[idx:] returns a slice from the index to end
                    # arr[:idx] returns a slice from the start to index
                    format_name = ''.join(value[value.rindex(' '):]).strip()
                    format_value = ''.join(value[:value.rindex(' ')]).strip()
                    try:
                        log_format = config['LogFormat']
                        log_format.update({format_name: format_value})
                    except KeyError:
                        # LogFormat is a dict
                        config['LogFormat'] = {format_name: format_value}
                elif field == 'ErrorLog':
                    try:
                        error_logs = config['ErrorLog']
                        error_logs.append(value)
                    except KeyError:
                        # ErrorLog is array
                        config['ErrorLog'] = [value]
                elif field == 'ErrorLogFormat':
                    try:
                        error_log_formats = config['ErrorLogFormat']
                        error_log_formats.append(value)
                    except KeyError:
                        # ErrorLogFormat is array
                        config['ErrorLogFormat'] = [value]
                else:
                    config[key] = value
            except ValueError:
                # if there was no space
                pass


def read_lines(config_path):
    '''returns file content as lines'''
    if not os.path.exists(config_path):
        return []
    with io.open(config_path, 'r', encoding='UTF-8') as config_file:
        lines = config_file.readlines()
        # lines are unicode, converting them to str
        lines = [line.rstrip().encode('utf-8') for line in lines]
        return lines


def write_lines(conf_path, lines):
    '''Compares existing contents in the file and updates only if needed.

    Parameters:
        conf_path str: 
        lines list[str]: 

    Returns:
        bool: True if write was needed/successful else False
    '''
    existing_lines = read_lines(conf_path)
    if existing_lines == lines:
        logger.debug('update not needed for: {}'.format(conf_path))
        return False
    with io.open(conf_path, 'w', encoding='UTF-8') as conf_file:
        logger.info('writing: {}'.format(conf_path))
        lines = ['{}\n'.format(line).decode('UTF-8') for line in lines]
        conf_file.writelines(lines)
        return True


def identify_extra_config_paths(config_path, os_type):
    '''Fetches include paths in a config file recursively

    Returns:
        list[str]: all paths
    '''
    lines = read_lines(config_path)
    # look for includes, which are references to files with more configuration info
    included_paths = []
    for line in lines:
        path = identify_abs_or_relative_path(line.strip(), os_type)
        if path is not None:
            # expand the path
            for expanded_path in glob.glob(path):
                paths = identify_extra_config_paths(expanded_path, os_type)
                included_paths.append(expanded_path)
                included_paths.extend(paths)
    return included_paths


def get_root_settings(config_path):
    '''Extracts important settings that are not tied to a particular virtual host
    '''
    root_settings = {}
    lines = read_lines(config_path)
    for line in lines:
        line = line.strip()
        assign_values(line, root_settings)
    return root_settings


def get_virtual_hosts(config_path):
    '''Look for relevant settings in a file from start of <VirtualHost to start of </VirtualHost>
    '''
    lines = read_lines(config_path)
    # look for virtual hosts
    virtual_host_def_start = False
    virtual_hosts = []
    for index in range(len(lines)):
        stripped_line = lines[index].strip()
        # There can be multiple VirtualHost definitions in one conf file.
        if stripped_line.startswith('<VirtualHost'):
            matched = re.search(r'^<VirtualHost\s+(.+)>$', stripped_line)
            '''If the regex matches, then it is added to virtual_host_config
             as 'name': <VirtualHost *:80>
            '''
            virtual_host_config = {
                'name': matched.group(1),
                'start_index': index
            }
            virtual_host_def_start = True
        if stripped_line.startswith('</VirtualHost>'):
            virtual_host_def_start = False
            virtual_host_config['end_index'] = index
            virtual_hosts.append(virtual_host_config)
        if virtual_host_def_start:
            assign_values(stripped_line, virtual_host_config)
    return virtual_hosts


def check_updation(lines, config, os_type, root_config={}, insert_offset=0):
    '''
    ``lines`` is lines read from file
    ``insert_offset`` should be -1 for a new file and should be shared thereafter
    ``config`` is parsed apache config for a file
    ``root_config`` is parsed httpd.conf

    This function inserts needed settings or replaces conflicting settings in place.
    Ensures if CustomLog is defined
    Ensures if ErrorLog is defined
    Ensures if LogFormat is defined
    Ensures if both these logs are using the correct log format
    '''
    try:
        doc_root = config['DocumentRoot']
    except KeyError:
        # this site does not have a custom doc_root
        # check if it has a ServerName or ServerAlias defined then use those values else use logs
        if 'ServerName' in config:
            dir_name = config['ServerName']
        elif 'ServerAlias' in config:
            dir_name = config['ServerAlias']
        else:
            dir_name = 'logs'
        # We need doc_root as log directory is relative to it.
        # Get the default.
        if 'DocumentRoot' not in root_config:
            raise Exception('cannot determine DocumentRoot')
        doc_root = '{}/{}'.format(
            root_config['DocumentRoot'], dir_name)
    # line index where this virtualhost definition ends
    end_index = config['end_index']

    std_log_format_name = 'tgrc_log_format'
    # paths may be enclosed with double quotes
    doc_root = doc_root.replace('"', '')
    custom_log_path = '{}/log/standard_access.log'.format(doc_root)
    error_log_path = '{}/log/standard_error.log'.format(doc_root)

    tgrc_std_log_format = 'LogFormat {} {}'.format(
        TGRC_STD_LOG_PATTERN, std_log_format_name).decode("utf-8")
    tgrc_std_error_log_format = 'ErrorLogFormat {}'.format(
        TGRC_STD_ERROR_LOG_PATTERN).decode("utf-8")

    # CustomLog with this pattern are supposedly added by this script in previous run
    # and should be ensured they are up to date.
    custom_log_match_pattern = r'^"\|.+" {log_format}$'.format(
        log_format=std_log_format_name).decode("utf-8")
    tgrc_std_custom_log = 'CustomLog "|{rotatelogs} {log_path} {rotate_time}" {log_format}'.format(
        rotatelogs=OPTIONS[os_type]['rotatelogs'], log_path=custom_log_path, rotate_time=3600, log_format=std_log_format_name).decode("utf-8")
    tgrc_std_error_log = 'ErrorLog "|{rotatelogs} {log_path} {rotate_time}"'.format(
        rotatelogs=OPTIONS[os_type]['rotatelogs'], log_path=error_log_path, rotate_time=3600).decode("utf-8")

    try:
        log_format_pattern = config['LogFormat'][std_log_format_name]
        # std_log_format_name is already defined in this config
        if log_format_pattern != TGRC_STD_LOG_PATTERN:
            # look for ''LogFormat {}'.format(log_format_pattern)
            # and replace it with tgrc_std_log_format
            logger.warning('replacing format as: {} not equal to {}'.format(
                log_format_pattern, TGRC_STD_LOG_PATTERN))
            for idx in range(len(lines)):
                if lines[idx].strip().startswith('LogFormat {}'.format(log_format_pattern)):
                    break
            lines[idx] = tgrc_std_log_format
    except KeyError:
        logger.info('inserting: {}'.format(tgrc_std_log_format))
        # inserting
        lines.insert(end_index + insert_offset, tgrc_std_log_format)
        insert_offset += 1
    try:
        custom_logs = config['CustomLog']
        tgrc_std_custom_log_exists = False
        for custom_log in custom_logs:
            logger.debug('Searching pattern {} in {}'.format(
                custom_log_match_pattern, custom_log))
            matched = re.search(custom_log_match_pattern, custom_log)
            # If it exactly matches than no update needed
            if 'CustomLog {}'.format(custom_log) == tgrc_std_custom_log:
                logger.debug('match found for custom_log')
                tgrc_std_custom_log_exists = True
            if matched > 0 and not tgrc_std_custom_log_exists:
                logger.warn('Match found for custom_log, replacing it')
                # let's find this line and replace it
                # It would be closest line before the end index
                idx = end_index + insert_offset
                while idx > 0:
                    if lines[idx] == custom_log:
                        logger.info('replacing {} with: {}'.format(
                            custom_log, tgrc_std_custom_log))
                        lines[idx] = tgrc_std_custom_log
                        tgrc_std_custom_log_exists = True
                        break
                    idx = idx - 1
        if not tgrc_std_custom_log_exists:
            logger.info('inserting: {}'.format(tgrc_std_custom_log))
            # inserting
            lines.insert(end_index + insert_offset, tgrc_std_custom_log)
            insert_offset += 1
    except KeyError:
        logger.info('inserting: {}'.format(tgrc_std_custom_log))
        # inserting
        lines.insert(end_index + insert_offset, tgrc_std_custom_log)
        insert_offset += 1
    try:
        error_log_formats = config['ErrorLogFormat']
        std_error_log_exists = False
        for error_log_format in error_log_formats:
            if error_log_format == TGRC_STD_ERROR_LOG_PATTERN:
                std_error_log_exists = True

        if not std_error_log_exists:
            lines.insert(end_index + insert_offset, tgrc_std_error_log_format)
            insert_offset += 1
    except KeyError:
        logger.info('inserting: {}'.format(tgrc_std_error_log_format))
        # inserting
        lines.insert(end_index + insert_offset, tgrc_std_error_log_format)
        insert_offset += 1
    try:
        # ErrorLog line must come immediately after ErrorLogFormat
        error_logs = config['ErrorLog']
        std_error_log_exists = False
        for error_log in error_logs:
            if 'ErrorLog {}'.format(error_log) == tgrc_std_error_log:
                std_error_log_exists = True
        if not std_error_log_exists:
            logger.info('inserting: {}'.format(tgrc_std_error_log))
            # inserting
            lines.insert(end_index + insert_offset, tgrc_std_error_log)
            insert_offset += 1
    except KeyError:
        logger.info('inserting: {}'.format(tgrc_std_error_log))
        # inserting
        lines.insert(end_index + insert_offset, tgrc_std_error_log)
        insert_offset += 1
    return insert_offset, custom_log_path, error_log_path


def ensure_appropriate_permissions(file_paths, os_type):
    '''Create directory if not exists
    Add write permission to the directory if not already
    '''
    for file_path in file_paths:
        # ASSUMPTION: file_path we added is absolute path
        dir_path, _ = os.path.split(file_path)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
        if os_type == 'centos':
            # example output
            # httpd_log_t is the context needed for apache to write logs
            # drwx------. root root unconfined_u:object_r:httpd_log_t:s0 /var/www/example.com/html/log/
            check_permission = 'ls -dlZ {}'.format(dir_path)
            output = os.popen(check_permission).read()
            if 'httpd_log_t' in output:
                logger.debug(
                    'Path {} has required permission'.format(dir_path))
                continue
            add_permission = 'semanage fcontext -a -t httpd_log_t "{}(/.*)?"'.format(
                dir_path)
            logger.info('executing: {}'.format(add_permission))
            os.system(add_permission)
            # apply the changes and let them survive reboots
            restore_con = 'restorecon -R -v {}'.format(dir_path)
            logger.info('executing: {}'.format(restore_con))
            os.system(restore_con)


def enforce_rsyslog_config(os_type, access_log_paths, error_log_paths):
    '''Ensures config at ``OPTIONS[os_type]['rsyslog_conf_path']`` is up to date
    Restarts rsyslog if it was updated
    Note that restarting rsyslog may result in event loss but there is no other way (maybe use RELP or accept the loss)
    https://github.com/rsyslog/rsyslog/issues/3759#issuecomment-671655320

    Still using legacy rsyslog definition for backward compatibility.
    '''
    access_log_settings = []
    for access_file_path in access_log_paths:
        access_log_settings.append('$InputFileName {access_file_path}*'.format(
            access_file_path=access_file_path))
        access_log_settings.append('$InputFileTag apache-access:')
        access_log_settings.append('$InputFileSeverity info')
        access_log_settings.append('$InputRunFileMonitor')
        # new line
        access_log_settings.append('')

    error_log_settings = []
    for error_file_path in error_log_paths:
        error_log_settings.append('$InputFileName {error_file_path}*'.format(
            error_file_path=error_file_path))
        error_log_settings.append('$InputFileTag apache-error:')
        error_log_settings.append('$InputFileSeverity error')
        error_log_settings.append('$InputRunFileMonitor')
        # new line
        error_log_settings.append('')

    # update rsyslog config
    rsyslog_config_lines = [
        # Add notice
        '# This file is generated by configure_apache script and would be overwritten if changed',
        # Load file input module
        '$ModLoad imfile',
        '',
        # Add log forwarding for this script logs too
        '$InputFileName {script_log_path}'.format(
            script_log_path=OPTIONS[os_type]['script_log_path']),
        '$InputFileTag configure-apache:',
        '$InputFileSeverity info',
        '$InputRunFileMonitor',
        ''
    ]

    rsyslog_config_lines = rsyslog_config_lines + \
        access_log_settings + error_log_settings

    rsyslog_conf_path = OPTIONS[os_type]['rsyslog_conf_path']
    dir_path, _ = os.path.split(rsyslog_conf_path)
    if not os.path.exists(dir_path):
        logger.info('Creating directory {}'.format(error_log_paths))
        os.makedirs(dir_path)
    is_rsyslog_restart_required = write_lines(
        rsyslog_conf_path, rsyslog_config_lines)
    # If the file was updated, restart rsyslog.
    if is_rsyslog_restart_required:
        logger.info('rsyslog config created')
        restart_rsyslog = 'systemctl restart rsyslog'
        logger.info('executing: {}'.format(restart_rsyslog))
        os.system(restart_rsyslog)


def configure_standard_logging(os_type):
    '''This is the main method
    Parse root conf and get all include paths
    Parse confs in include paths and get virtual host sections.
    Insert standard logging if needed
    Ensure appropriate permissions at standard logging locations
    Ensure rsyslog config is up to date to receive logs from above locations and restart rsyslog if needed.

    Generate a notice for server to be restarted.
    '''
    root_dir = OPTIONS[os_type]['root_path']
    master_config_path = os.path.join(root_dir, 'conf/httpd.conf')
    logger.debug('looking for includes in {} recursively'.format(
        master_config_path))
    conf_paths = identify_extra_config_paths(master_config_path, os_type)
    conf_paths.append(master_config_path)

    # conf path as key and parsed VirtualHost config list as value
    virtual_host_conf_dict = {}
    # relevant values parsed from non virtualhost sections
    root_config = {}
    for path in conf_paths:
        logger.debug('looking for virtual_host definitions in {}'.format(path))
        virtual_host_configs = get_virtual_hosts(path)
        root_config = get_root_settings(path)
        if virtual_host_configs:
            virtual_host_conf_dict[path] = virtual_host_configs

    # List of conf files that would be updated to enforce our standard.
    # This would be used to notify server admins.
    files_changed = []
    # enforced access_log_paths based on defined configs
    access_log_paths = []
    # enforced error_log_paths based on defined configs
    error_log_paths = []
    # if virtual host is defined configure logging in that else use root config
    if len(virtual_host_conf_dict.keys()) > 0:
        logger.debug('virtual host configs: {}'.format(
            json.dumps(virtual_host_conf_dict)))
        for conf_path in virtual_host_conf_dict.keys():
            lines = read_lines(conf_path)
            virtual_hosts = virtual_host_conf_dict[conf_path]
            # insert logging in each virtual host section
            # as these sections are part of same file they must share insert_offset
            insert_offset = 0
            for virtual_host in virtual_hosts:
                insert_offset, new_access_log_path, new_error_log_path = check_updation(lines,
                                                                                        virtual_host, os_type,  root_config=root_config, insert_offset=insert_offset)
                access_log_paths.append(new_access_log_path)
                error_log_paths.append(new_error_log_path)

            if write_lines(conf_path, lines):
                files_changed.append(conf_path)
    else:
        # there is no virtual host, update the master config
        logger.debug('root config: {}'.format(json.dumps(root_config)))
        lines = read_lines(master_config_path)
        # Assign line number in the file before which standard logging should be added
        root_config['end_index'] = len(lines)
        _, new_access_log_path, new_error_log_path = check_updation(
            lines, root_config, os_type)
        access_log_paths.append(new_access_log_path)
        error_log_paths.append(new_error_log_path)

        if write_lines(master_config_path, lines):
            files_changed.append(master_config_path)

    logger.debug('access_log_paths: {}'.format(access_log_paths))
    logger.debug('error_log_paths: {}'.format(error_log_paths))

    # create directory and add permission if required
    ensure_appropriate_permissions(access_log_paths, os_type)
    ensure_appropriate_permissions(error_log_paths, os_type)

    if len(files_changed) > 0:
        logger.info(
            'Server restart is required as config files changed: {}'.format(files_changed))

    # Create rsyslog config and restart rsyslog if needed
    enforce_rsyslog_config(os_type, access_log_paths, error_log_paths)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(usage='%(prog)s [options]', description='Configures an Apache server for standard logging and adds logforwarding via rsyslog')
    # Add a positional argument as this is mandatory
    parser.add_argument(
        dest='os_type', type=str, help='should be one of: {}'.format(', '.join(OPTIONS.keys())))
    args = parser.parse_args()
    os_type = args.os_type

    # Logging for this script
    logger.setLevel(logging.INFO)
    script_log_path = OPTIONS[os_type]['script_log_path']
    script_log_dir, _ = os.path.split(script_log_path)
    if not os.path.exists(script_log_dir):
        os.makedirs(script_log_dir)
    # Could not get SysLogHandler working so using File and reading that from rsyslog
    file_handler = RotatingFileHandler(
        script_log_path, maxBytes=10240, backupCount=2)
    formatter = logging.Formatter(
        "%(levelname)s L%(lineno)d - %(message)s")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Configure apache logging
    configure_standard_logging(os_type)
