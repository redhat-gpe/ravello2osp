#!/usr/bin/python

# Copyright: (c) 2020, Marcos Amorim <mamorim@redhat.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

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
  mode:
    description:
      - Switches the module behaviour between put (upload), get (download), geturl (return download url, Ansible 1.3+),
        getstr (download object as string (1.3+)), list (list keys, Ansible 2.0+), create (bucket), delete (bucket),
        and delobj (delete object, Ansible 2.0+).
    required: true
    choices: ['get', 'put', 'delete', 'create', 'geturl', 'getstr', 'delobj', 'list']
    type: str
  bucket:
    description:
      - Bucket name.
    required: true
    type: str
  src:
    description:
      - The source file path when performing a PUT operation.
    version_added: "1.3"
    type: str
  dest:
    description:
      - The destination file path when downloading an object/key with a GET operation.
    version_added: "1.3"
    type: path
  object:
    description:
      - Keyname of the object inside the bucket. Can be used to create "virtual directories", see examples.
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
- name: Get bucket {{ ibm_bucket_name }} content
  ibm_cos:
    ibm_endpoint: "{{ ibm_endpoint }}"
    ibm_auth_endpoint: "{{ ibm_auth_endpoint }}"
    ibm_api_key: "{{ ibm_api_key }}"
    ibm_resource_id: "{{ ibm_resource_id }}"
    mode: list
    bucket: "{{ ibm_bucket_name }}"

- name: Upload file
  ibm_cos:
    ibm_endpoint: "{{ ibm_endpoint }}"
    ibm_auth_endpoint: "{{ ibm_auth_endpoint }}"
    ibm_api_key: "{{ ibm_api_key }}"
    ibm_resource_id: "{{ ibm_resource_id }}"
    mode: put
    bucket: "{{ ibm_bucket_name }}"
    object: "/1Desktop Host-vol1"
    src: "/root/images/1Desktop Host-vol1"

- name: Download S3 file  
  ibm_cos:
    ibm_endpoint: "{{ ibm_endpoint }}"
    ibm_auth_endpoint: "{{ ibm_auth_endpoint }}"
    ibm_api_key: "{{ ibm_api_key }}"
    ibm_resource_id: "{{ ibm_resource_id }}"
    mode: get
    bucket: "{{ ibm_bucket_name }}"
    object: "/1Desktop Host-vol1"
    dest: "/tmp//1Desktop Host-vol1"
'''

RETURN = '''
s3_keys:
  description: List of object keys.
  returned: (for list operation)
  type: list
  elements: str
  sample:
  - prefix1/
  - prefix1/key1
  - prefix1/key2
'''

from ansible.module_utils.basic import AnsibleModule
import ibm_boto3
import os
from ibm_botocore.client import Config, ClientError

try:
    import botocore
except ImportError:
    pass  # will be detected by imported AnsibleAWSModule


def path_check(path):
    if os.path.exists(path):
        return True
    else:
        return False


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
    # module.fail_json(msg="Connection {0}".format(dir(cos)))
    return cos


def get_bucket_contents(module, bucket, s3):

    if module.check_mode:
        module.exit_json(msg="Get operation skipped - running in check mode", changed=True)

    keys = []
    try:
        files = s3.Bucket(bucket).objects.all()
        for content in files:
            keys.extend([content.key])
    except ClientError as be:
        module.fail_json(msg="CLIENT ERROR: {0}\n".format(be))
    except Exception as e:
        module.fail_json(msg="Unable to retrieve bucket contents: {0}".format(e))

    module.exit_json(msg="LIST operation complete", s3_keys=keys)


def download_s3file(module, s3, bucket_name, object, dest):
    bucket = s3.Bucket(bucket_name)
    obj = bucket.Object(object)

    # set 5 MB chunks
    part_size = 1024 * 1024 * 5

    # set threadhold to 15 MB
    file_threshold = 1024 * 1024 * 15

    # set the transfer threshold and chunk size
    transfer_config = ibm_boto3.s3.transfer.TransferConfig(
        multipart_threshold=file_threshold,
        multipart_chunksize=part_size
    )

    try:
        with open(dest, 'wb') as data:
            obj.download_fileobj(Fileobj=data,
                                 Config=transfer_config)
        module.exit_json(msg="Transfer for {0} Complete!\n".format(dest))
    except Exception as e:
        module.fail_json(msg="Unable to complete multi-part download: {0}".format(e))


def multi_part_upload(module, s3, bucket, item_name, file_path):
    if module.check_mode:
        module.exit_json(msg="PUT operation skipped - running in check mode", changed=True)

    try:

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

        module.exit_json(msg="Transfer for {0} Complete!\n".format(item_name))
    except ClientError as be:
        module.fail_json(msg="CLIENT ERROR: {0}\n".format(be))
    except Exception as e:
        module.fail_json(msg="Unable to complete multi-part upload: {0}".format(e))


def run_module():
    module_args = dict(
        ibm_endpoint=dict(type='str',required=True),
        ibm_api_key=dict(type='str',required=True),
        ibm_auth_endpoint=dict(type='str', default='https://iam.cloud.ibm.com/identity/token'),
        ibm_resource_id=dict(type='str',required=True),
        mode=dict(choices=['get', 'put', 'delete', 'create', 'geturl', 'getstr', 'delobj', 'list'], required=True),
        bucket=dict(required=True),
        src=dict(),
        object=dict(),
        dest=dict(default=None, type='path'),
        overwrite=dict(aliases=['force'], default='always'),
        chunk_file_size=dict(default=5, type='int'),
        threshold_file_size=dict(default=15, type='int'),

    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
        required_if=[['mode', 'put', ['src', 'object', 'bucket']],
                     ['mode', 'get', ['dest', 'object', 'bucket']]]
    )

    mode = module.params.get('mode')
    bucket = module.params.get('bucket')
    src = module.params.get('src')
    obj = module.params.get('object')
    dest = module.params.get('dest', '')
    overwrite = module.params.get('overwrite')

    # if the user is working with this module in only check mode we do not
    # want to make any changes to the environment, just return the current
    # state with no modifications
    if module.check_mode:
        module.exit_json(msg="Operation skipped - running in check mode", changed=True)

    s3 = get_connection(module)

    if mode == 'list':
        get_bucket_contents(module, bucket, s3)

    if mode == 'put':
        if not path_check(src):
            module.fail_json(msg="Local object for PUT does not exist")

        multi_part_upload(module, s3, bucket, obj, src)

    if mode == 'get':
        if path_check(dest) and overwrite != 'always':
            module.exit_json(msg="Local object already exists and overwrite is disabled.", changed=False)

        download_s3file(module, s3, bucket, obj, dest)

    module.exit_json(failed=False)

def main():
    run_module()

if __name__ == '__main__':
    main()

