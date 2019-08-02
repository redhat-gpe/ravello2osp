from ravello_sdk import *
import json
import time
from jinja2 import Environment, FileSystemLoader
import argparse
import os,sys
debug = False
options = argparse.ArgumentParser()
options.add_argument("-bp", "--blueprint", required=True, help="Name of the blueprint")
options.add_argument("-o", "--output", required=True, help="Output directory")
options.add_argument("-u", "--user", required=True, help="Ravello domain/username")
options.add_argument("-p", "--password", required=True, help="Ravello password")

args = vars(options.parse_args())

output_dir = os.path.realpath(args["output"])

if not os.path.exists(output_dir):
  try:
      os.mkdir(output_dir)
  except OSError:
      print ("Creation of the directory %s failed" % output_dir)
      sys.exit(-1)

file_loader = FileSystemLoader("templates")

bpname = args["blueprint"]

client = RavelloClient()
client.login(args["user"], args["password"])
bp = client.get_blueprints(filter={"name": bpname})[0]
config = client.get_blueprint(bp["id"])
network_config = config["design"]["network"]
vms_config = config["design"]["vms"]

if debug:
  print("Name: %s Description: %s" % (bpname, bp["description"]))
  print("Tags", config["design"]["tags"])


env = Environment(loader=file_loader)
header = env.get_template('header.j2')
stack_admin = header.render()
stack_user = header.render()
tplproject = env.get_template('project.j2')
stack_admin += tplproject.render()

print("INFO: Generated %s" % (output_dir + "/stack_admin.yaml"))
fp = open(output_dir + "/stack_admin.yaml", "w")
fp.write(stack_admin)
fp.close()



disks_created=[]
networks = []

def get_network_name_from_segment_id(id):
  for switch in network_config["switches"]:
    for segment in switch["networkSegments"]:
      if segment["id"] == id:
        if (segment["vlanId"] != 1):
          return "%s_vlan%s" % (switch["name"], segment["vlanId"])
        else:
          return switch["name"]

def generate_networks():
  global stack_user
  global networks
  for switch in network_config["switches"]:
    for segment in switch["networkSegments"]:
      if (segment["vlanId"] != 1): #TODO
        network = "%s_vlan%s" % (switch["name"], segment["vlanId"]) 
        if debug:
          print("Create network %s_vlan%s" % (switch["name"], segment["vlanId"]))
      else:
        network = switch["name"]
        if debug:
          print("Create network %s" % switch["name"])
      networks.append(switch["name"])
      tplnetwork = env.get_template('network.j2')
      stack_user += tplnetwork.render(name=network )


def generate_subnets():
  global stack_user
  global networks
  subnets_networks=[]
  for subnet in network_config["subnets"]:
    network = get_network_name_from_segment_id(subnet["networkSegmentId"])
    subnets_networks.append(network)
    gw = get_gateway(subnet["ipConfigurationIds"])
    if debug:
      print("Create subnet %s/%s on network %s" % (subnet["net"], subnet["mask"],get_network_name_from_segment_id(subnet["networkSegmentId"])))
      print("Gateway: %s" % (get_gateway(subnet["ipConfigurationIds"])))
    netmask = str(sum(bin(int(x)).count('1') for x in subnet["mask"].split('.')))
    tplsubnet = env.get_template('subnet.j2')
    stack_user += tplsubnet.render(name="sub-" + network, cidr=subnet["net"]+ "/" + netmask, gateway=gw, net=network)
  for network in list(set(networks) - set(subnets_networks)):
    tplsubnet = env.get_template('subnet.j2')
    stack_user += tplsubnet.render(name="sub-" + network, cidr="1.1.1.1/8", gateway="", net=network)

def get_gateway(configIds):
    for ipconfig in configIds:
      for interfaces in network_config["services"]["networkInterfaces"]:
        for ifconfig in interfaces["ipConfigurations"]:
          if ifconfig["id"] == ipconfig:
            if not is_dns_server_ip(ifconfig["id"]):
              return ifconfig["staticIpConfig"]["ip"]

