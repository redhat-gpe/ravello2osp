#!/bin/bash

usage() {
echo "Usage: $0 <<blueprint name>> [options]"
echo -e "\t-heatonly|--heatonly - Create heat files and update repository"
echo -e "\t-of=*|--offset=* From which disk number start to migrate disks [default: 0]"
echo -e "\t-maxcount=*|--maxcount=* Max number of disks to be attached [default: 10]"
}

if [ ! -f creds.inc ]
then
  echo "Please create creds.inc from creds.inc.example"
  exit 1
fi

. creds.inc

if [ -z "$1" ]
then
  usage
fi

blueprint=$1

options=""
heatonly=false
for i in "$@"
do
case $i in
    -heatonly|--heatonly)
    options="$options --heatonly"
    heatonly=true
    shift
    ;;
    -of=*|--offset=*)
    options="$options -of ${i#*=}"
    shift
    ;;
    -maxcount=*|--maxcount=*)
    options="$options --max-count ${i#*=}"
    shift
    ;;
    -h|--help)
    usage
    exit 0
    ;;
    *)
          # unknown option
    ;;
esac
done

outputdir="imported/${blueprint}-playbooks"
mkdir -p $outputdir

appName="exporter-app-${ravelloUser}-$$"

if [ -n "$pubKeyFile" ]
then
  echo "Using public key $pubKeyFile"
  pk="--pubkeyfile $pubKeyFile"
else
  echo "Using password auth"
  pk=""
fi

echo "Deploying Ravello app: $appName"

python3 convert-blueprint.py  --blueprint $blueprint --output $outputdir --user $ravelloUser \
  --password $ravelloPass --name $appName $pk --importhost $import_host --auth-url $ospAuthURL \
  --auth-user $ospUser --auth-password $ospPass --ibm-endpoint $ibm_endpoint --ibm-api-key $ibm_api_key \
  --ibm-bucket-name $ibm_bucket_name --ibm-resource-id $ibm_resource_id  --domain-id $ravelloDomain $options

if [ $? -ne 0 ]
then
  echo "convert-blueprint.py failed."
  python3 delete-app.py --user $ravelloUser   --password $ravelloPass --domain-id $ravelloDomain -a ${appName}
  exit 1
fi

if [ "$heatonly" == "true" ]
then
  ansible-playbook -i $outputdir/inventory playbook_update_heat_templates.yml -u root -e blueprint_name=$blueprint
  exit
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
CURRENT=$PWD
cd  $outputdir
rm -f library
ln -s ../../library
cd $CURRENT
ansible-playbook --skip-tags shutdown -i $outputdir/inventory $outputdir/class_playbook_export_disks.yaml -u root

if [ $? -ne 0 ]
then
  echo "ansible-playbook export disks failed."
  python3 delete-app.py --user $ravelloUser   --password $ravelloPass --domain-id $ravelloDomain -a ${appName}
  exit 1
fi

#ansible-playbook --skip-tags shutdown -i $outputdir/inventory $outputdir/class_playbook_import_disks.yaml -u root
#
#if [ $? -ne 0 ]
#then
#  echo "ansible-playbook import failed."
#  #curl -s -X DELETE --user ${ravelloUser}:${ravelloPass} https://cloud.ravellosystems.com/api/v1/applications/${appID}
#  exit 1
#fi

echo "Deleting $appName from Ravello"
python3 delete-app.py --user $ravelloUser   --password $ravelloPass --domain-id $ravelloDomain -a ${appName}

echo "The HEAT templates are in $outputdir/{stack_admin.yaml,stack_user.yaml}"
