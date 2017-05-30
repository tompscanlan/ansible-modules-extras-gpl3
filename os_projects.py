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

ANSIBLE_METADATA = {'metadata_version': '1.0',
                    'status': ['preview'],
                    'supported_by': 'community'}

DOCUMENTATION = '''
module: os_projects
short_description: Creates Deletes openstack project
description:
    Creates Deletes openstack project
requirements:
    - keystoneauth1
    - keystoneclient
    - inspect
    - logging
    - ansible 2.x
Tested on:
    - VIO 3.0 / Openstack Mitaka
author: VMware
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
    project_name:
        description:
            - Project to create delete
        required: True
    enabled:
        description:
            - Project enabled, defaults to True
        required: False
        type: bool
    project_domain_id:
        description:
            - Domain for the project being deleted created, defaults to 'default'
        required: False
    project_description:
        description:
            - description for the project
        required: False
    state:
        description:
            - If should be present or absent
        choices: ['present', 'absent']
        required: True
'''

EXAMPLES = '''
- name: Demo Project
  os_projects:
    auth_url: 'https://{{ vio_loadbalancer_vip }}:5000/v3'
    auth_user: "{{ authuser }}"
    auth_password: "{{ authpass }}"
    auth_project: 'admin'
    auth_project_domain: 'default'
    auth_user_domain: 'default'
    project_name: "{{ demo_project_name }}"
    enabled: True
    state: "{{ desired_state }}"
'''

RETURN = '''
description: Returns the project id 
returned: project_id
type: str
sample: uuid
'''

try:
    from keystoneauth1.identity import v3
    from keystoneauth1 import session
    from keystoneclient.v3 import client
    HAS_CLIENTS = True
except ImportError:
    HAS_CLIENTS = False


class OpenstackProject(object):

    def __init__(self, module):
        super(OpenstackProject, self).__init__()
        self.module = module
        self.auth_url = module.params['auth_url']
        self.auth_user = module.params['auth_user']
        self.auth_pass = module.params['auth_password']
        self.auth_project = module.params['auth_project']
        self.auth_project_domain = module.params['auth_project_domain']
        self.auth_user_domain = module.params['auth_user_domain']
        self.project_name = module.params['project_name']
        self.project_enabled = module.params['enabled']
        self.project_desc = module.params['project_description']
        self.project_domain_id = \
            module.params['project_domain_id'] if module.params['project_domain_id'] else 'default'
        self.project_description = \
            module.params['project_description'] if module.params['project_description'] else 'New Project: %s' % self.project_name
        self.ks = self.keystone_auth()
        self.project_id = None
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
        changed       = False
        result        = None
        msg           = None

        current_state = self.check_project_state()
        desired_state = self.module.params['state']
        module_state  = (current_state == desired_state)

        if module_state:
            changed, result = self.state_exit_unchanged()

        if current_state == 'absent' and desired_state == 'present':
            changed, project = self.state_create_project(self.project_name,
                                                         self.project_domain_id,
                                                         self.project_description)
            self.project_id = project.id
            result = self.project_id

        if current_state == 'present' and desired_state == 'absent':
            changed, delete_result = self.state_delete_project(self.project)
            result = str(delete_result[0])

        self.module.exit_json(changed=changed, result=result, project_id=self.project_id)

    def state_exit_unchanged(self):
        return False, self.project_id

    def state_delete_project(self, project):
        changed       = False
        delete_status = None

        try:
            delete_status = self.ks.projects.delete(project)
            changed = True
        except Exception as e:
            msg = "Failed to delete Project: %s " % str(e)
            self.module.fail_json(msg=msg)
        return changed, delete_status

    def state_create_project(self, _name, _domain_id, _description):
        changed = False
        project = None

        try:
            project = self.ks.projects.create(_name, _domain_id, _description)
            changed = True
        except Exception as e:
            msg = "Failed to create project: %s " % str(e)
            self.module.fail_json(msg=msg)

        return changed, project

    def check_project_state(self):
        project = None
        try:
            project = [p for p in self.ks.projects.list() if p.name == self.project_name][0]
        except IndexError:
            return 'absent'
        self.project_id = project.id
        self.project = project

        return 'present'



def main():
    argument_spec = dict(
        auth_url=dict(required=True, type='str'),
        auth_user=dict(required=True, type='str'),
        auth_password=dict(required=True, type='str', no_log=True),
        auth_project=dict(required=True, type='str'),
        auth_project_domain=dict(required=True, type='str'),
        auth_user_domain=dict(required=True, type='str'),
        project_name=dict(required=True, type='str'),
        enabled=dict(required=True, type='bool'),
        project_domain_id=dict(required=False, type='str'),
        project_description=dict(required=False, type='str'),
        state=dict(default='present', choices=['present', 'absent'], type='str'),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=False)

    if not HAS_CLIENTS:
        module.fail_json(msg='python-keystone is required for this module')

    os = OpenstackProject(module)
    os.run_state()


from ansible.module_utils.basic import *

if __name__ == '__main__':
    main()
