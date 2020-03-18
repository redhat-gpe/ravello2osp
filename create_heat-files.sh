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

python3 convert-blueprint.py  --blueprint $blueprint --output $outputdir --user $ravelloUser \
  --password $ravelloPass --name $appName $pk --importhost $import_host --auth-url $ospAuthURL \
  --auth-user $ospUser --auth-password $ospPass --ibm-endpoint $ibm_endpoint --ibm-api-key $ibm_api_key \
  --ibm-bucket-name $ibm_bucket_name --ibm-resource-id $ibm_resource_id  --domain-id $ravelloDomain --heatonly
