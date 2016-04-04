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
module: vio_deploy
short_description: Deploy vio cluster for chaperone vio
description:
    - This module is for deploying the vio cluster as part of the chaperone vio role. Using the omsclient
      which can be obtained by:  pip install --index-url http://p3-pypi.eng.vmware.com:3141/slave/dev/+simple --trusted-host p3-pypi.eng.vmware.com oms-client
      the chaperone ui server that executes this module must be on the same management network as the oms
      server. This module will kick off the vio cluster deployment return 202 created if successful.
      If the state obtained is either 'PROVISIONING', 'RUNNING' module will return 'exit unchanged'.
      If the state obtained is 'PROVISION_ERROR' the module will delete the vio cluster and redeploy. It is
      recommeded that if there is a PROVISION_ERROR state then do trouble shooting to fix errors before
      executing the module again.
author: Jake Dupuy jdupuy@vmware.com
credits: Much thanks to VMware VIO Team for creating the omsclient
options:
    oms_server:
        description:
            - IP of the oms on the management network
        required: True
        type: str
    login:
        description:
            - username for the user on the oms server
        required: True
        type: str
    password:
        description:
            - password for the oms server
        required: True
        type: str
    cluster_spec_json:
        description:
            - path to the vio cluster specification json file.
        required: True
        type: str
    state:
        description:
            - desired state of the vio cluster
        choices: present, absent


requirements: omsclient, json
'''

EXAMPLE = '''
- name: Kick off VIO Deployment
  vio_deploy:
    oms_server: "{{ vio_oms_ip_address }}"
    login: "{{ vio_oms_vcenter_username }}"
    password: "{{ vio_oms_vcenter_pwd }}"
    cluster_spec_json: "{{ vio_cluster_spec }}"
    vio_deployment_name: "{{ vio_cluster_name }}"
    state: 'present'
