#!/usr/bin/python
# Copyright: (c) 2020, Marcos Amorim <mamorim@redhat.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

ANSIBLE_METADATA = {
    'metadata_version': '1.1',
    'status': ['preview'],
    'supported_by': 'community'
}

DOCUMENTATION = '''
---
module: ibm_cos

short_description: manage objects in IBM Cloud Object Store using S3

version_added: "2.7"

description:
    - This module allows the user to manage S3 buckets and the objects within them. Includes support for creating 
      objects, retrieving objects as files or strings and generating download links.
      This module has a dependency on ibm-cos-sdk.

options:
  ibm_auth_endpoint:
    description:
      - Authentication endpoint https://iam.cloud.ibm.com/identity/token
    default: "https://iam.cloud.ibm.com/identity/token"
    required: false
    type: str
  ibm_endpoint
    description:
      - is a service endpoint URL, inclusive of the https:// protocol. This value is not the endpoints value that is 
      found in the Service Credential. For more information about endpoints, see Endpoints and storage locations.
      https://cloud.ibm.com/docs/services/cloud-object-storage/iam?topic=cloud-object-storage-service-credentials
    required: true
    type: str
  ibm_api_key:
    description: 
      - is the value found in the Service Credential as apikey.
        https://cloud.ibm.com/docs/services/cloud-object-storage/iam?topic=cloud-object-storage-service-credentials
      required: true
      type: str
  ibm_resource_id:
    description: 
      - ibm_service_instance_id is the value found in the Service Credential as resource_instance_id.
        https://cloud.ibm.com/docs/services/cloud-object-storage/iam?topic=cloud-object-storage-service-credentials
    required: true
    type: str
  bucket:
    description:
      - Bucket name.
    required: true
    type: str
  images:
    description:
      - List of images to convert and upload
    type: str
  output_dir:
    description:
      - Directory to save images
    type: str
  overwrite:
    description:
      - Force overwrite either locally on the filesystem or remotely with the object/key. Used with PUT and GET operations.
        Boolean or one of [always, never, different], true is equal to 'always' and false is equal to 'never', new in 2.0.
        When this is set to 'different', the md5 sum of the local file is compared with the 'ETag' of the object/key in S3.
        The ETag may or may not be an MD5 digest of the object data. See the ETag response header here
        U(https://docs.aws.amazon.com/AmazonS3/latest/API/RESTCommonResponseHeaders.html)
    default: 'always'
    aliases: ['force']
    type: str
  threshold_file_size:
    description:
      - The transfer size threshold for which multipart uploads, downloads, and copies will automatically be triggered.
    type: int
    default: 15
  chunk_file_size:
    description:
      - The max size of each chunk in the io queue. Currently, this is size used when read is called on the downloaded stream as well.
    type: int
    default: 5

extends_documentation_fragment:
    - aws_s3

author:
    - Marcos Amorim (@marcosmamorim)
'''

EXAMPLES = '''
- name: Test module convert
  convert_images:
    ibm_endpoint: "{{ ibm_endpoint }}"
    ibm_auth_endpoint: "{{ ibm_auth_endpoint }}"
    ibm_api_key: "{{ ibm_api_key }}"
    ibm_resource_id: "{{ ibm_resource_id }}"
    bucket: "{{ ibm_bucket_name }}"
    blueprint: "{{ project_name }}"
    output_dir: "{{ output_dir }}"
    images: "{{ images }}"
    overwrite: None
'''

RETURN = '''
'''

from ansible.module_utils.basic import *
from ansible.module_utils.openstack import openstack_full_argument_spec, openstack_module_kwargs, openstack_cloud_from_module
import ibm_boto3
import os
from ibm_botocore.client import Config, ClientError

try:
    import botocore
except ImportError:
    pass  # will be detected by imported AnsibleAWSModule