def is_dns_server_ip(id):
  for dns_servers in  network_config["services"]["dnsServers"]:
    if id in dns_servers["ipConfigurationIds"]:
      return True



def find_subnet_from_rourter_if(id):
  for subnet in network_config["subnets"]:
    for configId in subnet["ipConfigurationIds"]:
      if configId == id:
        return get_network_name_from_segment_id(subnet["networkSegmentId"])

def generate_routers():
  i=0
  global stack_user
  for router in network_config["services"]["routers"]:
    if debug:
      print("Create Router%s" % i)
    ports = []
    for ipconfig in router["ipConfigurationIds"]:
      for interfaces in network_config["services"]["networkInterfaces"]:
        for ifconfig in interfaces["ipConfigurations"]:
          if ifconfig["id"] == ipconfig:
            network = find_subnet_from_rourter_if(ipconfig)
            ports.append({"ip": ifconfig["staticIpConfig"]["ip"], "net": network, "subnet": "sub-" + network })
    tplrouter= env.get_template('router.j2')
    stack_user += tplrouter.render(name="Router%s" % i, interfaces=ports)
    i=i+1

# TODO: Search for bootable

def get_root_disk_size(vm):
  for disk in vm["hardDrives"]:
    if disk["index"] == 0 and disk["type"] == "DISK":
      return disk["size"]["value"]

  for disk in vm["hardDrives"]:
    if disk["index"] == 1 and disk["type"] == "DISK":
      return disk["size"]["value"]

def get_root_disk_name(vm):
  for disk in vm["hardDrives"]:
    if disk["index"] == 0 and disk["type"] == "DISK":
      return disk["name"]

  for disk in vm["hardDrives"]:
    if disk["index"] == 1 and disk["type"] == "DISK":
      return disk["name"]


def find_device_network(id):
  for switch in network_config["switches"]:
    for port in switch["ports"]:
      if port["deviceId"] == id:
        return get_network_name_from_segment_id(port["networkSegmentReferences"][0]["networkSegmentId"])


def get_port_ip_address(id):
  for dhcp in network_config["services"]["dhcpServers"]:
    for ip in dhcp["reservedIpEntries"]:
      if ip["ipConfigurationId"] == id:
        return ip["ip"]

    
