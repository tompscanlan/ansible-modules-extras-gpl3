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
module: vcenter_datacenter
short_description: Manage VMware vSphere Datacenters
description:
    - Create vcenter datacenter
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
    datacenter_name:
        description:
            - The name of the datacenter the cluster will be created in.
        required: True
    state:
        description:
            - If the datacenter should be present or absent
        choices: ['present', 'absent']
        required: True
'''

EXAMPLES = '''
- name: Create Datacenter
  ignore_errors: no
  vcenter_datacenter:
    hostname: "{{ vcenter_host }}"
    username: "{{ vcenter_user }}"
    password: "{{ vcenter_password }}"
    validate_certs: False
    datacenter_name: "{{ datacenter_name }}"
    state: 'present'
  tags:
    - datacenter
'''

try:
    from pyVmomi import vim, vmodl
    HAS_PYVMOMI = True
except ImportError:
    HAS_PYVMOMI = False

def get_datacenter(context, module):
    try:
        datacenter_name = module.params.get('datacenter_name')
        datacenter = find_datacenter_by_name(context, datacenter_name)
        return datacenter
    except vmodl.RuntimeFault as runtime_fault:
        module.fail_json(msg=runtime_fault.msg)
    except vmodl.MethodFault as method_fault:
        module.fail_json(msg=method_fault.msg)


def create_datacenter(context, module):
    datacenter_name = module.params.get('datacenter_name')
    folder = context.rootFolder

    try:
        datacenter = get_datacenter(context, module)
        changed = False
        if not datacenter:
            changed = True
            if not module.check_mode:
                folder.CreateDatacenter(name=datacenter_name)
        module.exit_json(changed=changed)
    except vim.fault.DuplicateName:
        module.fail_json(msg="A datacenter with the name %s already exists" % datacenter_name)
    except vim.fault.InvalidName:
        module.fail_json(msg="%s is an invalid name for a cluster" % datacenter_name)
    except vmodl.fault.NotSupported:
        # This should never happen
        module.fail_json(msg="Trying to create a datacenter on an incorrect folder object")
    except vmodl.RuntimeFault as runtime_fault:
        module.fail_json(msg=runtime_fault.msg)
    except vmodl.MethodFault as method_fault:
        module.fail_json(msg=method_fault.msg)


def destroy_datacenter(context, module):
    result = None

    try:
        datacenter = get_datacenter(context, module)
        changed = False
        if datacenter:
            changed = True
            if not module.check_mode:
                task = datacenter.Destroy_Task()
                changed, result = wait_for_task(task)
        module.exit_json(changed=changed, result=result)
    except vim.fault.VimFault as vim_fault:
        module.fail_json(msg=vim_fault.msg)
    except vmodl.RuntimeFault as runtime_fault:
        module.fail_json(msg=runtime_fault.msg)
    except vmodl.MethodFault as method_fault:
        module.fail_json(msg=method_fault.msg)


def check_datacenter_state(context, module):

    datacenter = get_datacenter(context, module)

    if datacenter:
        return 'present'
    else:
        return 'absent'


def state_exit_unchanged(module):
    module.exit_json(changed=False, msg="EXIT UNCHANGED")


def main():
    argument_spec = vmware_argument_spec()

    argument_spec.update(
        dict(
            datacenter_name=dict(required=True, type='str'),
            state=dict(required=True, choices=['present', 'absent'], type='str'),
        )
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=False)

    if not HAS_PYVMOMI:
        module.fail_json(msg='pyvmomi is required for this module')

    context = connect_to_api(module)

    desired_state = module.params['state']
    current_state = check_datacenter_state(context, module)

    if (desired_state == current_state):
        state_exit_unchanged(module)

    if desired_state == 'present':
        create_datacenter(context, module)

    if desired_state == 'absent':
        destroy_datacenter(context, module)

from ansible.module_utils.basic import *
from ansible.module_utils.vmware import *

if __name__ == '__main__':
    main()
