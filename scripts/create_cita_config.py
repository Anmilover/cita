#!/usr/bin/env python3
# -*- coding:utf-8 -*-
# pylint: disable=missing-docstring

import argparse
import hashlib
import logging
import os
import shutil
import sys
import tempfile
import toml


def update_search_paths(work_dir):
    """Add new path to the search path."""
    sys.path.insert(0,
                    os.path.abspath(
                        os.path.join(work_dir, 'scripts/config_tool')))
    paths = os.environ['PATH'].split(':')
    paths.insert(0, os.path.abspath(os.path.join(work_dir, 'bin')))
    os.environ['PATH'] = ':'.join(paths)


def generate_prevhash(resource_dir):
    if resource_dir is not None \
            and os.path.exists(resource_dir) \
            and os.path.isdir(resource_dir):
        file_list_filename = 'files.list'
        file_list_filepath = os.path.abspath(
            os.path.join(resource_dir, file_list_filename))
        # Get a list of paths for all files in resource directory.
        file_list = []
        for root, _, files in os.walk(resource_dir, topdown=True):
            for filename in files:
                filepath = os.path.abspath(os.path.join(root, filename))
                if filepath != file_list_filepath:
                    file_list.append(filepath)
        if file_list:
            file_list.sort()
            # Calculate hash for all files
            md5obj = hashlib.md5()
            for filepath in file_list:
                with open(filepath, 'rb') as stream:
                    md5obj.update(stream.read())
            res_hash = md5obj.hexdigest()
            # Write all relative filepaths into a file.
            file_relpaths = [
                os.path.relpath(filepath, resource_dir)
                for filepath in file_list
            ]
            with open(file_list_filepath, 'w') as stream:
                stream.writelines('\n'.join(file_relpaths))
            # Return a hash after padding.
            return '0x{:064x}'.format(int(res_hash, 16))
    return None


def generate_authorities(amount):
    authorities = AuthorityList()
    signers = list()
    _, address_path = tempfile.mkstemp()
    _, secret_path = tempfile.mkstemp()
    cmd = 'create_key_addr "{}" "{}"'.format(secret_path, address_path)
    for _ in range(0, amount):
        os.system(cmd)
        with open(address_path, 'rt') as stream:
            address = stream.read().strip()
        with open(secret_path, 'rt') as stream:
            secret = stream.read().strip()
        os.remove(address_path)
        os.remove(secret_path)
        authorities.add_after_check(address)
        signers.append(secret)
    return authorities, signers


def need_directory(dirpath):
    """Create a directory if it is not existed."""
    if not os.path.exists(dirpath):
        os.makedirs(dirpath)


class AddressList(list):
    @classmethod
    def from_str(cls, addrs_str, size_check=None, delimiter=','):
        addrs = cls()
        for addr_str in addrs_str.split(delimiter):
            if not addr_str:
                continue
            addr = addr_str.split(':')
            if len(addr) == 2 and addr[0] and addr[1]:
                host = addr[0]
                port = int(addr[1])
                if port > 65535 or port < 1:
                    raise Exception(
                        'input port {} is not right'.format(addr_str))
                addrs.add_after_check(host, port)
            else:
                raise Exception(
                    'input {} is not like IP:PORT'.format(addr_str))
        if size_check and size_check != len(addrs):
            raise Exception('Except {} but got {} addresses from {}.'.format(
                size_check, len(addrs), addrs_str))
        return addrs

    @classmethod
    def from_str_get_one(cls, addrs_str, delimiter=','):
        return cls.from_str(addrs_str, size_check=1, delimiter=delimiter)

    def add_after_check(self, host, port):
        for addr in self:
            if addr['host'] == host and addr['port'] == port:
                raise Exception('address {}:{} has been added twice'.format(
                    host, port))
        self.append(dict(host=host, port=port, signer=''))

    def add_signers(self, signers):
        if len(self) != len(signers):
            raise Exception('Size of signers [{}] is not equal to'
                            ' size of addresses [{}].'.format(
                                len(signers), len(self)))
        size = len(self)
        for idx in range(0, size):
            self[idx]['signer'] = signers[idx]


