#!/bin/bash

if [ ! -f creds.inc ]
then
  echo "Please create creds.inc from creds.inc.example"
  exit 1
fi

. creds.inc

if [ -z "$1" ]
then
  echo "Usage: $0 <blueprint>"
  exit 1
fi

blueprint=$1
outputdir="imported/${blueprint}-playbooks"
mkdir -p $outputdir

appName="exporter-app-mamorim+gptelatam@redhat.com-15483"

if [ -n "$pubKeyFile" ]
then
  echo "Using public key $pubKeyFile"
  pk="--pubkeyfile $pubKeyFile"
else
  echo "Using password auth"
  pk=""
fi

if [ -n "$domain_id" ]
then
  domain="--domain-id $domain_id"
else
  domain=""
fi

echo "Deploying Ravello app: $appName"

python convert-blueprint.py  --blueprint $blueprint --output $outputdir --user $ravelloUser \
  --password $ravelloPass --name $appName $pk --importhost $import_host --auth-url $ospAuthURL \
  --auth-user $ospUser --auth-password $ospPass --ibm-endpoint $ibm_endpoint --ibm-api-key $ibm_api_key \
  --ibm-bucket-name $ibm_bucket_name --ibm-resource-id $ibm_resource_id $domain

if [ $? -ne 0 ]
then
  echo "ravellodisks2glance.py failed."
  exit 1
fi

echo "Waiting for SSH service to start on VM."
sleep 35

if [ -z "$pubKeyFile" ]
then
  echo "Enter the root password for exporter VM 'r3dh4t1!'"
  ssh-copy-id -o StrictHostKeyChecking=no root@${ravelloHost}
  if [ $? -ne 0 ]
  then
    echo "ssh-copy-id failed."
    exit 1
  fi
fi

export ANSIBLE_HOST_KEY_CHECKING=False
cp -a library $outputdir
ansible-playbook --skip-tags shutdown -i $outputdir/inventory $outputdir/class_playbook_export_disks.yaml -u root

if [ $? -ne 0 ]
then
  echo "ansible-playbook export disks failed."
  #curl -s -X DELETE --user ${ravelloUser}:${ravelloPass} https://cloud.ravellosystems.com/api/v1/applications/${appID}
  exit 1
fi

ansible -i $outputdir/playbook_import_disks.hosts -m shell -a "shutdown -h now" export

ansible-playbook --skip-tags shutdown -i $outputdir/inventory $outputdir/class_playbook_import_disks.yaml -u root

if [ $? -ne 0 ]
then
  echo "ansible-playbook import failed."
  #curl -s -X DELETE --user ${ravelloUser}:${ravelloPass} https://cloud.ravellosystems.com/api/v1/applications/${appID}
  exit 1
fi

#curl -s -X DELETE --user ${ravelloUser}:${ravelloPass} https://cloud.ravellosystems.com/api/v1/applications/${appID}

echo "The HEAT templates are in $outputdir/{stack_admin.yaml,stack_user.yaml}"