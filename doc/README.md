# Convert Ravello Blueprint to OpenStack

Several scripts perform the activities for converting the blueprint to OpenStack, this includes:

* One part is for export the disk images and upload the images to IBM Cloud using QCOW2 format
* Second part is to generate Heat Orchestration Template (HOT) to create the project and the elements inside
* Third part is download the images from IBM Cloud, convert to RAW format and import to Glance (disabled by default)

## Requirements 

### Install python requirements
To perform the conversions, it is necessary to install some python modules, use the file `requirements.txt`

```bash
pip install -r requirements.txt
```

### Configure Credentials 
Configure the `creds.inc` file with the information below

| Parameter         | Description   
| ------------------|:-------------
| ravelloUser       | Ravello Username
| ravelloPass       | Ravello Password 
| ravelloDomain     | Ravello Domain Identity (default is `None`)
| ospUser           | OpenStack Admin Username
| ospPass           | OpenStack Admin Password
| ospProject        | OpenStack Project (default is `admin`)
| ospAuthURL        | OpenStack Keystone URL
| pubKeyFile        | Your SSH key (default is `~/.ssh/id_rsa`)
| ibm_api_key       | IBM Cloud Storage Key**
| ibm_bucket_name   | IBM Cloud Storage bucket name (default is `gpte-novello-images`)
| ibm_endpoint      | IBM Cloud Storage URL
| ibm_auth_endpoint | IBM Cloud Storage auth URL (default is `https://s3.us-east.cloud-object-storage.appdomain.cloud`)
| ibm_resource_id   | IBM Cloud Storage Resource ID**
| import_host       | IP / Hostname to the import host server running on OpenStack**
| import_host_user  | Username to connect to the import host (default is `cloud-user`)

    
** Request credentials to Marcos Amorim <mamorim@redhat.com>, Patrick Rutledge <prutledg@redhat.com> 
or Josh Disraeli <jdisrael@redhat.com>

```bash
cp creds.inc.example creds.inc
```

Edit this file and setting up your credentials


### Executing the conversion

The `convert.sh` or` convert-v2.sh` script must be used to perform the blueprint conversion, the scripts need only one parameter, which is the name of the blueprint in Ravello

```bash
./convert.sh <<blueprint_name>>
```

## Known issues

If you see this error message:
```bash
TASK [Wait 600 seconds for target connection to become reachable/usable] *******************************************************************************************************************************
Wednesday 26 February 2020  11:20:18 -0500 (0:00:00.061)       0:00:00.061 **** 
 [WARNING]: Unhandled error in Python interpreter discovery for host exporter-exporterappmamorim-hr28csvv.srv.ravcloud.com: Failed to connect to the host via ssh: ssh: connect to host exporter-
exporterappmamorim-hr28csvv.srv.ravcloud.com port 22: Network is unreachable

```
Go to Ravello and restart your application, this issues happens because the application started using the wrong disk