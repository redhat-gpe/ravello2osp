# ravello2osp

Repository with the scripts to export a Ravello Blueprint into to OpenStack, contains two parts:

* One part is for export the disk images
* Second part is to generate Heat Orchestration Template (HOT) to create the project and the elements inside

Check the examples/ directory to see an example output


Before to use you have to install *ravello-sdk*:
~~~
# git clone https://github.com/ravello/python-sdk.git 
# cd python-sdk
# python setup.py install
~~~

Main script is **ravello2osp.py**

Syntax:
~~~
usage: ravello2osp.py [-h] [-o OUTPUT] [-bp BLUEPRINT] [-u USER] [-p PASSWORD]
                      [-j JSONF]

optional arguments:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
                        Output directory

  -bp BLUEPRINT, --blueprint BLUEPRINT
                        Name of the blueprint
  -u USER, --user USER  Ravello domain/username
  -p PASSWORD, --password PASSWORD
                        Ravello password

  -j JSONF, --jsonf JSONF
                        JSON file containing definition
~~~

Example:
`# python ravello2osp.py -bp OPTLC-OSP_AdvancedNetworking-v6.4-bp -o OSPAN -u a493395/alberto.gonzalez@redhat.com -p SECRET`

Then you can create the project as administrator
~~~
$ openstack stack create -t stack_admin.yaml stack_admin_gptestudent1 --parameter project_name=gptestudent1 --parameter project_description=josegonz-redhat.com --wait
2019-08-02 18:01:47Z [stack_admin_gptestudent1]: CREATE_IN_PROGRESS  Stack CREATE started
2019-08-02 18:01:47Z [stack_admin_gptestudent1.openstack_project]: CREATE_IN_PROGRESS  state changed
2019-08-02 18:01:48Z [stack_admin_gptestudent1.openstack_project]: CREATE_COMPLETE  state changed
2019-08-02 18:01:48Z [stack_admin_gptestudent1.openstack_project_quota]: CREATE_IN_PROGRESS  state changed
2019-08-02 18:01:48Z [stack_admin_gptestudent1.openstack_project_role]: CREATE_IN_PROGRESS  state changed
2019-08-02 18:01:48Z [stack_admin_gptestudent1.openstack_project_quota]: CREATE_COMPLETE  state changed
2019-08-02 18:01:49Z [stack_admin_gptestudent1.openstack_project_role]: CREATE_COMPLETE  state changed
2019-08-02 18:01:49Z [stack_admin_gptestudent1]: CREATE_COMPLETE  Stack CREATE completed successfully
+---------------------+--------------------------------------+
| Field               | Value                                |
+---------------------+--------------------------------------+
| id                  | f36f7bb8-e370-45cd-a900-65f5c9ce4343 |
| stack_name          | stack_admin_gptestudent1             |
| description         | Create a project                     |
| creation_time       | 2019-08-02T18:01:47Z                 |
| updated_time        | None                                 |
| stack_status        | CREATE_COMPLETE                      |
| stack_status_reason | Stack CREATE completed successfully  |
+---------------------+--------------------------------------+
~~~

And then create all the elements inside the project
~~~
$ OS_PROJECT_NAME=gptestudent1 openstack stack create -t stack_user.yaml stack_user_gptestudent1 --parameter project_name=gptestudent1 --parameter project_description=josegonz-redhat.com --wait
2019-08-02 18:04:23Z [stack_user_gptestudent1.2Compute Node 00_server]: CREATE_COMPLETE  state changed
2019-08-02 18:04:24Z [stack_user_gptestudent1.6Network Node 02_server]: CREATE_COMPLETE  state changed
2019-08-02 18:04:24Z [stack_user_gptestudent1.1Controller_server]: CREATE_COMPLETE  state changed
2019-08-02 18:04:24Z [stack_user_gptestudent1]: CREATE_COMPLETE  Stack CREATE completed successfully
+---------------------+--------------------------------------+
| Field               | Value                                |
+---------------------+--------------------------------------+
| id                  | 833d1b52-8a2b-45c6-a679-4d1f6f64c9de |
| stack_name          | stack_user_gptestudent1              |
| description         | Create a project                     |
| creation_time       | 2019-08-02T18:03:17Z                 |
| updated_time        | None                                 |
| stack_status        | CREATE_COMPLETE                      |
| stack_status_reason | Stack CREATE completed successfully  |
+---------------------+--------------------------------------+
~~~

