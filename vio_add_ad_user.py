#!/usr/bin/env python
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
module: vio_add_ad_user
short_description: Add and existing AD user to a project
description:
    - This module is intended to be used as part of the chaperone vio role. This role will add an
      active directory user to a specified project. You must have the VIO cluster using active
      directory as the authentication source. Currently supports add and remove user from specified
      project with desired states 'present' 'absent'.
author: Jake Dupuy jdupuy@vmware.com
options:
    auth_url:
        description:
            - keystone authentication url
        required: True
        type: str
    username:
        description:
            - username for the admin user for the admin project.
        required: True
        type: str
    password:
        description:
            - password for the admin user for the amdin project
        required: True
        type: str
    tenant_name:
        description:
            - tenant name for the admin tenant
        required: True
        type: str
    user_to_add:
        description:
            - existing AD user in the previously specified dn user tree as part of the VIO configuration
        required: True
        type: str
    tenant_add_to:
        description:
            - tenant name for an existing tenant
        required: True
        type: str
    state:
        description:
            - tenant name for an existing tenant
        required: True
        choices: present, absent
        type: str
'''

EXAMPLE = '''
- name: Add AD User to Project
  vio_add_ad_user:
    auth_url: 'https://192.168.0.100:5000/v2.0'
    username: 'vioadmin@corp.local'
    password: 'VMware1!'
    tenant_name: 'admin'
    user_to_add: 'viouser01@corp.local'
    tenant_add_to: 'dev01'
    state: 'present'
'''

try:
    from keystoneclient.v2_0 import client as ks_client
    HAS_CLIENTS = True
except ImportError:
    HAS_CLIENTS = False


def keystone_auth(module):
    try:
        ksclient = ks_client.Client(
            username=module.params['username'],
            password=module.params['password'],
            tenant_name=module.params['tenant_name'],
            auth_url=module.params['auth_url'],
            insecure=True
        )
    except Exception as e:
        module.fail_json(msg="Failed to get keystone client authentication: {}".format(e))

    return ksclient


def state_exit_unchanged(module):
    module.exit_json(changed=False, msg="Exit Unchanged")


def state_update_user(module):
    module.exit_json(changed=False, msg="Update user - currently not supported")


def state_user(module):
    result = None
    changed = False

    ks = keystone_auth(module)

    user_name = module.params['user_to_add']
    tenant_name = module.params['tenant_add_to']

    user_to_add = [u for u in ks.users.list() if u.name == user_name][0]
    role = [r for r in ks.roles.list() if r.name == '_member_'][0]
    tenant = [t for t in ks.tenants.list() if t.name == tenant_name][0]

    try:
        if module.params['state'] == 'present':
            tenant.add_user(user_to_add, role)
            result = "ADDED USER"

        if module.params['state'] == 'absent':
            tenant.remove_user(user_to_add, role)
            result = "REMOVED USER"

        changed = True

    except Exception as e:
        module.fail_json(msg="Failed adding/removing user to project: {}".format(e))

    module.exit_json(changed=changed, result=result)


def check_user_present(module):

    ks = keystone_auth(module)

    users = [u.name for u in ks.users.list()]

    if module.params['user_to_add'] in users:
        return True
    else:
        return False


def check_user_in_tenant(module):

    ks = keystone_auth(module)
    tenant_name = module.params['tenant_add_to']
    user_name = module.params['user_to_add']

    tenant_id = [tenant.id for tenant in ks.tenants.list() if tenant.name == tenant_name][0]

    tenants_users = [user.username for user in ks.tenants.list_users(tenant_id)]

    if user_name in tenants_users:
        return True
    else:
        return False


def check_tenant_present(module):

    ks = keystone_auth(module)

    tenants = [t.name for t in ks.tenants.list()]

    if module.params['tenant_add_to'] in tenants:
        return True
    else:
        return False


def check_user_state(module):

    user = module.params['user_to_add']
    tenant = module.params['tenant_add_to']

    if not check_user_present(module):
        module.fail_json(msg="User: {} not an existing user".format(user))

    if not check_tenant_present(module):
        module.fail_json(msg="Tenant: {} not an existing tenant".format(tenant))

    if check_user_in_tenant(module):
        return 'present'
    else:
        return 'absent'


def main():
    argument_spec = dict(
        auth_url=dict(required=True, type='str'),
        username=dict(required=True, type='str'),
        password=dict(required=True, type='str'),
        tenant_name=dict(required=True, type='str'),
        user_to_add=dict(required=True, type='str'),
        tenant_add_to=dict(required=True, type='str'),
        state=dict(default='present', choices=['present', 'absent'], type='str'),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=False)

    if not HAS_CLIENTS:
        module.fail_json(msg='python-keystone is required for this module')

    try:
        vio_user_states = {
            'absent': {
                'update': state_user,
                'present': state_user,
                'absent': state_exit_unchanged,
            },
            'present': {
                'update': state_update_user,
                'present': state_exit_unchanged,
                'absent': state_user,
            }
        }

        vio_user_states[module.params['state']][check_user_state(module)](module)

    except Exception as e:
        module.fail_json(msg=str(e))


from ansible.module_utils.basic import *

if __name__ == '__main__':
    main()
