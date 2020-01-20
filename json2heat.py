from jinja2 import Environment, FileSystemLoader
import json
import os,sys
import argparse
options = argparse.ArgumentParser()
options.add_argument("-j", "--jsonf", required=True, help="Json File")

debug = False
args = vars(options.parse_args())
json_file = args["jsonf"]
output_directory = json_file.split(".")
output_dir = os.path.realpath(output_directory[0])
file_loader = FileSystemLoader("templates")
env = Environment(loader=file_loader)
header = env.get_template('header.j2')
stack_user = header.render()

if not os.path.exists(output_dir):
  try:
      os.mkdir(output_dir)
  except OSError:
      print ("Creation of the directory %s failed" % output_dir)
      sys.exit(-1)


with open(json_file, 'r') as f:
  data_json = json.load(f)
#print(data_json)

#print(json.dumps(data_json["design"]["network"]["subnets"][0]["networkSegmentId"]))
#subnets = json.dumps(data_json["design"]["network"]["subnets"])
network_config = data_json["design"]["network"]
vms_config = data_json["design"]["vms"]

disks_created=[]
networks = []
subnets_and_networks={}

def get_network_name_from_segment_id(id):
  for switch in network_config["switches"]:
    for segment in switch["networkSegments"]:
      if segment["id"] == id:
        if (segment["vlanId"] != 1):
          return "%s_vlan%s" % (str(switch["id"]), segment["vlanId"])
        else:
          return str(switch["id"])

def gets_networks():
  global networks
  for switch in network_config["switches"]:
    for segment in switch["networkSegments"]:
      if (segment["vlanId"] != 1): #TODO
        network = "%s_vlan%s" % (str(switch["id"]), segment["vlanId"])
        if debug:
          print("Create network %s_vlan%s" % (str(switch["id"]), segment["vlanId"]))
      else:
        network = str(switch["id"])
        if debug:
          print("Create network %s" % str(switch["id"]))
      networks.append(str(switch["id"]))

def gets_subnets():
  global networks
  global subnets_and_networks
  num = 0
  for subnet in network_config["subnets"]:
    network = get_network_name_from_segment_id(subnet["networkSegmentId"])
    subnets_and_networks[network]=subnet["net"]

def change_id_names_and_generate_networks():
  global stack_user
  global networks
  global subnets_and_networks
  for switch in network_config["switches"]:
    if "172.25.250" in (subnets_and_networks[str(switch["id"])]):
      subnets_and_networks[str(switch["id"])] = "private"
    elif "172.25.252" in (subnets_and_networks[str(switch["id"])]):
      subnets_and_networks[str(switch["id"])] = "classroom"
    elif "10.1." in (subnets_and_networks[str(switch["id"])]):
      subnets_and_networks[str(switch["id"])] = "external"

    tplnetwork = env.get_template('network.j2')
    stack_user += tplnetwork.render(name=subnets_and_networks[str(switch["id"])])

  subnets_networks=[]
  for subnet in network_config["subnets"]:
    network = get_network_name_from_segment_id(subnet["networkSegmentId"])
    subnets_networks.append(network)
    gw = get_gateway(subnet["ipConfigurationIds"])
    netmask = str(sum(bin(int(x)).count('1') for x in subnet["mask"].split('.')))
    tplsubnet = env.get_template('subnet.j2')
    stack_user += tplsubnet.render(name="sub-" + subnets_and_networks[network], cidr=subnet["net"]+ "/" + netmask, gateway=gw, net=subnets_and_networks[network])

def get_gateway(configIds):
    for ipconfig in configIds:
      for interfaces in network_config["services"]["networkInterfaces"]:
        for ifconfig in interfaces["ipConfigurations"]:
          if ifconfig["id"] == ipconfig:
            if not is_dns_server_ip(ifconfig["id"]):
              return ifconfig["staticIpConfig"]["ip"]

def is_dns_server_ip(id):
  try:
    for dns_servers in  network_config["services"]["dnsServers"]:
      if id in dns_servers["ipConfigurationIds"]:
        return True
  except KeyError:
    dns_servers = []

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
            ports.append({"ip": ifconfig["staticIpConfig"]["ip"], "net": subnets_and_networks[str(network)], "subnet": "sub-" + network })
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
  try:
    for dhcp in network_config["services"]["dhcpServers"]:
      for ip in dhcp["reservedIpEntries"]:
        if ip["ipConfigurationId"] == id:
          return ip["ip"]
  except KeyError:
    ip = []


def generate_vms():
  global subnets_and_networks
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
          images.append({"name": disk["name"], "size": size, "id": disk["id"], "vm": vm["name"]})
        else:
          volumes.append({"name": disk["name"], "size": size, "id": disk["id"], "vm": vm["name"]})
      else:
        print("Add cdrom %s" % (disk["name"]))
        images.append({"name": disk["name"], "size": size, "id": disk["id"], "vm": vm["name"]})
        cdrom = disk["name"]
        #voltype="image"
      diskimagename="%s-%s" % (vm["name"], disk["name"])
   
    vmdesc = ""
    if "description" in vm:
      vmdesc = vm["description"]
    vmuserdata = ""
    if "userData" in vm:
      vmuserdata = vm["userData"]
    vms[vm["name"]] = {"flavor": name_flavor, "network": networks, "volumes": volumes, "images": images, "vm": vm, "description": vmdesc, "userdata": vmuserdata, "cdrom": cdrom}
   

  for flavor,res in flavors.items():
    tplflavor = env.get_template('flavor.j2')
    stack_user += tplflavor.render(name=flavor, cpu=res["cpu"], memory=res["memory"], disk=res["disk"])

  for vm,data in networks.items():
    i=0
    for vmnetwork in data:
      tplport= env.get_template('port.j2')
      stack_user += tplport.render(name="%s-%d" % (vm, vmnetwork["index"]), mac=vmnetwork["mac"],
        network=subnets_and_networks[str(vmnetwork["network"])], ip_address=vmnetwork["ip_address"])
      i=i+1
  for vm,data in trunks.items():
    for vmnetwork in data:
      tpltrunk = env.get_template('trunk.j2')
      stack_user += tpltrunk.render(name="%s-%d" % (vm, vmnetwork["index"]), mac=vmnetwork["mac"],
        network=vmnetwork["network"],subports=vmnetwork["subports"])

  for vm,data in vms.items():
    tplvm = env.get_template('server.j2')
    stack_user += tplvm.render(name=vm, flavor=data["flavor"], nics=networks[vm], root_disk=get_root_disk_name(data["vm"]))

  for vm, data in vms.items():
    for volume in data["volumes"]:
      tplvol = env.get_template('volume.j2')
      stack_user += tplvol.render(vm=volume["vm"], volume=volume["name"])


gets_networks()
gets_subnets()
change_id_names_and_generate_networks()
generate_routers()
generate_vms()

print("INFO: Generated %s" % (output_dir + "/stack_user.yaml"))
fp = open(output_dir + "/stack_user.yaml", "w")
fp.write(stack_user)
fp.close()

#print("NETS: %s" % networks)
#print("SUB y NETS: %s" % subnets_and_networks)
