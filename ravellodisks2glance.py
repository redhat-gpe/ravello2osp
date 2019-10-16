from ravello_sdk import *
import json
import time
from jinja2 import Environment, FileSystemLoader
import argparse
import os,sys
debug = False
options = argparse.ArgumentParser()
options.add_argument("-o", "--output", required=True, help="Output directory")
options_bp= options.add_argument_group()
options_bp.add_argument("-bp", "--blueprint", required=True, help="Name of the blueprint")
options_bp.add_argument("-u", "--user", required=True, help="Ravello domain/username")
options_bp.add_argument("-p", "--password", required=True, help="Ravello password")
options_bp.add_argument("-a", "--application", required=True, help="Ravello application")
options_bp.add_argument("-m", "--vm", required=True, help="Ravello VM in application")


args = vars(options.parse_args())

if not args["blueprint"]:
      print ("You have to use --blueprint option")
      sys.exit(-1)

  
if args["output"]:
  output_dir = os.path.realpath(args["output"])
else:
  print ("You have to use --output with --blueprint")
  sys.exit(-1)

if args["blueprint"]:
  if not args["user"] or not args["password"]:
      print ("You have to use --user and --password with --blueprint")
      sys.exit(-1)

if not os.path.exists(output_dir):
  try:
      os.mkdir(output_dir)
  except OSError:
      print ("Creation of the directory %s failed" % output_dir)
      sys.exit(-1)

file_loader = FileSystemLoader("templates")
disks_created=[]


if args["blueprint"]:
  bpname = args["blueprint"]
  client = RavelloClient()
  client.login(args["user"], args["password"])
  bp = client.get_blueprints(filter={"name": bpname})[0]
  config = client.get_blueprint(bp["id"])
else:
  json_file = args["jsonf"]
  config = json.loads(open(json_file,"r").read())
  bpname = config["name"]

network_config = config["design"]["network"]
vms_config = config["design"]["vms"]

def get_root_disk_size(vm):
  for disk in vm["hardDrives"]:
    if disk["boot"] and disk["type"] == "DISK":
      return disk["size"]["value"]

def get_root_disk_name(vm):
  for disk in vm["hardDrives"]:
    if disk["boot"] and disk["type"] == "DISK":
      return disk["name"]

def generate_disks():
  global disks_created
  vms = {}
  for vm in vms_config:
    root_disk_size = get_root_disk_size(vm)
    images = []
    volumes = []
    cdrom = ""
    for disk in sorted(vm["hardDrives"], key=lambda k: k["index"]):
      size = disk["size"]["value"]*1024 if (disk["size"]["unit"]=="GB") else disk["size"]["value"]
      voltype="volume"
      if disk["type"] == "DISK":
        if debug:
          print("Add disk %s" % (disk["name"]))
        if get_root_disk_name(vm) == disk["name"]:
          voltype="image"
      else:
        print("Add cdrom %s" % (disk["name"]))
        cdrom = disk["name"]
        #voltype="image"
      diskimagename="%s-%s" % (vm["name"], disk["name"])
      bpdisk = client.get_diskimages(filter={"name": diskimagename})
      if bpdisk:
        client.delete_diskimage(bpdisk[0]["id"])
      disks_created.append([voltype,client.create_diskimage({"diskId": disk["id"], "vmId": vm["id"], "diskImage": { "name": diskimagename}, "applicationId": bp["id"], "blueprint": "true", "offline": "false"})])
  return disks_created

print(generate_disks())

app_id = args["application"]
vm_id = args["vm"]
app = client.get_application(app_id)
vm = client.get_vm(app_id,vm_id,'deployment')
if vm["state"] == 'STARTED':
  client.stop_vm(app, vm)
  while vm["state"] != "STOPPED":
    print("Waiting till VM is stopped")
    vm = client.get_vm(app_id,vm_id,'deployment')
    time.sleep(30)

# Remove current disks

if len(vm["hardDrives"]) > 1:
  root_disk = vm["hardDrives"][0]
  vm["hardDrives"] = [root_disk]
  client.update_vm(app, vm)
  client.publish_application_updates(app)

# Add new disks
i=1
import_images = []
for voltype, disk in disks_created:
  print(disk)
  vm["hardDrives"].append({"name": disk["name"], "baseDiskImageId": disk["id"], "baseDiskImageName": disk["name"], "type": "DISK", "controllerIndex": i, "size": disk["size"], "controller": "VIRTIO"})
  import_images.append({"device": "vd%s" % chr(97+i), "name":  disk["name"], "size": disk["size"]["value"]})
  i=i+1
client.update_vm(app, vm)
client.publish_application_updates(app)
client.reload(vm)



tplimportdisks = env.get_template('import_disks.j2')
import_disks = tplimportdisks.render(images=import_images)

print("INFO: Generated %s" % (output_dir + "/playbook_import_disks.yaml"))
fp = open(output_dir + "/playbook_import_disks.yaml", "w")
fp.write(import_disks)
fp.close()

if vm["state"] == 'STOPPED':
  client.start_vm(app,vm)
  while vm["state"] != "STARTED":
    print("Waiting till VM is started")
    vm = client.get_vm(app_id,vm_id,'deployment')
    time.sleep(30)
