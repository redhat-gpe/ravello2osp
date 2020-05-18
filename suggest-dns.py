#!/usr/bin/python3
import yaml, os, sys, ipaddress

MIN_NUMBER_HOSTS = 1

if len(sys.argv) != 2:
    print("Syntax: %s path/stack_user.yaml" % sys.argv[0])

content = open(sys.argv[1], "r")
template = yaml.load(content, Loader=yaml.FullLoader)

subnet_ips = {}

def find_subnet(network):
    for element, data in template["resources"].items():
        if data["type"] == "OS::Neutron::Subnet":    
            if data["properties"]["network_id"]["get_resource"] == network:
                return element

for element, data in template["resources"].items():
    if data["type"] == "OS::Neutron::Port":
        if "fixed_ips" in data["properties"]:
           for fixed_ip in data["properties"]["fixed_ips"]:
                if "subnet" in fixed_ip:
                    subnet = fixed_ip["subnet"]["get_resource"]

                else:
                    subnet = find_subnet(data["properties"]["network"]["get_resource"])
                if subnet not in subnet_ips:
                    subnet_ips[subnet] = []
                subnet_ips[subnet].append(fixed_ip["ip_address"])

for subnet,ips in subnet_ips.items():
    start = None
    end = 254
    #print(subnet)
    for ip in sorted(ips, key=lambda item: ipaddress.ip_address(item)):
        prefix = ".".join(ip.split(".")[0:3])
        if not start:
            start = int(ip.split(".")[3])+1
        else:
            end = int(ip.split(".")[3])-1
            if start < end and end-start > MIN_NUMBER_HOSTS:
                print("%s.%d" % (prefix, start))
                exit()
