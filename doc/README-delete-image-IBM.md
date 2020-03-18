# Playbook to delete images from IBM 

you must configure your `creds.inc` with IBM Cloud credentials

# Set environment variables

. creds.inc

# Run playbook to remove images from IBM

`ansible-playbook  ansible-playbook  delete-images.yaml -e project=<<BLUEPRINT_NAME>>`
