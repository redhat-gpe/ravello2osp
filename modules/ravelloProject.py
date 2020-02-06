from ravello_sdk import *
import sys
from os import path


class ravelloProject:
    def __init__(self, args, client):
        self.client = client
        # self.src_bp = "EXPORT-RAVELLO-DISKS-V3-BP"
        self.src_bp = args["src_bp"]
        self.debug = args["debug"]
        self.app_name = args["name"]
        self.published = False
        self.bp = self.client.get_blueprints(filter={"name": self.src_bp})[0]
        self.pub_key = args["pubkeyfile"]
        self.vm_info = {}
        self.created = {}
        if self.debug:
            print("Variables: src_bp: %s - app_name: %s - pub_key: %s" % (self.src_bp, self.app_name, self.pub_key))

    def create_application(self):
        if not self.app_name:
            print("You have to use --name option")
            sys.exit(-1)

        try:
            self.created = self.client.get_application_by_name(self.app_name)
            print("Using %s as exporter server" % self.app_name)
            self.published = True
        except RavelloError as e:
            print("Creating %s as exporter server" % self.app_name)
            self.created = self.client.create_application( {"name": self.app_name, "description": "Based on BP %s" % self.src_bp, "baseBlueprintId": self.bp["id"]})
            self.published = False

        appid = self.created["id"]
        vmid = self.created["design"]["vms"][0]["id"]
        self.vm_info = self.created["design"]["vms"][0]
        dns = self.created["design"]["vms"][0]["networkConnections"][0]["ipConfig"]["fqdn"]
        # vm = self.client.get_vm(appid, vmid)
        print("App id: %s\nVM id: %s\nDNS: %s" % (appid, vmid, dns))

        if self.pub_key:
            pubkeyfile = self.pub_key
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
                self.created["design"]["vms"][0]["userData"] = userData
                self.client.update_application(self.created)
            else:
                print("Error, cannot find specified public key file %s!  Exiting." % (pubkeyfile))
                sys.exit(-1)

        if not self.published:
            print("Publishing %s" % self.app_name)
            self.client.publish_application(self.created, {"startAllVms": False})

    def get_export_hostname(self):
        return self.vm_info["networkConnections"][0]["ipConfig"]["fqdn"]

    def get_vm_exporter(self):
        self.create_application()
        return self.created