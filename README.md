ansible-joyent-inventory
========================

Ansible dynamic inventory script

### Dependencies: 

* [smartdc](https://pypi.python.org/pypi/smartdc)

```sh
pip install -r requirements.txt
```

### Install
- Put it the file in your ansible directory 
- Configure the following environmental variables 

```sh
JOYENT_USERNAME	Your joyent user name
JOYENT_KEYNAME	Your joyent key name
joyent_location	Joyent data ceneter hostname  
```
- Your ssh key located in your **~/.ssh/id.rsa**

### Usage:

```sh
python joyent.py --list
python joyent.py --host <HOSTNAME>
```

