# Alberto Gonzalez, GPTE Team <alberto.gonzalez@redhat.com>
# ChangeLog:
# - Version 0.1: Initial version, for testing
# - Version 0.2: Bug Fixes, new features

from jinja2 import Environment, FileSystemLoader
from netaddr import IPNetwork, IPAddress
import argparse
import base64
import json
import math
import os
import socket
import struct
import sys
from classes import *

try:
    from ravello_sdk import RavelloClient
    ravello_sdk_enabled = True
except ImportError:
    ravello_sdk_enabled = False


options = argparse.ArgumentParser()
options.add_argument("-n", "--nodesc", required=False, help="Skip VM Descriptions", action='store_true')
options.add_argument("-o", "--output", required=False, help="Output directory")
options.add_argument("-e", "--emptyvolumes", required=False,
                     help="True=Create Empty Volumes", action='store_true')
options_bp = options.add_argument_group()
options_bp.add_argument("-bp", "--blueprint",
                        required=False, help="Name of the blueprint")
options_bp.add_argument("-u", "--user", required=False,
                        help="Ravello domain/username")
options_bp.add_argument(
    "-p", "--password", required=False, help="Ravello password")
options_json = options.add_argument_group()
options_json.add_argument("-j", "--jsonf", required=False,
                          help="JSON file containing definition")
options_dns = options.add_argument_group()

options_dns.add_argument(
    "-dns", "--enabledns", required=False, help="Enable DNS", action='store_true')

options_dns.add_argument(
    "--dns-ip", required=False, help="Specify manually an IP for DNS server\
        instead auto-generated one")

options.add_argument(
    "--bootorder", required=False, help="Enable boot order. Options: signal or depends")

options.add_argument(
    "--ipmiserver", required=False, help="Specify the name of your IPMI VM")
options.add_argument("-d", "--debug", required=False,
                     help="Debug", action='store_true')

args = vars(options.parse_args())

debug = args["debug"]

if not args["jsonf"] and not args["blueprint"]:
    print("You have to use --jsonf or --blueprint options")
    sys.exit(-1)

emptyvolumes = args["emptyvolumes"]
enabledns = args["enabledns"]
ipmiserver = args["ipmiserver"]

json_file = args["jsonf"]

nodesc = args["nodesc"]

if args["output"]:
    output_dir = os.path.realpath(args["output"])
else:
    if not args["jsonf"]:
        print("You have to use --output with --blueprint")
        sys.exit(-1)
    output_directory = json_file.split(".")
    output_dir = os.path.realpath(output_directory[0])

if args["blueprint"]:
    if not args["user"] or not args["password"]:
        print("You have to use --user and --password with --blueprint")
        sys.exit(-1)

if args["bootorder"]:
    if args["bootorder"] not in ("signal", "depends"):
        print("Valid boot orders: signal or depends")
        sys.exit(-1)
bootordermode = args["bootorder"]
        

if not os.path.exists(output_dir):
    try:
        os.mkdir(output_dir)
    except OSError:
        print("Creation of the directory %s failed" % output_dir)
        sys.exit(-1)

file_loader = FileSystemLoader("templates")


if args["blueprint"]:
    if not ravello_sdk_enabled:
        print("Python module ravello_sdk is not installed in your environment.")
        sys.exit(-1)
    bpname = args["blueprint"]
    client = RavelloClient()
    client.login(args["user"], args["password"])
    bp = client.get_blueprints(filter={"name": bpname})[0]
    config = client.get_blueprint(bp["id"])
    fp = open(output_dir + "/blueprint.json", "w")
    fp.write(json.dumps(config, indent=2))
    fp.close()
else:
    config = json.loads(open(json_file, "r").read())
    bpname = config["name"]

network_config = config["design"]["network"]
vms_config = config["design"]["vms"]

if debug:
    print("Name: %s Description: %s" % (bpname, bp["description"]))
    if "tags" in config["design"]:
        print("Tags", config["design"]["tags"])


env = Environment(loader=file_loader)
header_admin = env.get_template('header_admin.j2')
header_user = env.get_template('header_user.j2')
stack_admin = header_admin.render()
stack_user = header_user.render()
tplproject = env.get_template('project.j2')
stack_admin += tplproject.render()


