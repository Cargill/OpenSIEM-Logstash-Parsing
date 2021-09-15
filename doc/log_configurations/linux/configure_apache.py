import re
import os

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

os_type =  'centos'
options = {
    'centos' : {
        'root_path' : '/etc/httpd/'
    }
}
root_dir = options[os_type]['root_path']
# for include_file in sorted(glob.glob(filepath)):
# included_paths may be a glob pattern conf.d/*.conf
included_paths = []
master_config_path = os.path.join(root_dir, 'conf/httpd.conf')

def get_included_paths(stripped_lines):
    # look for includes
    included_paths = []
    for line in stripped_lines:
        if line.startswith("IncludeOptional"):
            include_path = line.split("IncludeOptional")[1].strip()
            abs_include_path = ''
            if include_path.startswith("/"):
                # it's an absolute path
                abs_include_path = include_path
            else:
                # it's a relative path
                abs_include_path = os.path.join(root_dir, include_path)
            included_paths.append(abs_include_path)
    return included_paths

def parse_config(config_path):
    # returns a tuple of list of virtual_hosts definitions and list of includes path
    # parse this config and get all included paths
    with open(config_path) as config_path:
        virtual_hosts = []
        orig_lines = config_path.readlines()
        lines = [line.strip() for line in orig_lines]
        lines = list(filter(lambda line: not line.startswith('#'), lines))
        included_paths = get_included_paths(lines)
        # look for virtual hosts
        virtual_host_def_start = False
        for line in lines:
            if line.startswith('<VirtualHost'):
                matched = re.search('^<VirtualHost\s+(.+)>$', line)
                virtual_host_config = {
                    'name' : matched.group(1)
                }
                virtual_host_def_start = True
            if line.startswith('</VirtualHost>'):
                virtual_host_def_start = False
                virtual_hosts.append(virtual_host_config)
            if virtual_host_def_start:
                # We are interested in DocumentRoot, ServerName, ServerAlias, LogFormat, CustomLog, ErrorLog
                # getting the index of first space character
                # the word before it is the key and everything after is the value
                key = ''.join(line[:line.index(' ')]).strip()
                value = ''.join(line[line.index(' '):]).strip()
                virtual_host_config[key] = value

        return virtual_hosts, included_paths

confs_to_update = []
config_path = master_config_path
virtual_host_configs, more_paths = parse_config(config_path)
if virtual_host_configs:
    # if it has virtual_host_configs
    # add this config path to the list to update 
    confs_to_update.append(config_path)

print(more_paths)
print(virtual_host_configs)
