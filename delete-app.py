import argparse
import sys
import json

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
    options.add_argument("-u", "--user", required=True, help="Ravello domain/username")
    options.add_argument("-p", "--password", required=True, help="Ravello password")
    options.add_argument("-di", "--domain-id", required=True, help="Ravello domain identity", default=None)
    options.add_argument("-a", "--app-name", required=True, help="Ravello application name", default=None)

    args = vars(options.parse_args())
    client = ravello_login(args)

    try:
        print("Deleting application {}".format(args['app_name']))
        app = client.get_application_by_name(args['app_name'])
        # print("Deleting application {}".format(app['id']))
        # print(json.dumps(app, indent=2))
        client.delete_application(app['id'])
    except Exception as e:
        print("Error deleting application: {}".format(e))
        sys.exit(-1)


if __name__ == '__main__':
    main()
