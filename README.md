ansible-joyent-inventory
========================

Ansible dynamic inventory script

### Dependencies: 

* [smartdc](https://pypi.python.org/pypi/smartdc) to use the tag grouping functionality use my fork (https://github.com/ahelal/py-smartdc/tree/feature/tags) 
* [daemonize](https://github.com/bmc/daemonize)

### Install
```sh
pip install -r requirements.txt
```
- Put it the file in your ansible directory 
- chmod +x joyent.ini

### Configure
- You can use *joyent.ini* or setup environment variable for all options. 
- Precedence will go to environmental variable



#### bash env setting
```sh
JOYENT_INV_AUTH_USERNAME (no default)
JOYENT_INV_AUTH_KEY_NAME (no default)
JOYENT_INV_CACHE_EXPIRE (default 300)
JOYENT_INV_CACHE_FILE (default /tmp/ansible_inventory_joyent.cache")
JOYENT_INV_URI (default "eu-ams-1.api.joyentcloud.com")
JOYENT_INV_AUTH_KEY (default ~/.ssh/id_rsa)
```

#### ini env setting
```sh
auth_username (no default)
auth_key (no default)
cache_expire (default 300)
cache_file (default /tmp/ansible_inventory_joyent.cache")
uri (default "eu-ams-1.api.joyentcloud.com")
auth_key (default ~/.ssh/id_rsa)
```


### Usage:

```sh
python joyent.py --list
python joyent.py --host <HOSTNAME>
```

