#!/usr/bin/env python

import os
import sys
import time
import ConfigParser
import logging
import cPickle as pickle
from datetime import datetime

try:
    import json
except ImportError:
    import simplejson as json

def fail_stderr(msg):
    # Print error and dont break ansible by printing an emtpy JSON
    print >> sys.stderr, msg
    print json.dumps(json.loads("{ \"\":\"\" }"), indent=4, sort_keys=True)
    sys.exit(1)

try:
    from smartdc import DataCenter
except ImportError:
    ## Print error but dont break ansible inventory
    fail_stderr("Cant import DataCenter. Please install smartdc")


class JoyentInventory(object):

    def __init__(self):

        self.inventory = {}
        self.get_config()
        self.set_logger()

    def get_config(self):

        # Read config
        self.config = ConfigParser.SafeConfigParser()
        for config_filename in [os.path.abspath(sys.argv[0]).rstrip('.py') + '.ini', 'joyent.ini']:
            if os.path.exists(config_filename):
                self.config.read(config_filename)
                break
        self.cache_smart = self.config.getboolean('cache', 'cache_smart')
        self.cache_expire = self.config.getint('cache', 'cache_expire')
        self.cache_dir = self.config.get('cache', 'cache_dir')
        self.cache_file = self.cache_dir + "/ansible_joyent.cache"
        self.joyent_uri = self.config.get('api', 'uri')
        if self.config.get('auth', 'auth_type') == "key":
            self.joyent_secret = self.config.get('auth', 'auth_key')
            self.joyent_username = self.config.get('auth', 'auth_username')
            self.joyent_key_name = self.config.get('auth', 'auth_key_name')
            self.joyent_key_id = "/" + self.joyent_username + "/keys/" + self.joyent_key_name
        self.debug = False
        if self.config.has_option('defaults', 'debug'):
            self.debug = self.config.getboolean('defaults', 'debug')

    def set_logger(self):
        #Logging System
        self.logger = logging.getLogger("joyent")
        if self.debug:
            self.logger.setLevel(logging.DEBUG)
            handler = logging.FileHandler('hello.log')
            formatter = logging.Formatter('%(asctime)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        self.logger.debug("starting joyent inventory script")
        self.logger.debug("using the following file for cache %s" % self.cache_file)
        self.logger.debug("cache expire time %d" % self.cache_expire)
        self.logger.debug("using id_rsa: " + self.joyent_secret + " with '" + self.joyent_key_id + "'")


    def use_smart_cache(self):
        try:
            pid = os.fork()
            if pid > 0:
                return self.get_cache()
                # exit first parent
                ##sys.exit(0)
        except OSError, e:
            fail_stderr("use_smart_cache: fork #1 failed: %d (%s)" % (e.errno, e.strerror))


        # decouple from parent environment
        os.chdir("/")
        os.setsid()
        os.umask(0)

        # do second fork
        try:
            pid = os.fork()
            if pid > 0:
                # exit from second parent, print eventual PID before
                self.logger.debug("use_smart_cache: Daemon PID %d" % pid)
                sys.exit(0)
        except OSError, e:
            fail_stderr("use_smart_cache: fork #2 failed: %d (%s)" % (e.errno, e.strerror))

        ##
        # Redirect standard file descriptors
        if not self.debug:
            sys.stdin = open('/dev/null', 'r')
            sys.stdout = open('/dev/null', 'w')
            sys.stderr = open('/dev/null', 'w')
        self.build_inv_from_api()
        self.logger.debug("use_smart_cache:  PID %d is exiting" % pid)
        sys.exit(0)

    def check_cache(self):
        ''' Checks if we can server from cache or API call '''

        self.logger.debug("check_cache: my pid is %d" % os.getpid())
        try:
            stats = os.stat(self.cache_file)
        except:
            # No cache or cant read just get from API
            return self.build_inv_from_api()

        seconds_since_last_modified = (datetime.now() - datetime.fromtimestamp(stats.st_mtime)).total_seconds()
        self.logger.debug("check_cache: seconds since last modification %d", seconds_since_last_modified)

        if seconds_since_last_modified < self.cache_expire:
            self.logger.debug("check_cache: retrieving servers from cache.")
            return self.get_cache()
        else:
            self.logger.debug("check_cache: cache expired.")
            if self.cache_smart:
                self.logger.debug("check_cache: use smart cache.")
                return self.use_smart_cache()
            else:
                self.logger.debug("check_cache: dont use smart cache.")
                return self.build_inv_from_api()


    def build_inv_from_api(self):
        servers = self.api_get()
        self.inventory["all"] = []
        self.inventory["hosts"] = {}
        self.logger.debug("build_inv_from_api - initialised inventory: {}".format(self.inventory))
        for server in servers:
            ## Groups Management
            group = server.type
            if group is None:
                group = 'ungrouped'
            if not group in self.inventory:
                self.inventory.update({group: []})
            ## Add to a group and all
            self.inventory[group].append(server.name)
            self.inventory["all"].append(server.name)

            ## hosts Management
            ## hosts.update({server.name: []})
            if server.public_ips:
                ssh_connection = server.public_ips[0]
            elif server.private_ips:
                ssh_connection = server.private_ips[0]
            else:
                ssh_connection = server.name

            self.inventory["hosts"][server.name] = {"joyent_id": server.id,
                                  "joyent_public_ip": server.public_ips,
                                  "joyent_private_ip": server.private_ips,
                                  "ansible_ssh_host": ssh_connection}
            ##SmartOS python
            if server.type == "smartmachine":
                self.inventory["hosts"][server.name]["ansible_python_interpreter"] = "/opt/local/bin/python"
            ##hosts[server.name]["ansible_ssh_user"] = "root"

        self.logger.debug("build_inv_from_api - constructed inventory: {}".format(self.inventory))
        self.save_cache()


    def api_get(self):
        """ Ask Joyent for all servers in a data center"""
        self.logger.debug("API asking for servers from " + self.joyent_uri)
        sdc = DataCenter(location=self.joyent_uri, key_id=self.joyent_key_id, secret=self.joyent_secret, verbose=self.debug)
        servers = sdc.machines()
        self.logger.debug("API finished")
        return servers


    def get_cache(self):
        self.logger.debug("Reading from to cache... " + self.cache_file)
        try:
            with open(self.cache_file, 'r') as f:
                self.inventory = json.load(f)
        except IOError, e:
            fail_stderr("save cache IO Error")

    def save_cache(self):
        self.logger.debug("Writing to cache... " + self.cache_file)
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.inventory, f)
        except IOError, e:
            fail_stderr("save cache IO Error")

if __name__ == '__main__':

    joyent = JoyentInventory()

    ## Command line parser
    if len(sys.argv) == 2 and (sys.argv[1] == '--list'):
        joyent.check_cache()
        #print json.dumps(joyent.inventory, indent=4)
        sys.stdout.write(json.dumps(joyent.inventory, indent=4))
        sys.stdout.flush()
        ##print json.dumps(get_inventory(), indent=4)
    elif len(sys.argv) == 3 and (sys.argv[1] == '--host'):
        joyent.check_cache()
        print json.dumps(joyent.inventory["hosts"][sys.argv[2]], indent=4)
        #print json.dumps(get_host(sys.argv[2]), indent=4)
    elif len(sys.argv) == 2 and (sys.argv[1] == '--pint'):
        print json.dumps(joyent.build_inv_from_api(), indent=4)
    else:
        print "Usage: %s --list or --host <hostname>" % sys.argv[0]
        sys.exit(1)

    ##sys.stdout.write(str(inventory))
    ##sys.stdout.flush()

    joyent.logger.debug("Exiting...")
    sys.exit(0)