import math
class Flavor:
  def __init__(self, cpu, memory, disk):
    self.cpu = cpu
    self.memory = memory
    self.disk = disk
    self.name = "CPU_%s_Memory_%s_Disk_%s" % (self.cpu, self.memory, self.disk)

  def generate_template(self,env):
    tplflavor = env.get_template('flavor.j2')
    return tplflavor.render(name=self.name, cpu=self.cpu, memory=self.memory, disk=self.disk)

class SecurityGroup:
  def __init__(self, name, rules, bpname):
    self.name = name
    self.rules = rules
    self.bpname = bpname
  
  def generate_template(self,env):
    tplsgservice = env.get_template('sgservice.j2')
    return tplsgservice.render(name=self.name, rules=self.rules, bpname=self.bpname)

class VM:
  def __init__(self, name, description, flavor, networks, rootdisk, userdata, cdrom, bpname, \
    volumes, hostname, bootorder, waitfor, bootordermode, is_public, public_dns):
    self.name = name
    self.description = description
    self.flavor = flavor
    self.networks = networks
    self.rootdisk = rootdisk
    self.userdata = userdata
    self.cdrom = cdrom         
    self.bpname = bpname
    self.volumes = volumes
    self.hostname = hostname
    self.bootorder = bootorder
    self.waitfor = waitfor
    self.bootordermode = bootordermode
    self.is_public = is_public
    self.public_dns = ":".join(public_dns)

  def generate_template(self,env, ipmiserver):
    tplvm = env.get_template('server.j2')
    return tplvm.render(name=self.name, description=self.description, flavor=self.flavor, \
        nics=self.networks, root_disk=self.rootdisk, userdata=self.userdata, \
        cdrom=self.cdrom, bpname=self.bpname, volumes=self.volumes, hostname=self.hostname, \
        bootorder=self.bootorder, waitfor=self.waitfor, bootordermode=self.bootordermode, \
        ipmiserver=ipmiserver, is_public=self.is_public, public_dns=self.public_dns)



class Volume:
  def __init__(self, vm, name, size, bpname, emptyvolumes):
    self.vm = vm
    self.volume = name 
    self.size = size
    self.bpname = bpname
    self.emptyvolumes = emptyvolumes

  def generate_template(self,env):
    tplvol = env.get_template('volume.j2')
    return tplvol.render(vm=self.vm, volume=self.volume, size=self.size, \
        bpname=self.bpname, emptyvolumes=self.emptyvolumes)


class Network:
  def __init__(self, name):
    self.name = name
  def generate_template(self,env):
    tplnetwork = env.get_template('network.j2')
    return tplnetwork.render(name=self.name)

class Subnet:
  def __init__(self, name, cidr, gateway, network, dnsip, dhcp, dhcpstart=None, dhcpend=None):
    self.name = name
    self.cidr = cidr 
    self.gateway = gateway
    self.network = network
    self.dnsip = dnsip
    self.dhcp = dhcp
    self.dhcpstart = dhcpstart
    self.dhcpend = dhcpend

  def generate_template(self,env):
    tplsubnet = env.get_template('subnet.j2')
    return tplsubnet.render(name="sub-" + self.network, cidr=self.cidr, gateway=self.gateway, \
        network=self.network, dhcp=self.dhcp, dnsip=self.dnsip, dhcpstart=self.dhcpstart, \
        dhcpend=self.dhcpend)


class Port:
  def __init__(self, index , mac, vm, network, ip_address, depends, services, bpname):
    self.name = "%s-%d" % (vm, index)
    self.mac = mac
    self.vm = vm
    self.network = network
    self.ip_address = ip_address
    self.depends = depends
    self.services = services
    self.bpname = bpname

  def generate_template(self,env):
    tplport = env.get_template('port.j2')
    return tplport.render(name=self.name, mac=self.mac, vm=self.vm, network=self.network, \
        ip_address=self.ip_address, depends=self.depends, services=self.services, bpname=self.bpname)

class Trunk:
  def __init__(self, name, index, mac, network, subports):
    self.name = name
    self.index = index
    self.network = network
    self.mac = mac 
    self.subports = subports

  def generate_template(self,env):
    tpltrunk = env.get_template('trunk.j2')
    return tpltrunk.render(name="%s-%d" % (self.name, self.index), mac=self.mac, \
        network=self.network, subports=self.subports)


class Router:
  def __init__(self, name, interfaces):
    self.name = name
    self.interfaces = interfaces

  def generate_template(self,env):
    tplrouter = env.get_template('router.j2')
    return tplrouter.render(name=self.name, interfaces=self.interfaces)

class RouterPort:
  def __init__(self, ip, net, subnet):
    self.ip = ip
    self.net = net
    self.subnet = subnet


class FIP:
  def __init__(self, index, network, vm):
    self.index = index
    self.network = network
    self.vm = vm

  def generate_template(self,env):
    tplfip = env.get_template('fip.j2')
    return tplfip.render(port="%s-%d" % (self.vm, self.index), \
        network=self.network, vm=self.vm)

class DnsServer:
  def __init__(self, entries, network, dnsip):
    self.entries = entries
    self.network = network
    self.dnsip = dnsip

  def generate_template(self,env):
    tpldnsserver = env.get_template('dnsserver.j2')
    return tpldnsserver.render(entries=self.entries,
        network=self.network, dnsip=self.dnsip)

