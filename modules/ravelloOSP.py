
from jinja2 import Environment, FileSystemLoader
from netaddr import IPNetwork, IPAddress
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


class RavelloOsp:
    def __init__(self, args, client):
        self.debug = args["debug"]
        self.emptyvolumes = args["emptyvolumes"]
        self.enabledns = args["enabledns"]
        self.ipmiserver = args["ipmiserver"]
        self.json_file = args["jsonf"]
        self.output_dir = os.path.realpath(args["output"])
        self.bootordermode = args["bootorder"]
        self.file_loader = FileSystemLoader("templates")
        self.blueprint = args["blueprint"]
        self.json_file = args["jsonf"]
        self.env = Environment(loader=self.file_loader)
        self.header_admin = self.env.get_template('header_admin.j2')
        self.header_user = self.env.get_template('header_user.j2')
        self.stack_user = self.header_user.render()
        self.tplproject = self.env.get_template('project.j2')
        self.stack_admin = self.header_admin.render()
        self.stack_admin += self.tplproject.render()
        self.networks = []
        self.dnsip = args["dns_ip"]
        self.dnsports = {}
        self.sg_outputs = {}
        self.bootorders = {}
        self.dnsnetwork = None
        self.fips = []
        # self.ravello_domain = args["domain"]
        self.client = client
        self.unit_conversion_map = {
            "TB": lambda s: int(s * 1024),
            "GB": lambda s: int(s),
            "MB": lambda s: int(math.ceil(s / 1024.0)),
            "KB": lambda s: int(math.ceil(s / (1024.0 * 1024))),
            "BYTE": lambda s: int(math.ceil(s / (1024.0 * 1024 * 1024))),
        }

        if self.blueprint:
            if not ravello_sdk_enabled:
                print("Python module ravello_sdk is not installed in your environment.")
                sys.exit(-1)
            bp = self.client.get_blueprints(filter={"name": self.blueprint})[0]
            self.config = client.get_blueprint(bp["id"])
            fp = open(self.output_dir + "/blueprint.json", "w")
            fp.write(json.dumps(self.config, indent=2))
            fp.close()
        else:
            config = json.loads(open(self.json_file, "r").read())
            self.blueprint = config["name"].replace(":","_")

        self.network_config = self.config["design"]["network"]
        self.vms_config = self.config["design"]["vms"]

    def generate_networks(self):
        i = 0
        # self.get_blueprint()
        for switch in self.network_config["switches"]:
            for segment in switch["networkSegments"]:
                if (segment["vlanId"] != 1):  # TODO
                    key_use = 'name' if 'name' in switch else 'id'
                    network = Network("%s_vlan%s" % (switch[key_use], segment["vlanId"]))
                    if self.debug:
                        print("Create network %s_vlan%s" %
                              (switch[key_use], segment["vlanId"]))
                else:
                    if "name" not in switch:
                        switch["name"] = "Network" + str(i)
                        i += 1
                    network = Network(switch["name"])
                    if self.debug:
                        print("Create network %s" % switch["name"])

                self.networks.append(network.name)
                self.stack_user += network.generate_template(self.env)

    def get_network_name_from_segment_id(self, id):
        for switch in self.network_config["switches"]:
            for segment in switch["networkSegments"]:
                key_use = 'name' if 'name' in switch else 'id'
                if segment["id"] == id:
                    if (segment["vlanId"] != 1):
                        return "%s_vlan%s" % (switch[key_use], segment["vlanId"])
                    else:
                        return switch[key_use]

    def is_gateway_ip(self, id):
        if "routers" in self.network_config["services"]:
            for routers in self.network_config["services"]["routers"]:
                if id in routers["ipConfigurationIds"]:
                    return True

    def get_gateway(self, configIds):
        networkInterfaces = self.network_config["services"].get("networkInterfaces", None)
        if networkInterfaces is None:
            return ""
        for ipconfig in configIds:
            for interfaces in networkInterfaces:
                if "ipConfigurations" in interfaces:
                    for ifconfig in interfaces["ipConfigurations"]:
                        if ifconfig["id"] == ipconfig:
                            if self.debug:
                                print(self.network_config["services"]["routers"])
                            if self.is_gateway_ip(ifconfig["id"]):
                                return ifconfig["staticIpConfig"]["ip"]
        return ""

    def is_dhcp(self, ids):
        if "dhcpServers" in self.network_config["services"]:
            for dhcp in self.network_config["services"]["dhcpServers"]:
                if dhcp["ipConfigurationId"] in ids:
                    return dhcp
        return None

    def is_dns_server_ip(self, ip_conf_id):
        if "dnsServers" in self.network_config["services"]:
            for dns_servers in self.network_config["services"]["dnsServers"]:
                if ("ipConfigurationIds" in dns_servers and
                        ip_conf_id in dns_servers["ipConfigurationIds"]):
                    return True

    def get_dns(self, configIds):
        for ipconfig in configIds:
            for interfaces in self.network_config["services"]["networkInterfaces"]:
                if "ipConfigurations" in interfaces:
                    for ifconfig in interfaces["ipConfigurations"]:
                        if ifconfig["id"] == ipconfig:
                            if self.debug:
                                print(self.network_config["services"]["routers"])
                            if self.is_dns_server_ip(ifconfig["id"]):
                                return ifconfig["staticIpConfig"]["ip"]
        return ""

    def generate_subnets(self):
        subnets_networks = []
        for subnet in self.network_config["subnets"]:
            network = self.get_network_name_from_segment_id(subnet["networkSegmentId"])
            subnets_networks.append(network)
            gw = ""
            if "ipConfigurationIds" in subnet:
                gw = self.get_gateway(subnet["ipConfigurationIds"])
            if self.debug:
                print("Create subnet %s/%s on network %s" %
                      (subnet["net"], subnet["mask"], self.get_network_name_from_segment_id(subnet["networkSegmentId"])))
                print("Gateway: %s" % (self.get_gateway(subnet["ipConfigurationIds"])))

            if (self.enabledns and not self.dnsip) and "ipConfigurationIds" in subnet and self.get_dns(subnet["ipConfigurationIds"]):
                dnsip = self.get_dns(subnet["ipConfigurationIds"])
                self.dnsnetwork = network
            else:
                if self.dnsip and IPAddress(self.dnsip) in IPNetwork("%s/%s" % (subnet["net"], subnet["mask"])):
                    self.dnsnetwork = network

            cidr = IPNetwork('{net}/{mask}'.format(**subnet)).cidr
            dhcp = dhcpstart = dhcpend = False
            if "ipConfigurationIds" in subnet and self.is_dhcp(subnet["ipConfigurationIds"]):
                dhcp = True
                dhcpdata = self.is_dhcp(subnet["ipConfigurationIds"])
                dhcpstart = dhcpdata["poolStart"]
                dhcpend = dhcpdata["poolEnd"]
                excludedips = []
                if "excludedIpEntries" in dhcpdata:
                    excludedips = [exclude["ip"]
                                   for exclude in dhcpdata["excludedIpEntries"]]

                if "reservedIpEntries" in dhcpdata:
                    excludedips += [exclude["ip"]
                                    for exclude in dhcpdata["reservedIpEntries"]]

                def ip2int(ipstr):
                    return struct.unpack(
                        '!I', socket.inet_aton(ipstr))[0]

                def int2ip(n):
                    return socket.inet_ntoa(struct.pack('!I', n))

                while dhcpstart in excludedips:
                    ipint = ip2int(dhcpstart)
                    dhcpstart = int2ip(ipint + 1)
                while dhcpend in excludedips:
                    ipint = ip2int(dhcpend)
                    dhcpend = int2ip(ipint - 1)

                if self.dnsip == gw:
                    dnsip = dhcpstart
                    ipint = ip2int(dhcpstart)
                    dhcpstart = int2ip(ipint + 1)
            subnet = Subnet(name="sub-" + network, cidr=cidr, gateway=gw, network=network, \
                            dnsip=self.dnsip, dhcp=dhcp, dhcpstart=dhcpstart, dhcpend=dhcpend)
            self.stack_user += subnet.generate_template(self.env)

        for network in list(set(self.networks) - set(subnets_networks)):
            subnet = Subnet(name="sub-" + network, cidr="1.1.1.1/8", gateway="", \
                            network=network, dhcp=False, dnsip=self.dnsip)
            self.stack_user += subnet.generate_template(self.env)

    def find_subnet_from_router_if(self, id):
        for subnet in self.network_config["subnets"]:
            if "ipConfigurationIds" in subnet:
                for configId in subnet["ipConfigurationIds"]:
                    if configId == id:
                        return self.get_network_name_from_segment_id(subnet["networkSegmentId"])

    def generate_routers(self):
        for i, router in enumerate(self.network_config["services"]["routers"]):
            if self.debug:
                print("Create Router%s" % i)
            ports = []
            if 'ipConfigurationIds' in router:
                for ipconfig in router["ipConfigurationIds"]:
                    for interfaces in self.network_config["services"]["networkInterfaces"]:
                        if "ipConfigurations" in interfaces:
                            for ifconfig in interfaces["ipConfigurations"]:
                                if ifconfig["id"] == ipconfig:
                                    network = self.find_subnet_from_router_if(ipconfig)
                                    if ifconfig["staticIpConfig"]["ip"] != self.dnsip:
                                        ports.append(RouterPort(ifconfig["staticIpConfig"]["ip"], \
                                                                network, "sub-" + network))
            router = Router(name="Router%s" % i, interfaces=ports)
            self.stack_user += router.generate_template(self.env)

    def get_root_disk_size(self, vm):
        for disk in vm["hardDrives"]:
            if disk["boot"] and disk["type"] == "DISK":
                size = disk["size"]["value"]
                size_unit = disk["size"]["unit"]
                try:
                    size = self.unit_conversion_map[size_unit](size)
                except KeyError:
                    print("Blueprint returned an unexpected size unit. Please create an issue on GitHub.")
                    print("The unexpected unit is: {}".format(size_unit))
                    sys.exit(-1)
                return size
        # If there is not bootable disk, just return first one
        for disk in vm["hardDrives"]:
            if disk["index"] == 0  and disk["type"] == "DISK":
                size = disk["size"]["value"]
                size_unit = disk["size"]["unit"]
                try:
                    size = self.unit_conversion_map[size_unit](size)
                except KeyError:
                    print("Blueprint returned an unexpected size unit. Please create an issue on GitHub.")
                    print("The unexpected unit is: {}".format(size_unit))
                    sys.exit(-1)
                return size
     

    def get_port_ip_address(self, id):
        if "dhcpServers" in self.network_config["services"]:
            for dhcp in self.network_config["services"]["dhcpServers"]:
                if "reservedIpEntries" in dhcp:
                    for ip in dhcp["reservedIpEntries"]:
                        if ip["ipConfigurationId"] == id:
                            return ip["ip"]

    def find_device_network(self, id):
        for switch in self.network_config["switches"]:
            if "ports" in switch:
                for port in switch["ports"]:
                    if port["deviceId"] == id:
                        for segment in port["networkSegmentReferences"]:
                            if segment["egressPolicy"] == "UNTAGGED":
                                return self.get_network_name_from_segment_id(segment["networkSegmentId"])
                        # If all is tagged, return first one
                        return self.get_network_name_from_segment_id(port["networkSegmentReferences"][0]["networkSegmentId"])

    def get_root_disk_name(self, vm):
        for disk in vm["hardDrives"]:
            if disk["boot"] and disk["type"] == "DISK":
                return disk["name"]
        # If there is not bootable disk, just return first one
        for disk in vm["hardDrives"]:
            if disk["index"] == 0 and disk["type"] == "DISK":
                return disk["name"]


    def generate_vms(self):
        flavors = {}
        vms = {}
        networks = {}
        trunks = {}

        for vm in self.vms_config:
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
                sgservice = SecurityGroup(vm["name"], rules, self.blueprint)
                hostname = None
                if "hostnames" in vm:
                    hostname = vm["hostnames"][0]
                    for hn in vm["hostnames"]:
                        if "REPL" in hn:
                            hostname = hn
                self.sg_outputs.update(sgservice.generate_template_output(hostname.split(".")[0] + ".DOMAIN", self.env))

                for subnet in self.network_config["subnets"]:
                    netmask = str(ipaddress.ip_network(subnet["net"] + "/" + subnet["mask"], False))
                    rules.append({"name": "%s%s%s" % (service["name"],
                                                       subnet["net"], "tcp"),
                                  "proto": "tcp", "min": 1, "max": 65535,
                                  "remote_ip": netmask})
                    rules.append({"name": "%s%s%s" % (service["name"],
                                                      subnet["net"], "udp"),
                                  "proto": "udp", "min": 1, "max": 65535,
                                  "remote_ip": netmask})

                sgservice = SecurityGroup(vm["name"], rules, self.blueprint)
                self.stack_user += sgservice.generate_template(self.env)

            bootorder = None
            if "vmOrderGroupId" in vm:
                for group in self.config["design"]["vmOrderGroups"]:
                    if group["id"] == vm["vmOrderGroupId"]:
                        bootorder = group
                        if group["order"] not in self.bootorders:
                            self.bootorders[group["order"]] = []
                        self.bootorders[group["order"]].append(vm["name"])
            memorymb = vm["memorySize"]["value"] * \
                       1024 if (vm["memorySize"]["unit"] ==
                                "GB") else vm["memorySize"]["value"]
            root_disk_size = self.get_root_disk_size(vm)
            name_flavor = "CPU_%s_Memory_%s_Disk_%s" % (vm["numCpus"], memorymb, root_disk_size)
            flavors["%s_%s_%s" % (vm["numCpus"], memorymb, root_disk_size)] = Flavor(vm["numCpus"], memorymb,
                                                                                     root_disk_size)
            hostname = None
            if "hostnames" in vm:
                hostname = vm["hostnames"][0]
                for hn in vm["hostnames"]:
                    if "REPL" in hn:
                        hostname = hn
                        break
            else:
                hostname = vm["name"]

            if self.debug:
                print("Create VM %s with flavor %s" % (vm["name"], name_flavor))
            networks[vm["name"]] = []
            trunks[vm["name"]] = []
            if "networkConnections" in vm:
                for network in sorted(vm["networkConnections"], key=lambda k: k["device"]["index"]):
                    assign_public = False
                    if "ipConfig" in network:
                        self.dnsports[network["ipConfig"]["id"]] = {
                            "vm": vm["name"], "index": network["device"]["index"]}
                        if "staticIpConfig" in network["ipConfig"]:
                            ip_address = network["ipConfig"]["staticIpConfig"]["ip"]
                        else:
                            ip_address = self.get_port_ip_address(network["ipConfig"]["id"])
                        if network["ipConfig"]["hasPublicIp"]:
                            assign_public = True
                    else:
                        ip_address = ""
                    if "mac" not in network["device"]:
                        network["device"]["mac"] = network["device"]["generatedMac"]
                    if self.debug:
                        print("Create network device with mac %s on network %s with ip %s"
                              % (network["device"]["mac"], self.find_device_network(network["id"]), ip_address))
                    networks[vm["name"]].append({"mac": network["device"]["mac"],
                                                 "network": self.find_device_network(network["id"]),
                                                 "ip_address": ip_address,
                                                 "index": network["device"]["index"],
                                                 "public": assign_public,
                                                 "services": "suppliedServices" in vm
                                                 })

                    if "vlanInterfaces" in network:
                        trunks[vm["name"]].append({"mac": network["device"]["mac"],
                                                   "network": self.find_device_network(network["id"]),
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
                    size = self.unit_conversion_map[size_unit](size)
                except KeyError:
                    print("Blueprint returned an unexpected size unit. Please create an issue on GitHub.")
                    print("The unexpected unit is: {}".format(size_unit))
                    sys.exit(-1)

                if disk["type"] == "DISK":
                    if self.debug:
                        print("Add disk %s" % (disk["name"]))
                    if "name" not in disk:
                        if "baseDiskImageName" in disk:
                            disk["name"] = disk["baseDiskImageName"].split(".")[0]
                        else:
                            disk["name"] = disk["id"]
                    if self.get_root_disk_name(vm) == disk["name"]:
                        images.append(
                            {"name": disk["name"], "size": size, "id": disk["id"], "vm": vm["name"]})
                    else:
                        volumes.append(
                            {"name": disk["name"], "size": size, "id": disk["id"], "vm": vm["name"]})
                else:
                    if self.debug:
                        print("Add cdrom %s" % (disk["name"]))
                    images.append(
                        {"name": disk["name"], "size": size, "id": disk["id"], "vm": vm["name"]})
                    cdrom = disk["name"]

            if 'description' in vm:
                vmdesc = vm["description"].replace('\n', ' ').replace('"', '')
            else:
                vmdesc = ''

            vmuserdata = ""
            if "userData" in vm:
                if "#cloud-config" in vm["userData"]:
                    vmuserdata = vm["userData"].replace(
                        "#cloud-config", "#cloud-config\nhostname:  %s" % hostname)
                    if bootorder and self.bootordermode == "signal":
                        vmuserdata += "\nruncmd:\n- - sleep %s && SIGNAL" % (bootorder["delay"])
                else:
                    userdata64 = base64.b64encode(vm["userData"].encode('utf8')).decode('utf8')
                    vmuserdata = "#cloud-config\nhostname: %s\nruncmd:\n- echo %s |base64 -d|sh\n" % (
                        hostname, userdata64)
                    if bootorder and self.bootordermode == "signal":
                        vmuserdata += "\n - sleep %s && SIGNAL\n" % (bootorder["delay"])
            else:
                vmuserdata = "#cloud-config\nhostname: %s" % hostname
                if bootorder and self.bootordermode == "signal":
                    vmuserdata += "\nruncmd:\n - sleep %s && SIGNAL" % (bootorder["delay"])

            if "hostnames" not in vm:
                vm["hostnames"] = []
            vms[vm["name"]] = {"flavor": name_flavor, "network": networks, "volumes": volumes,
                               "bootorder": bootorder, "images": images, "vm": vm, "description": vmdesc,
                               "userdata": vmuserdata, "cdrom": cdrom, "is_public": vm_is_public,
                               "hostnames": ":".join(vm["hostnames"])
                               }

        for flavor in flavors:
            self.stack_admin += flavors[flavor].generate_template(self.env)

        depends_ip = ""
        for vm, data in networks.items():
            # First ports with IP
            for vmnetwork in data:
                if vmnetwork["ip_address"]:
                    depends_ip = "%s-%d" % (vm, vmnetwork["index"])
                    port = Port(vmnetwork["index"], vmnetwork["mac"], vm, vmnetwork["network"],
                                vmnetwork["ip_address"], None, vmnetwork["services"], self.blueprint)
                    self.stack_user += port.generate_template(self.env)
                if vmnetwork["public"]:
                    fip = FIP(vmnetwork["index"], vmnetwork["network"], vm)
                    self.fips.append("%s-%s" % (vm, vmnetwork["index"]))
                    self.stack_user += fip.generate_template(self.env)

        for vm, data in networks.items():
            # Second ports without IP
            for vmnetwork in data:
                if not vmnetwork["ip_address"]:
                    port = Port(vmnetwork["index"], vmnetwork["mac"], vm, vmnetwork["network"],
                                vmnetwork["ip_address"], depends_ip, vmnetwork["services"], self.blueprint)
                    self.stack_user += port.generate_template(self.env)

        for vm, data in trunks.items():
            for vmnetwork in data:
                trunk = Trunk(vm, vmnetwork["index"], vmnetwork["mac"], vmnetwork["network"],
                              vmnetwork["subports"])
                self.stack_user += trunk.generate_template(self.env)

        for vm, data in vms.items():
            for volume in data["volumes"]:
                volume = Volume(volume["vm"], volume["name"], volume["size"],
                                self.blueprint, self.emptyvolumes)
                self.stack_user += volume.generate_template(self.env)

        for vm, data in sorted(vms.items()):
            waitfor = []
            if self.bootorders:
                bootordersn = sorted(self.bootorders.keys())
                bootorder = data["bootorder"]
                if bootorder and bootordersn.index(bootorder["order"]) != 0:
                    for server in self.bootorders[bootordersn[bootordersn.index(bootorder["order"]) - 1]]:
                        waitfor.append(server)
                if bootorder and bootordersn.index(bootorder["order"]) == len(bootordersn) - 1:
                    bootorder = False
            rootdisk = self.get_root_disk_name(data["vm"])
            publicdnsnames = []
            primaryhostname = data["hostnames"].split(":")[0].split(".")[0]
            for hostname in data["hostnames"].split(":"):
                if "REPL" in hostname:
                    primaryhostname = hostname.split(".")[0]
                    publicdnsnames.append(hostname)
            vm = VM(vm, data["description"].replace('\n', ' '), data["flavor"], networks[vm], rootdisk,
                    data["userdata"], data["cdrom"], self.blueprint, data["volumes"], primaryhostname,
                    bootorder, waitfor, bootordermode=self.bootordermode, is_public=data["is_public"],
                    public_dns=publicdnsnames)
            self.stack_user += vm.generate_template(self.env, self.ipmiserver)

    def get_dns(self, configIds):
        for ipconfig in configIds:
            for interfaces in self.network_config["services"]["networkInterfaces"]:
                if "ipConfigurations" in interfaces:
                    for ifconfig in interfaces["ipConfigurations"]:
                        if ifconfig["id"] == ipconfig:
                            if self.debug:
                                print(self.network_config["services"]["routers"])
                            if self.is_dns_server_ip(ifconfig["id"]):
                                return ifconfig["staticIpConfig"]["ip"]
        return ""

    def get_dns_id(self, configIds):
        for ipconfig in configIds:
            for interfaces in self.network_config["services"]["networkInterfaces"]:
                if "ipConfigurations" in interfaces:
                    for ifconfig in interfaces["ipConfigurations"]:
                        if ifconfig["id"] == ipconfig:
                            if self.is_dns_server_ip(ifconfig["id"]):
                                return ifconfig["id"]
        return ""

    def get_dns_entries(self, id):
        if "dnsServers" in self.network_config["services"]:
            for dns_servers in self.network_config["services"]["dnsServers"]:
                if id in dns_servers["ipConfigurationIds"]:
                    return dns_servers["entries"]

    def generate_dns(self):
        entries = []
        for subnet in self.network_config["subnets"]:
            if self.enabledns and "ipConfigurationIds" in subnet and self.get_dns(subnet["ipConfigurationIds"]):
                # dns = get_dns(subnet["ipConfigurationIds"])
                dns_id = self.get_dns_id(subnet["ipConfigurationIds"])
                for entry in self.get_dns_entries(dns_id):
                    if "ravcloud.com" not in entry["name"] and "A" == entry["type"]:
                        ipid = entry["ipConfigurationId"]

                        entries.append([entry["name"],
                                        "{get_attr: [%s-%s_port, fixed_ips, 0, ip_address]}" % (
                                        self.dnsports[ipid]["vm"], self.dnsports[ipid]["index"])])
        dnsserver = DnsServer(entries, self.dnsnetwork, self.dnsip)
        self.stack_user += dnsserver.generate_template(self.env)

    def generate_footer(self):
        footer_user = self.env.get_template('footer_user.j2')
        self.stack_user += footer_user.render(fips=self.fips, services=self.sg_outputs)
        print("INFO: Generated %s" % (self.output_dir + "/stack_user.yaml"))
        fp = open(self.output_dir + "/stack_user.yaml", "w")
        fp.write(self.stack_user)
        fp.close()

        print("INFO: Generated %s" % (self.output_dir + "/stack_admin.yaml"))
        fp = open(self.output_dir + "/stack_admin.yaml", "w")
        fp.write(self.stack_admin)
        fp.close()

    def generate_all(self):
        self.generate_networks()
        self.generate_subnets()
        self.generate_routers()
        self.generate_vms()
        if self.enabledns:
            self.generate_dns()
        self.generate_footer()
