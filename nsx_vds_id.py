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
module: nsx_vds_id
short_description: Get the specified nsx vdnscope ID
description:
    - This module is for getting the vdnscope (transport zone) id. Intended to be used as part of
      the deploy and configure chaperone VIO role. This module will get the vdnscope id and
      output as an ansible variable to be used in later tasks
author: Jake Dupuy jdupuy@vmware.com
credits: VMware VIO Team
options:
    nsx_manager:
        description:
            - NSX manger ip
        required: True
        type: str
    nsx_manager_username:
        description:
            - NSX manager username
        required: True
        type: str
    nsx_manager_password:
        description:
            - password for the NSX manager user
        required: True
        type: str
    nsx_api_version:
        description:
            - NSX api version
        choices: 2.0, 1.0
        required: True
    vdnscope_name
        description:
            - The name of the vdn scope you need the ID of
        required: True
        type: str
    ansible_variable_name:
        description:
            - valid ansible variable name for the vdnscope id
        required: True
        type: str

requirements: requests, ElementTree, json
'''

EXAMPLE = '''
- name: Get Transport Zone Id
  nsx_vds_id:
    nsx_manager: "{{ vio_nsx_manager_ip }}"
    nsx_manager_username: "{{ vio_nsx_manager_username }}"
    nsx_manager_password: "{{ vio_nsx_manager_password }}"
    nsx_api_version: "2.0"
    vdnscope_name: "{{ vio_nsx_transport_zone }}"
    ansible_variable_name: "vdnscope_id"

- name: Debug vdnscope id variable
  debug: var=vdnscop_id
'''


try:
    import requests
    import xml.etree.ElementTree as ET
    import json
    IMPORTS = True
except ImportError:
    IMPORTS = False


class NsxRestClient(object):

    _url_template_prefix = "https://{}/{}"

    def __init__(self, module, server, username, password, api_version, verify, stream=True):
        self.module = module
        self._server = server
        self._username = username
        self._password = password
        self._api_version = api_version
        self._verfiy = verify
        self._stream = stream
        self._session = requests.Session()
        self._session.verify = self._verfiy
        self._session.auth = (self._username, self._password)

    def _api_url(self, path):
        api_url_template = "api/{}/{}"
        api_url_path = api_url_template.format(self._api_version, path)
        return self._url_template_prefix.format(self._server, api_url_path)

    def do_session_reqeust(self, method, path, data=None, headers=None, params=None, stream=True):

        url = self._api_url(path)

        response = self._session.request(
            method,
            url,
            headers=headers,
            stream=stream,
            params=params,
            data=data
        )

        return response

    def vds_scope_id(self, response_content, scope_name):

        root = ET.fromstring(response_content)

        if root.findtext('vdnScope/name') == scope_name:
            return root.findtext('vdnScope/objectId')
        else:
            return None



def main():
    argument_spec = dict(
        nsx_manager=dict(type='str', required=True),
        nsx_manager_username=dict(type='str', required=True),
        nsx_manager_password=dict(type='str', required=True),
        nsx_api_version=dict(type='str', default="2.0"),
        vdnscop_name=dict(type='str', required=True),
        ansible_variable_name=dict(type='str'),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=False)

    if not IMPORTS:
        module.fail_json(msg="failed to import required modules")

    rheaders = {'Content-Type': 'application/xml'}

    n = NsxRestClient(
        module,
        module.params['nsx_manager'],
        module.params['nsx_manager_username'],
        module.params['nsx_manager_password'],
        module.params['nsx_api_version'],
        False
    )

    resp = n.do_session_reqeust('GET', 'vdn/scopes', headers=rheaders)

    if resp.status_code != 200:
        module.fail_json(msg="Failed with response code--> {}".format(resp.status_code))

    vds_id = n.vds_scope_id(resp.content, module.params['vds_name'])

    if vds_id:

        ansible_facts_dict = {
            "changed": False,
            "ansible_facts": {

            }
        }

        ansible_facts_dict['ansible_facts'].update(
            {module.params['ansible_variable_name']: vds_id}
        )

        print json.dumps(ansible_facts_dict)

    else:
        module.exit_json(msg="Failed to get vdscope id")


from ansible.module_utils.basic import *
from ansible.module_utils.facts import *

if __name__ == '__main__':
    main()


