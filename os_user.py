#!/usr/bin/python
# coding=utf-8
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
module: os_user
short_description: Creates and deletes a user adding user as specified roles to project
description:
  Creates and deletes a user adding user as specified roles to project. 
requirements:
    - ansible 2.x
    - keystoneauth1
    - keystoneclient
author: VMware
version_added: 2.1
options:
    auth_url:
        description:
            - keystone authentication for the openstack api endpoint
        example:
            - https://<endpoint>:5000/v3
        required: True
    auth_user:
        description:
            - User with openstack admin rights usually admin or LDAP/AD admin user
        required: True
    auth_password:
        description:
            - Users password
        required: True
    auth_project:
        description:
            - Users project
    auth_project_domain:
        description:
            - Users project domain
        required: True
    auth_user_domain:
        description:
            - Users user domain
        required: True
    user_name:
        description:
            - Username to create or delete
        required: True
        type: str
    user_password:
        description:
            - User password
        required: True
    domain:
        description:
            - Users domain
        required: False
    state:
        description:
            - If should be present or absent
        choices: ['present', 'absent']
        required: True
    required_together:
        domain:
          description:
            domain for user
          required: true
          type: str
        default_project:
          description:
            default project for user
          required: true
          type: str
        roles:
          description:
            list of roles for the user
          type: list
          required: true
'''

EXAMPLES = '''
- name: Demo User
  os_user:
    auth_url: 'https://{{ vio_loadbalancer_vip }}:5000/v3'
    auth_user: "{{ authuser }}"
    auth_password: "{{ authpass }}"
    auth_project: 'admin'
    auth_project_domain: 'default'
    auth_user_domain: 'default'
    user_name: "{{ demo_username }}"
    user_password: "{{ demo_user_password }}"
    default_project: "{{ demo_project_name }}"
    domain: 'default'
    roles:
      - '_member_'
      - 'heat_stack_user'
    state: "{{ desired_state }}"
  register: demo_project_user
  tags:
    - quick_val
