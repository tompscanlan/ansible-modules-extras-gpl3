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

ANSIBLE_METADATA = {'metadata_version': '1.0',
                    'status': ['preview'],
                    'supported_by': 'community'}


DOCUMENTATION = '''
module: vio_provider_network
short_description: Create External Floating IP Network for VIO
description:
  This module is for creating an external network and a subnet for VIO. Created specifically for creating
  external provider network for VIO Setup to support the provider type and provider physical network.
  Currently only supports create and delete. IP address's are not validated in this module only that the provided
  gateway and allocation pool ips are within the provided subnet. Intended for use within the chaperone vio role.
author: VMware
requirements:
  - netaddr
  - neutronclient
options:
    auth_url:
        description:
          keystone authentication url
        required: True
        type: str
    username:
        description:
          username for the admin user for the admin project.
        required: True
        type: str
    password:
        description:
          password for the admin user for the amdin project
        required: True
        type: str
    tenant_name:
        description:
          tenant name for the admin tenant
        required: True
        type: str
    network:
        description:
          dictionary containing the network properties
        options:
          name:
             description:
               name the network, should be descriptive ex: external_network
             type: str
          admin_state_up:
             description:
               set admin state
             type: bool
          port_security_enabled:
             description:
               enable port security
             type: bool
          provider_network_type:
             descriptions:
               type of network 
             choices: [portgroup, flat]
             type: str
          provider_physical_network:
            description:
              provide the portgroup moid
            type: str
          router_external:
            description:
              set router external setting
            type: bool
          shared:
            description:
              set shared
            type: bool
        required: True
    subnet:
        description:
          dictionary containing the subnet properties
        options:
          name:
            description:
              name the subnet for the external network
            type: str
          enable_dhcp:
            description:
              enable dhcp
            type: bool
          gateway_ip:
            description:
              the gateway ip address of the subnet
            type: str
          ip_version:
            description:
              ip version for the network
            type: int
          cidr:
            description:
              valid network in cidr notation
            type: str
          allocation_pools:
            description:
              starting and ending ip allowation pool. this is the pool of ips that will be used as floating ips
              for instances and routers needing a floating ip. Make sure to make the range to meet expected capacity.
            type: list
        required: True
    state:
        description:
            desired state
        choices: [present, absent]
        required: True
'''

EXAMPLES = '''
- name: Create Openstack network and subnet
  vio_create_network:
    auth_url: 'https://localhost:5000/v2.0
    username: 'vioadmin'
    password: 'VMware1!'
    tenant_name: 'admin'
    state: 'present'
    network:
      name: 'ext-net'
      admin_state_up: True
      port_security_enabled: True
      provider_network_type: "portgroup"
      provider_physical_network: "dvportgroup-222"
      router_external: True
      shared: True
    subnet:
      name: 'ext-subnet'
      enable_dhcp: False
      gateway_ip: '192.168.0.2'
      ip_version: 4
      cidr: '192.168.0.0/24'
      allocation_pools:
        - start: '192.168.0.50'
          end: '192.168.0.100'
'''

RETURN = '''
net_id:
  description: id for the network
  type: str
  sample: uuid
'''

try:
    from neutronclient.v2_0 import client as neutron_client
    import netaddr
    HAS_CLIENTS = True
except ImportError:
    HAS_CLIENTS = False


def state_exit_unchanged(module):
    neutron = get_neutron_client(module)
    net_id = get_network_id(module, neutron)
    module.exit_json(changed=False, net_id=net_id, msg='EXIT UNCHANGED')

def state_exit_unchanged_absent(module):
    #neutron = get_neutron_client(module)
    #net_id = get_network_id(module, neutron)
    module.exit_json(changed=False, net_id=None, msg='EXIT UNCHANGED')

def state_delete_network(module):
    neutron = get_neutron_client(module)
    net_id = get_network_id(module, neutron)
    try:
        del_net = neutron.delete_network(net_id)
    except Exception as e:
        module.fail_json(msg="Failed deleting network: {}".format(e))
    module.exit_json(changed=True, result=del_net, msg="DELETE NETWORK")

def state_update_network(module):
    module.exit_json(changed=False, msg="UPDATE NETWORK - currently not supported")

def state_update_subnet(module):
    module.exit_json(changed=False, msg="UPDATE SUBNET - currently not supported")

def state_sub_not_present(module):
    neutron = get_neutron_client(module)
    net_id = get_network_id(module, neutron)
    subnet = create_subnet(module, neutron, net_id)
    if subnet:
        module.exit_json(changed=True, result=subnet, msg="Created Subnet")
    else:
        module.fail_json(msg="Failed Creating subnet")

def state_create_network(module):
    neutron = get_neutron_client(module)
    network_id = create_network(module, neutron)
    subnet = create_subnet(module, neutron, network_id)
    if subnet:
        module.exit_json(changed=True, net_id=network_id, msg="CREATE NETWORK")
    else:
        module.exit_json(changed=False, msg="Failed creating network")

