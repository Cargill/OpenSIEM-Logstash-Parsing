import glob
import io
import os
import re

# If using VirtualHosts
#       get DocumentRoot
#       get ServerName
#       get ServerAlias
#       define LogFormat as tgrc_apache_log_format
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
    '''reads lines
    '''
    with io.open(config_path, 'r', encoding='UTF-8') as config_file:
        lines = config_file.readlines()
        lines = [line.rstrip() for line in lines]
        return lines


def write_lines(conf_path, lines):
    with io.open(conf_path, 'w', encoding='UTF-8') as conf_file:
        print('writing', conf_path)
        lines = ['{}\n'.format(line).decode('UTF-8') for line in lines]
        conf_file.writelines(lines)


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
        assign_values(line, root_settings)
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
            assign_values(stripped_line, virtual_host_config)
            # # Since CustomLog is a list
            # try:
            #     custom_logs = virtual_host_config['CustomLog']
            # except KeyError:
            #     custom_logs = []
            #     virtual_host_config['CustomLog'] = custom_logs
            # if 'CustomLog' in values:
            #     custom_logs.extend(values['CustomLog'])
            # else:
            #     virtual_host_config.update(values)
    return virtual_hosts


def check_updation(lines, access_logs, error_logs, config, root_config={}):
    # Check if CustomLog is defined
    # Check if ErrorLog is defined
    # Check if LogFormat is defined
    # Check if both these logs are using the correct log format
    insert_offset = -1
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
    std_log_format_name = 'tgrc_log_format'
    custom_log_path = '{}/log/access.log'.format(doc_root)
    error_log_path = '{}/log/error.log'.format(doc_root)
    
    # log pattern
    # <%t Time the request was received> <%Z > <%z > <%v The canonical ServerName of the server serving the request.> <%L Request log ID> <%m The request method> <%U The URL path requested> <%q The query string> <%p The canonical port of the server serving the request.> <%a Client IP address of the request> <%H The request protocol.> <%s Status> <%I Bytes received> <%O Bytes sent> <%T The time taken to serve the request, in seconds.>
    tgrc_std_log_pattern = '"%t %Z %z %v %L %m %U %q %p %a %H %s %I %O %T \"%{Referer}i\" \"%{User-Agent}i\" %{X-Forwarded-For}i"'
    tgrc_std_error_log_pattern = '"[%t] [%v] [%l] [pid %P] %F: %E: [client %a] %M"'
    
    tgrc_std_log_format = 'LogFormat {} {}'.format(
        tgrc_std_log_pattern, std_log_format_name).decode("utf-8")
    tgrc_std_error_log_format = 'ErrorLogFormat {}'.format(
        tgrc_std_error_log_pattern).decode("utf-8")
    tgrc_std_custom_log = 'CustomLog {} {}'.format(
        custom_log_path, std_log_format_name).decode("utf-8")
    tgrc_std_error_log = 'ErrorLog {}'.format(error_log_path).decode("utf-8")
    try:
        log_format_pattern = config['LogFormat'][std_log_format_name]
        # std_log_format_name is already defined in this config
        if log_format_pattern != tgrc_std_log_pattern:
            # look for ''LogFormat {}'.format(log_format_pattern)
            # and replace it with tgrc_std_log_format
            print('WARNING', log_format_pattern,
                  'not equal to', tgrc_std_log_pattern)
            for idx in range(len(lines)):
                if lines[idx].strip().startswith('LogFormat {}'.format(log_format_pattern)):
                    break
            lines[idx] = tgrc_std_log_format
    except KeyError:
        print('inserting', tgrc_std_log_format)
        # inserting
        lines.insert(
            config['end_index'] + insert_offset, tgrc_std_log_format)
        insert_offset += 1
    try:
        custom_logs = config['CustomLog']
        tgrc_std_custom_log_exists = False
        for custom_log in custom_logs:
            if 'CustomLog {}'.format(custom_log) == tgrc_std_custom_log:
                print('match found for ', 'custom_log')
                tgrc_std_custom_log_exists = True
        if not tgrc_std_custom_log_exists:
            print('inserting', tgrc_std_custom_log)
            # inserting
            lines.insert(
                config['end_index'] + insert_offset, tgrc_std_custom_log)
            insert_offset += 1
    except KeyError:
        # inserting
        lines.insert(
            config['end_index'] + insert_offset, tgrc_std_custom_log)
        insert_offset += 1
    try:
        error_log_formats = config['ErrorLogFormat']
        std_error_log_exists = False
        for error_log_format in error_log_formats:
            if error_log_format == tgrc_std_error_log_pattern:
                std_error_log_exists = True

        if not std_error_log_exists:
            lines.insert(
                config['end_index'] + insert_offset, tgrc_std_error_log_format)
            insert_offset += 1
    except KeyError:
        print('inserting', tgrc_std_error_log_format)
        # inserting
        lines.insert(
            config['end_index'] + insert_offset, tgrc_std_error_log_format)
        insert_offset += 1
    try:
        error_logs = config['ErrorLog']
        std_error_log_exists = False
        for error_log in error_logs:
            if error_log == tgrc_std_error_log:
                std_error_log_exists = True
        if not std_error_log_exists:
            # inserting
            lines.insert(
                config['end_index'] + insert_offset, tgrc_std_error_log)
            insert_offset += 1
    except KeyError:
        # inserting
        lines.insert(
            config['end_index'] + insert_offset, tgrc_std_error_log)
        insert_offset += 1
    access_logs.append(custom_log_path)
    error_logs.append(error_log_path)