networks = []
fips = []
dnsports = {}
dnsnetwork = None
dnsip = args["dns_ip"]
bootorders = {}


def get_network_name_from_segment_id(id):
    for switch in network_config["switches"]:
        for segment in switch["networkSegments"]:
            key_use = 'name' if 'name' in switch else 'id'
            if segment["id"] == id:
                if (segment["vlanId"] != 1):
                    return "%s_vlan%s" % (switch[key_use], segment["vlanId"])
                else:
                    return switch[key_use]


def generate_networks():
    global stack_user
    global networks
    i = 0
    for switch in network_config["switches"]:
        for segment in switch["networkSegments"]:
            if (segment["vlanId"] != 1):  # TODO
                key_use = 'name' if 'name' in switch else 'id'
                network = Network("%s_vlan%s" % (switch[key_use], segment["vlanId"]))
                if debug:
                    print("Create network %s_vlan%s" %
                          (switch[key_use], segment["vlanId"]))
            else:
                if "name" not in switch:
                    switch["name"] = "Network" + str(i)
                    i += 1
                network = Network(switch["name"])
                if debug:
                    print("Create network %s" % switch["name"])
            
            networks.append(network.name)
            stack_user += network.generate_template(env)


def generate_dns():
    global stack_user
    global networks
    global dnsports
    global dnsnetwork
    entries = []
    for subnet in network_config["subnets"]:
        if enabledns and "ipConfigurationIds" in subnet and get_dns(subnet["ipConfigurationIds"]):
            # dns = get_dns(subnet["ipConfigurationIds"])
            dns_id = get_dns_id(subnet["ipConfigurationIds"])
            for entry in get_dns_entries(dns_id):
                if "ravcloud.com" not in entry["name"] and "A" == entry["type"]:
                    ipid = entry["ipConfigurationId"]

                    entries.append([entry["name"],
                                    "{get_attr: [%s-%s_port, fixed_ips, 0, ip_address]}" % (dnsports[ipid]["vm"], dnsports[ipid]["index"])])
    dnsserver = DnsServer(entries, dnsnetwork, dnsip)
    stack_user += dnsserver.generate_template(env)


def generate_subnets():
    global stack_user
    global networks
    global dnsnetwork
    global dnsip
    subnets_networks = []
    for subnet in network_config["subnets"]:
        network = get_network_name_from_segment_id(subnet["networkSegmentId"])
        subnets_networks.append(network)
        gw = ""
        if "ipConfigurationIds" in subnet:
            gw = get_gateway(subnet["ipConfigurationIds"])
        if debug:
            print("Create subnet %s/%s on network %s" %
                  (subnet["net"], subnet["mask"], get_network_name_from_segment_id(subnet["networkSegmentId"])))
            print("Gateway: %s" % (get_gateway(subnet["ipConfigurationIds"])))

        if (enabledns and not dnsip) and "ipConfigurationIds" in subnet and get_dns(subnet["ipConfigurationIds"]):
            dnsip = get_dns(subnet["ipConfigurationIds"])
            dnsnetwork = network
        else:
            if dnsip and IPAddress(dnsip) in IPNetwork("%s/%s" % (subnet["net"], subnet["mask"])):
                dnsnetwork = network

            

        cidr = IPNetwork('{net}/{mask}'.format(**subnet)).cidr
        dhcp = dhcpstart = dhcpend = False
        if "ipConfigurationIds" in subnet and is_dhcp(subnet["ipConfigurationIds"]):
            dhcp = True
            dhcpdata = is_dhcp(subnet["ipConfigurationIds"])
            dhcpstart = dhcpdata["poolStart"]
            dhcpend = dhcpdata["poolEnd"]
            excludedips = []
            if "excludedIpEntries" in dhcpdata:
                excludedips = [exclude["ip"]
                               for exclude in dhcpdata["excludedIpEntries"]]

            if "reservedIpEntries" in dhcpdata:
                excludedips += [exclude["ip"] 
                              for exclude in  dhcpdata["reservedIpEntries"]]

            def ip2int(ipstr): return struct.unpack(
                '!I', socket.inet_aton(ipstr))[0]

            def int2ip(n): return socket.inet_ntoa(struct.pack('!I', n))
            while dhcpstart in excludedips:
                ipint = ip2int(dhcpstart)
                dhcpstart = int2ip(ipint + 1)
            while dhcpend in excludedips:
                ipint = ip2int(dhcpend)
                dhcpend = int2ip(ipint - 1)

            if dnsip == gw:
                dnsip = dhcpstart
                ipint = ip2int(dhcpstart)
                dhcpstart = int2ip(ipint + 1)
        subnet = Subnet(name="sub-" + network, cidr=cidr, gateway=gw, network=network, \
            dnsip=dnsip, dhcp=dhcp, dhcpstart=dhcpstart, dhcpend=dhcpend)
        stack_user +=  subnet.generate_template(env)

    for network in list(set(networks) - set(subnets_networks)):
        subnet = Subnet(name="sub-" + network, cidr="1.1.1.1/8", gateway="", \
            network=network, dhcp=False, dnsip=dnsip)
        stack_user +=  subnet.generate_template(env)


