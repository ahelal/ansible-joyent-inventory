#!/usr/bin/env python
# Uses py-smartdc fork in https://github.com/ahelal/py-smartdc.git

import os
import sys
import ConfigParser
from daemonize import Daemonize
from datetime import datetime

__DEFAULT_CACHE_FILE__ = "/tmp/ansible_inventory_joyent.cache"
__DEFAULT_PID_FILE__ = "/tmp/ansible_inventory_joyent.pid"
__DEFAULT_ENV_PREFIX__ = "JOYENT_INV_"
__DEFAULT_CACHE_EXPIRE__ = 300
__DEFAULT_URL__ = "eu-ams-1.api.joyentcloud.com"
__DEFAULT_AUTH_KEY__ = "~/.ssh/id_rsa"
try:
    import json
except ImportError:
    import simplejson as json


def safe_fail_stderr(msg):
    # Print error and dont break ansible by printing an emtpy JSON
    print >> sys.stderr, msg
    print json.dumps(json.loads("{}"), indent=4, sort_keys=True)
    sys.exit(1)

try:
    from smartdc import DataCenter
except ImportError:
    # Print error but dont break ansible inventory
    safe_fail_stderr("Cant import DataCenter. Please install smartdc")


class JoyentInventory(object):
    def __init__(self):
        self.inventory = {}
        self.__get_config__()
        self.debug = False
        self.pid_file = __DEFAULT_PID_FILE__
        self.tag_ignore = ["provisioner_ver", "provisioner"]

    def __get_config__(self):
        # Read config
        self.config = ConfigParser.SafeConfigParser()
        my_name = os.path.abspath(sys.argv[0]).rstrip('.py')
        path_search = [my_name + '.ini', 'joyent.ini']
        for config_filename in path_search:
            if os.path.exists(config_filename):
                self.config.read(config_filename)
                break

        self.cache_smart = self._get_config('cache_smart', fail_if_not_set=False, default_value="true").lower() \
                             in ['true', '1', 't', 'y', 'yes', 'yeah', 'yup', 'certainly', 'uh-huh']

        self.cache_expire = int(self._get_config('cache_expire', fail_if_not_set=False, default_value=300))
        self.cache_file = self._get_config('cache_file', fail_if_not_set=False, default_value=__DEFAULT_CACHE_FILE__)
        self.joyent_uri = self._get_config('uri', fail_if_not_set=False, default_value=__DEFAULT_URL__)
        self.joyent_secret = self._get_config('auth_key',  fail_if_not_set=False, default_value=__DEFAULT_AUTH_KEY__)
        self.joyent_username = self._get_config('auth_username', fail_if_not_set=True)
        self.joyent_key_name = self._get_config('auth_key_name', fail_if_not_set=True)
        # Compile key id
        self.joyent_key_id = "/" + self.joyent_username + "/keys/" + self.joyent_key_name

    def _get_config(self, value, fail_if_not_set=True, default_value=None, value_type=None):
        # Env variable always win
        if os.getenv(__DEFAULT_ENV_PREFIX__ + value.upper(), False):
            return os.getenv(__DEFAULT_ENV_PREFIX__ + value.upper())
        try:
            if self.config.get('main', value, vars=False):
                return self.config.get('main', value)
        except ConfigParser.NoOptionError:
            pass
        if fail_if_not_set:
            print "Failed to get setting for '{}' from environment and ini file".format(value)
        else:
            return default_value

    def check_cache(self):
        ''' Checks if we can server from cache or API call '''

        try:
            stats = os.stat(self.cache_file)
        except:
            # No cache or cant read just get from API
            return self.build_inv_from_api()

        seconds_since_last_modified = (datetime.now() - datetime.fromtimestamp(stats.st_mtime)).total_seconds()
        if seconds_since_last_modified < self.cache_expire:
            # Get data from cache
            self.read_cache()
        else:
            if self.cache_smart:
                # Get data from cache
                self.read_cache()
            else:
                # Get data from API
                self.build_inv_from_api()

    def build_inv_from_api(self):
        servers = self.api_get()
        self.inventory["all"] = []
        self.inventory["hosts"] = {}
        my_meta_data = {}
        for server in servers:
            self.inventory["hosts"][server.name] = {}  # Init server
            # Groups Management
            groups = [server.type]
            try:
                if server.tags:
                    self.inventory["hosts"][server.name].update({"joyent_tags": server.tags})
                    # Convert tags into groups except for the ignored list item
                    for tag in server.tags:
                        if tag not in self.tag_ignore:
                            groups.append(server.tags[tag])
            except AttributeError, E:
                pass
                #print "error:", E

            for group in groups:
                if group not in self.inventory:
                    # Add to a group
                    self.inventory.update({group: []})
                self.inventory[group].append(server.name)
            # Add tp group all
            self.inventory["all"].append(server.name)
            # hosts Management
            if server.public_ips:
                ssh_connection = server.public_ips[0]
            elif server.private_ips:
                ssh_connection = server.private_ips[0]
            else:
                ssh_connection = server.name

            try:
                self.inventory["hosts"][server.name].update({"joyent_image": server.image,
                                                             "joyent_compute_node": server.compute_node,
                                                             "joyent_networks": server.networks,
                                                             "joyent_package": server.package})
            except AttributeError:
                pass

            self.inventory["hosts"][server.name].update({"joyent_id": server.id,
                                                         "joyent_public_ip": server.public_ips,
                                                         "joyent_private_ip": server.private_ips,
                                                         "ansible_ssh_host": ssh_connection})

            # SmartOS python
            if server.type == "smartmachine":
                self.inventory["hosts"][server.name]["ansible_python_interpreter"] = "/opt/local/bin/python"
            # Build meta
            my_meta_data.update({server.name: self.inventory["hosts"][server.name]})
        self.inventory.update({'_meta': {'hostvars': my_meta_data}})
        self.save_cache()

    def api_get(self):
        """ Ask Joyent for all servers in a data center"""
        sdc = DataCenter(location=self.joyent_uri, key_id=self.joyent_key_id, secret=self.joyent_secret,
                         allow_agent=True, verbose=self.debug)
        servers = sdc.machines()
        return servers

    def read_cache(self):
        try:
            with open(self.cache_file, 'r') as f:
                self.inventory = json.load(f)
        except IOError, e:
            safe_fail_stderr("read cache IO Error")

    def save_cache(self):
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.inventory, f)
        except IOError, e:
            safe_fail_stderr("save cache IO Error")

    def main(self):
        # Command line parser
        if len(sys.argv) == 2 and (sys.argv[1] == '--list'):
            self.check_cache()
            print json.dumps(self.inventory, indent=4)
        elif len(sys.argv) == 3 and (sys.argv[1] == '--host'):
            self.check_cache()
            print json.dumps(self.inventory["hosts"][sys.argv[2]], indent=4)
        else:
            print "Usage: %s --list or --host <hostname>" % sys.argv[0]
            sys.exit(1)
        sys.stdout.flush()
        sys.stderr.flush()
        # Update cache if we are using smart cache
        if self.cache_smart and not os.path.exists(self.pid_file):
            daemon = Daemonize(app="joyent_inv", pid=self.pid_file, action=self.build_inv_from_api)
            daemon.start()

        sys.exit(0)


if __name__ == '__main__':
    JoyentInventory().main()