def get_connection(module):
    endpoint = module.params['ibm_endpoint']
    api_key = module.params['ibm_api_key']
    auth_endpoint = module.params['ibm_auth_endpoint']
    resource_id = module.params['ibm_resource_id']

    cos = ibm_boto3.resource("s3",
                             ibm_api_key_id=api_key,
                             ibm_service_instance_id=resource_id,
                             ibm_auth_endpoint=auth_endpoint,
                             config=Config(signature_version="oauth"),
                             endpoint_url=endpoint
                             )
    return cos


def multi_part_download(module, object, dest):
    module.log(msg="Starting download %s to %s" % (object, dest))
    if module.check_mode:
        module.exit_json(msg="PUT operation skipped - running in check mode", changed=True)

    try:
        s3 = get_connection(module)
        bucket_name = module.params.get('bucket')
        bucket = s3.Bucket(bucket_name)
        obj = bucket.Object(object)

        file_size = module.params.get('chunk_file_size')
        threshold_file = module.params.get('threshold_file_size')

        # set 5 MB chunks
        part_size = 1024 * 1024 * file_size

        # set threadhold to 15 MB
        file_threshold = 1024 * 1024 * threshold_file

        # set the transfer threshold and chunk size
        transfer_config = ibm_boto3.s3.transfer.TransferConfig(
            multipart_threshold=file_threshold,
            multipart_chunksize=part_size
        )

        with open(dest, 'wb') as data:
            obj.download_fileobj(Fileobj=data, Config=transfer_config)
        module.log(msg="Transfer for {0} Complete!\n".format(dest))
        return True
    except Exception as e:
        module.exit_json(msg="Unable to complete multi-part download: {0}".format(e))


def multi_part_upload(module, item_name, file_path):
    module.log(msg="Starting upload %s from %s" % (item_name, file_path))
    if module.check_mode:
        module.exit_json(msg="PUT operation skipped - running in check mode", changed=True)

    try:
        s3 = get_connection(module)
        bucket = module.params.get('bucket')
        file_size = module.params.get('chunk_file_size')
        threshold_file = module.params.get('threshold_file_size')

        # set 5 MB chunks
        part_size = 1024 * 1024 * file_size

        # set threadhold to 15 MB
        file_threshold = 1024 * 1024 * threshold_file

        # set the transfer threshold and chunk size
        transfer_config = ibm_boto3.s3.transfer.TransferConfig(
            multipart_threshold=file_threshold,
            multipart_chunksize=part_size
        )

        # the upload_fileobj method will automatically execute a multi-part upload
        # in 5 MB chunks for all files over 15 MB
        with open(file_path, "rb") as file_data:
            s3.Object(bucket, item_name).upload_fileobj(
                Fileobj=file_data,
                Config=transfer_config
            )
    except ClientError as be:
        module.log(msg="CLIENT ERROR: {0}\n".format(be))
        return False
    except Exception as e:
        module.log(msg="Unable to complete multi-part upload: {0}".format(e))
        return False
    module.log(msg="Upload completed for {0}".format(item_name))
    return True


def glance_image_exists(module, image_name):
    sdk, cloud = openstack_cloud_from_module(module)
    try:
        image = cloud.get_image(image_name)
        # module.log("IMAGE Result: %s" % image)
        return image

    except sdk.exceptions.OpenStackCloudException as e:
        module.fail_json(msg=str(e))


def image_exits(module, image_name, content=False):
    endpoint = module.params['ibm_endpoint']
    api_key = module.params['ibm_api_key']
    auth_endpoint = module.params['ibm_auth_endpoint']
    resource_id = module.params['ibm_resource_id']
    bucket = module.params.get('bucket')
    cos = ibm_boto3.client("s3",
                             ibm_api_key_id=api_key,
                             ibm_service_instance_id=resource_id,
                             ibm_auth_endpoint=auth_endpoint,
                             config=Config(signature_version="oauth"),
                             endpoint_url=endpoint
                             )

    module.log(msg="Checking if {0} exists".format(image_name))
    try:
        response = cos.list_objects_v2(Bucket=bucket, Prefix=image_name)
        if 'Contents' in response:
            if content:
                return response['Contents']
            else:
                return True
    except Exception as e:
        module.log(msg="Error get bucket content. {0}".format(e))
        return False


