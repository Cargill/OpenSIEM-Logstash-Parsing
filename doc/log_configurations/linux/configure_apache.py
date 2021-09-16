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


def assign_values(lines, num):
    '''We are interested in DocumentRoot, ServerName, ServerAlias, LogFormat, CustomLog, ErrorLog
    We are going to find the relevant fields up until the accompanying </VirtualHost> section
    '''
    dict_values = {}
    relevant_fields = ['DocumentRoot', 'ServerName',
                       'ServerAlias', 'LogFormat', 'CustomLog', 'ErrorLog']
    for l in range(num, len(lines)):
        if '</VirtualHost>' not in lines[l]:
            for field in relevant_fields:
                if field in lines[l]:
                    # getting the index of first space character
                    # the word before it is the key and everything after is the value
                    key = ''.join(lines[l][:lines[l].index(' ')]).strip()
                    value = ''.join(lines[l][lines[l].index(' '):]).strip()
                    dict_values[key] = value
                else:
                    pass
        else:
            # reached the end of the VirtualHost section
            break
    return dict_values


def read_lines(config_path):
    '''reads lines and strips them
    filters out the lines which start with # as they are comments
    '''
    print(config_path)
    with open(config_path) as config_file:
        orig_lines = config_file.readlines()
        lines = [line.strip() for line in orig_lines]
        lines = list(filter(lambda line: not line.startswith('#'), lines))
        return lines


def identify_extra_config_paths(config_path):
    '''fetches include paths in a config file
    TODO: Make recursive
    '''
    lines = read_lines(config_path)
    # look for includes, which are references to files with more configuration info
    included_paths = []
    for line in lines:
        path = identify_abs_or_relative_path(line)
        if path is not None:

            included_paths.append(path)
    return included_paths


def parse_config(config_path):
    lines = read_lines(config_path)
    # look for virtual hosts
    virtual_host_def_start = False
    virtual_hosts = []
    for idx in range(0, len(lines)):
        if lines[idx].startswith('<VirtualHost'):
            matched = re.search(r'^<VirtualHost\s+(.+)>$', lines[idx])
            '''If the regex matches, then it is added to virtual_host_config
             as 'name': <VirtualHost *:80>
            '''
            virtual_host_config = {
                'name': matched.group(1)
            }
            virtual_host_def_start = True
        if lines[idx].startswith('</VirtualHost>'):
            virtual_host_def_start = False
            virtual_hosts.append(virtual_host_config)
        if virtual_host_def_start:
            values = assign_values(lines, idx)
            virtual_host_config.update(values)
    return virtual_hosts


if __name__ == "__main__":
    os_type = 'centos'
    root_dir = options[os_type]['root_path']
    # for include_file in sorted(glob.glob(filepath)):
    # included_paths may be a glob pattern conf.d/*.conf
    included_paths = []
    # The config files that need to be updated i.e. configure logging for the VirtualHost
    confs_to_update = []
    master_config_path = os.path.join(root_dir, 'conf/httpd.conf')

    config_path = master_config_path
    more_paths = identify_extra_config_paths(config_path)
    if more_paths:
        for path in more_paths:
            additional_config = parse_config(path)
            included_paths.append(path)
    virtual_host_configs = parse_config(config_path)
    if virtual_host_configs:
        confs_to_update.append(config_path)

    print(more_paths)
    print(virtual_host_configs)
