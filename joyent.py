#!/usr/bin/env python

import os
import sys
import time
import cPickle as pickle
from datetime import datetime

from smartdc import DataCenter
try:
    import json
except ImportError:
    import simplejson as json 

debug = False
SMART_CACHE = True # Fork a new process to get cache and serve from cache
CACHE_EXPIRATION_IN_SECONDS = 300
SERVER_FILENAME = "joyent_server_cache.txt"
##
PATH_TO_FILE = os.getenv('HELPER')
joyent_key_id = "/" + os.environ['JOYENT_USERNAME'] + "/keys/" + os.environ['JOYENT_KEYNAME']
joyent_secret = os.environ['HOME'] + "/.ssh/id_rsa"
joyent_api = ['JOYENT_API_URL']
joyent_location = "eu-ams-1.api.joyentcloud.com"

if PATH_TO_FILE and  os.path.isdir(PATH_TO_FILE) :
    SERVER_FILENAME = PATH_TO_FILE + "/" + SERVER_FILENAME

if debug:
    print SERVER_FILENAME

def getInventory():
    servers = getServers()
    inventory = {}
    for server in servers:
        group = server.type
        if group is None:
            group = 'ungrouped'
        if not group in inventory:
           inventory[group] = []
        inventory[group].append(server.name)
    return inventory

def getHost(hostname):
    servers = getServers()
    allhosts = {}
    for server in servers:
        ## How to connect
        if server.public_ips:
            ssh_connection = server.public_ips[0]
        elif server.private_ips:
            ssh_connection = server.private_ips[0]
        else:
            ssh_connection = server.name

        allhosts[server.name] = {
                                  "joyent_id": server.id,
                                  "joyent_public_ip": server.public_ips,
                                  "joyent_private_ip": server.private_ips,
                                  "ansible_ssh_host": ssh_connection
                                }
        ##SmartOS python
        if server.type == "smartmachine":
            allhosts[server.name]["ansible_python_interpreter"] = "/opt/local/bin/python"
	    allhosts[server.name]["ansible_ssh_user"] = "root"
    return allhosts.get(hostname)

def getServers():
    ## No cache just get from server
    if not os.path.isfile(SERVER_FILENAME):
        return retrieveServerList()
  
    stats = os.stat(SERVER_FILENAME)
    modification_time = stats.st_mtime
    seconds_since_last_modified = (datetime.now() - datetime.fromtimestamp(modification_time)).total_seconds()
    
    if debug:
        print seconds_since_last_modified

    if seconds_since_last_modified < CACHE_EXPIRATION_IN_SECONDS:
        if debug:
            print "retireving servers from cache..."
        return fetchServersFromCache()
    else:
        if SMART_CACHE: 
            ## fork a new process to get cache
            fork_pid = os.fork()
            if fork_pid == 0:
                os.chdir("/")
                os.setsid()
                os.umask(0)
                if debug:
                    print "Fork child getting cache..."
                retrieveServerList()
                sys.exit()
                if debug:
                    print "Fork child exit..."
            else:
                return retrieveServerList()
        else:
            return fetchServersFromCache()

def retrieveServerList():
    """ Check cache period either read from cache or call api
    """
    if debug:
        print "retireving servers from the API..."
    sdc = DataCenter(location=joyent_api, key_id=joyent_key_id, secret=joyent_secret, verbose=debug)
    servers = sdc.machines()
    storeServersToCache(servers)
    return servers

class MyServer(object):
    def __init__(self, name, type, public_ips, private_ips, id):
        self.name = name
        self.type = type
        self.id = id
        self.private_ips = private_ips
        self.public_ips = public_ips

def fetchServersFromCache():
    return pickle.load(open(SERVER_FILENAME, "rb"))

def storeServersToCache(servers):
    myservers = [MyServer(server.name, server.type, server.public_ips, server.private_ips, server.id) for server in servers]
    pickle.dump(myservers, open(SERVER_FILENAME, "wb"))

if __name__ == '__main__':
    if debug:
        print "using id_rsa" + joyent_secret + " with '" + joyent_key_id + "'"

    if len(sys.argv) == 2 and (sys.argv[1] == '--list'):
        print json.dumps(getInventory(), indent=4)
    elif len(sys.argv) == 3 and (sys.argv[1] == '--host'):
        print json.dumps(getHost(sys.argv[2]), indent=4)
    else:
        print "Usage: %s --list or --host <hostname>" % sys.argv[0]
        sys.exit(1)
    
    if debug:
       print "Exiting..."        