Just some verifications:
~~~
(overcloud) [stack@undercloud ~]$ OS_PROJECT_NAME=gptestudent1 openstack network list
+--------------------------------------+---------------+--------------------------------------+
| ID                                   | Name          | Subnets                              |
+--------------------------------------+---------------+--------------------------------------+
| 45b3f7e7-5bac-4552-afc8-82b7531f59d0 | Management    | 0d76e09d-b3d9-4f54-baf8-06e6b7ce1786 |
| 5b28b0b9-21cf-4175-8360-9d6f2ffdb556 | Trunk_vlan10  |                                      |
| 83f56757-5a41-4019-9b92-c01bdc396f88 | Public        | 492891d6-1ca1-4205-bb09-035793dec485 |
| b878f104-526b-4eb2-ac54-0b1300e592c3 | Trunk         | 10ba49c2-9e91-4d90-bcee-5eb1ee02e1b0 |
| efcf5aab-eb95-4de0-81a0-2df6a05d9823 | Trunk_vlan100 |                                      |
| f62e4f0e-46a7-4c2a-897b-0f01d0a35b93 | Trunk_vlan5   |                                      |
+--------------------------------------+---------------+--------------------------------------+
(overcloud) [stack@undercloud ~]$ OS_PROJECT_NAME=gptestudent1 openstack server list
+--------------------------------------+------------------+--------+---------------------------------------------------------------------+-----------------------+---------------------------+
| ID                                   | Name             | Status | Networks                                                            | Image                 | Flavor                    |
+--------------------------------------+------------------+--------+---------------------------------------------------------------------+-----------------------+---------------------------+
| 0fec5146-48e8-4ebf-baf2-f804f3cd7fac | 0Workstation     | ACTIVE | Management=192.168.0.5; Public=10.0.0.14                            | 0Workstation-root     | CPU_1_Memory_2048_Disk_10 |
| 242ba36d-8653-41a4-becd-5f128f506ecd | 2Compute Node 00 | ACTIVE | Management=192.168.0.30; Public=10.0.0.12; Trunk=1.0.0.26, 1.0.0.6  | 2Compute Node 00-root | CPU_4_Memory_8192_Disk_30 |
| 30140bed-5152-4b58-9090-b7fcb8992e5f | 3Compute Node 01 | ACTIVE | Management=192.168.0.31; Public=10.0.0.28; Trunk=1.0.0.12, 1.0.0.21 | 3Compute Node 01-root | CPU_4_Memory_8192_Disk_30 |
| a5293be2-2171-4f0b-b938-b88e4073b509 | 9Storage         | ACTIVE | Management=192.168.0.40; Trunk=1.0.0.7, 1.0.0.16                    | 9Storage-root         | CPU_1_Memory_2048_Disk_10 |
| cf19a932-861e-48aa-8113-1dfef39767c7 | 1Controller      | ACTIVE | Management=192.168.0.20; Public=10.0.0.8; Trunk=1.0.0.8, 1.0.0.4    | 1Controller-root      | CPU_4_Memory_8192_Disk_30 |
| 75941dc2-37cb-4ca3-aa2b-84f203e56dcf | 6Network Node 02 | ACTIVE | Management=192.168.0.52; Public=10.0.0.13; Trunk=1.0.0.9, 1.0.0.23  | 6Network Node 02-root | CPU_4_Memory_8192_Disk_30 |
| b31fd9c7-4c1f-4610-be11-9e9176e13f96 | 5Network Node 01 | ACTIVE | Management=192.168.0.51; Public=10.0.0.24; Trunk=1.0.0.25, 1.0.0.3  | 5Network Node 01-root | CPU_4_Memory_8192_Disk_30 |
| f1322a2e-31e1-4c71-9e5d-489416074542 | 4Network Node 00 | ACTIVE | Management=192.168.0.50; Public=10.0.0.5; Trunk=1.0.0.2, 1.0.0.10   | 4Network Node 00-root | CPU_4_Memory_8192_Disk_30 |
+--------------------------------------+------------------+--------+---------------------------------------------------------------------+-----------------------+---------------------------+
~~~

To remove the project just delete the stack
~~~
$ OS_PROJECT_NAME=gptestudent1 openstack stack delete stack_user_gptestudent1 --wait
$ openstack stack delete stack_admin_gptestudent1 --wait
~~~
