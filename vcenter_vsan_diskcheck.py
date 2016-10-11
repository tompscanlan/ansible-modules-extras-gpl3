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
module: vcener_vsan_disk_check
Short_description: Reads, Checks if all hosts in specified cluster has specified number of disks (ssd,hdd)
    eligible for creating disk groups.
description:
    Reads, Checks if all hosts in specified cluster has specified number of disks (ssd,hdd)
    eligible for creating disk groups.
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
            - The name of the vCenter cluster
        required: True
    num_ssd:
        description:
            - The number of ssd that should be eligible for disk group creation
        required: True
    num_hdd:
        description:
            - The number of hdd disks that should be available for disk group creation
    state:
        choices: ['present', 'absent']
        required: True
'''

EXAMPLE = '''
- name: VSAN Disk Check
  vcenter_vsan_disk_check:
    hostname: "{{ vcenter }}"
    username: "{{ vcenter_user }}"
    password: "{{ vcenter_password }}"
    validate_certs: "{{ vcenter_validate_certs }}"
    datacenter_name: "{{ datacenter.name }}"
    cluster_name: "{{ item.name }}"
    num_ssd: "{{ item.vsan.num_disk_groups }}"
    num_hdd: "{{ item.vsan.num_disks_per_group }}"
    state: 'present'
  with_items:
    - "{{ datacenter.clusters }}"
  register: disk_check
  tags:
    - vsan_disk_check

- name: disk check debug
  debug: msg="HOST--> {{ item.item.name }} PASS Disk Check --> {{ item.result }}"
  failed_when: not item.result
  with_items:
    - "{{ disk_check.results }}"
  tags:
    - vsan_disk_check
'''

try:
    from pyVmomi import vim, vmodl
    import collections
    HAS_PYVMOMI = True
except ImportError:
    HAS_PYVMOMI = False


vc = {}


def check_hosts_disks(host):

    vsan_mgr = host.configManager.vsanSystem
    disks = host.config.storageDevice.scsiLun

    ssd = []
    hdd =[]

    for disk in disks:
        check_eligible = vsan_mgr.QueryDisksForVsan(disk.canonicalName)

        for d in check_eligible:
            if d.state == 'eligible' and d.disk.ssd:
                ssd.append(d.disk.canonicalName)
            if d.state == 'eligible' and (not d.disk.ssd):
                hdd.append(d.disk.canonicalName)
    
    return ssd, hdd


def state_exit_unchanged(module):
    module.exit_json(changed=False, msg="EXIT UNCHANGED")


def state_delete(module):
    module.exit_json(changed=False, msg="CURRENTLY NOT SUPPORTED")


def state_create(module):
    state = False
    results = []

    num_ssd = module.params['num_ssd']
    num_hdd = module.params['num_hdd']

    for h in vc['hosts']:
        ssd, hdd = check_hosts_disks(h)

        if (len(ssd) >= num_ssd) and (len(hdd) >= num_hdd * num_ssd):
            results.append(True)
        else:
            results.append(False)

    if False not in results:
        state = True

    module.exit_json(changed=False, result=state)


def check_vsan_state(module):

    content = connect_to_api(module)

    dc = find_datacenter_by_name(content, module.params['datacenter_name'])

    if not dc:
        module.fail_json(msg="Failed to get datacenter")

    vc['dc'] = dc

    cluster = find_cluster_by_name_datacenter(dc, module.params['cluster_name'])

    if not cluster:
        module.fail_json(msg="Failed to get cluster")

    vc['cluster'] = cluster

    if not cluster.host:
        module.fail_json(msg="No hosts in cluster")

    vc['hosts'] = cluster.host

    return 'absent'


def main():
    argument_spec = vmware_argument_spec()

    argument_spec.update(
        dict(
            datacenter_name=dict(required=True, type='str'),
            cluster_name=dict(required=True, type='str'),
            num_ssd=dict(required=True, type='int'),
            num_hdd=dict(required=True, type='int'),
            state=dict(default='present', choices=['present', 'absent'], type='str'),
        )
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=False)

    if not HAS_PYVMOMI:
        module.fail_json(msg='pyvmomi is required for this module')

    vsan_states = {
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
    current_state = check_vsan_state(module)

    vsan_states[desired_state][current_state](module)


from ansible.module_utils.basic import *
from ansible.module_utils.vmware import *

if __name__ == '__main__':
    main()
