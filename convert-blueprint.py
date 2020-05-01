
import argparse
import sys
from modules import ravelloOSP
from modules import ravelloProject
from modules import ravelloGlance

try:
    from ravello_sdk import RavelloClient
    ravello_sdk_enabled = True
except ImportError:
    ravello_sdk_enabled = False


def ravello_login(args):
    try:
        client = RavelloClient()
        domain = None if args["domain_id"] == "None" else args["domain_id"]
        client.login(args["user"], args["password"], domain)
        return client
    except Exception as e:
        print("Error connecting to Ravello: {0}".format(e))
        sys.exit(-1)

def main():
    options = argparse.ArgumentParser()
    options.add_argument("-o", "--output", required=False, help="Output directory")
    options.add_argument("-e", "--emptyvolumes", required=False,
                         help="True=Create Empty Volumes", action='store_true')
    options_bp = options.add_argument_group()
    options_bp.add_argument("-bp", "--blueprint",
                            required=False, help="Name of the blueprint")
    options_bp.add_argument("-u", "--user", required=False,
                            help="Ravello domain/username")
    options_bp.add_argument("-p", "--password", required=False, help="Ravello password")
    options_bp.add_argument("-di", "--domain-id", required=False, help="Ravello domain identity", default=None)

    options_json = options.add_argument_group()
    options_json.add_argument("-j", "--jsonf", required=False,
                              help="JSON file containing definition")
    options_dns = options.add_argument_group()

    options_dns.add_argument("-dns", "--enabledns", required=False, help="Enable DNS", action='store_true')

    options_dns.add_argument("--dns-ip", required=False,
                             help="Specify manually an IP for DNS server instead auto-generated one")

    options.add_argument("--bootorder", required=False, help="Enable boot order. Options: signal or depends")

    options.add_argument("--ipmiserver", required=False, help="Specify the name of your IPMI VM")
    options.add_argument("-d", "--debug", required=False, help="Debug", action='store_true')

    options.add_argument("-n", "--name", required=True, help="Name of the app to the exporter server")
    options.add_argument("-s", "--src-bp", required=False, help="Blueprint name to use as exporter server",
                         default="EXPORT-RAVELLO-DISKS-V3-BP", action="store_true")
    options.add_argument("--pubkeyfile", required=False, help="Public SSH key file to inject into export host")

    options.add_argument("-of", "--offset", required=False, default=0, type=int,
                         help="From which disk number start to migrate disks")

    options.add_argument("--max-count", required=False, default=10, type=int,
                         help="Number maximum of disk to be attached to the VM")

    options.add_argument("-dp", "--disk-prefix", required=False, default='',
                         help="Disk prefix to avoid moving around the work of others.")
    options.add_argument("-c", "--start-conv-character", required=False, default='a',
                         help="a-z, will proceed to convert devices at vd<character>. "
                              "Please note, anything other than 'a' will limit"
                              " the max number of disks to mount.")
    options.add_argument("--importhost", required=True,
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
    options.add_argument("--heatonly", required=False, help="Heat Only", default=False, action='store_true')

    args = vars(options.parse_args())
    client = ravello_login(args)

    # Create heat templates
    convert_bp = ravelloOSP.RavelloOsp(args, client)
    convert_bp.generate_all()

    if args["heatonly"]:
      exit()

    # Create application
    project = ravelloProject.ravelloProject(args, client)
    project.create_application()
    export_ip = project.get_export_hostname()
    vm_exporter = project.get_vm_exporter()
    print("Exporter hostname: %s" % export_ip)

    # Add disks to export vm
    ravello_glance = ravelloGlance.RavelloGlance(args, client, vm_exporter)
    ravello_glance.generate_disks()

if __name__ == '__main__':
    main()

# command line
# . creds.inc
# python convert-blueprint.py  --blueprint $blueprint --output $outputdir --user $ravelloUser --password $ravelloPass --name $appName $pk -d --importhost $import_host --auth-url $ospAuthURL --auth-user $ospUser --auth-password $ospPass --ibm-endpoint $ibm_endpoint --ibm-api-key $ibm_api_key --ibm-bucket-name $ibm_bucket_name --ibm-resource-id $ibm_resource_id

