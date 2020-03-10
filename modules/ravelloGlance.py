import time
from jinja2 import Environment, FileSystemLoader
import os
import sys
import json


class RavelloGlance():
    def __init__(self, args, client, exporter):
        self.file_loader = FileSystemLoader("templates")
        self.disks_created = []
        self.debug = args["debug"]
        self.auth_url = args['auth_url']
        self.auth_user = args['auth_user']
        self.auth_password = args['auth_password']
        self.osp_project = args['osp_project']
        self.offset = args["offset"]
        self.ibm_api_key = args['ibm_api_key']
        self.ibm_bucket_name = args['ibm_bucket_name']
        self.ibm_endpoint = args['ibm_endpoint']
        self.ibm_auth_endpoint = args['ibm_auth_endpoint']
        self.ibm_resource_id = args['ibm_resource_id']

        self.disk_prefix = args['disk_prefix']
        # self.image_format = args['image_format']
        self.start_conv_character = args['start_conv_character']
        self.single_vm = args['single_vm']
        self.max_mount_count = 25 - (ord(self.start_conv_character) - ord('a'))

        self.bpname = args["blueprint"]
        self.client = client
        self.bp = self.client.get_blueprints(filter={"name": self.bpname})[0]
        self.config = self.client.get_blueprint(self.bp["id"])
        self.env = Environment(loader=self.file_loader)

        self.network_config = self.config["design"]["network"]
        self.vms_config = self.config["design"]["vms"]
        self.output_dir = os.path.realpath(args["output"])
        self.exporter = exporter
        self.exporter_vm = self.exporter["design"]["vms"][0]
        self.importhost = args["importhost"]
        self.exporterhost = self.exporter_vm["networkConnections"][0]["ipConfig"]["fqdn"]

        self.app_id = self.exporter["id"]
        self.vm_id = self.exporter["design"]["vms"][0]["id"]
        self.app = self.client.get_application(self.app_id)
        self.vm = self.client.get_vm(self.app_id, self.vm_id, 'deployment')
        self.import_images = []

        if not os.path.exists(self.output_dir):
            try:
                os.makedirs(self.output_dir)
            except OSError:
                print("Creation of the directory %s failed" % self.output_dir)
                sys.exit(-1)

    def get_root_disk_size(vm):
        for disk in vm["hardDrives"]:
            if disk["boot"] and disk["type"] == "DISK":
                return disk["size"]["value"]

    def get_root_disk_name(self, vm):
        for disk in vm["hardDrives"]:
            if disk["boot"] and disk["type"] == "DISK":
                if "name" in disk:
                    return disk["name"]
                else:
                    return disk["baseDiskImageName"]

    def generate_disks(self):
        for vm in self.vms_config:
            if self.single_vm is not None and vm['name'] != self.single_vm:
                print("We skip {} because it is not {}".format(vm['name'], self.single_vm))
                continue
            for disk in sorted(vm["hardDrives"], key=lambda k: k["index"]):
                voltype = "volume"
                if disk["type"] == "DISK":
                    if self.debug:
                        print("Add disk %s" % (disk["name"]))
                    if "name" in disk:
                        if self.get_root_disk_name(vm) == disk["name"]:
                            voltype = "image"
                    else:
                        if self.get_root_disk_name(vm) == disk["baseDiskImageName"]:
                            voltype = "image"
                else:
                    if self.debug:
                        # TODO
                        print("Add cdrom %s" % (disk["name"]))
                    voltype="cdrom"
                    continue
                if len(self.disk_prefix) > 0:
                    diskimagename = '{}-{}'.format(self.disk_prefix, disk['baseDiskImageName'])
                else:
                    if "name" in disk:
                        diskimagename = "{}-{}".format(vm["name"], disk["name"])
                    else:
                        diskimagename = "{}-{}".format(vm["name"], disk["baseDiskImageName"].replace(".qcow", ""))
                bpdisk = self.client.get_diskimages(filter={"name": diskimagename})
                if bpdisk:
                    self.client.delete_diskimage(bpdisk[0]["id"])
                self.disks_created.append([vm["name"], voltype, self.client.create_diskimage({"diskId": disk["id"], "vmId": vm["id"], "diskImage": {
                                     "name": diskimagename}, "applicationId": self.bp["id"], "blueprint": "true", "offline": "false"})])
        self.prepare_vm()

    def prepare_vm(self):
        if self.vm["state"] != 'STOPPED':
            self.client.stop_vm(self.app, self.vm)
            while self.vm["state"] != "STOPPED":
                print("Waiting till VM is stopped")
                self.vm = self.client.get_vm(self.app_id, self.vm_id, 'deployment')
                time.sleep(30)

        # Remove current disks
        if len(self.vm["hardDrives"]) > 1:
            root_disk = self.vm["hardDrives"][0]
            self.vm["hardDrives"] = [root_disk]
            self.client.update_vm(self.app, self.vm)
            self.client.publish_application_updates(self.app)

        print("Wait 10 seconds before add the disks to the VM")
        time.sleep(10)

        i = 0

        if len(self.disks_created) > self.max_mount_count:
            if not self.offset:
                print(
                    ("WARNING: More than {mmc} disks in the blueprint, in total {disks_length} disks.\n"
                     "Only {mmc} disks are going to be attached. \nRun the command again with the option"
                     " --offset number to export the next {mmc}").format(mmc=self.max_mount_count,
                                                                         disks_length=len(self.disks_created))
                )

        self.disks_created.sort(key=lambda e: e[2]['name'])
        for vmname, voltype, disk in self.disks_created[self.offset:self.offset + self.max_mount_count]:
            print("Add disk %s to vm %s" % (disk["name"], vmname))
            self.vm["hardDrives"].append(
                {"name": disk["name"], "baseDiskImageId": disk["id"], "baseDiskImageName": disk["name"],
                 "type": "DISK", "controllerIndex": i, "size": disk["size"], "controller": "VIRTIO"})
            self.import_images.append({"device": "vd{}".format(chr(ord(self.start_conv_character) + i)), "name": disk["name"],
                                  "size": disk["size"]["value"], "type": voltype})
            i = i + 1
            while self.client.update_vm(self.app, self.vm) == None:
                next

        while self.client.update_vm(self.app, self.vm) == None:
            next
        self.client.publish_application_updates(self.app)
        self.client.reload(self.vm)
        self.generate_template()

    def generate_template(self):
        tplexportdisks = self.env.get_template('export_disks.j2')
        export_disks = tplexportdisks.render(images=self.import_images, project_name=self.bpname,
                                             ibm_api_key=self.ibm_api_key, ibm_bucket_name=self.ibm_bucket_name,
                                             ibm_endpoint=self.ibm_endpoint, ibm_auth_endpoint=self.ibm_auth_endpoint,
                                             ibm_resource_id=self.ibm_resource_id
        )

        print("INFO: Generated %s" % (self.output_dir + "/class_playbook_export_disks.yaml"))
        fp = open(self.output_dir + "/class_playbook_export_disks.yaml", "w")
        fp.write(export_disks)
        fp.close()

        tplimportdisks = self.env.get_template('import_disks.j2')
        import_disks = tplimportdisks.render(images=self.import_images, project_name=self.bpname,
                                             osp_auth_url=self.auth_url, osp_username=self.auth_user,
                                             osp_password=self.auth_password, osp_project=self.osp_project,
                                             ibm_api_key=self.ibm_api_key, ibm_bucket_name=self.ibm_bucket_name,
                                             ibm_endpoint=self.ibm_endpoint, ibm_auth_endpoint=self.ibm_auth_endpoint,
                                             ibm_resource_id=self.ibm_resource_id
        )

        print("INFO: Generated %s" % (self.output_dir + "/class_playbook_import_disks.yaml"))
        fp = open(self.output_dir + "/class_playbook_import_disks.yaml", "w")
        fp.write(import_disks)
        fp.close()

        print("INFO: Generated %s" % (self.output_dir + "/inventory"))
        fp = open(self.output_dir + "/inventory", "w")
        fp.write("[export]\n%s" % self.exporterhost)
        fp.write("\n[import]\n%s\n" % self.importhost)
        fp.close()

        if self.vm["state"] == 'STOPPED':
            self.client.start_vm(self.app, self.vm)
            while self.vm["state"] != "STARTED":
                print("Waiting till VM is started")
                self.vm = self.client.get_vm(self.app_id, self.vm_id, 'deployment')
                time.sleep(30)