class AuthorityList(list):
    @classmethod
    def from_str(cls, addrs_str, delimiter=','):
        addrs = cls()
        for addr_str in addrs_str.split(delimiter):
            if not addr_str:
                continue
            addrs.add_after_check(addr_str)
        return addrs

    def add_after_check(self, addr):
        if addr in self:
            raise Exception('authority {} has been added twice'.format(addr))
        self.append(addr)

    def to_str(self, delimiter=','):
        return delimiter.join(self)


class ChainInfo(object):
    # pylint: disable=too-many-instance-attributes

    def __init__(self, chain_name, output_dir):
        self.node_prefix = chain_name
        self.output_root = os.path.join(output_dir, self.node_prefix)

        self.template_dir = os.path.join(self.output_root, 'template')
        self.contracts_dir = os.path.join(self.template_dir, 'contracts')
        self.contracts_docs_dir = os.path.join(self.contracts_dir, 'docs')
        self.configs_dir = os.path.join(self.template_dir, 'configs')
        self.init_data_file = os.path.join(self.template_dir, 'init_data.yml')
        self.genesis_path = os.path.join(self.configs_dir, 'genesis.json')
        self.nodes_list = os.path.join(self.template_dir, 'nodes.list')
        self.authorities_list = os.path.join(self.template_dir,
                                             'authorities.list')
        self.nodes = AddressList()

    def template_create_from_arguments(self, args, contracts_dir_src,
                                       configs_dir_src):
        if os.path.exists(self.output_root):
            logging.critical(
                'The chain named `%s` has already been created.'
                ' Please specify another chain name use --chain_name,'
                ' or remove the old directory [%s].', self.node_prefix,
                self.output_root)
            sys.exit(1)
        else:
            os.makedirs(self.template_dir)
        shutil.copytree(contracts_dir_src, self.contracts_dir, False)
        need_directory(self.contracts_docs_dir)

        shutil.copytree(configs_dir_src, self.configs_dir, False)

        executor_config = os.path.join(self.configs_dir, 'executor.toml')
        with open(executor_config, 'rt') as stream:
            executor_data = toml.load(stream)
            executor_data['grpc_port'] = args.grpc_port
        with open(executor_config, 'wt') as stream:
            toml.dump(executor_data, stream)

        jsonrpc_config = os.path.join(self.configs_dir, 'jsonrpc.toml')
        with open(jsonrpc_config, 'rt') as stream:
            jsonrpc_data = toml.load(stream)
            jsonrpc_data['http_config']['listen_port'] \
                = str(args.jsonrpc_port)
            jsonrpc_data['ws_config']['listen_port'] \
                = str(args.ws_port)
        with open(jsonrpc_config, 'wt') as stream:
            toml.dump(jsonrpc_data, stream)

        network_config = os.path.join(self.configs_dir, 'network.toml')
        network_data = toml.loads('')
        network_data['peers'] = list()
        with open(network_config, 'wt') as stream:
            toml.dump(network_data, stream)

        open(self.nodes_list, 'wt').close()
        with open(self.authorities_list, 'wt') as stream:
            for authority in args.authorities:
                stream.write('{}\n'.format(authority))

    def template_load_from_existed(self):
        if not os.path.exists(self.output_root):
            logging.critical('The chain named `%s` has not been created.'
                             ' (directory [%s] is not existed)'
                             ' Please specify an existed chain.',
                             self.node_prefix, self.output_root)
        with open(self.nodes_list, 'rt') as stream:
            nodes_str = ''.join(stream.readlines()).replace('\n', ',')
        self.nodes = AddressList.from_str(nodes_str)

    def create_init_data(self, super_admin, contract_arguments):
        from create_init_data import core as create_init_data
        create_init_data(self.init_data_file, super_admin, contract_arguments)

    def create_genesis(self, timestamp, resource_dir):
        from create_genesis import core as create_genesis
        prevhash = generate_prevhash(resource_dir)
        if resource_dir is not None:
            shutil.copytree(resource_dir,
                            os.path.join(self.configs_dir, 'resource'), False)
        create_genesis(self.contracts_dir, self.contracts_docs_dir,
                       self.init_data_file, self.genesis_path, timestamp,
                       prevhash)

    def append_node(self, node):
        if isinstance(node, AddressList):
            node = node[0]
        node_id = len(self.nodes)
        self.nodes.add_after_check(node['host'], node['port'])
        node_dir = os.path.join(self.output_root, '{}'.format(node_id))

        shutil.copytree(self.configs_dir, node_dir, False)

        executor_config = os.path.join(node_dir, 'executor.toml')
        with open(executor_config, 'rt') as stream:
            executor_data = toml.load(stream)
            executor_data['grpc_port'] += node_id
        with open(executor_config, 'wt') as stream:
            toml.dump(executor_data, stream)

        jsonrpc_config = os.path.join(node_dir, 'jsonrpc.toml')
        with open(jsonrpc_config, 'rt') as stream:
            jsonrpc_data = toml.load(stream)
            jsonrpc_data['http_config']['listen_port'] \
                = str(int(
                    jsonrpc_data['http_config']['listen_port']) + node_id)
            jsonrpc_data['ws_config']['listen_port'] \
                = str(int(
                    jsonrpc_data['ws_config']['listen_port']) + node_id)
        with open(jsonrpc_config, 'wt') as stream:
            toml.dump(jsonrpc_data, stream)

        with open(os.path.join(node_dir, '.env'), 'wt') as stream:
            stream.write(
                'AMQP_URL=amqp://guest:guest@localhost/{}/{}\n'.format(
                    self.node_prefix, node_id))
            stream.write('DATA_PATH=./data\n')

        consensus_config = os.path.join(node_dir, 'privkey')
        with open(consensus_config, 'wt') as stream:
            stream.write(node['signer'])

        network_config = os.path.join(self.configs_dir, 'network.toml')
        with open(network_config, 'rt') as stream:
            network_data = toml.load(stream)
            network_data['peers'].append(
                dict(id_card=node_id, ip=node['host'], port=node['port']))
        with open(network_config, 'wt') as stream:
            toml.dump(network_data, stream)

        for old_id in range(0, node_id):
            old_dir = os.path.join(self.output_root, '{}'.format(old_id))
            network_config = os.path.join(old_dir, 'network.toml')
            with open(network_config, 'rt') as stream:
                network_data = toml.load(stream)
                network_data['peers'].append(
                    dict(id_card=node_id, ip=node['host'], port=node['port']))
            with open(network_config, 'wt') as stream:
                stream.write(f"# Current node ip is {node['host']}\n")
                toml.dump(network_data, stream)

        network_config = os.path.join(node_dir, 'network.toml')
        with open(network_config, 'rt') as stream:
            network_data = toml.load(stream)
            network_data['id_card'] = node_id
            network_data['port'] = node['port']
        with open(network_config, 'wt') as stream:
            stream.write(f"# Current node ip is {node['host']}\n")
            toml.dump(network_data, stream)

        with open(self.nodes_list, 'at') as stream:
            stream.write('{}:{}\n'.format(node['host'], node['port']))


