# Migrating images from one OpenStack to another

Today we have a migration server, this server is used to convert images from IBM Cloud and import to Ceph and Glance, 
this server also have access to all ceph gluster


## Connect to Migration server 

Use opentlc backdor to get access

```bash
ssh -l root 169.47.25.34
```

## Export Image


Let's use and example to migrate an image from Red Cluster to Green Cluster, in that case our source image will be Red

### Environment Variables

```bash
export CEPH_CONF=/etc/ceph/red.conf
```

### Export from Ceph to a raw image

```bash
rbd export red-images/<<IMAGE_ID>>@snap /tmp/<<IMAGE_NAME>>-<<IMAGE_ID>>
```

* Replace <<IMAGE_ID>> by the source image ID
* Replace <<IMAGE_NAME>> by the source image name

## Import image to Ceph

In this example we are using Green as the destination 

### Environment Variables

```bash
export CEPH_CONF=/etc/ceph/green.conf
```

### Import image

```bash
rbd import /tmp/<<IMAGE_NAME>>-<<IMAGE_ID>> green-images/<<IMAGE_ID>>
```

### Create snapshot

```bash
rbd snap create green-images/<<IMAGE_ID>>@snap
```


## Create Glance Image

### Get cluster ID

We need the Ceph cluster id, this information will be used to create the Glance image
```bash
ceph fsid
```

### Creating image

```bash
openstack --os-cloud green image create --disk-format raw --id <<IMAGE_ID>> --container-format bare --public <<IMAGE_NAME>> 
```

### Update location

```bash
glance --os-user-domain-name Default --os-project-id e5e3e1713fc040d99f01d55005a61a3c --os-project-name admin --os-username admin --os-auth-url http://169.62.96.66:5000/v3  location-add --url 'rbd://<<CLUSTER_ID>>/green-images/<<IMAGE_ID>>/snap' <<IMAGE_ID>>
```