def get_gateway(configIds):
    networkInterfaces = network_config["services"].get("networkInterfaces", None)
    if networkInterfaces is None:
        return ""
    for ipconfig in configIds:
        for interfaces in networkInterfaces:
            if "ipConfigurations" in interfaces:
                for ifconfig in interfaces["ipConfigurations"]:
                    if ifconfig["id"] == ipconfig:
                        if debug:
                            print(network_config["services"]["routers"])
                        if is_gateway_ip(ifconfig["id"]):
                            return ifconfig["staticIpConfig"]["ip"]
    return ""


def get_dns(configIds):
    for ipconfig in configIds:
        for interfaces in network_config["services"]["networkInterfaces"]:
            if "ipConfigurations" in interfaces: 
                for ifconfig in interfaces["ipConfigurations"]:
                    if ifconfig["id"] == ipconfig:
                        if debug:
                            print(network_config["services"]["routers"])
                        if is_dns_server_ip(ifconfig["id"]):
                            return ifconfig["staticIpConfig"]["ip"]
    return ""


def get_dns_id(configIds):
    for ipconfig in configIds:
        for interfaces in network_config["services"]["networkInterfaces"]:
            if "ipConfigurations" in interfaces:
                for ifconfig in interfaces["ipConfigurations"]:
                    if ifconfig["id"] == ipconfig:
                        if is_dns_server_ip(ifconfig["id"]):
                            return ifconfig["id"]
    return ""


def is_gateway_ip(id):
    if "routers" in network_config["services"]:
        for routers in network_config["services"]["routers"]:
            if id in routers["ipConfigurationIds"]:
                return True


def is_dhcp(ids):
    if "dhcpServers" in network_config["services"]:
        for dhcp in network_config["services"]["dhcpServers"]:
            if dhcp["ipConfigurationId"] in ids:
                return dhcp
    return None


def is_dns_server_ip(ip_conf_id):
    if "dnsServers" in network_config["services"]:
        for dns_servers in network_config["services"]["dnsServers"]:
            if ("ipConfigurationIds" in dns_servers and
                    ip_conf_id in dns_servers["ipConfigurationIds"]):
                return True
            # elif ("ipConfigurationIds" not in dns_servers and
            #         'entries' in dns_servers):
            #     # We make the assumption the above case happens some times,
            #     # although our sample json files don't yet have the case.
            #     for entry in dns_servers['entries']:
            #         if ip_conf_id == entry.get('ipConfigurationId', None):
            #             return True


def get_dns_entries(id):
    if "dnsServers" in network_config["services"]:
        for dns_servers in network_config["services"]["dnsServers"]:
            if id in dns_servers["ipConfigurationIds"]:
                return dns_servers["entries"]


def find_subnet_from_router_if(id):
    for subnet in network_config["subnets"]:    
        if "ipConfigurationIds" in subnet:
           for configId in subnet["ipConfigurationIds"]:
               if configId == id:
                   return get_network_name_from_segment_id(subnet["networkSegmentId"])


