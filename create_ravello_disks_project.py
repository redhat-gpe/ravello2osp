from ravello_sdk import *
import json
import time
from jinja2 import Environment, FileSystemLoader
import argparse
import os,sys
import os.path
from os import path
debug = False
bpname = "EXPORT-RAVELLO-DISKS-BP"
options = argparse.ArgumentParser()
options.add_argument("-n", "--name", required=True, help="Name of the app")
options.add_argument("-u", "--user", required=True, help="Ravello domain/username")
options.add_argument("-p", "--password", required=True, help="Ravello password")
options.add_argument("-bp", "--bpname", required=False, help="Ravello bp to be used (instead default EXPORT-RAVELLO-DISKS-BP)")
options.add_argument("--pubkeyfile", required=False, help="Public SSH key file to inject into export host")

args = vars(options.parse_args())

if args["bpname"]:
  bpname = args["bpname"]

if not args["name"]:
  print ("You have to use --name option")
  sys.exit(-1)

  
if not args["user"] or not args["password"]:
  print ("You have to use --user and --password with --blueprint")
  sys.exit(-1)

client = RavelloClient()
client.login(args["user"], args["password"])
bp = client.get_blueprints(filter={"name": bpname})[0]

published = False

try:
  created = client.get_application_by_name(args["name"])
  published = True
except RavelloError as e:
 created = client.create_application(
   {"name": args["name"], "description": "Based on BP %s" % bpname, "baseBlueprintId": bp["id"]})

appid = created["id"]
vmid = created["design"]["vms"][0]["id"]
dns = created["design"]["vms"][0]["networkConnections"][0]["ipConfig"]["fqdn"]
vm = client.get_vm(appid, vmid)
print("App id: %s\nVM id: %s\nDNS: %s" % (appid, vmid, dns))

if args["pubkeyfile"]:
  pubkeyfile = args["pubkeyfile"]
  if path.exists(pubkeyfile):
    print("Using public key file %s" % (pubkeyfile))
    try:
      f = open(pubkeyfile, "r")
    except:
      print("ERROR: Could not open public key file %s" % (pubkeyfile))
    try:
      pubkey = f.read()
    except:
      print("ERROR: Could not read public key file %s" % (pubkeyfile))
    if pubkey == "":
      print("ERROR: Public key is blank/unreadable. Exiting.")
      sys.exit(-1)
    userData = """#cloud-config
ssh_pwauth: False
disable_root: False
users:
  - name: root
    lock_passwd: false
    ssh_authorized_keys:
      - {key} 
chpasswd:
  list: |
    root:r3dh4t1!
  expire: False"
""".format(key=pubkey)
    created["design"]["vms"][0]["userData"] = userData
    client.update_application(created)
  else:
    print("Error, cannot find specified public key file %s!  Exiting." % (pubkeyfile))
    sys.exit(-1)

if not published:
  client.publish_application(created, {"startAllVms": False})