'''

try:
    from  omsclient import oms_controller
    import json
    import os
    HAS_OMS_CLIENT = True
except ImportError:
    HAS_OMS_CLIENT = False


def vio_delete_deployment(module, oms):

    deployment_name = module.params['vio_deployment_name']
    delete_deploy = oms.delete_deployment(deployment_name)

    if delete_deploy.status_code != 202:
        module.fail_json(msg="Failed deleting deployment")

    module.exit_json(changed=True, result=delete_deploy.status_code)


def state_exit_unchanged(module, oms):
    module.exit_json(changed=False, msg="Exit unchanged")


def state_update_deployment(module, oms):

    cluster = module.params['vio_deployment_name']
    cluster_json = create_json_body(module)
    cluster_plan = create_plan(module, oms, cluster_json)
    cluster_spec = create_cluster_spec(cluster_plan, cluster_json)

    cluster_retry = oms.retry_cluster(cluster, cluster_spec)

    if cluster_retry.status_code != 202:
        module.fail_json(msg="Failed to retry cluster deployment")

    module.exit_json(changed=True, result=cluster_retry.status_code)

def _parse_response(module, response, key):
    if response.status_code != 200:
        module.fail_json(msg="Status Code not 200 status code: {}".format(response.status_code))

    resp_content = json.loads(response.content)

    try:
        target = [v for k, v in resp_content.iteritems() if k == key][0]
    except KeyError as e:
        module.fail_json(msg="KeyError: {}".format(e))

    return target


def oms_status(module, oms, key, state):

    status = False

    resp = oms.get_oms_vc_status()
    restart_vapp = _parse_response(module, resp, key)

    if restart_vapp != state:
        return status
    else:
        status = True

    return status


def oms_vc_connection_status(module, oms):

    connection_status = oms.check_oms_vc_connection()

    if connection_status.status_code != 200:
        module.fail_json(msg="Failed to get connection status")

    if json.loads(connection_status.content) != 'success':
        return False
    else:
        return True


def oms_plugin_state(module, oms):

    resp = oms.get_plugin_status()

    if resp.status_code != 200:
        module.fail_json(msg="Failed to get plugin status")

    return json.loads(resp.content)


def list_deployments(module, oms):

    deployments = oms.list_deployments()

    if deployments.status_code != 200:
        module.fail_json(msg="Failed to get deployments: {}".format(deployments.status_code))

    return deployments


def check_deployment_present(module, deployments):
    deployment_list = json.loads(deployments.content)

    if not deployment_list:
        return False

    try:
        deployment_name = [v for i in deployment_list for k, v in i.iteritems() if k == 'name'][0]
    except KeyError as k:
        module.fail_json(msg="KeyError checking deployment: {}".format(k))

    if deployment_name == module.params['vio_deployment_name']:
        return True
    else:
        return False


def create_json_body(module):

    jsonfile = module.params['cluster_spec_json']

    try:
        with open(jsonfile, 'r') as json_data:
            cluster_spec = json.load(json_data)
    except ValueError as e:
        module.fail_json(msg="Invalid json: {}".format(e))

    return cluster_spec


def create_plan(module, oms, cluster_spec_json):
    json_to_string = json.dumps(cluster_spec_json)

    cluster_plan = oms.create_deployment_plan(json_to_string)

    if cluster_plan.status_code != 200:
        module.fail_json(msg="Failed creating cluster spec plan")

    return cluster_plan


def create_cluster_spec(plan, cluster_spec):
    cluster_spec['attributes']['plan'] = plan.content
    return cluster_spec


def state_create_deployment(module, oms):

    cluster_json = create_json_body(module)
    cluster_plan = create_plan(module, oms, cluster_json)
    cluster_spec = create_cluster_spec(cluster_plan, cluster_json)

    vio_deployment = oms.create_deployment_by_spec(cluster_spec)

    if vio_deployment.status_code != 202:
        module.fail_json(msg="Failed to deploy VIO Cluster Status: {}".format(vio_deployment.status_code))

    module.exit_json(changed=True, result=vio_deployment.status_code)


def get_deployment_status(deployments):
    deploy_list = json.loads(deployments.content)

    status = [v for i in deploy_list for k, v in i.iteritems() if k == 'status'][0]

    return status


def check_deployment_state(module, oms):

    oms_vc_reachable = oms_status(module, oms, 'oms.vc.reachable', 'true')
    if not oms_vc_reachable:
        module.fail_json(msg="Cannot reach oms")

    oms_vapp_restart = oms_status(module, oms, 'oms.need.restart.vapp', 'false')
    if not oms_vapp_restart:
        module.fail_json(msg="oms needs restart detected")

    oms_ext_reg = oms_status(module, oms, 'oms.extension.registered', 'true')
    if not oms_ext_reg:
        module.fail_json(msg="oms extention not registered")

    oms_vc_connection_state = oms_vc_connection_status(module, oms)
    if not oms_vc_connection_state:
        module.fail_json(msg="OMS not connected to VC")

    oms_plugin = oms_plugin_state(module, oms)
    if not oms_plugin:
        module.fail_json(msg="OMS plugin status failed")

    if not os.path.exists(module.params['cluster_spec_json']):
        module.fail_json(msg="Cluster spec json file not present")

    deployments = list_deployments(module, oms)

    if check_deployment_present(module, deployments):

        deploy_status = get_deployment_status(deployments)

        if deploy_status == 'PROVISION_ERROR':
            return 'update'
        elif deploy_status in ['PROVISIONING', 'RUNNING']:
            return 'present'
    else:
        return 'absent'



def main():
    argument_spec = dict(
        oms_server=dict(required=True, type='str'),
        login=dict(required=True, type='str'),
        password=dict(required=True, type='str'),
        cluster_spec_json=dict(required=True, type='str'),
        vio_deployment_name=dict(required=True, type='str'),
        state=dict(default='present', choices=['present', 'absent'], type='str'),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=False)

    if not HAS_OMS_CLIENT:
        module.fail_json(msg='omsclient is required for this module')

    try:
        vio_deploy_states = {
            'absent': {
                'update': vio_delete_deployment,
                'present': vio_delete_deployment,
                'absent': state_exit_unchanged,
            },
            'present': {
                'update': state_update_deployment,
                'present': state_exit_unchanged,
                'absent': state_create_deployment,
            }
        }

        oms = oms_controller.OmsController(module.params['oms_server'],
                                           module.params['login'],
                                           module.params['password'])


        vio_deploy_states[module.params['state']][check_deployment_state(module, oms)](module, oms)

    except Exception as e:
        module.fail_json(msg=str(e))


from ansible.module_utils.basic import *

if __name__ == '__main__':
    main()
