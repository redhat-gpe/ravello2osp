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

python ravello2osp.py  --blueprint $blueprint --output $outputdir --user $ravelloUser --password $ravelloPass

if [ $? -ne 0 ]
then
  echo "ravello2osp.py failed."
  exit 1
fi

outfile=/tmp/.convert.$$
appName="exporter-app"

if [ -n "$pubKeyFile" ]
then
  echo "Using public key $pubKeyFile"
  pk="--pubkeyfile $pubKeyFile"
else
  echo "Using password auth"
  pk=""
fi

python create_ravello_disks_project.py -n $appName -u $ravelloUser -p $ravelloPass $pk > $outfile

if [ $? -ne 0 ]
then
  echo "create_ravello_disks_project.py failed."
  exit 1
fi

appID=`grep 'App id' $outfile|cut -f2 -d:`
vmID=`grep 'VM id' $outfile|cut -f2 -d:`
ravelloHost=`grep 'DNS:' $outfile|cut -f2 -d:|sed 's/ //g'`

rm -f $outfile

python ravellodisks2glance.py --auth-url $ospAuthURL --auth-user $ospUser --auth-password $ospPass \
  -o $outputdir -bp $blueprint -u $ravelloUser -p $ravelloPass -a $appID -m $vmID --host $ravelloHost \
  --osp-project $ospProject --ibm-auth-endpoint $ibm_auth_endpoint --ibm-endpoint $ibm_endpoint \
  --ibm-api-key $ibm_api_key --ibm-bucket-name $ibm_bucket_name --ibm-resource-id "$ibm_resource_id" \
  --importhost $import_host

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
ansible-playbook --skip-tags shutdown -i $outputdir/playbook_import_disks.hosts $outputdir/playbook_export_disks.yaml -u root

if [ $? -ne 0 ]
then
  echo "ansible-playbook export disks failed."
  exit 1
fi

ansible-playbook --skip-tags shutdown -i $outputdir/playbook_import_disks.hosts $outputdir/playbook_import_disks.yaml -u root

if [ $? -ne 0 ]
then
  echo "ansible-playbook import failed."
  exit 1
fi

curl -s -X DELETE --user ${ravelloUser}:${ravelloPass} https://cloud.ravellosystems.com/api/v1/applications/${appID}

echo "The HEAT templates are in $outputdir/{stack_admin.yaml,stack_user.yaml}"