'''

RETURN = '''
description: Returns the user id
returned: result
type: str
sample: uuid
'''

try:
    from keystoneauth1.identity import v3
    from keystoneauth1 import session
    from keystoneauth1 import exceptions as key_auth1_exceptions
    from keystoneclient.v3 import client
    HAS_CLIENTS = True
except ImportError:
    HAS_CLIENTS = False


member_roles = ['_member_',
                'heat_stack_owner',
                'heat_stack_user',
                'admin']


class OpenstackUser(object):

    def __init__(self, module):
        super(OpenstackUser, self).__init__()
        self.module = module
        self.auth_url = module.params['auth_url']
        self.auth_user = module.params['auth_user']
        self.auth_pass = module.params['auth_password']
        self.auth_project = module.params['auth_project']
        self.auth_project_domain = module.params['auth_project_domain']
        self.auth_user_domain = module.params['auth_user_domain']
        self.user_name = module.params['user_name']
        self.user_password = module.params['user_password']
        self.ks = self.keystone_auth()
        self.user = None
        self.user_id = None
        self.project_member = None
        self.roles = None
        self.project = None

    def keystone_auth(self):
        ks = None
        try:
            auth = v3.Password(auth_url=self.auth_url,
                               username=self.auth_user,
                               password=self.auth_pass,
                               project_name=self.auth_project,
                               project_domain_id=self.auth_project_domain,
                               user_domain_id=self.auth_user_domain)
            sess = session.Session(auth=auth, verify=False)
            ks = client.Client(session=sess)
        except Exception as e:
            msg = "Failed to get client: %s " % str(e)
            self.module.fail_json(msg=msg)
        return ks

    def run_state(self):
        changed = False
        result = None

        current_state = self.check_user_state()
        desired_state = self.module.params['state']
        exit_unchanged = (current_state == desired_state)

        if exit_unchanged:
            changed, result = self.state_exit_unchanged()

        if current_state == 'absent' and desired_state == 'present':
            params = self._setup_params()

            if not self.user:
                changed, user = self.state_create_user(**params)
                self.user_id = user.id
                result = self.user_id

            if self.roles:
                for role in self.roles:
                    role_assign = self.user_role(params['name'],
                                                 params['default_project'].name,
                                                 role)
                changed = True
                result = self.user_id

        if current_state == 'present' and desired_state == 'absent':
            changed, delete_result = self.state_delete_user()
            result = self.user_id

        self.module.exit_json(changed=changed, result=result)

    def state_exit_unchanged(self):
        return False, self.user_id

    def state_delete_user(self):
        changed       = False
        delete_status = None

        try:
            delete_status = self.ks.users.delete(self.user)
            changed = True
        except Exception as e:
            msg = "Failed to delete User: %s " % str(e)
            self.module.fail_json(msg=msg)
        return changed, delete_status

    def _setup_params(self):
        user_data = {'name': self.user_name,
                     'password': self.user_password}

        _optional_params = ['domain', 'default_project',
                            'email', 'description']

        params = [p for p in self.module.params.keys() if p in _optional_params and \
                    self.module.params[p]]

        if not params:
            return user_data

        for param in params:
            if param == 'default_project':
                project = self.get_project(self.module.params[param])
                user_data.update({param: project})
            else:
                user_data.update({param: self.module.params[param]})

        return user_data

    def state_create_user(self, **kwargs):
        changed = False
        user = None

        try:
            user = self.ks.users.create(**kwargs)
            changed = True
        except Exception as e:
            msg = "Failed to create user: %s " % str(e)
            self.module.fail_json(msg=msg)

        return changed, user

    def get_project(self, project_name):
        project = None
        try:
            project = [p for p in self.ks.projects.list() if p.name == project_name][0]
        except IndexError:
            return project
        return project

    def get_role(self, role_name):
        role = None
        try:
            role = [r for r in self.ks.roles.list() if r.name == role_name][0]
        except IndexError:
            return role

        return role

    def user_role(self, user_name, project_name, role_name):
        grant_role = None
        _role = self.get_role(role_name)
        _project = self.get_project(project_name)
        _user = self.get_user(user_name)

        try:
            grant_role = self.ks.roles.grant(_role, user=_user,
                                            project=_project)
        except Exception as e:
            msg = "Failed to grant role: %s " % str(e)
            self.module.fail_json(msg=msg)

        return grant_role

    def get_user(self, user_name):
        user = None
        try:
            user = [u for u in self.ks.users.list() if u.name == user_name][0]
        except IndexError:
            return user
        return user

    def check_user_project(self, user, project):
        state = False

        user_projects = self.ks.projects.list(user=user)

        if not user_projects:
            return state
        if project in self.ks.projects.list(user=user):
            state = True
        return state

    def check_user_roles(self, project, user, roles):
        state = []
        user_roles = None
        try:
            user_roles = self.ks.roles.list(user=user, project=project)
        except Exception as e:
            return False

        if not user_roles:
            return roles

        user_roles_names = [r.name for r in user_roles]

        if set(roles) == set(user_roles_names):
            return state

        state = list(set(roles) - set(user_roles_names))
        return state

    def check_user_state(self):
        state = 'absent'

        user = self.get_user(self.user_name)

        if not user:
            self.roles = \
                self.module.params['roles'] if self.module.params['roles'] else []
            return state

        self.user = user
        self.user_id = user.id

        if self.module.params['default_project']:
            project = self.get_project(self.module.params['default_project'])

            if not project:
                msg = "Failed finding project: %s " % self.module.params['default_project']
                self.module.fail_json(msg=msg)

            self.project = project
            user_project_state = self.check_user_project(self.user, project)

            if user_project_state:
                self.project_member = True

        if self.module.params['roles']:
            desired_user_roles = self.module.params['roles']
            roles = self.check_user_roles(self.project, self.user, desired_user_roles)

            if roles:
                self.roles = roles

        if self.user and self.project_member and not self.roles:
            state = 'present'

        return state


def main():
    argument_spec = dict(
        auth_url=dict(required=True, type='str'),
        auth_user=dict(required=True, type='str'),
        auth_password=dict(required=True, type='str', no_log=True),
        auth_project=dict(required=True, type='str'),
        auth_project_domain=dict(required=True, type='str'),
        auth_user_domain=dict(required=True, type='str'),
        user_name=dict(required=True, type='str'),
        user_password=dict(required=True, type='str', no_log=True),
        domain=dict(required=False, type='str'),
        default_project=dict(required=False, type='str'),
        roles=dict(required=False, type='list'),
        email=dict(required=False, type='str'),
        description=dict(required=False, type='str'),
        state=dict(default='present', choices=['present', 'absent'], type='str'),
    )

    module = AnsibleModule(argument_spec=argument_spec,
                           supports_check_mode=False,
                           required_together=[
                               ['domain', 'default_project', 'roles'],
                           ])

    if not HAS_CLIENTS:
        module.fail_json(msg='python-keystone is required for this module')

    os = OpenstackUser(module)
    os.run_state()


from ansible.module_utils.basic import *

if __name__ == '__main__':
    main()
