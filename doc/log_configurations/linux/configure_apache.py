import glob
import os
import re

# If using VirtualHosts
# look for LogFormat in VirtualHosts:
#   if not defined:
#       get DocumentRoot
#       get ServerName
#       get ServerAlias
#       define LogFormat as tgrc_apache_log_format
#       create DocumentRoot/log directory if not exists and execute
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
        if field in line:
            # getting the index of first space character
            # the word before it is the key and everything after is the value
            key = ''.join(line[:line.index(' ')]).strip()
            value = ''.join(line[line.index(' '):]).strip()
            dict_values[key] = value
    return dict_values


def read_lines(config_path):
    '''reads lines and strips them
    filters out the lines which start with # as they are comments
    '''
    with open(config_path) as config_file:
        orig_lines = config_file.readlines()
        lines = [line.strip() for line in orig_lines]
        lines = list(filter(lambda line: not line.startswith('#'), lines))
        return lines


def identify_extra_config_paths(config_path):
    '''fetches include paths in a config file
    '''
    lines = read_lines(config_path)
    # look for includes, which are references to files with more configuration info
    included_paths = []
    for line in lines:
        path = identify_abs_or_relative_path(line)
        if path is not None:
            # expand the path
            for expanded_path in glob.glob(path):
                paths = identify_extra_config_paths(expanded_path)
                included_paths.append(expanded_path)
                included_paths.extend(paths)
    return included_paths


def parse_config(config_path):
    lines = read_lines(config_path)
    # look for virtual hosts
    virtual_host_def_start = False
    virtual_hosts = []
    for line in lines:
        # There can be multiple VirtualHost definitions in one conf file.
        if line.startswith('<VirtualHost'):
            matched = re.search(r'^<VirtualHost\s+(.+)>$', line)
            '''If the regex matches, then it is added to virtual_host_config
             as 'name': <VirtualHost *:80>
            '''
            virtual_host_config = {
                'name': matched.group(1)
            }
            virtual_host_def_start = True
        if line.startswith('</VirtualHost>'):
            virtual_host_def_start = False
            virtual_hosts.append(virtual_host_config)
        if virtual_host_def_start:
            values = assign_values(line)
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
    for path in more_paths:
        virtual_host_configs = parse_config(path)
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
            with open(conf_path, 'r') as conf_file:
                conf_str = conf_file.read()
            with open(conf_path, 'w') as conf_file:
                modified_conf_str = conf_str
                # TODO
                # for each virtual host
                # add logic to insert LogFormat, CustomLog and ErrorLog
                conf_file.write(modified_conf_str)
            # TODO
            # create directory and add permission
            # make a rsyslog conf