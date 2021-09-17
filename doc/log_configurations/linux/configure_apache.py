import glob
import io
import os
import re
import uuid

# If using VirtualHosts
#       get DocumentRoot
#       get ServerName
#       get ServerAlias
#       define LogFormat as tgrc_apache_log_formata
#       create ./log directory if not exists and execute
#           if CENTOS
#              semanage fcontext -a -t httpd_log_t "<log_directory>(/.*)?"
#              restorecon -R -v <log_directory>
#       define CustomLog as DocumentRoot/log/access.log and use tgrc_apache_log_format
#       define ErrorLog as DocumentRoot/log/error.log and use tgrc_apache_log_format

options = {
    'centos': {
        'root_path': '/etc/httpd/'
    },
    'Red Hat': {
        'root_path': '/etc/httpd/'
    }
}


def identify_abs_or_relative_path(line):
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
                abs_include_path = os.path.join(root_dir, include_path)
            return abs_include_path
    return None


def assign_values(line):
    '''We are interested in DocumentRoot, ServerName, ServerAlias, LogFormat, CustomLog, ErrorLog
    We are going to find the relevant fields up until the accompanying </VirtualHost> section
    '''
    dict_values = {}
    relevant_fields = ['DocumentRoot', 'ServerName',
                       'ServerAlias', 'LogFormat', 'CustomLog', 'ErrorLog']
    for field in relevant_fields:
        if line.startswith(field):
            # getting the index of first space character
            # the word before it is the key and everything after is the value
            try:
                key = ''.join(line[:line.index(' ')]).strip()
                value = ''.join(line[line.index(' '):]).strip()
                dict_values[key] = value
                if field == 'LogFormat':
                    # rindex is first index of space from right of the string
                    # word after last space character is the log format name
                    # arr[idx:] returns a slice from the index to end
                    # arr[:idx] returns a slice from the start to index
                    format_name = ''.join(value[value.rindex(' '):]).strip()
                    format_value = ''.join(value[:value.rindex(' ')]).strip()
                    dict_values[key] = {format_name: format_value}
            except ValueError:
                # if there was no space
                pass
    return dict_values


def read_lines(config_path):
    '''reads lines and strips them
    filters out the lines which start with # as they are comments
    '''
    with io.open(config_path, 'r', encoding='UTF-8') as config_file:
        lines = config_file.readlines()
        return lines


def identify_extra_config_paths(config_path):
    '''fetches include paths in a config file
    '''
    lines = read_lines(config_path)
    # look for includes, which are references to files with more configuration info
    included_paths = []
    for line in lines:
        path = identify_abs_or_relative_path(line.strip())
        if path is not None:
            # expand the path
            for expanded_path in glob.glob(path):
                paths = identify_extra_config_paths(expanded_path)
                included_paths.append(expanded_path)
                included_paths.extend(paths)
    return included_paths


def get_root_settings(config_path):
    '''
    Extracts important settings that are not tied to a particular virtual host
    '''
    root_settings = {}
    lines = read_lines(config_path)
    for line in lines:
        line = line.strip()
        values = assign_values(line)
        root_settings.update(values)
    return root_settings


def get_virtual_hosts(config_path):
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
            values = assign_values(stripped_line)
            virtual_host_config.update(values)
    return virtual_hosts