def generate_routers():
    global stack_user
    for i, router in enumerate(network_config["services"]["routers"]):
        if debug:
            print("Create Router%s" % i)
        ports = []
        if 'ipConfigurationIds' in router:
            # It seems that there can be routers which aren't configured.
            # ravello's blueprint shows the router, but it has no
            # ipConfigurationsIds, so no interfaces or ports
            for ipconfig in router["ipConfigurationIds"]:
                for interfaces in network_config["services"]["networkInterfaces"]:
                    if "ipConfigurations" in interfaces:
                        for ifconfig in interfaces["ipConfigurations"]:
                           if ifconfig["id"] == ipconfig:
                               network = find_subnet_from_router_if(ipconfig)
                               if ifconfig["staticIpConfig"]["ip"] != dnsip:
                                   ports.append(RouterPort(ifconfig["staticIpConfig"]["ip"], \
                                    network,"sub-" + network))
        router = Router(name="Router%s" % i, interfaces=ports)
        stack_user += router.generate_template(env)

# TODO: Search for bootable


def get_root_disk_size(vm):
    for disk in vm["hardDrives"]:
        if disk["boot"] and disk["type"] == "DISK":
            size = disk["size"]["value"]
            size_unit = disk["size"]["unit"]
            try:
                size = unit_conversion_map[size_unit](size)
            except KeyError:
                print("Blueprint returned an unexpected size unit. Please create an issue on GitHub.")
                print("The unexpected unit is: {}".format(size_unit))
                sys.exit(-1)
            return size


def get_root_disk_name(vm):
    for disk in vm["hardDrives"]:
        if disk["boot"] and disk["type"] == "DISK":
            return disk["name"]


def find_device_network(id):
    for switch in network_config["switches"]:
        if "ports" in switch:
            for port in switch["ports"]:
                if port["deviceId"] == id:
                    return get_network_name_from_segment_id(port["networkSegmentReferences"][0]["networkSegmentId"])


def get_port_ip_address(id):
    if "dhcpServers" in network_config["services"]:
        for dhcp in network_config["services"]["dhcpServers"]:
            if "reservedIpEntries" in dhcp:
               for ip in dhcp["reservedIpEntries"]:
                   if ip["ipConfigurationId"] == id:
                       return ip["ip"]

unit_conversion_map = {
    "TB": lambda s: int(s * 1024),
    "GB": lambda s: int(s),
    "MB": lambda s: int(math.ceil(s / 1024.0)),
    "KB": lambda s: int(math.ceil(s / (1024.0 * 1024))),
    "BYTE": lambda s: int(math.ceil(s / (1024.0 * 1024 * 1024))),
}

