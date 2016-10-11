#!/usr/bin/python
#
# (c) 2015, Joseph Callen <jcallen () csc.com>
# Portions Copyright (c) 2015 VMware, Inc. All rights reserved.
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

DOCUMENTATION = '''
module: vcener_rename_vsan_ds
Short_description: Renames vcenter datastore.
description:
    Renames vcenter datastore to cluster name + VSAN_DS. Modules specifically developed for the
    purpose of renaming newly created vsan datastores.
requirements:
    - pyvmomi 6
    - ansible 2.x
Tested on:
    - vcenter 6.0
    - pyvmomi 6
    - esx 6
    - ansible 2.1.2
options:
    hostname:
        description:
            - The hostname or IP address of the vSphere vCenter API server
        required: True
    username:
        description:
            - The username of the vSphere vCenter with Admin rights
        required: True
        aliases: ['user', 'admin']
    password:
        description:
            - The password of the vSphere vCenter user
        required: True
        aliases: ['pass', 'pwd']
    datacenter_name:
        description:
            - The name of the datacenter.
        required: True
    cluster_name:
        description:
            - The name of the vCenter cluster to create the disk groups in
        required: True
    state:
        description:
            - Desired state of the disk group
        choices: ['present', 'absent']
        required: True
'''

EXAMPLE = '''
- name: Rename VSAN Datastores
  vcenter_rename_vsan_ds:
    hostname: "{{ vcenter }}"
    username: "{{ vcenter_user }}"
    password: "{{ vcenter_password }}"
    validate_certs: False
    datacenter_name: "{{ datacenter.name }}"
    cluster_name: "{{ item.name }}"
    state: 'present'
  with_items:
    - "{{ datacenter.clusters }}"
  tags:
    - vio_rename_vsan_ds
'''


try:
    from pyVmomi import vim, vmodl
    import collections
    HAS_PYVMOMI = True
except ImportError:
    HAS_PYVMOMI = False


vc = {}


def find_vcenter_object_by_name(content, vimtype, object_name):
    vcenter_object = get_all_objs(content, [vimtype])

    for k, v in vcenter_object.items():
        if v == object_name:
            return k
    else:
        return None


def state_delete(module):
    module.exit_json(changed=False, msg="CURRENTLY NOT SUPPORTED")


def state_exit_unchanged(module):
    module.exit_json(changed=False, msg="EXIT UNCHANGED")


def state_create(module):

    changed = False
    result = None

    dc = vc['dc']
    cl = vc['cluster']

    new_ds_name = "{}_VSAN_DS".format(module.params['cluster_name'])

    hosts_in_cluster = [host for host in cl.host]
    datastores = dc.datastoreFolder.childEntity

    for ds in datastores:
        ds_hosts = [h.key for h in ds.host]
        compare = lambda x, y: collections.Counter(x) == collections.Counter(y)

        if compare(hosts_in_cluster, ds_hosts):
            ds.Rename_Task(new_ds_name)
            changed = True
            result = new_ds_name

    module.exit_json(changed=changed, result=result)



def check_ds_state(module):

    content = connect_to_api(module)

    dc = find_vcenter_object_by_name(content, vim.Datacenter, module.params['datacenter_name'])

    if not dc:
        module.fail_json(msg="Failed to find datacenter")

    vc['dc'] = dc

    cluster = find_vcenter_object_by_name(content, vim.ClusterComputeResource, module.params['cluster_name'])

    if not cluster:
        module.fail_json(msg="Failed to find cluster")

    vc['cluster'] = cluster

    datastores = dc.datastoreFolder.childEntity

    ds_name = "{}_VSAN_DS".format(module.params['cluster_name'])

    ds = [d for d in datastores if d.name == ds_name]

    if ds:
        return 'present'
    else:
        return 'absent'



def main():
    argument_spec = vmware_argument_spec()

    argument_spec.update(
        dict(
            datacenter_name=dict(required=True, type='str'),
            cluster_name=dict(required=True, type='str'),
            state=dict(default='present', choices=['present', 'absent'], type='str'),
        )
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=False)

    if not HAS_PYVMOMI:
        module.fail_json(msg='pyvmomi is required for this module')

    ds_states = {
        'absent': {
            'absent': state_exit_unchanged,
            'present': state_delete,
        },
        'present': {
            'absent': state_create,
            'present': state_exit_unchanged,
        }
    }

    desired_state = module.params['state']
    current_state = check_ds_state(module)

    ds_states[desired_state][current_state](module)


from ansible.module_utils.basic import *
from ansible.module_utils.vmware import *

if __name__ == '__main__':
    main()