def convert_to_qcow(module):
    images = module.params.get('images')
    output_dir = module.params.get('output_dir')
    blueprint = module.params.get('blueprint')
    overwrite = module.params.get('overwrite')

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    for img in images:
        device = "/dev/{0}".format(img[1])
        name = "%s.qcow2" % img[2]
        outfile = "%s/%s" % (output_dir, name)
        cmd = "qemu-img convert -O qcow2 -p %s '%s'" % (device, outfile)

        item_name = "%s/%s" % (blueprint, name)

        if image_exits(module, item_name) and not overwrite:
            module.log("Image {0} already uploaded to IBM. Continue ".format(item_name))
            continue

        module.log("Start converting '%s' blueprint, image name '%s' to '%s' directory" % (blueprint, name, output_dir))

        if os.path.isfile(outfile) and overwrite == 'always':
            os.remove(outfile)

        try:
            module.log("Converting command: %s" % cmd)
            rc, out, err = module.run_command(cmd, check_rc=True)
        except Exception as e:
            module.log(msg="Unable to complete the conversion: {0}. Go to next disk".format(e))
            module.exit_json(msg="Error converting image %s" % name)

        module.log("DEBUG: rc: %s - out: %s - err: %s" % (rc, out, err))
        retries = module.params.get('retries')
        while retries > 0:
            if multi_part_upload(module, item_name, outfile):
                module.log(msg="Successfully uploaded {0}".format(name))
                break
            retries = retries - 1

    module.exit_json(msg="Conversion successfully executed for {0}".format(blueprint))


def check_snapshot_ceph(module, img_id):
    glance_pool = module.params.get("glance_pool")

    cmd = 'rbd snap list {0}/{1}'.format(glance_pool, img_id)
    rc, out, err = module.run_command(cmd)
    module.log("CHECK SNAP: %s - rc: %s - out: %s - %s" % (cmd, rc, out, err))

    if len(out) == 0:
        return True
    else:
        return False


def convert_from_ceph(module, direct_url, image_name):
    ceph_cluster_id = direct_url[2]
    ceph_pool = direct_url[3]
    ceph_image_id = direct_url[4]
    output_dir = module.params.get("output_dir")
    project = module.params.get("project")
    overwrite = boolean(module.params.get("overwrite"))
    object_name = "%s/%s.qcow2" % (project, image_name)
    file_path = "%s/%s.qcow2" % (output_dir, image_name)

    module.log(
        "Ceph Cluster ID: {0} - Ceph Pool: {1} - Image ID: {2} - Image Name: {3}".format(ceph_cluster_id, ceph_pool, ceph_image_id, image_name))

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    if not check_snapshot_ceph(module, ceph_image_id):
        if image_exits(module, object_name) is not None and not overwrite:
            module.log("Image {0} already exists. Overwrite: {1}".format(object_name, overwrite))
            return True

        cmd = "qemu-img convert -O qcow2 -f raw 'rbd:{0}/{1}@snap' '{2}' ".format(ceph_pool, ceph_image_id, file_path)
        module.log(cmd)
        module.run_command(cmd, check_rc=True)
        if multi_part_upload(module, object_name, file_path):
            os.remove(file_path)


def delete_image(module):
    blueprint = module.params.get('project')
    bucket_name = module.params.get('bucket')
    image_list = image_exits(module, blueprint, True)
    cos = get_connection(module)
    if image_list is None:
        module.exit_json(msg="Image does not exists")
    for img in image_list:
        try:
            cos.Object(bucket_name, img['Key']).delete()
            module.log("Image {} deleted".format(img['Key']))
        except ClientError as be:
            module.exit_json(msg="CLIENT ERROR: {0}\n".format(be))
        except Exception as e:
            module.exit_json(msg="Unable to delete item: {0}".format(e))