def get_neutron_client(module):
    try:
        neutron = neutron_client.Client(username=module.params['username'],
                                        password=module.params['password'],
                                        tenant_name=module.params['tenant_name'],
                                        auth_url=module.params['auth_url'],
                                        insecure=True)
    except Exception as e:
        module.fail_json(msg="Failed Authenticating for neutron client: {}".format(e))
    return neutron

def check_network_present(module, neutron):
    network_name = module.params['network']['name']
    network_list = neutron.list_networks()
    net_names = [v for i in network_list['networks'] for k, v in i.items() if k == 'name']
    if network_name in net_names:
        return True
    else:
        return False

def get_network_id(module, neutron):
    network_name = module.params['network']['name']
    network_list = neutron.list_networks()
    net = [i for i in network_list['networks'] for k, v in i.items() if k == 'name' if v == network_name][0]
    return net['id']

def set_net_params(module):
    net = module.params['network']
    network_params = {
      'name': net['name'],
      'admin_state_up': net['admin_state_up'],
      'port_security_enabled': net['port_security_enabled'],
      'provider:network_type': net['provider_network_type'],
      'provider:physical_network': net['provider_physical_network'],
      'router:external': net['router_external'],
      'shared': net['shared']
    }
    return network_params

def check_network_config(module, neutron):
    net_config = set_net_params(module)
    net_name = net_config['name']
    network_list = neutron.list_networks()
    net = [i for i in network_list['networks'] for k, v in i.items() if k == 'name' if v == net_name][0]

    for x in set(net_config).intersection(set(net)):
        if not (net_config[x] == net[x]):
            return False
    return True

def check_subnet_present(module, neutron):
    subnet_name = module.params['subnet']['name']
    subnet_list = neutron.list_subnets()
    sub_names = [v for i in subnet_list['subnets'] for k, v in i.items() if k == 'name']
    if subnet_name in sub_names:
        return True
    else:
        return False

def check_subnet_config(module, neutron):
    sub_config = module.params['subnet']
    subnet_name = sub_config['name']
    subnets = neutron.list_subnets()
    sub = [i for i in subnets['subnets'] for k,v in i.items() if k == 'name' if v == subnet_name][0]

    for x in set(sub_config).intersection(set(sub)):
        if not (sub_config[x] == sub[x]):
            return False
    return True

def create_network(module, neutron):
    net_params = set_net_params(module)
    network_body = {'network': net_params}
    try:
        network = neutron.create_network(body=network_body)
    except Exception as e:
        module.fail_json(msg="Failed Creating Network: {}".format(e))
    net = network['network']
    net_id = net['id']
    return net_id


def create_subnet(module, neutron, network_id):
    module.params['subnet']['network_id'] = network_id
    subnet_params = {'subnets': [module.params['subnet']]}
    try:
        subnet = neutron.create_subnet(body=subnet_params)
    except Exception as e:
        module.fail_json(msg="Failed creating network: {}".format(e))
    return subnet

def check_ips_within_subnet(module):

    ips_to_check = [module.params['subnet']['gateway_ip'],
                    module.params['subnet']['allocation_pools'][0]['start'],
                    module.params['subnet']['allocation_pools'][0]['end']]
    for ip in ips_to_check:
        if netaddr.IPAddress(ip) not in netaddr.IPNetwork(module.params['subnet']['cidr']):
            return False, ip
    return True, None

def check_network_state(module):
    ip_check, ip = check_ips_within_subnet(module)
    if not ip_check:
        module.fail_json(changed=False, msg="IP: {} is not within subnet specified".format(ip))
    neutron = get_neutron_client(module)
    net_present = check_network_present(module, neutron)
    if not net_present:
        return 'absent'
    net_config = check_network_config(module, neutron)
    if not net_config:
        return 'update'
    subnet_present = check_subnet_present(module, neutron)
    if not subnet_present:
        return 'absent_subnet'
    subnet_config = check_subnet_config(module, neutron)
    if not subnet_config:
        return 'update_subnet'
    return 'present'

def main():
    argument_spec = dict(
        auth_url=dict(required=True, type='str'),
        username=dict(required=True, type='str'),
        password=dict(required=True, type='str', no_log=True),
        tenant_name=dict(required=True, type='str'),
        network=dict(required=True, type='dict'),
        subnet=dict(required=True, type='dict'),
        state=dict(default='present', choices=['present', 'absent'], type='str'),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=False)

    if not HAS_CLIENTS:
        module.fail_json(msg='Openstack Clients are required for this module')

    try:
        vio_network_states = {
            'absent': {
                'update': state_delete_network,
                'update_subnet': state_delete_network,
                'absent_subnet': state_delete_network,
                'present': state_delete_network,
                'absent': state_exit_unchanged_absent,
            },
            'present': {
                'update': state_update_network,
                'update_subnet': state_update_subnet,
                'absent_subnet': state_sub_not_present,
                'present': state_exit_unchanged,
                'absent': state_create_network,
            }
        }

        vio_network_states[module.params['state']][check_network_state(module)](module)

    except Exception as e:
        module.fail_json(msg=str(e))


from ansible.module_utils.basic import *

if __name__ == '__main__':
    main()
