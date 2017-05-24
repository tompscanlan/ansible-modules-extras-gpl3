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
module: os_create_project
short_description: Creates openstack project
description:
    Creates openstack project
requirements:
    - keystoneclient.v2_0
    - ansible 2.x
options:
    auth_url:
        description:
            - keystone authentication for the openstack api endpoint
        required: True
    username:
        description:
            - user with rights to create project
        required: True
    password:
        description:
            - password for specified user
        required: True
    tenant_name:
        description:
            - tenant name with authorization to create project
        ex: 'admin'
        required: True
    new_project_name:
        description:
            - name of the project to create
        required: True
    state:
        description:
            - If should be present or absent
        choices: ['present', 'absent']
        required: True
'''

EXAMPLES = '''
- name: Create Demo Project
  os_create_project:
    auth_url: 'https://{{ vio_loadbalancer_vip }}:5000/v2.0'
    username: "{{ authuser }}"
    password: "{{ authpass }}"
    tenant_name: 'admin'
    new_project_name: "{{ vio_val_project_name }}"
    state: "{{ desired_state }}"
  register: os_new_project
  tags:
    - validate_openstack

'''


try:
    from keystoneclient.v2_0 import client as ks_client
    HAS_CLIENTS = True
except ImportError:
    HAS_CLIENTS = False


os = {}


def state_exit_unchanged(module):
    project = None

    ks = keystone_auth(module)

    tenants = [t for t in ks.tenants.list()]

    for tenant in tenants:
        if tenant.name == module.params['new_project_name']:
            project = tenant

    module.exit_json(changed=False,
                     msg="EXIT UNCHANGED",
                     project_name=project.name,
                     project_id=project.id)


def state_create_project(module):

    new_project, changed = create_project(module)

    if changed:
        module.exit_json(changed=changed,
                         project_name=new_project.name,
                         project_id=new_project.id)
    else:
        module.exit_json(changed=changed, msg="failed to create project")



def state_update_project(module):
    module.exit_json(changed=False, msg="Update Project")


def state_delete_project(module):
    module.exit_json(changed=False, msg="delete Project")


def keystone_auth(module):

    ksclient = None

    try:
        ksclient = ks_client.Client(username=module.params['username'],
                                    password=module.params['password'],
                                    tenant_name=module.params['tenant_name'],
                                    auth_url=module.params['auth_url'],
                                    insecure=True)
    except Exception as e:
        module.fail_json(msg="Failed to get keystone client authentication: {}".format(e))

    return ksclient


def create_project(module):
    tenant = None
    changed = False

    ks = keystone_auth(module)

    try:
        tenant = ks.tenants.create(module.params['new_project_name'])
        changed = True
    except Exception as e:
        module.fail_json(msg="Failed to create project: {}".format(e))

    return tenant, changed


def check_project_present(module):

    ks = keystone_auth(module)

    tenants = [t.name for t in ks.tenants.list()]

    if module.params['new_project_name'] in tenants:
        return True

    return False


def check_project_state(module):

    if check_project_present(module):
        return 'present'
    else:
        return 'absent'


def main():
    argument_spec = dict(
        auth_url=dict(required=True, type='str'),
        username=dict(required=True, type='str'),
        password=dict(required=True, type='str'),
        tenant_name=dict(required=True, type='str'),
        new_project_name=dict(required=True, type='str'),
        state=dict(default='present', choices=['present', 'absent'], type='str'),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=False)

    if not HAS_CLIENTS:
        module.fail_json(msg='python-keystone is required for this module')

    try:
        project_states = {
            'absent': {
                'update': state_delete_project,
                'present': state_delete_project,
                'absent': state_exit_unchanged,
            },
            'present': {
                'update': state_update_project,
                'present': state_exit_unchanged,
                'absent': state_create_project,
            }
        }

        project_states[module.params['state']][check_project_state(module)](module)

    except Exception as e:
        module.fail_json(msg=str(e))


from ansible.module_utils.basic import *

if __name__ == '__main__':
    main()