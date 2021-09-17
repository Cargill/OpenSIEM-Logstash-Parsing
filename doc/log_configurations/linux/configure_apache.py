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
#       define CustomLog as DocumentRoot/log/requests.log and use tgrc_apache_log_format
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
    os_type = 'centos'
    root_dir = options[os_type]['root_path']
    # The config files that need to be updated i.e. configure logging for the VirtualHost
    confs_to_update = {}
    master_config_path = os.path.join(root_dir, 'conf/httpd.conf')

    more_paths = identify_extra_config_paths(master_config_path)
    more_paths.append(master_config_path)
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
            virtual_hosts = confs_to_update[conf_path]
            for virtual_host in virtual_hosts:
                # Check if CustomLog is defined
                # Check if ErrorLog is defined
                # Check if LogFormat is defined
                # Check if both these logs are using the correct log format
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
                    doc_root = '{}/{}'.format(
                        root_config['DocumentRoot'], dir_name)

                tgrc_std_custom_log = '{}/log/requests.log tgrc_log_format'.format(
                    doc_root)
                tgrc_std_error_log = '{}/log/error.log tgrc_log_format'.format(
                    doc_root)
                tgrc_std_log_format = '"%h %l %u %t \"%r\" %>s %b \"%{Referer}i\" \"%{User-Agent}i\" \"%{X-Forwarded-For}i\"" tgrc_log_format'
                try:
                    custom_log = virtual_host['CustomLog']
                    tgrc_std_custom_log = custom_log
                    # replacing
                except KeyError:
                    # inserting
                    pass
                try:
                    error_log = virtual_host['ErrorLog']
                    tgrc_std_error_log = error_log
                    # replacing
                except KeyError:
                    # inserting
                    pass
                try:
                    log_format = virtual_host['LogFormat']
                    tgrc_std_log_format = log_format
                    # replacing
                except KeyError:
                    # inserting
                    pass
            with io.open(conf_path, 'r') as conf_file:
                conf_str = conf_file.read()
            with io.open(conf_path, 'w', encoding='UTF-8') as conf_file:
                modified_conf_str = conf_str
                # TODO
                # for each virtual host
                # add logic to insert LogFormat, CustomLog and ErrorLog
                conf_file.write(modified_conf_str)
            # TODO
            # create directory and add permission
            # make a rsyslog conf