if __name__ == "__main__":
    '''
    About Apache Logging:
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
    This has a drawback. In case one wants to do a custom logging for a virtual host then this logging would be suppressed.

    About this script:
    Considerations:
        Admins are enabled to log in their desired format to a different location.
        If a log is defined to log at a custom location with our standard pattern that can be used for rsyslog too.
        But this aproach can cause issues if logging was defined to a pipe rather than a file. So the script adds logging to standard location.
    
    It does not overwrites any predefined logging.
    It adds access logging and error logging per virtual host.
    The paths are log/access.log and log/error.log relative to DocumentRoot/(ServerName or ServerAlias)
    Creates DocumentRoot/(ServerName or ServerAlias)/log if not exists and adds necessary permissions to the directory.
    If either of ServerName and ServerAlias are not defined path is DocumentRoot/logs/log
    
    If no virtualhost is defined then logging is configured in root httpd.conf file.
    This means that requests would be logged in _two_ error log files and _two_ access log files
    as there would already be a default log definition.

    Log format:
    Virtual host name is also logged so it can be extracted with logstash. This way log parsing config would still work if 
    the server admin later decides to go with single logging approach.
    A logformat would be overwritten with our standard log format only if it was defined with name tgrc_log_format.
    
    Error Logs take all the formats defined, so it's hard to determine which format is being used. https://httpd.apache.org/docs/2.4/mod/core.html#errorlogformat
    It's possible to enforce an error logging pattern only by removing all errorlogformats and using our standard only.
    
    Currently, we just add a standard error logging pattern and log to standard error log location.

    Collecting Apache Logs:
    Rsyslog can be configured just to read all apache logs and forward them to centrallized location with the tag of apache.
    It can also be configured to pre-parse it and send data in structured format.


    Tests:
    1. Overwrites tgrc_log_format LogFormat with standard one.
    2. Inserts tgrc_std_log_format, tgrc_std_custom_log, tgrc_std_error_log if either are absent in Virtual hosts section.
    3. Inserts tgrc_std_log_format, tgrc_std_custom_log, tgrc_std_error_log in root config.
    '''

    os_type = 'centos'
    root_dir = options[os_type]['root_path']
    # The config files that need to be updated i.e. configure logging for the VirtualHost
    confs_to_update = {}
    master_config_path = os.path.join(root_dir, 'conf/httpd.conf')

    conf_paths = identify_extra_config_paths(master_config_path)
    conf_paths.append(master_config_path)
    root_config = {}
    access_logs = []
    error_logs = []

    for path in conf_paths:
        virtual_host_configs = get_virtual_hosts(path)
        root_config = get_root_settings(path)
        if virtual_host_configs:
            confs_to_update[path] = virtual_host_configs
    # there is no virtual host update the master config
    import json
    print(json.dumps(root_config, indent=2))
    print('updating root config')
    lines = read_lines(master_config_path)
    # Assign line number in the file before which standard logging should be added
    root_config['end_index'] = len(lines)
    check_updation(lines, access_logs, error_logs, root_config)
    write_lines(master_config_path, lines)
    if len(confs_to_update.keys()) > 0:
        import json
        print(json.dumps(confs_to_update, indent=2))

        for conf_path in confs_to_update.keys():
            lines = read_lines(conf_path)
            virtual_hosts = confs_to_update[conf_path]
            for virtual_host in virtual_hosts:
                check_updation(lines, access_logs, error_logs,
                               virtual_host, root_config)

            # Update the config file at conf_path
            write_lines(conf_path, lines)
    print('access_log', access_logs)
    print('error_logs', error_logs)
    # create directory and add permission
    for access_log in access_logs:
        pass
    # for error_log in error_logs:
    # Add to rsyslog
