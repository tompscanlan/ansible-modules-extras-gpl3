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
---
module: vcenter_portgroup
short_description: Manage VMware vSphere VDS Portgroup
description:
	- Manage VMware vCenter portgroups in a given virtual distributed switch
version_added: 1.0
notes:
	- Tested on vSphere 6.0
requirements:
	- "python >= 2.6"
	- PyVmomi
options:
	hostname:
		description:
			- The hostname or IP address of the vSphere vCenter API server
		required: True
	username:
		description:
			- The username of the vSphere vCenter
		required: True
		aliases: ['user', 'admin']
	password:
		description:
			- The password of the vSphere vCenter
		required: True
		aliases: ['pass', 'pwd']
	vds_name:
		description:
			- The name of the distributed virtual switch where the port group is added to.
				The vds must exist prior to adding a new port group, otherwise, this
				process will fail.
		required: True
	port_group_name:
		description:
			- The name of the port group the cluster will be created in.
		required: True
	port_binding:
		description:
			- Available port binding types - static, dynamic, ephemeral
		required: True
	port_allocation:
		description:
			- Allocation model of the ports - fixed, elastic
			- Fixed allocation always reserve the number of ports requested
			- Elastic allocation increases/decreases the number of ports as needed
		required: True
	numPorts:
		description:
			- The number of the ports for the port group
			- Default value will be 0 - no ports
	state:
		description:
		- If the port group should be present or absent
		choices: ['present', 'absent']
		required: True
'''
EXAMPLES = '''
- name: create portgroups
  vcenter_portgroup:
    hostname: '172.16.78.15'
    username: 'administrator@vsphere.local'
    password: 'VMware1!'
    validate_certs: False
    vds_name: 'vds001'
    port_group_name: "{{ item['name'] }}"
    port_binding: "{{ item['binding'] }}"
    port_allocation: "{{ item['allocation'] }}"
    numPorts: "{{ item['numports'] }}"
    vlan:
    state: 'present'
  with_items:
    - { name: 'pg001', binding: 'static', allocation: 'elastic', numports: 8 }