def generate_vms():
  global stack_user
  global disks_created
  flavors = {}
  vms = {}
  networks = {} 
  trunks = {} 
  for vm in vms_config:
    memorymb = vm["memorySize"]["value"]*1024 if (vm["memorySize"]["unit"]=="GB") else vm["memorySize"]["value"]
    root_disk_size = get_root_disk_size(vm)
    name_flavor = "CPU_%s_Memory_%s_Disk_%s" % (vm["numCpus"], memorymb, root_disk_size)
    flavors[name_flavor] = {"cpu": vm["numCpus"], "memory": memorymb, "disk": root_disk_size}
    if debug:
      print("Create VM %s with flavor %s" % (vm["name"], name_flavor))
    networks[vm["name"]] = []
    trunks[vm["name"]] = []
    for network in sorted(vm["networkConnections"], key=lambda k: k["device"]["index"]):
      ip_address = get_port_ip_address(network["ipConfig"]["id"]) if "ipConfig" in network else ""
      if debug:
        print("Create network device with mac %s on network %s with ip %s" 
          % (network["device"]["mac"], find_device_network(network["id"]),ip_address))
      networks[vm["name"]].append({"mac": network["device"]["mac"], 
         "network": find_device_network(network["id"]),
         "ip_address": ip_address,
         "index": network["device"]["index"]
          })
      if "ipConfig" in network:
        if network["ipConfig"]["hasPublicIp"]:
          print("TODO: Create floating IP for VM %s" % vm["name"]) # TODO
      if "vlanInterfaces" in network:
        trunks[vm["name"]].append({"mac": network["device"]["mac"], 
           "network": find_device_network(network["id"]),
           "ip_address": ip_address,
           "subports": network["vlanInterfaces"],
           "index": network["device"]["index"]
           })
    disks = []
    for disk in sorted(vm["hardDrives"], key=lambda k: k["index"]):
      if disk["type"] == "DISK":
        size = disk["size"]["value"]*1024 if (disk["size"]["unit"]=="GB") else disk["size"]["value"]
        if debug:
          print("Add disk %s" % (disk["name"]))
        disks.append({"name": disk["name"], "size": size, "id": disk["id"], "vm": vm["name"]})
      else:
        print("Add cdrom %s" % (disk["name"]))
      diskimagename="%s-%s" % (vm["name"], disk["name"])
      bpdisk = client.get_diskimages(filter={"name": diskimagename})
      if bpdisk:
        client.delete_diskimage(bpdisk[0]["id"])
      disks_created.append(client.create_diskimage({"diskId": disk["id"], "vmId": vm["id"], "diskImage": { "name": diskimagename}, "applicationId": bp["id"], "blueprint": "true", "offline": "false"}))

    vms[vm["name"]] = {"flavor": name_flavor, "network": networks, "disk": disks, "vm": vm}
  for flavor,res in flavors.items():
    tplflavor = env.get_template('flavor.j2')
    stack_user += tplflavor.render(name=flavor, cpu=res["cpu"], memory=res["memory"], disk=res["disk"])

  for vm,data in networks.items():
    i=0
    for vmnetwork in data: 
      tplport= env.get_template('port.j2')
      stack_user += tplport.render(name="%s-%d" % (vm, vmnetwork["index"]), mac=vmnetwork["mac"], 
        network=vmnetwork["network"], ip_address=vmnetwork["ip_address"])
      i=i+1
  for vm,data in trunks.items():
    for vmnetwork in data: 
      tpltrunk = env.get_template('trunk.j2')
      stack_user += tpltrunk.render(name="%s-%d" % (vm, vmnetwork["index"]), mac=vmnetwork["mac"], 
        network=vmnetwork["network"],subports=vmnetwork["subports"])

  for vm,data in vms.items():
    tplvm = env.get_template('server.j2')
    stack_user += tplvm.render(name=vm, flavor=data["flavor"], nics=networks[vm], root_disk=get_root_disk_name(data["vm"]))


generate_networks()
generate_subnets()
generate_routers()
generate_vms()

print("INFO: Generated %s" % (output_dir + "/stack_user.yaml"))
fp = open(output_dir + "/stack_user.yaml", "w")
fp.write(stack_user)
fp.close()

vm_id = 3895024678045852
app = client.get_application(3125680014112)
vm = client.get_vm(3125680014112,3895024678045852,'deployment')
if vm["state"] == 'STARTED':
  client.stop_vm(app, vm)
  while vm["state"] != "STOPPED":
    print("Waiting till VM is stopped")
    vm = client.get_vm(3125680014112,3895024678045852,'deployment')
    time.sleep(30)

# Remove current disks

if len(vm["hardDrives"]) > 1:
  root_disk = vm["hardDrives"][0]
  vm["hardDrives"] = [root_disk]
  client.update_vm(app, vm)
  client.publish_application_updates(app)

# Add new disks
i=1
import_disks = []
for disk in disks_created:
  vm["hardDrives"].append({"name": disk["name"], "baseDiskImageId": disk["id"], "baseDiskImageName": disk["name"], "type": "DISK", "controllerIndex": i, "size": disk["size"], "controller": "VIRTIO"})
  import_disks.append({"device": "vd%s" % chr(97+i), "name":  disk["name"]})
  i=i+1
client.update_vm(app, vm)
client.publish_application_updates(app)
client.reload(vm)



tplimportdisks = env.get_template('import_disks.j2')
import_disks = tplimportdisks.render(disks=import_disks)

print("INFO: Generated %s" % (output_dir + "/playbook_import_disks.yaml"))
fp = open(output_dir + "/playbook_import_disks.yaml", "w")
fp.write(import_disks)
fp.close()

if vm["state"] == 'STOPPED':
  client.start_vm(app,vm)
  while vm["state"] != "STARTED":
    print("Waiting till VM is started")
    vm = client.get_vm(3125680014112,3895024678045852,'deployment')
    time.sleep(30)

 