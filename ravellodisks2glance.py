from ravello_sdk import RavelloClient
import json
import time
from jinja2 import Environment, FileSystemLoader
import argparse
import os
import sys
debug = False
options = argparse.ArgumentParser()
options.add_argument("-o", "--output", required=True, help="Output directory")
options.add_argument("-bp", "--blueprint", required=True,
                     help="Name of the blueprint")
options.add_argument("-u", "--user", required=True,
                     help="Ravello domain/username")
options.add_argument("-p", "--password", required=True,
                     help="Ravello password")
options.add_argument("-a", "--application", required=True,
                     help="Ravello application")
options.add_argument("-m", "--vm", required=True,
                     help="Ravello VM in application")
options.add_argument("-s", "--offset", required=False,
                     help="From which disk number start to migrate disks")
options.add_argument("-dp", "--disk-prefix", required=False, default='',
                     help="Disk prefix to avoid moving around the work of others.")
options.add_argument("-i", "--image-format", required=False, default='raw',
                     help="Resulting image format (raw, qcow2).")
options.add_argument("-c", "--start-conv-character", required=False, default='a',
                     help="a-z, will proceed to convert devices at vd<character>. "
                          "Please note, anything other than 'a' will limit"
                          " the max number of disks to mount.")
options.add_argument("--host", required=True, 
                     help="Server to connect to export the disks")
options.add_argument("--osp-project", required=False, default='admin',
                     help="OpenStack project")
options.add_argument("--auth-url", required=True, 
                     help="OpenStack auth url, i.e: http://host:5000")
options.add_argument("--auth-user", required=True, 
                     help="OpenStack auth user")
options.add_argument("--auth-password", required=True, 
                     help="OpenStack auth password")

options.add_argument("--ibm-auth-endpoint",
                     help="IBM Auth Endpoint. default(https://iam.cloud.ibm.com/identity/token",
                     default="https://iam.cloud.ibm.com/identity/token")
options.add_argument("--ibm-endpoint", required=True,
                     help="IBM Cloud Storage endpoint")
options.add_argument("--ibm-api-key", required=True,
                     help="IBM API Key")
options.add_argument("--ibm-bucket-name", required=True,
                     help="Bucket name to store all images")
options.add_argument("--ibm-resource-id", required=True,
                     help="IBM Resource ID")

options.add_argument("-sv", "--single-vm", required=False, default=None,
                     help="Specify with VM name to only setup a single VM's disks.")

args = vars(options.parse_args())

if not args["blueprint"]:
    print("You have to use --blueprint option")
    sys.exit(-1)


if args["output"]:
    output_dir = os.path.realpath(args["output"])
else:
    print("You have to use --output with --blueprint")
    sys.exit(-1)

if args["blueprint"]:
    if not args["user"] or not args["password"]:
        print("You have to use --user and --password with --blueprint")
        sys.exit(-1)

if not os.path.exists(output_dir):
    try:
        os.mkdir(output_dir)
    except OSError:
        print("Creation of the directory %s failed" % output_dir)
        sys.exit(-1)

file_loader = FileSystemLoader("templates")
disks_created = []

auth_url = args['auth_url']
auth_user = args['auth_user']
auth_password = args['auth_password']
osp_project = args['osp_project']
exporterhost = args["host"]

ibm_api_key = args['ibm_api_key']
ibm_bucket_name =  args['ibm_bucket_name']
ibm_endpoint = args['ibm_endpoint']
ibm_auth_endpoint = args['ibm_auth_endpoint']
ibm_resource_id = args['ibm_resource_id']

disk_prefix = args['disk_prefix']
image_format = args['image_format']
start_conv_character = args['start_conv_character']
single_vm = args['single_vm']
max_mount_count = 25 - (ord(start_conv_character) - ord('a'))