'''


try:
    from pyVmomi import vim, vmodl
    HAS_PYVMOMI = True
except ImportError:
    HAS_PYVMOMI = False


pgTypeMap = {
    'static': 'earlyBinding',
    'dynamic': 'lateBinding',
    'ephemeral': 'ephemeral',
}

pg_allocation = {
    'elastic': True,
    'fixed': False,
}


def find_vds_by_name(content, vds_name):
    vdSwitches = get_all_objs(content, [vim.dvs.VmwareDistributedVirtualSwitch])
    for vds in vdSwitches:
        if vds_name == vds.name:
            return vds
    return None


def find_vdspg_by_name(vdSwitch, portgroup_name):
    portgroups = vdSwitch.portgroup

    for pg in portgroups:
        if pg.name == portgroup_name:
            return pg
    return None


def state_exit_unchanged(si, module):
    module.exit_json(changed=False, msg="EXIT UNCHANGED")


def state_destroy_port_group(module):
    # TODO
    module.exit_json(changed=False)


def check_pg_spec(si, module):

    state = True

    vds_name = module.params['vds_name']
    vds = find_vds_by_name(si, vds_name)

    pg_name = module.params['port_group_name']
    pg = find_vdspg_by_name(vds, pg_name)

    check_vals = [
        (pgTypeMap[module.params['port_binding']] == pg.config.type),
        (pg_allocation[module.params['port_allocation']] == pg.config.autoExpand),
        (module.params['numPorts'] == pg.config.numPorts),
    ]

    if False in check_vals:
        state = False

    return state


def create_pg_spec(si, update, module):

    port_group_name = module.params['port_group_name']

    port_group_spec = vim.dvs.DistributedVirtualPortgroup.ConfigSpec()
    port_group_spec.name = port_group_name
    port_group_spec.numPorts = module.params['numPorts']
    port_group_spec.type = pgTypeMap[module.params['port_binding']]
    #port_group_spec.autoExpand = pg_allocation[module.params['port_allocation']]

    pg_policy = vim.dvs.DistributedVirtualPortgroup.PortgroupPolicy()
    port_group_spec.policy = pg_policy

    if module.params['vlan']:
        port_group_spec.defaultPortConfig = vim.dvs.VmwareDistributedVirtualSwitch.VmwarePortConfigPolicy()
        port_group_spec.defaultPortConfig.vlan = vim.dvs.VmwareDistributedVirtualSwitch.VlanIdSpec()
        port_group_spec.defaultPortConfig.vlan.vlanId = module.params['vlan']
        #port_group_spec.defaultPortConfig.vlan.inherited = False

    if update:
        vds_name = module.params['vds_name']
        vds = find_vds_by_name(si, vds_name)

        pg_name = module.params['port_group_name']
        pg = find_vdspg_by_name(vds, pg_name)

        port_group_spec.configVersion = pg.config.configVersion

    return port_group_spec


def state_create_port_group(si, module):

    port_group_spec = create_pg_spec(si, False, module)

    vds_name = module.params['vds_name']
    vds = find_vds_by_name(si, vds_name)

    try:
        if not module.check_mode:

            task = vds.AddDVPortgroup_Task(spec=[port_group_spec])

            changed, result = wait_for_task(task)
            module.exit_json(changed=changed, result=result)

    except Exception, e:
        module.fail_json(msg=str(e))


def state_update_port_group(si, module):

    vds_name = module.params['vds_name']
    vds = find_vds_by_name(si, vds_name)

    pg_name = module.params['port_group_name']
    pg = find_vdspg_by_name(vds, pg_name)

    pg_spec = create_pg_spec(si, True, module)

    try:
        reconfig_task = pg.ReconfigureDVPortgroup_Task(pg_spec)
        changed, result = wait_for_task(reconfig_task)
    except Exception as e:
        module.fail_json(msg="Failed to reconfigure pg: {}".format(e))

    module.exit_json(changed=changed, result=result)


def check_port_group_state(si, module):

    vds_name = module.params['vds_name']
    port_group_name = module.params['port_group_name']
    vlan = module.params['vlan']

    if vlan:
        module.params['vlan'] = int(vlan)
    else:
        module.params['vlan'] = None

    vds = find_vds_by_name(si, vds_name)

    port_group = find_vdspg_by_name(vds, port_group_name)

    if port_group is None:
        return 'absent'
    elif not check_pg_spec(si, module):
        return 'update'
    else:
        return 'present'


def main():
    argument_spec = vmware_argument_spec()

    argument_spec.update(
        dict(
            vds_name=dict(type='str', required=True),
            port_group_name=dict(required=True, type='str'),
            port_binding=dict(required=True, choices=['static', 'dynamic', 'ephemeral'], type='str'),
            port_allocation=dict(choices=['fixed', 'elastic'], type='str'),
            numPorts=dict(required=True, type='int'),
            vlan=dict(type='str', required=False, default=False),
            state=dict(required=True, choices=['present', 'absent'], type='str'),
        )
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    if not HAS_PYVMOMI:
        module.fail_json(msg='pyvmomi is required for this module')

    port_group_states = {
        'absent': {
            'present': state_destroy_port_group,
            'absent': state_exit_unchanged,
        },
        'present': {
            'present': state_exit_unchanged,
            'update': state_update_port_group,
            'absent': state_create_port_group,
        }
    }

    si = connect_to_api(module)

    vds_name = module.params['vds_name']
    vds = find_vds_by_name(si, vds_name)

    if not vds:
        module.fail_json(msg="Could not find vds: {}".format(vds_name))

    desired_state = module.params['state']
    current_state = check_port_group_state(si, module)

    port_group_states[desired_state][current_state](si, module)


from ansible.module_utils.basic import *
from ansible.module_utils.vmware import *

if __name__ == '__main__':
    main()
