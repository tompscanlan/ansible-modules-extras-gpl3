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
module: vio_unregister_extension
short_description: Unregisters vio or nsx plugins from vcenter
description:
    Unregisters vio or nsx plugins from vcenter.
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
    extention_type:
        description:
            - type of extention to unregister
        choices: nsx, vio

'''

EXAMPLES = '''
- name: Unregister Extention
  vio_unregister_extension:
    hostname: "{{ vcenter }}"
    username: "{{ vcenter_user }}"
    password: "{{ vcenter_password }}"
    validate_certs: "{{ vcenter_validate_certs }}"
    extention_type: 'nsx'

'''

try:
    from pyVmomi import vim, vmodl
    HAS_PYVMOMI = True
except ImportError:
    HAS_PYVMOMI = False


vio_ext =['com.vmware.openstack.ui',
          'org.os.vmw.plugin']

nsx_ext = ['com.vmware.vShieldManager']

vc = {}


def state_exit_unchanged(module):
    module.exit_json(changed=False, result=vc['current_ext'], msg="EXIT Unchanged")


def state_unregister_ext(module):

    extensions_to_unregister = vc['current_ext']
    content = vc['content']

    failed_to_unregister =[]

    for ext in extensions_to_unregister:

        try:
            content.extensionManager.UnregisterExtension(ext)
        except vim.fault.NotFound:
            failed_to_unregister.append(ext)
        except Exception as e:
            module.fail_json(msg="Failed to unregister extension: {} with error: {}".format(ext, str(e)))

    module.exit_json(changed=False, result=failed_to_unregister, msg="UNregister ext")


def state_register_ext(module):
    module.exit_json(changed=False, msg="NOT SUPPORTED use appliance specific extension registration")


def get_instance_ext_id(extention_keys):

    instance_ext_ids = []

    for ext in extention_keys:
        exts = ext.split('.')
        if 'vcext' in exts:
            inst_id = exts[-1]
            inst_ext_id = "com.vmware.openstack.vcext.{}".format(inst_id)
            instance_ext_ids.append(inst_ext_id)

    return instance_ext_ids

def check_extention_state(module):
    state = 'absent'

    content = connect_to_api(module)

    vc['content'] = content

    extentions = content.extensionManager.extensionList

    ext_keys = [k.key for k in extentions]

    if module.params['extention_type'] == 'nsx':

        if nsx_ext[0] in ext_keys:
            state = 'present'

    if module.params['extention_type'] == 'vio':

        instance_ext_ids = get_instance_ext_id(ext_keys)
        vio_extensions = vio_ext + instance_ext_ids

        if all(x in ext_keys for x in vio_extensions):
            state ='present'

        vc['current_ext'] = [e for e in vio_extensions if e in ext_keys]

    return state


def main():
    argument_spec = vmware_argument_spec()

    argument_spec.update(
        dict(
            extention_type=dict(choices=['vio', 'nsx'], type='str'),
            state=dict(default='present', choices=['present', 'absent'], type='str'),
        )
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=False)

    if not HAS_PYVMOMI:
        module.fail_json(msg='pyvmomi is required for this module')

    states = {
        'absent': {
            'absent': state_exit_unchanged,
            'present': state_unregister_ext,
        },
        'present': {
            'present': state_exit_unchanged,
            'absent': state_register_ext,
        }
    }


    desired_state = module.params['state']
    current_state = check_extention_state(module)

    states[desired_state][current_state](module)

from ansible.module_utils.basic import *
from ansible.module_utils.vmware import *

if __name__ == '__main__':
    main()