bpname = args["blueprint"]
client = RavelloClient()
client.login(args["user"], args["password"])
bp = client.get_blueprints(filter={"name": bpname})[0]
config = client.get_blueprint(bp["id"])
env = Environment(loader=file_loader)

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
    # vms = {}
    for vm in vms_config:
        # root_disk_size = get_root_disk_size(vm)
        # images = []
        # volumes = []
        # cdrom = ""
        if single_vm is not None and vm['name'] != single_vm:
            print("We skip {} because it is not {}".format(vm['name'], single_vm))
            continue
        for disk in sorted(vm["hardDrives"], key=lambda k: k["index"]):
            # size = disk["size"]["value"] * \
            #     1024 if (disk["size"]["unit"] ==
            #              "GB") else disk["size"]["value"]
            voltype = "volume"
            if disk["type"] == "DISK":
                if debug:
                    print("Add disk %s" % (disk["name"]))
                if get_root_disk_name(vm) == disk["name"]:
                    voltype = "image"
            else:
                if debug:
                    # TODO
                    print("Add cdrom %s" % (disk["name"]))
                # cdrom = disk["name"]
                #continue
                voltype="cdrom"
                continue
                # voltype="image"
            if len(disk_prefix) > 0:
                diskimagename = '{}-{}'.format(disk_prefix, disk['baseDiskImageName'])
            else:
                diskimagename = "{}-{}".format(vm["name"], disk["name"])
            bpdisk = client.get_diskimages(filter={"name": diskimagename})
            if bpdisk:
                client.delete_diskimage(bpdisk[0]["id"])
            disks_created.append([vm["name"], voltype, client.create_diskimage({"diskId": disk["id"], "vmId": vm["id"], "diskImage": {
                                 "name": diskimagename}, "applicationId": bp["id"], "blueprint": "true", "offline": "false"})])
    return disks_created


generate_disks()

app_id = args["application"]
vm_id = args["vm"]
app = client.get_application(app_id)
vm = client.get_vm(app_id, vm_id, 'deployment')
if vm["state"] == 'STARTED':
    client.stop_vm(app, vm)
    while vm["state"] != "STOPPED":
        print("Waiting till VM is stopped")
        vm = client.get_vm(app_id, vm_id, 'deployment')
        time.sleep(30)

# Remove current disks
if len(vm["hardDrives"]) > 1:
    root_disk = vm["hardDrives"][0]
    vm["hardDrives"] = [root_disk]
    client.update_vm(app, vm)
    client.publish_application_updates(app)

print("Wait 10 seconds before add the disks to the VM")
time.sleep(10)
# Add new disks
i = 0
import_images = []
if args["offset"]:
    offset = int(args["offset"])
else:
    offset = 0

if len(disks_created) > max_mount_count:
    if not offset:
        print(
          ("WARNING: More than {mmc} disks in the blueprint, in total {disks_length} disks.\n"
           "Only {mmc} disks are going to be attached. \nRun the command again with the option"
           " --offset number to export the next {mmc}").format(mmc=max_mount_count, disks_length=len(disks_created))
        )

disks_created.sort(key=lambda e: e[2]['name'])
for vmname, voltype, disk in disks_created[offset:offset+max_mount_count]:
    vm["hardDrives"].append({"name": disk["name"], "baseDiskImageId": disk["id"], "baseDiskImageName": disk["name"],
                             "type": "DISK", "controllerIndex": i, "size": disk["size"], "controller": "VIRTIO"})
    import_images.append({"device": "vd{}".format(chr(ord(start_conv_character) + i)), "name":  disk["name"],
                          "size": disk["size"]["value"], "type": voltype})
    i = i+1
    while client.update_vm(app, vm) == None:
        next

while client.update_vm(app, vm) == None:
    next
client.publish_application_updates(app)
client.reload(vm)


tplimportdisks = env.get_template('import_disks.j2')
import_disks = tplimportdisks.render(
    images=import_images, project_name=bpname, format=image_format,
    auth_url=auth_url, auth_user=auth_user, auth_password=auth_password,
    osp_project=osp_project,ibm_api_key=ibm_api_key,ibm_bucket_name=ibm_bucket_name,
    ibm_endpoint=ibm_endpoint,ibm_auth_endpoint=ibm_auth_endpoint,ibm_resource_id=ibm_resource_id
)

print("INFO: Generated %s" % (output_dir + "/playbook_import_disks.yaml"))
fp = open(output_dir + "/playbook_import_disks.yaml", "w")
fp.write(import_disks)
fp.close()

print("INFO: Generated %s" % (output_dir + "/playbook_import_disks.hosts"))
fp = open(output_dir + "/playbook_import_disks.hosts", "w")
fp.write("[all]\n%s" % exporterhost)
fp.close()

sys.exit(0)
if vm["state"] == 'STOPPED':
    client.start_vm(app, vm)
    while vm["state"] != "STARTED":
        print("Waiting till VM is started")
        vm = client.get_vm(app_id, vm_id, 'deployment')
        time.sleep(30)
