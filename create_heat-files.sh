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

outputdir="imported/${blueprint}-playbooks"

mkdir -p $outputdir

python ravello2osp.py --blueprint $blueprint --output $outputdir --user $ravelloUser --password $ravelloPass --domain $ravelloDomain