def run_subcmd_create(args, work_dir):
    info = ChainInfo(args.chain_name, work_dir)
    info.template_create_from_arguments(
        args, os.path.join(work_dir, 'scripts/contracts'),
        os.path.join(work_dir, 'scripts/config_tool/config_example'))
    info.create_init_data(args.super_admin, args.contract_arguments)
    info.create_genesis(args.timestamp, args.resource_dir)
    for node in args.nodes:
        info.append_node(node)


def run_subcmd_append(args, work_dir):
    info = ChainInfo(args.chain_name, work_dir)
    info.template_load_from_existed()
    info.append_node(args.node)


def parse_arguments():
    from create_init_data import KeyKeyValueDict, KeyKeyValueAction

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(
        dest='subcmd', title='subcommands', help='additional help')

    #
    # Subcommand: create
    #

    pcreate = subparsers.add_parser(
        SUBCMD_CREATE, help='create a chain with nodes')

    pcreate.add_argument(
        '--authorities',
        type=AuthorityList.from_str,
        metavar='{var}[,{var}[,{var}[,{var}[, ...]]]]'.format(var='AUTHORITY'),
        help='Authorities (addresses) list.')
    pcreate.add_argument(
        '--chain_name',
        default='test-chain',
        help='Name of the new chain.')

    pcreate.add_argument(
        '--nodes',
        type=AddressList.from_str,
        default=AddressList(),
        metavar='{var}[,{var}[,{var}[,{var}[, ...]]]]'.format(var='IP:PORT'),
        help='Node network addresses for new nodes.')

    # For create init data
    pcreate.add_argument('--super_admin', help='Address of super admin.')
    pcreate.add_argument(
        '--contract_arguments',
        nargs='+',
        type=KeyKeyValueDict.str2tuple,
        action=KeyKeyValueAction,
        default=KeyKeyValueDict(),
        metavar='Contract.Argument=Value',
        help='Update constructor arguments for system contract.'
        ' Can be specify more than once.')

    # For create genesis
    pcreate.add_argument(
        '--timestamp', type=int, help='Specify a timestamp to use.')
    pcreate.add_argument('--resource_dir', help='Chain resource directory.')

    # Modify ports
    pcreate.add_argument(
        '--grpc_port', type=int, default=5000, help='grpc port for this chain')
    pcreate.add_argument(
        '--jsonrpc_port',
        type=int,
        default=1337,
        help='jsonrpc port for this chain')
    pcreate.add_argument(
        '--ws_port',
        type=int,
        default=4337,
        help='websocket port for this chain')

    #
    # Subcommand: append
    #

    pappend = subparsers.add_parser(
        SUBCMD_APPEND, help='append a node into a existed chain')

    pappend.add_argument(
        '--chain_name',
        required=True,
        help='Name of the existed chain.')

    pappend.add_argument(
        '--signer',
        help='The signer of new node. Will generate a new if not set.')

    pappend.add_argument(
        '--node',
        required=False,
        type=AddressList.from_str_get_one,
        metavar='IP:PORT',
        help='Node network addresses for new nodes.')

    args = parser.parse_args()

    # Check arguments
    if args.subcmd == SUBCMD_CREATE:
        if not args.authorities:
            if not args.nodes:
                logging.critical('Both --authorities and --nodes is empty.')
                sys.exit(1)
            authorities, signers = generate_authorities(len(args.nodes))
            args.nodes.add_signers(signers)
            setattr(args, 'authorities', authorities)
        for val in (('authorities', 'NodeManager', 'nodes'),
                    ('chain_name', 'SysConfig', 'chainName')):
            if args.contract_arguments.kkv_get(val[1], val[2]):
                logging.critical('Please use --%s to instead of specify'
                                 ' --contract_arguments %s.%s directly',
                                 val[0], val[1], val[2])
                sys.exit(1)
        args.contract_arguments.kkv_set('SysConfig', 'chainName',
                                        args.chain_name)
        args.contract_arguments.kkv_set('NodeManager', 'nodes',
                                        args.authorities.to_str())
        if not args.contract_arguments.kkv_get('NodeManager', 'stakes'):
            stakes = ','.join(['0' for _ in args.authorities])
            args.contract_arguments.kkv_set('NodeManager', 'stakes', stakes)
    elif args.subcmd == SUBCMD_APPEND:
        if args.signer:
            args.node.add_signers([args.signer])
        else:
            _, signers = generate_authorities(1)
            args.node.add_signers(signers)
    else:
        logging.critical('Please select a valid subcommand.')
        sys.exit(1)
    return args


def main():
    # All source files are relative path.
    work_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), os.pardir))

    update_search_paths(work_dir)

    args = parse_arguments()

    funcs_router = {
        SUBCMD_CREATE: run_subcmd_create,
        SUBCMD_APPEND: run_subcmd_append,
    }
    funcs_router[args.subcmd](args, work_dir)


if __name__ == '__main__':
    SUBCMD_CREATE = 'create'
    SUBCMD_APPEND = 'append'
    main()