if __name__ == "__main__":
    '''
    CustomLog can be defined multiple times i.e. multiple patterns and multiple log paths.
    If CustomLog is defined in VirtualHost section it is used else CustomLog is picked up from root httpd.conf
    CustomLog can be set in VirtualHost section also.
    Recommendations:
    1. Use BufferedLogs https://httpd.apache.org/docs/current/mod/mod_log_config.html#bufferedlogs
    On some systems, this may result in more efficient disk access and hence higher performance. 
    It may be set only once for the entire server;
    it cannot be configured per virtual-host.
    This directive should be used with caution as a crash might cause loss of logging data.
    2. Use single access log file for all sites/hosts on the server and 
    log name of the virtual host in each request to keep file descriptors low.
    https://httpd.apache.org/docs/2.4/logs.html#virtualhost


    This script adds access logging and error logging per virtual host.
    The path is doc_root/log/access.log and doc_root/log/error.log
    It does not overwrites any predefined logging. So admins can also log in their desired format to a different location.
    
    Only if by chance a logformat is defined with name tgrc_log_format it would be overwritten with our standard log format.
    
    If no virtualhost is defined then logging is configured in root httpd.conf file.
    This means that requests would be logged in two error log files and two access log files
    as there would already be a default log definition.

    Need DocumentRoot for log file path.
    Need ServerName and/or ServerAlias for determining site name as it would be used in rsyslog.
    But site name can also be a part of each log so this may not be needed.

    So change logging to log site name.
    Log to different places. But you don't need site name to pass now. It would be parsed from the logs.
    OR
    Enforce logging to one file by removing any other CustomLog directive from VirtualHost
    And
    
    TODO
    FIXME So we don't need to parse server name or alias.

    '''
    os_type = 'centos'
    root_dir = options[os_type]['root_path']
    # The config files that need to be updated i.e. configure logging for the VirtualHost
    confs_to_update = {}
    master_config_path = os.path.join(root_dir, 'conf/httpd.conf')

    more_paths = identify_extra_config_paths(master_config_path)
    more_paths.append(master_config_path)
    # TODO
    # Need DocumentRoot for log file path
    # Need ServerName and/or ServerAlias for determining site name. It would be used in rsyslog.
    # But site name can also be a part of each log so this may not be needed.
    root_config = {}
    for path in more_paths:
        virtual_host_configs = get_virtual_hosts(path)
        # root_settings = get_root_settings(path)
        # root_config.update(root_settings)
        if virtual_host_configs:
            confs_to_update[path] = virtual_host_configs
    if len(confs_to_update.keys()) == 0:
        # there is no virtual host update the master config
        # TODO add logic
        pass
    else:
        import json
        print(json.dumps(confs_to_update, indent=2))
        for conf_path in confs_to_update.keys():
            lines = read_lines(conf_path)
            virtual_hosts = confs_to_update[conf_path]
            for virtual_host in virtual_hosts:
                # Check if CustomLog is defined
                # Check if ErrorLog is defined
                # Check if LogFormat is defined
                # Check if both these logs are using the correct log format
                insert_offset = 0
                try:
                    doc_root = virtual_host['DocumentRoot']
                except KeyError:
                    # this site does not have a custom doc_root
                    # check if it has a ServerName or ServerAlias defined then use those values else generate a random id
                    if 'ServerName' in virtual_host:
                        dir_name = virtual_host['ServerName']
                    elif 'ServerAlias' in virtual_host:
                        dir_name = virtual_host['ServerAlias']
                    else:
                        dir_name = str(uuid.uuid4())
                    # We need doc_root as log directory is relative to it.
                    # Get the default.
                    doc_root = '{}/{}'.format(
                        root_config['DocumentRoot'], dir_name)
                std_log_format_name = 'tgrc_log_format'
                custom_log_path = '{}/log/access.log'.format(doc_root)
                error_log_path = '{}/log/error.log'.format(doc_root)
                # tgrc_std_log_pattern = '"%h %l %u %t \"%r\" %>s %b \"%{Referer}i\" \"%{User-Agent}i\" \"%{X-Forwarded-For}i\""'
                tgrc_std_log_pattern = '"%t %Z %z %m %U %q %p %a %H %v %s %I % O %T \"%{Referer}i\" \"%{User-Agent}i\" %{X-Forwarded-For}i"'
                tgrc_std_log_format = 'LogFormat {} {}'.format(tgrc_std_log_pattern, std_log_format_name)
                tgrc_std_custom_log = 'CustomLog {} {}'.format(custom_log_path, std_log_format_name)
                tgrc_std_error_log = 'ErrorLog {}'.format(error_log_path)
                try:
                    log_format_pattern = virtual_host['LogFormat'][std_log_format_name]
                    # std_log_format_name is already defined in this config
                    if log_format_pattern != tgrc_std_log_pattern:
                        # replacing
                        pass
                except KeyError:
                    # inserting
                    lines.insert(
                        insert_offset + virtual_host['end_index'], tgrc_std_log_format)
                    insert_offset += 1
                try:
                    custom_log = virtual_host['CustomLog']
                    # checking if custom_log is using tgrc standard log format
                    log_file_path = ''.join(
                        custom_log[custom_log.rindex(' '):]).strip()
                    log_format_name = ''.join(
                        custom_log[:custom_log.rindex(' ')]).strip()
                    if log_format_name != 'tgrc_log_format':
                        # inserting
                        lines.insert(
                            insert_offset + virtual_host['end_index'], tgrc_std_custom_log)
                        insert_offset += 1
                    else:
                        # logging format is good user may want to have a different path, so note it down
                        # we are enforcing log pattern not log location
                        custom_log_path = log_file_path
                except KeyError:
                    # inserting
                    lines.insert(
                        insert_offset + virtual_host['end_index'], tgrc_std_custom_log)
                    insert_offset += 1
                try:
                    error_log = virtual_host['ErrorLog']
                    if log_format_name != 'tgrc_log_format':
                        # inserting
                        lines.insert(
                            insert_offset + virtual_host['end_index'], tgrc_std_error_log)
                        insert_offset += 1
                    else:
                        # logging format is good user may want to have a different path, so note it down
                        # we are enforcing log pattern not log location
                        error_log_path = log_file_path
                    tgrc_std_error_log = error_log
                    # replacing
                except KeyError:
                    # inserting
                    lines.insert(insert_offset +
                                 virtual_host['end_index'], tgrc_std_error_log)
                    insert_offset += 1
            with io.open(conf_path, 'w', encoding='UTF-8') as conf_file:
                conf_file.writelines(lines)
            # TODO
            # create directory and add permission
            # make a rsyslog conf
