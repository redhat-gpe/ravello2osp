# Convert qcow image to Ceph Glance

## Requirements

* `yum install qemu-img`
* `yum install ceph-common python-rbd`
* `ceph.conf` from the ceph cluster
* Client admin key or user can write on the glance pool
* OS_* variables to access OpenStack

## How to
1) Convert qcow2 to ceph pool

    ```bash
    export IMAGE_ID=`uuidgen`
    export POOL="red-images"
    qemu-img convert -f qcow2 -O raw 5Network-Node-01-root.qcow2 rbd:$POOL/$IMAGE_ID
    ```

2) Create image snapshot and protect 

    ```bash
    rbd snap create $POOL/$IMAGE_ID@snap
    rbd snap protect $POOL/$IMAGE_ID@snap
    ```

3) Create empty glance image 

    ```bash
    glance image-create --disk-format raw --id $IMAGE_ID --container-format bare --name IMAGE_NAME
    ```
4) Update image location

    ```bash
    CLUSTER_ID=`ceph fsid`
    glance --os-image-api-version 2 location-add --url "rbd://$CLUSTER_ID/$POOL/$IMAGE_ID/snap" $IMAGE_ID
    ```
