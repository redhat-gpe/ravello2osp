# Convert Glance image to IBM Cloud

This process convert image from OpenStack Glance and upload to IBM Cloud

# Requirements

1. Name of blueprint
2. Glance image ID
3. OpenStack identities
4. IBM Credentials
5. Access to Import host using opentlc backdoor key 


# Configure Secrets

1) Create a secret file

```bash
vi my_secrets.yaml
```
```yaml
ibm_api_key: "<<<IBM_API_KEY>>>"
ibm_bucket_name: "gpte-novello-images"
ibm_endpoint: "https://s3.us-east.cloud-object-storage.appdomain.cloud"
ibm_auth_endpoint: "https://iam.cloud.ibm.com/identity/token"
ibm_resource_id: "crn:v1:bluemix:public:cloud-object-storage:global:a/42479cf18c194be58cbfc2ab1a476649:f9a99873-8bf9-409a-9ba7-325738f6fce9::"
osp_auth_url: http://169.47.188.15:5000/v3
osp_auth_username: opentlc-mgr
osp_auth_password: "<<OPENTLC_PASSWORD>>"
osp_auth_project_domain: "default"
osp_auth_user_domain: "default"
```

# Run playbook to convert the image 

```bash
ansible-playbook -i inventory-update-images playbook_convert-osp-to-ibm.yml -e @my_secrets.yaml
```