def generate_vms():
    global stack_user
    global stack_admin
    global dnsports
    global bootorders
    global ipmiserver
    global bpname
    flavors = {}
    vms = {}
    networks = {}
    trunks = {}
    for vm in vms_config:
        vm_is_public = False
        if "suppliedServices" in vm:
            rules = []
            for service in vm["suppliedServices"]:
                if "portRange" in service:
                    for port in service["portRange"].split(","):
                        if "-" in port:
                            pmin, pmax = port.split("-")
                        else:
                            pmin = pmax = port

                if int(pmin) <= 22 <= int(pmax):
                    vm_is_public = True
                protocol = "tcp"
                if service["protocol"] == "UDP":
                    protocol = "udp"
                if service["protocol"] == "IP" and service["ipProtocol"] == 1:
                    protocol = "icmp"
                if "portRange" in service:
                    rules.append({"name": service["name"], "proto": protocol,
                                  "min": pmin, "max": pmax, "remote_ip": "0.0.0.0/0"})
                else:
                    rules.append({"name": service["name"], "proto": protocol,
                                  "remote_ip": "0.0.0.0/0"})
            for subnet in network_config["subnets"]:
                netmask = subnet["net"] + "/" + subnet["mask"]
                rules.append({"name": "%s%s%s" % (
                    service["name"], subnet["net"], "tcp"), "proto": "tcp", "min": 1, "max": 65535, "remote_ip": netmask})
                rules.append({"name": "%s%s%s" % (
                    service["name"], subnet["net"], "udp"), "proto": "udp", "min": 1, "max": 65535, "remote_ip": netmask})

            sgservice = SecurityGroup(vm["name"], rules, bpname)
            stack_user += sgservice.generate_template(env)
        bootorder = None
        if "vmOrderGroupId" in vm:
            for group in config["design"]["vmOrderGroups"]:
                if group["id"] == vm["vmOrderGroupId"]:
                    bootorder = group
                    if group["order"] not in bootorders:
                      bootorders[group["order"]] = []
                    bootorders[group["order"]].append(vm["name"])
        memorymb = vm["memorySize"]["value"] * \
            1024 if (vm["memorySize"]["unit"] ==
                     "GB") else vm["memorySize"]["value"]
        root_disk_size = get_root_disk_size(vm)
        name_flavor = "CPU_%s_Memory_%s_Disk_%s" % (
            vm["numCpus"], memorymb, root_disk_size)
        flavors["%s_%s_%s" % (vm["numCpus"], memorymb, root_disk_size)] = Flavor(vm["numCpus"], memorymb, root_disk_size)
        hostname = None
        if "hostnames" in vm:
            hostname = vm["hostnames"][0]
            for hn in vm["hostnames"]:
              if "REPL" in hn:
                hostname = hn
                break
        else:
            hostname = vm["name"]
        if debug:
            print("Create VM %s with flavor %s" % (vm["name"], name_flavor))
        networks[vm["name"]] = []
        trunks[vm["name"]] = []
        if "networkConnections" in vm:
            for network in sorted(vm["networkConnections"], key=lambda k: k["device"]["index"]):
                assign_public = False
                if "ipConfig" in network:
                    dnsports[network["ipConfig"]["id"]] = {
                        "vm": vm["name"], "index": network["device"]["index"]}
                    if "staticIpConfig" in network["ipConfig"]:
                        ip_address = network["ipConfig"]["staticIpConfig"]["ip"]
                    else:
                        ip_address = get_port_ip_address(network["ipConfig"]["id"])
                    if network["ipConfig"]["hasPublicIp"]:
                        assign_public = True
                else:
                    ip_address = ""
                if "mac" not in network["device"]:
                    network["device"]["mac"] = network["device"]["generatedMac"]
                if debug:
                    print("Create network device with mac %s on network %s with ip %s"
                          % (network["device"]["mac"], find_device_network(network["id"]), ip_address))
                networks[vm["name"]].append({"mac": network["device"]["mac"],
                                             "network": find_device_network(network["id"]),
                                             "ip_address": ip_address,
                                             "index": network["device"]["index"],
                                             "public": assign_public,
                                             "services": "suppliedServices" in vm
                                             })

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
            size = disk["size"]["value"]
            size_unit = disk["size"]["unit"]
            try:
                size = unit_conversion_map[size_unit](size)
            except KeyError:
                print("Blueprint returned an unexpected size unit. Please create an issue on GitHub.")
                print("The unexpected unit is: {}".format(size_unit))
                sys.exit(-1)
            # voltype="volume"
            if disk["type"] == "DISK":
                if debug:
                    print("Add disk %s" % (disk["name"]))
                if "name" not in disk:
                    if "baseDiskImageName" in disk:
                        disk["name"] = disk["baseDiskImageName"].split(".")[0]
                    else:
                        disk["name"] = disk["id"]
                if get_root_disk_name(vm) == disk["name"]:
                    # voltype="image"
                    images.append(
                        {"name": disk["name"], "size": size, "id": disk["id"], "vm": vm["name"]})
                else:
                    volumes.append(
                        {"name": disk["name"], "size": size, "id": disk["id"], "vm": vm["name"]})
            else:
                if debug:
                    print("Add cdrom %s" % (disk["name"]))
                images.append(
                    {"name": disk["name"], "size": size, "id": disk["id"], "vm": vm["name"]})
                cdrom = disk["name"]
                # voltype="image"
            # diskimagename="%s-%s" % (vm["name"], disk["name"])
            # bpdisk = client.get_diskimages(filter={"name": diskimagename})
            # if bpdisk:
            #   client.delete_diskimage(bpdisk[0]["id"])

        vmdesc = ""
        if "description" in vm:
          if not nodesc:
            vmdesc = vm["description"]
        vmuserdata = ""

        if "userData" in vm:
            if "#cloud-config" in vm["userData"]:
                vmuserdata = vm["userData"].replace(
                    "#cloud-config", "#cloud-config\nhostname:  %s" % hostname)
                if bootorder and bootordermode == "signal":
                  vmuserdata += "\nruncmd:\n- - sleep %s && SIGNAL" % (bootorder["delay"])
            else:
                userdata64 = base64.b64encode(vm["userData"].encode('utf8')).decode('utf8')
                vmuserdata = "#cloud-config\nhostname: %s\nruncmd:\n- echo %s |base64 -d|sh\n" % (
                    hostname, userdata64)
                if bootorder and bootordermode == "signal":
                  vmuserdata += "\n - sleep %s && SIGNAL\n" % (bootorder["delay"])
        else:
            vmuserdata = "#cloud-config\nhostname: %s" % hostname
            if bootorder and bootordermode == "signal":
              vmuserdata += "\nruncmd:\n - sleep %s && SIGNAL" % (bootorder["delay"])


        if "hostnames" not in vm:
            vm["hostnames"] = []
        vms[vm["name"]] = {"flavor": name_flavor, "network": networks, "volumes": volumes, 
                           "bootorder": bootorder, "images": images, "vm": vm, "description": vmdesc, 
                           "userdata": vmuserdata, "cdrom": cdrom, "is_public": vm_is_public,
                           "hostnames": ":".join(vm["hostnames"])
                           }

    for flavor in flavors:
        stack_admin += flavors[flavor].generate_template(env)

    depends_ip = ""
    for vm, data in networks.items():
        # First ports with IP
        for vmnetwork in data:
            if vmnetwork["ip_address"]:
                depends_ip = "%s-%d" % (vm, vmnetwork["index"])
                port = Port(vmnetwork["index"], vmnetwork["mac"], vm, vmnetwork["network"], \
                    vmnetwork["ip_address"], None, vmnetwork["services"], bpname)
                stack_user += port.generate_template(env)
            if vmnetwork["public"]:
                fip = FIP(vmnetwork["index"], vmnetwork["network"], vm)
                fips.append("%s-%s" % (vm, vmnetwork["index"]))
                stack_user += fip.generate_template(env)

    for vm, data in networks.items():
        # Second ports without IP
        for vmnetwork in data:
            if not vmnetwork["ip_address"]:
                port = Port(vmnetwork["index"], vmnetwork["mac"], vm, vmnetwork["network"], \
                    vmnetwork["ip_address"], depends_ip, vmnetwork["services"], bpname)
                stack_user += port.generate_template(env)

    for vm, data in trunks.items():
        for vmnetwork in data:
            trunk = Trunk(vm, vmnetwork["index"], vmnetwork["mac"], vmnetwork["network"], \
                vmnetwork["subports"])
            stack_user += trunk.generate_template(env)

    for vm, data in vms.items():
        for volume in data["volumes"]:
            volume = Volume(volume["vm"], volume["name"], volume["size"], \
                bpname, emptyvolumes)
            stack_user += volume.generate_template(env)


    for vm, data in sorted(vms.items()):
        waitfor = []
        if bootorders:
            bootordersn = sorted(bootorders.keys())
            bootorder = data["bootorder"]
            if bootorder and bootordersn.index(bootorder["order"]) != 0:
              for server in bootorders[bootordersn[bootordersn.index(bootorder["order"])-1]]:
                waitfor.append(server)
            if bootorder and bootordersn.index(bootorder["order"]) == len(bootordersn)-1:
               bootorder = False
        rootdisk = get_root_disk_name( data["vm"])
        publicdnsnames = []
        primaryhostname = data["hostnames"].split(":")[0].split(".")[0]
        for hostname in data["hostnames"].split(":"):
            if "REPL" in hostname:
                primaryhostname = hostname.split(".")[0]
                publicdnsnames.append(hostname)
        if nodesc:
          data["description"] = ""
        vm = VM(vm, data["description"], data["flavor"], networks[vm], rootdisk, \
            data["userdata"], data["cdrom"], bpname, data["volumes"], primaryhostname, \
            bootorder, waitfor, bootordermode=bootordermode, is_public=data["is_public"], \
            public_dns=publicdnsnames)
        stack_user += vm.generate_template(env, ipmiserver)


generate_networks()
generate_subnets()
generate_routers()
generate_vms()
if enabledns:
    generate_dns()

footer_user = env.get_template('footer_user.j2')
stack_user += footer_user.render(fips=fips)

print("INFO: Generated %s" % (output_dir + "/stack_admin.yaml"))
fp = open(output_dir + "/stack_admin.yaml", "w")
fp.write(stack_admin)
fp.close()
print("INFO: Generated %s" % (output_dir + "/stack_user.yaml"))
fp = open(output_dir + "/stack_user.yaml", "w")
fp.write(stack_user)
fp.close()