def update_image(module):
    blueprint = module.params.get('project')
    images = module.params.get("images")
    for image in images:
        image_facts = glance_image_exists(module, image)
        if image_facts is None:
            module.log("Images {} not exists".format(image))
            continue

        image_name = image_facts['name']
        if blueprint in image_facts['name']:
            image_name = image_facts['name'][len(blueprint)+1:]

        module.log("Image Facts: %s" % image_facts)
        if not 'direct_url' in image_facts:
            module.log("Directl URL does not exists in the images")
            continue

        direct_url = image_facts['direct_url'].split('/')
        module.log("DEBUG direct_url: {}".format(direct_url))
        if not direct_url[0] == "rbd:":
            module.log("The image {} is not RBD image to convert".format(image))

        convert_from_ceph(module, direct_url, image_name)

    module.exit_json(msg="Conversion successfully executed for {0}".format(blueprint))


def convert_to_raw(module):
    images = module.params.get('images')
    output_dir = module.params.get('output_dir')
    blueprint = module.params.get('blueprint')
    overwrite = module.params.get('overwrite')
    image_to_upload = []
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    for img in images:
        disk_name = "%s" % img[2]
        image_name = "%s-%s" % (blueprint, disk_name)
        module.log("Check if image exists: %s" % image_name)

        check_image = glance_image_exists(module, image_name)

        if check_image is not None and overwrite != 'always':
            module.log("Image %s already uploaded to glance. skipping..." % image_name)
            continue

        module.log("Image does not exists starting download: %s" % image_name)
        object_name = "%s/%s.qcow2" % (blueprint, disk_name)
        dest_disk = "%s/%s.qcow2" % (output_dir, disk_name)
        raw_name = "%s/%s.raw" % (output_dir, disk_name.replace(" ", "-"))

        image_to_upload.extend([{"name": image_name, "filename": raw_name, "blueprint": blueprint}])

        if not multi_part_download(module, object_name, dest_disk):
            module.exit_json(msg="Error download images %s to %s " % (object_name, dest_disk))

        cmd = "qemu-img convert -O raw -p '%s' '%s/%s.raw'" % (dest_disk, output_dir, disk_name.replace(" ", "-"))
        module.log("Stating conversion from qcow to raw for the image %s/%s.raw" % (output_dir,
                                                                                    disk_name.replace(" ", "-")))
        rc, out, err = module.run_command(cmd, check_rc=True)
    module.exit_json(changed=False, openstack_image=image_to_upload)


def run_module():
    module_args = dict(
        ibm_endpoint=dict(type='str', required=True),
        ibm_api_key=dict(type='str', required=True, no_log=True),
        ibm_auth_endpoint=dict(type='str', default='https://iam.cloud.ibm.com/identity/token'),
        ibm_resource_id=dict(type='str', required=True),
        project=dict(aliases=['blueprint'], type='str', required=True),
        bucket=dict(required=True),
        mode=dict(choices=['upload', 'download', 'update', 'delete'], default='upload'),
        output_dir=dict(default="/images/import"),
        glance_pool=dict(required=False),
        images=dict(type=list),
        overwrite=dict(aliases=['force'], default=False, type=bool),
        chunk_file_size=dict(default=5, type='int'),
        threshold_file_size=dict(default=15, type='int'),
        retries=dict(default=5, type=int)
    )

    argument_spec = openstack_full_argument_spec(
        image=dict(required=False),
    )
    module_args.update(argument_spec)
    module_kwargs = openstack_module_kwargs()
    module = AnsibleModule(module_args, **module_kwargs)

    # if the user is working with this module in only check mode we do not
    # want to make any changes to the environment, just return the current
    # state with no modifications
    if module.check_mode:
        module.exit_json(msg="Operation skipped - running in check mode", changed=True)

    mode = module.params.get("mode")
    if mode == "upload":
        convert_to_qcow(module)

    if mode == "download":
        convert_to_raw(module)

    if mode == "update":
        update_image(module)

    if mode == "delete":
        delete_image(module)

    module.exit_json(failed=False)


def main():
    run_module()

if __name__ == '__main__':
    main()

