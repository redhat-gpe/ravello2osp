#!/bin/bash

if [ -z "$ravelloDomain" ];
then
  ravelloDomain=None
fi

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
appName="exporter-app-${ravelloUser}-$$"

outputdir="imported/${blueprint}-playbooks"

mkdir -p $outputdir
tmpdir=/tmp/tmpdir.$$
tmpfile=/tmp/tmpfile.$$.yaml

mkdir -p $tmpdir
git -C $tmpdir clone https://github.com/redhat-gpe/novello-templates.git > /dev/null 2>&1
dns_ip=`python3 suggest-dns.py $tmpdir/novello-templates/heat-templates/$blueprint/stack_user.yaml`
rm -rf $tmpdir

python3 convert-blueprint.py  --blueprint $blueprint --output $outputdir --user $ravelloUser \
  --password $ravelloPass --name $appName $pk --importhost $import_host --auth-url $ospAuthURL \
  --auth-user $ospUser --auth-password $ospPass --ibm-endpoint $ibm_endpoint --ibm-api-key $ibm_api_key \
  --ibm-bucket-name $ibm_bucket_name --ibm-resource-id $ibm_resource_id  --domain-id $ravelloDomain --heatonly \
  --enabledns \
  --dns-ip $dns_ip

#python3 merge.py --file1 $outputdir/stack_user.yaml --file2 $tmpfile --output $outputdir/stack_user.yaml
#rm -f $tmpfile
#exit

gsed -i "s/rhpds.opentlc.com/DOMAIN/g" $outputdir/stack_user.yaml

echo "Update the ranges in $outputdir/stack_user.yaml as seen here"
python3 suggest-range.py $outputdir/stack_user.yaml

echo "After updating run: this command:"
echo ansible-playbook -i $outputdir/inventory playbook_update_heat_templates_repo.yml -u root -e blueprint_name=$blueprint

